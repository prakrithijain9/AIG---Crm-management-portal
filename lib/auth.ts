/** Shared sign-in constants and helpers (no React, so they can be unit tested and used by proxy.ts). */

/** Name of the HttpOnly session cookie set by the API. JavaScript cannot read its value. */
export const SESSION_COOKIE_NAME = "aig_crm_session"

export const LOGIN_PATH = "/login"

/** Why the login page is being shown, passed as ?reason=. */
export type LoginReason = "expired" | "signed-out"

/**
 * A same-site path to return to after signing in, or "/".
 * Rejects absolute URLs, protocol-relative "//host" and "/\host" forms, control
 * characters, and the login page itself, so ?next= cannot redirect off-site or loop.
 */
export function safeNextPath(raw: string | null | undefined): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//")) return "/"
  if (/[\\\u0000-\u001f\u007f]/.test(raw)) return "/"
  if (raw === LOGIN_PATH || raw.startsWith(`${LOGIN_PATH}?`) || raw.startsWith(`${LOGIN_PATH}/`)) return "/"
  return raw
}

/** The login URL for returning to `path` afterwards. */
export function loginUrl(path: string, reason?: LoginReason): string {
  const params = new URLSearchParams()
  const next = safeNextPath(path)
  if (next !== "/") params.set("next", next)
  if (reason) params.set("reason", reason)
  const query = params.toString()
  return query ? `${LOGIN_PATH}?${query}` : LOGIN_PATH
}
