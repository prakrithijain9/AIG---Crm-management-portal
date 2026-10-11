"use client"

import type { ReactNode } from "react"
import { CrmProvider } from "@/components/crm/crm-provider"
import { Sidebar } from "@/components/layout/sidebar"

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <CrmProvider>
      <div className="min-h-screen bg-slate-50">
        <Sidebar />
        <main className="min-h-screen min-w-0 md:ml-64">
          <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 sm:py-8">
            {children}
          </div>
        </main>
      </div>
    </CrmProvider>
  )
}
