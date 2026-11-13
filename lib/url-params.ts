/** Pure helpers for the list pages' URL params (?search=&status=&stage=&open=). No React here, so they are unit-tested. */

/** A param value that must be one of `allowed`; anything else (missing, misspelt, hand-edited) falls back. */
export function choiceParam<T extends string>(
  value: string | null,
  allowed: readonly T[],
  fallback: T | "all" = "all",
): T | "all" {
  return value !== null && (allowed as readonly string[]).includes(value) ? (value as T) : fallback
}

/** `current` ("?a=1" or "a=1") with `updates` applied. null, "" and "all" remove the key. Returns "" or "?x=y". */
export function withParams(current: string, updates: Record<string, string | null>): string {
  const params = new URLSearchParams(current)
  for (const [key, value] of Object.entries(updates)) {
    if (value === null || value === "" || value === "all") params.delete(key)
    else params.set(key, value)
  }
  const query = params.toString()
  return query ? `?${query}` : ""
}
