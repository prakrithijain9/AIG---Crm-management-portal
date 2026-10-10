"use client"

import type { ReactNode } from "react"
import { CrmProvider } from "@/components/crm/crm-provider"
import { Sidebar } from "@/components/layout/sidebar"

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <CrmProvider>
      <div className="min-h-full bg-slate-50">
        <Sidebar />
        <main className="ml-64 min-h-screen">
          <div className="mx-auto max-w-7xl px-6 py-8">{children}</div>
        </main>
      </div>
    </CrmProvider>
  )
}
