// Unit tests for the API client. No extra dependencies: Node's built-in test runner.
// Run: npm run test:frontend
import assert from "node:assert/strict"
import { afterEach, describe, it } from "node:test"
import { api, ApiError } from "./api.ts"

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

afterEach(() => {
  globalThis.fetch = realFetch
})

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
