import type { Metadata } from "next"
import { Suspense } from "react"
import { LoginForm } from "@/components/auth/login-form"
import { Brand } from "@/components/layout/sidebar"
import { Card, CardContent } from "@/components/ui/card"

export const metadata: Metadata = {
  title: "Sign in · AIG CRM",
}

export default function LoginPage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-8 bg-slate-950 px-4 py-12 text-slate-100">
      <Brand />
      {/* LoginForm reads ?next= and ?reason=, so it renders on the client inside Suspense. */}
      <Suspense fallback={<LoginFallback />}>
        <LoginForm />
      </Suspense>
    </main>
  )
}

function LoginFallback() {
  return (
    <Card className="w-full max-w-sm">
      <CardContent className="py-16 text-center text-sm text-muted-foreground">Loading…</CardContent>
    </Card>
  )
}
