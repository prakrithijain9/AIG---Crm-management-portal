import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import type {
  ActivityStatus,
  CompanyStatus,
  DealStage,
} from "@/lib/types"

const toneClasses: Record<string, string> = {
  Active: "border-emerald-200 bg-emerald-50 text-emerald-800",
  Prospect: "border-sky-200 bg-sky-50 text-sky-800",
  Inactive: "border-slate-200 bg-slate-100 text-slate-700",
  Lead: "border-slate-200 bg-slate-100 text-slate-700",
  Qualified: "border-sky-200 bg-sky-50 text-sky-800",
  Proposal: "border-violet-200 bg-violet-50 text-violet-800",
  Negotiation: "border-amber-200 bg-amber-50 text-amber-800",
  Won: "border-emerald-200 bg-emerald-50 text-emerald-800",
  Lost: "border-rose-200 bg-rose-50 text-rose-800",
  Pending: "border-amber-200 bg-amber-50 text-amber-800",
  Completed: "border-emerald-200 bg-emerald-50 text-emerald-800",
}

type StatusBadgeProps = {
  value: CompanyStatus | DealStage | ActivityStatus | string
}

export function StatusBadge({ value }: StatusBadgeProps) {
  return (
    <Badge
      variant="outline"
      className={cn("font-medium", toneClasses[value] ?? "bg-muted")}
    >
      {value}
    </Badge>
  )
}
