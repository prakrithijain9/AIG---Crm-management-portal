import type {
  Activity,
  ActivityInput,
  Company,
  CompanyInput,
  Contact,
  ContactInput,
  Deal,
  DealInput,
} from "@/lib/types"

/**
 * Error from the CRM API, normalised for the UI.
 * - status 0: the server could not be reached
 * - fieldErrors: camelCase field name -> message (from 422 responses)
 */
export class ApiError extends Error {
  readonly status: number
  readonly fieldErrors: Record<string, string>

  constructor(message: string, status: number, fieldErrors: Record<string, string> = {}) {
    super(message)
    this.name = "ApiError"
    this.status = status
    this.fieldErrors = fieldErrors
  }
}

type ValidationIssue = { loc?: (string | number)[]; msg?: string }

const PAGE_SIZE = 500 // the API's maximum

async function toApiError(response: Response): Promise<ApiError> {
  let detail: unknown
  try {
    detail = (await response.json())?.detail
  } catch {
    // Non-JSON body, e.g. the dev proxy's error page when FastAPI is down.
  }

  if (typeof detail === "string") {
    return new ApiError(detail, response.status)
  }
  if (Array.isArray(detail)) {
    const fieldErrors: Record<string, string> = {}
    for (const issue of detail as ValidationIssue[]) {
      const field = issue.loc?.at(-1)
      // Pydantic messages start with "Value error, " for custom checks; drop that prefix.
      const message = (issue.msg ?? "Invalid value").replace(/^Value error, /, "")
      if (typeof field === "string" && field !== "body" && !fieldErrors[field]) {
        fieldErrors[field] = message
      }
    }
    const general = Object.keys(fieldErrors).length
      ? "Please correct the highlighted fields."
      : ((detail as ValidationIssue[])[0]?.msg ?? "The request was rejected.")
    return new ApiError(general, response.status, fieldErrors)
  }
  if (response.status >= 500) {
    return new ApiError(
      `The CRM server had a problem (HTTP ${response.status}). Check that the backend is running.`,
      response.status
    )
  }
  return new ApiError(`Request failed (HTTP ${response.status}).`, response.status)
}

// --- Session state shared with the UI ------------------------------------------------
//
// The session itself is an HttpOnly cookie the browser sends automatically; this code
// never sees the JWT. The CSRF token from /auth/login or /auth/me is kept in memory only
// (never localStorage/sessionStorage) and echoed in X-CSRF-Token on every write.

export const CSRF_HEADER_NAME = "X-CSRF-Token"
const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"])

let csrfToken: string | null = null
let onUnauthorized: (() => void) | null = null

/** Called when a CRM request gets 401 (session expired or revoked). */
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler
}

/** Whether a CSRF token is currently held (for tests and diagnostics; never exposes it). */
export function hasCsrfToken(): boolean {
  return csrfToken !== null
}

export type Session = {
  username: string
  /** ISO timestamp when the session cookie expires. */
  expiresAt: string
}

type SessionResponse = Session & { csrfToken: string }

function acceptSession(body: SessionResponse): Session {
  csrfToken = body.csrfToken
  return { username: body.username, expiresAt: body.expiresAt }
}

type RequestOptions = RequestInit & {
  /** Auth endpoints handle their own 401s; don't treat them as an expired session. */
  authEndpoint?: boolean
}

async function request(path: string, init: RequestOptions = {}): Promise<Response> {
  const { authEndpoint = false, ...requestInit } = init
  const method = (requestInit.method ?? "GET").toUpperCase()
  const headers: Record<string, string> = { Accept: "application/json" }
  if (requestInit.body) headers["Content-Type"] = "application/json"
  if (UNSAFE_METHODS.has(method) && csrfToken) headers[CSRF_HEADER_NAME] = csrfToken

  let response: Response
  try {
    response = await fetch(`/api${path}`, {
      ...requestInit,
      headers,
      credentials: "same-origin", // send the session cookie (same-origin via the Next.js proxy)
      cache: "no-store",
    })
  } catch (error) {
    if (requestInit.signal?.aborted) throw error // cancelled on purpose, not a network failure
    throw new ApiError("Can't reach the CRM server. Check your connection and that the backend is running.", 0)
  }
  if (!response.ok) {
    if (response.status === 401 && !authEndpoint) {
      csrfToken = null
      onUnauthorized?.()
      throw new ApiError("Your session has expired. Please sign in again.", 401)
    }
    if (response.status === 403 && !authEndpoint) {
      throw new ApiError("Your session could not be verified. Refresh the page or sign in again.", 403)
    }
    throw await toApiError(response)
  }
  return response
}

const auth = {
  /** Sign in. Throws ApiError (401 with the server's generic message) on bad credentials. */
  async login(username: string, password: string): Promise<Session> {
    const response = await request("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
      authEndpoint: true,
    })
    return acceptSession((await response.json()) as SessionResponse)
  },

  /** The current session, or null if not signed in (or it expired). */
  async me(signal?: AbortSignal): Promise<Session | null> {
    try {
      const response = await request("/auth/me", { signal, authEndpoint: true })
      return acceptSession((await response.json()) as SessionResponse)
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        csrfToken = null
        return null
      }
      throw error
    }
  },

  /** Sign out everywhere. The local CSRF token is dropped even if the request fails. */
  async logout(): Promise<void> {
    try {
      await request("/auth/logout", { method: "POST", authEndpoint: true })
    } finally {
      csrfToken = null
    }
  },
}

function resource<T, TInput>(path: string) {
  return {
    /** Every record, following pagination via the X-Total-Count header. */
    async listAll(signal?: AbortSignal): Promise<T[]> {
      const items: T[] = []
      for (let offset = 0; ; offset += PAGE_SIZE) {
        const response = await request(`${path}?limit=${PAGE_SIZE}&offset=${offset}`, { signal })
        const page = (await response.json()) as T[]
        items.push(...page)
        const total = Number(response.headers.get("X-Total-Count") ?? items.length)
        if (page.length === 0 || items.length >= total) return items
      }
    },
    async create(input: TInput): Promise<T> {
      const response = await request(path, { method: "POST", body: JSON.stringify(input) })
      return (await response.json()) as T
    },
    async update(id: string, input: Partial<TInput>): Promise<T> {
      const response = await request(`${path}/${id}`, { method: "PATCH", body: JSON.stringify(input) })
      return (await response.json()) as T
    },
    async remove(id: string): Promise<void> {
      await request(`${path}/${id}`, { method: "DELETE" })
    },
  }
}

export const api = {
  auth,
  companies: resource<Company, CompanyInput>("/companies"),
  contacts: resource<Contact, ContactInput>("/contacts"),
  deals: resource<Deal, DealInput>("/deals"),
  activities: resource<Activity, ActivityInput>("/activities"),
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Something went wrong."
}
