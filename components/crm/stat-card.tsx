import type { LucideIcon } from "lucide-react"
import { Card, CardContent } from "@/components/ui/card"

type StatCardProps = {
  label: string
  value: string | number
  hint?: string
  icon: LucideIcon
}

export function StatCard({ label, value, hint, icon: Icon }: StatCardProps) {
  return (
    <Card>
      <CardContent className="flex items-start justify-between">
        <div>
          <p className="text-sm text-muted-foreground">{label}</p>
          <p className="mt-2 text-2xl font-semibold tracking-tight">{value}</p>
          {hint ? (
            <p className="mt-1 text-xs text-muted-foreground">{hint}</p>
          ) : null}
        </div>
        <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-teal-50 text-teal-700">
          <Icon className="size-5" />
        </div>
      </CardContent>
    </Card>
  )
}
