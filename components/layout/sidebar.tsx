"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import {
  Building2,
  CalendarCheck2,
  Handshake,
  LayoutDashboard,
  Users,
} from "lucide-react"
import { cn } from "@/lib/utils"

const navigation = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/companies", label: "Companies", icon: Building2 },
  { href: "/contacts", label: "Contacts", icon: Users },
  { href: "/deals", label: "Deals", icon: Handshake },
  { href: "/activities", label: "Activities", icon: CalendarCheck2 },
]

export function Sidebar() {
  const pathname = usePathname()

  return (
    <aside className="fixed inset-y-0 left-0 z-40 flex w-64 flex-col overflow-hidden bg-slate-950 text-slate-100">
      <div className="flex h-16 shrink-0 items-center gap-3 border-b border-white/10 px-5">
        <div className="flex size-9 items-center justify-center rounded-lg bg-teal-500 text-sm font-semibold text-white">
          AIG
        </div>
        <div>
          <p className="text-sm font-semibold tracking-wide">AIG CRM</p>
          <p className="text-xs text-slate-400">Internal workspace</p>
        </div>
      </div>

      <nav className="flex-1 space-y-1 px-3 py-4">
        {navigation.map((item) => {
          const isActive =
            item.href === "/"
              ? pathname === "/"
              : pathname.startsWith(item.href)
          const Icon = item.icon

          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-white/10 text-white"
                  : "text-slate-300 hover:bg-white/5 hover:text-white"
              )}
            >
              <Icon className="size-4" />
              {item.label}
            </Link>
          )
        })}
      </nav>

      <div className="shrink-0 border-t border-white/10 px-5 py-4">
        <p className="truncate text-sm font-medium">Prakrithi Jain</p>
        <p className="truncate text-xs text-slate-400">Account executive</p>
      </div>
    </aside>
  )
}
