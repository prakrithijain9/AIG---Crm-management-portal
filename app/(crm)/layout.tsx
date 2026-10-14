import type { ReactNode } from "react"
import { AppShell } from "@/components/layout/app-shell"

/** Every CRM page (Dashboard, Companies, Contacts, Deals, Activities) requires a signed-in admin. */
export default function CrmLayout({ children }: { children: ReactNode }) {
  return <AppShell>{children}</AppShell>
}
