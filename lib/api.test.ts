// Unit tests for the API client. No extra dependencies: Node's built-in test runner.
// Run: npm run test:frontend
import assert from "node:assert/strict"
import { afterEach, describe, it } from "node:test"
import { api, ApiError, CSRF_HEADER_NAME, hasCsrfToken, setUnauthorizedHandler } from "./api.ts"

const realFetch = globalThis.fetch
type Call = { url: string; init?: RequestInit }
let calls: Call[] = []

function mockFetch(...responses: (Response | Error)[]) {
  calls = []
  globalThis.fetch = (async (url: string, init?: RequestInit) => {
    calls.push({ url, init })
    const next = responses.shift()
    if (next instanceof Error) throw next
    if (!next) throw new Error("unexpected fetch")
    return next
  }) as typeof fetch
}

function json(body: unknown, status = 200, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  })
}

async function rejection(promise: Promise<unknown>): Promise<ApiError> {
  try {
    await promise
  } catch (error) {
    assert.ok(error instanceof ApiError, `expected ApiError, got ${error}`)
    return error
  }
  assert.fail("expected the call to fail")
}

afterEach(async () => {
  // Reset the in-memory session between tests.
  mockFetch(new Response(null, { status: 204 }))
  await api.auth.logout()
  setUnauthorizedHandler(null)
  globalThis.fetch = realFetch
})

function headersOf(call: Call): Record<string, string> {
  return (call.init?.headers ?? {}) as Record<string, string>
}

const SESSION_BODY = { username: "admin", csrfToken: "csrf-from-server", expiresAt: "2026-10-14T18:00:00Z" }

describe("api client", () => {
  it("sends camelCase JSON to the same-origin /api proxy", async () => {
    mockFetch(json({ id: "u1", name: "Acme" }, 201))
    await api.companies.create({
      name: "Acme",
      industry: "Software",
      email: "a@acme.example",
      phone: "1",
      location: "X",
      status: "Active",
    })
    assert.equal(calls[0].url, "/api/companies")
    assert.equal(calls[0].init?.method, "POST")
    assert.equal(JSON.parse(String(calls[0].init?.body)).name, "Acme")
  })

  it("updates with PATCH to /api/<entity>/<uuid>", async () => {
    mockFetch(json({ id: "u1" }))
    await api.deals.update("u1", { stage: "Won" })
    assert.equal(calls[0].url, "/api/deals/u1")
    assert.equal(calls[0].init?.method, "PATCH")
  })

  it("treats 204 No Content as success on delete", async () => {
    mockFetch(new Response(null, { status: 204 }))
    await api.contacts.remove("u1")
    assert.equal(calls[0].init?.method, "DELETE")
  })

  it("listAll follows pagination using X-Total-Count", async () => {
    const first = Array.from({ length: 500 }, (_, i) => ({ id: `a${i}` }))
    mockFetch(
      json(first, 200, { "X-Total-Count": "501" }),
      json([{ id: "last" }], 200, { "X-Total-Count": "501" })
    )
    const all = await api.activities.listAll()
    assert.equal(all.length, 501)
    assert.deepEqual(
      calls.map((c) => c.url),
      ["/api/activities?limit=500&offset=0", "/api/activities?limit=500&offset=500"]
    )
  })

  it("maps 422 validation errors to camelCase field messages", async () => {
    mockFetch(
      json(
        {
          detail: [
            { loc: ["body", "email"], msg: "value is not a valid email address" },
            { loc: ["body", "contactId"], msg: "Value error, Contact belongs to a different company" },
          ],
        },
        422
      )
    )
    const error = await rejection(api.activities.create({} as never))
    assert.equal(error.status, 422)
    assert.equal(error.message, "Please correct the highlighted fields.")
    assert.deepEqual(error.fieldErrors, {
      email: "value is not a valid email address",
      contactId: "Contact belongs to a different company",
    })
  })

  it("uses the server's message for 409 conflicts and 404s", async () => {
    mockFetch(json({ detail: "A company with this name already exists." }, 409))
    const conflict = await rejection(api.companies.create({} as never))
    assert.equal(conflict.status, 409)
    assert.equal(conflict.message, "A company with this name already exists.")

    mockFetch(json({ detail: "Deal not found" }, 404))
    assert.equal((await rejection(api.deals.remove("x"))).message, "Deal not found")
  })

  it("explains server errors without JSON (e.g. backend down behind the proxy)", async () => {
    mockFetch(new Response("Internal Server Error", { status: 500 }))
    const error = await rejection(api.companies.listAll())
    assert.equal(error.status, 500)
    assert.match(error.message, /backend is running/)
  })

  it("reports network failures as status 0", async () => {
    mockFetch(new TypeError("fetch failed"))
    const error = await rejection(api.companies.listAll())
    assert.equal(error.status, 0)
    assert.match(error.message, /Can't reach the CRM server/)
  })

  it("lets deliberate cancellation through unchanged", async () => {
    const controller = new AbortController()
    controller.abort()
    const abort = new DOMException("aborted", "AbortError")
    mockFetch(abort)
    await assert.rejects(api.companies.listAll(controller.signal), (e) => e === abort)
  })
})

describe("sign-in and session handling", () => {
  it("logs in with JSON and keeps the CSRF token in memory, not in the returned session", async () => {
    mockFetch(json(SESSION_BODY))
    const session = await api.auth.login("admin", "pw-typed-by-user")
    assert.deepEqual(session, { username: "admin", expiresAt: SESSION_BODY.expiresAt })
    assert.equal(calls[0].url, "/api/auth/login")
    assert.equal(calls[0].init?.method, "POST")
    assert.equal(calls[0].init?.credentials, "same-origin")
    assert.deepEqual(JSON.parse(String(calls[0].init?.body)), { username: "admin", password: "pw-typed-by-user" })
    assert.equal(hasCsrfToken(), true)
  })

  it("reports bad credentials with the server's generic message, without an expired-session redirect", async () => {
    let expired = 0
    setUnauthorizedHandler(() => expired++)
    mockFetch(json({ detail: "Invalid username or password." }, 401))
    const error = await rejection(api.auth.login("admin", "wrong"))
    assert.equal(error.status, 401)
    assert.equal(error.message, "Invalid username or password.")
    assert.equal(expired, 0)
    assert.equal(hasCsrfToken(), false)
  })

  it("loads the current session on startup", async () => {
    mockFetch(json(SESSION_BODY))
    assert.deepEqual(await api.auth.me(), { username: "admin", expiresAt: SESSION_BODY.expiresAt })
    assert.equal(calls[0].url, "/api/auth/me")
    assert.equal(hasCsrfToken(), true)
  })

  it("treats a 401 from /auth/me as signed out", async () => {
    let expired = 0
    setUnauthorizedHandler(() => expired++)
    mockFetch(json({ detail: "Not authenticated." }, 401))
    assert.equal(await api.auth.me(), null)
    assert.equal(expired, 0)
    assert.equal(hasCsrfToken(), false)
  })

  it("sends the CSRF token on writes but not on reads", async () => {
    mockFetch(json(SESSION_BODY))
    await api.auth.login("admin", "pw")

    mockFetch(json([], 200, { "X-Total-Count": "0" }), json({ id: "c1" }, 201), json({ id: "c1" }), new Response(null, { status: 204 }))
    await api.companies.listAll()
    await api.companies.create({} as never)
    await api.companies.update("c1", {})
    await api.companies.remove("c1")
    assert.equal(headersOf(calls[0])[CSRF_HEADER_NAME], undefined)
    for (const call of calls.slice(1)) {
      assert.equal(headersOf(call)[CSRF_HEADER_NAME], "csrf-from-server")
      assert.equal(call.init?.credentials, "same-origin")
    }
  })

  it("handles an expired session: notifies the app and forgets the CSRF token", async () => {
    mockFetch(json(SESSION_BODY))
    await api.auth.login("admin", "pw")
    let expired = 0
    setUnauthorizedHandler(() => expired++)

    mockFetch(json({ detail: "Not authenticated." }, 401))
    const error = await rejection(api.deals.listAll())
    assert.equal(error.status, 401)
    assert.match(error.message, /session has expired/)
    assert.equal(expired, 1)
    assert.equal(hasCsrfToken(), false)
  })

  it("explains a 403 (CSRF/origin rejection) without signing out", async () => {
    let expired = 0
    setUnauthorizedHandler(() => expired++)
    mockFetch(json({ detail: "CSRF check failed." }, 403))
    const error = await rejection(api.companies.create({} as never))
    assert.equal(error.status, 403)
    assert.match(error.message, /could not be verified/)
    assert.equal(expired, 0)
  })

  it("logs out with the CSRF token, then forgets it", async () => {
    mockFetch(json(SESSION_BODY))
    await api.auth.login("admin", "pw")
    mockFetch(new Response(null, { status: 204 }))
    await api.auth.logout()
    assert.equal(calls[0].url, "/api/auth/logout")
    assert.equal(calls[0].init?.method, "POST")
    assert.equal(headersOf(calls[0])[CSRF_HEADER_NAME], "csrf-from-server")
    assert.equal(hasCsrfToken(), false)
  })

  it("forgets the CSRF token even if logout cannot reach the server", async () => {
    mockFetch(json(SESSION_BODY))
    await api.auth.login("admin", "pw")
    mockFetch(new TypeError("fetch failed"))
    await rejection(api.auth.logout())
    assert.equal(hasCsrfToken(), false)
  })
})
