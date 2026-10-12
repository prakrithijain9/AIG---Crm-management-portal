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

async function request(path: string, init?: RequestInit): Promise<Response> {
  let response: Response
  try {
    response = await fetch(`/api${path}`, {
      ...init,
      headers: { Accept: "application/json", ...(init?.body ? { "Content-Type": "application/json" } : {}) },
      cache: "no-store",
    })
  } catch (error) {
    if (init?.signal?.aborted) throw error // cancelled on purpose, not a network failure
    throw new ApiError("Can't reach the CRM server. Check your connection and that the backend is running.", 0)
  }
  if (!response.ok) throw await toApiError(response)
  return response
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
  companies: resource<Company, CompanyInput>("/companies"),
  contacts: resource<Contact, ContactInput>("/contacts"),
  deals: resource<Deal, DealInput>("/deals"),
  activities: resource<Activity, ActivityInput>("/activities"),
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Something went wrong."
}
