"use client"

import { useEffect, type ReactNode } from "react"
import { usePathname, useRouter } from "next/navigation"
import { LoaderCircle, RefreshCw, TriangleAlert } from "lucide-react"
import { useSession } from "@/components/auth/session-provider"
import { CrmProvider } from "@/components/crm/crm-provider"
import { DataGate } from "@/components/crm/data-gate"
import { Sidebar } from "@/components/layout/sidebar"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { loginUrl } from "@/lib/auth"

export function AppShell({ children }: { children: ReactNode }) {
  const { state } = useSession()
  const router = useRouter()
  const pathname = usePathname()
  const authenticated = state.status === "authenticated"

  // Not signed in (or the session expired): go to the login page, then come back here.
  useEffect(() => {
    if (state.status === "unauthenticated") {
      router.replace(loginUrl(pathname, state.reason))
    }
  }, [state, pathname, router])

  return (
    // Keyed by the signed-in user, so signing out discards all loaded CRM data.
    <CrmProvider key={authenticated ? state.session.username : "signed-out"} enabled={authenticated}>
      <div className="min-h-screen bg-slate-50">
        <Sidebar />
        <main className="min-h-screen min-w-0 md:ml-64">
          <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 sm:py-8">
            <SessionStatus />
            {/* The page stays in the tree (hidden) so Next.js can prerender it; see DataGate. */}
            <div hidden={!authenticated}>
              <DataGate>{children}</DataGate>
            </div>
          </div>
        </main>
      </div>
    </CrmProvider>
  )
}

function SessionStatus() {
  const { state, retry } = useSession()

  if (state.status === "loading" || state.status === "unauthenticated") {
    return (
      <Card>
        <CardContent
          role="status"
          className="flex items-center justify-center gap-3 py-16 text-sm text-muted-foreground"
        >
          <LoaderCircle className="size-5 animate-spin text-teal-700" />
          {state.status === "loading" ? "Checking your session…" : "Redirecting to sign in…"}
        </CardContent>
      </Card>
    )
  }

  if (state.status === "error") {
    return (
      <Card>
        <CardContent role="alert" className="flex flex-col items-center gap-3 py-16 text-center">
          <div className="flex size-10 items-center justify-center rounded-lg bg-red-50 text-red-700">
            <TriangleAlert className="size-5" />
          </div>
          <div>
            <p className="font-medium">Couldn&apos;t check your session</p>
            <p className="mt-1 max-w-md text-sm text-muted-foreground">{state.message}</p>
          </div>
          <Button variant="outline" onClick={retry}>
            <RefreshCw data-icon="inline-start" />
            Try again
          </Button>
        </CardContent>
      </Card>
    )
  }

  return null
}
