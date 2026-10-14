"use client"

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react"
import { api, errorMessage, setUnauthorizedHandler, type Session } from "@/lib/api"
import type { LoginReason } from "@/lib/auth"

export type SessionState =
  | { status: "loading" }
  | { status: "authenticated"; session: Session }
  | { status: "unauthenticated"; reason?: LoginReason }
  | { status: "error"; message: string }

type SessionContextValue = {
  state: SessionState
  signIn: (username: string, password: string) => Promise<void>
  signOut: () => Promise<void>
  retry: () => void
}

const SessionContext = createContext<SessionContextValue | null>(null)

/**
 * Knows whether an admin is signed in. The session is an HttpOnly cookie, so on load it
 * asks the API (/auth/me); any later 401 from a CRM request marks the session expired.
 */
export function SessionProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<SessionState>({ status: "loading" })
  const [checkCount, setCheckCount] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    api.auth
      .me(controller.signal)
      .then((session) => {
        setState(session ? { status: "authenticated", session } : { status: "unauthenticated" })
      })
      .catch((error) => {
        if (controller.signal.aborted) return
        setState({ status: "error", message: errorMessage(error) })
      })
    return () => controller.abort()
  }, [checkCount])

  // Any CRM request answered with 401: the session expired or was revoked elsewhere.
  useEffect(() => {
    setUnauthorizedHandler(() => setState({ status: "unauthenticated", reason: "expired" }))
    return () => setUnauthorizedHandler(null)
  }, [])

  // Sign out locally when the cookie's lifetime runs out, even if no request is made.
  const expiresAt = state.status === "authenticated" ? state.session.expiresAt : null
  useEffect(() => {
    if (!expiresAt) return
    const remaining = Date.parse(expiresAt) - Date.now()
    // setTimeout's maximum delay is about 24.8 days; sessions are at most 24 hours.
    const timer = setTimeout(
      () => setState({ status: "unauthenticated", reason: "expired" }),
      Math.max(0, Math.min(remaining, 2 ** 31 - 1))
    )
    return () => clearTimeout(timer)
  }, [expiresAt])

  const signIn = useCallback(async (username: string, password: string) => {
    const session = await api.auth.login(username, password)
    setState({ status: "authenticated", session })
  }, [])

  const signOut = useCallback(async () => {
    try {
      await api.auth.logout()
    } finally {
      // Signed out locally either way; the cookie is cleared by the server when reachable.
      setState({ status: "unauthenticated", reason: "signed-out" })
    }
  }, [])

  const retry = useCallback(() => {
    setState({ status: "loading" })
    setCheckCount((count) => count + 1)
  }, [])

  const value = useMemo(() => ({ state, signIn, signOut, retry }), [state, signIn, signOut, retry])
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
}

export function useSession() {
  const context = useContext(SessionContext)
  if (!context) {
    throw new Error("useSession must be used within SessionProvider")
  }
  return context
}
