"use client"

import { LoaderCircle, RefreshCw, TriangleAlert } from "lucide-react"
import type { ReactNode } from "react"
import { useCrm } from "@/components/crm/crm-provider"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"

/** Shows a loading or error state until the CRM data has been fetched from the API. */
export function DataGate({ children }: { children: ReactNode }) {
  const { loadState, reload } = useCrm()

  if (loadState.status === "loading") {
    return (
      <Card>
        <CardContent
          role="status"
          className="flex items-center justify-center gap-3 py-16 text-sm text-muted-foreground"
        >
          <LoaderCircle className="size-5 animate-spin text-teal-700" />
          Loading CRM data…
        </CardContent>
      </Card>
    )
  }

  if (loadState.status === "error") {
    return (
      <Card>
        <CardContent role="alert" className="flex flex-col items-center gap-3 py-16 text-center">
          <div className="flex size-10 items-center justify-center rounded-lg bg-red-50 text-red-700">
            <TriangleAlert className="size-5" />
          </div>
          <div>
            <p className="font-medium">Couldn&apos;t load CRM data</p>
            <p className="mt-1 max-w-md text-sm text-muted-foreground">{loadState.message}</p>
          </div>
          <Button variant="outline" onClick={reload}>
            <RefreshCw data-icon="inline-start" />
            Try again
          </Button>
        </CardContent>
      </Card>
    )
  }

  return children
}
