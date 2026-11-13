import { Suspense, type ReactNode } from "react"
import { AppShell } from "@/components/layout/app-shell"

/**
 * Every CRM page (Dashboard, Companies, Contacts, Deals, Activities) requires a signed-in admin.
 *
 * The pages read their filters from the URL (useSearchParams), which Next.js cannot know at
 * build time, so they sit in a Suspense boundary: the shell prerenders and the page itself
 * renders in the browser. The fallback is empty on purpose, because DataGate already shows
 * the loading state.
 */
export default function CrmLayout({ children }: { children: ReactNode }) {
  return (
    <AppShell>
      <Suspense fallback={null}>{children}</Suspense>
    </AppShell>
  )
}
