"use client"

import { useEffect, useState } from "react"
import Image from "next/image"
import Link from "next/link"
import { usePathname } from "next/navigation"
import {
  Building2,
  CalendarCheck2,
  Handshake,
  LayoutDashboard,
  Menu,
  Users,
  X,
} from "lucide-react"
import { cn } from "@/lib/utils"

const navigation = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/companies", label: "Companies", icon: Building2 },
  { href: "/contacts", label: "Contacts", icon: Users },
  { href: "/deals", label: "Deals", icon: Handshake },
  { href: "/activities", label: "Activities", icon: CalendarCheck2 },
]

function Brand() {
  return (
    <div className="flex items-center gap-3">
      <div className="relative size-9 shrink-0 overflow-hidden rounded-lg bg-white">
        {/* Source has uneven white margins; offset so the mark is centred. */}
        <Image
          src="/aig-logo.png"
          alt="AIG Tech Solution logo"
          width={732}
          height={686}
          sizes="50px"
          className="absolute top-[-10.6%] left-[-23.6%] h-auto w-[138.4%] max-w-none"
        />
      </div>
      <div>
        <p className="text-sm font-semibold tracking-wide">AIG CRM</p>
        <p className="text-xs text-slate-400">Internal workspace</p>
      </div>
    </div>
  )
}

export function Sidebar() {
  const pathname = usePathname()
  const [isOpen, setIsOpen] = useState(false)
  const [lastPathname, setLastPathname] = useState(pathname)

  // Close the drawer on any navigation (including browser back/forward).
  if (pathname !== lastPathname) {
    setLastPathname(pathname)
    setIsOpen(false)
  }

  useEffect(() => {
    if (!isOpen) return

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setIsOpen(false)
    }
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = "hidden"

    window.addEventListener("keydown", handleKeyDown)
    return () => {
      window.removeEventListener("keydown", handleKeyDown)
      document.body.style.overflow = previousOverflow
    }
  }, [isOpen])

  return (
    <>
      {/* Mobile top bar */}
      <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-white/10 bg-slate-950 px-4 text-slate-100 md:hidden">
        <Brand />
        <button
          type="button"
          onClick={() => setIsOpen(true)}
          aria-label="Open navigation menu"
          aria-expanded={isOpen}
          aria-controls="app-sidebar"
          className="flex size-10 items-center justify-center rounded-lg text-slate-200 hover:bg-white/10"
        >
          <Menu className="size-5" />
        </button>
      </header>

      {/* Mobile backdrop */}
      {isOpen && (
        <button
          type="button"
          aria-label="Close navigation menu"
          onClick={() => setIsOpen(false)}
          className="fixed inset-0 z-40 bg-slate-950/50 md:hidden"
        />
      )}

      <aside
        id="app-sidebar"
        className={cn(
          "fixed inset-y-0 left-0 z-50 flex w-64 max-w-[85vw] flex-col overflow-y-auto bg-slate-950 text-slate-100 transition-transform duration-200 ease-in-out md:z-40 md:translate-x-0",
          isOpen ? "translate-x-0 shadow-xl" : "-translate-x-full"
        )}
      >
        <div className="flex h-16 shrink-0 items-center justify-between gap-3 border-b border-white/10 px-5">
          <Brand />
          <button
            type="button"
            onClick={() => setIsOpen(false)}
            aria-label="Close navigation menu"
            className="rounded-md p-1 text-slate-300 hover:bg-white/10 md:hidden"
          >
            <X className="size-5" />
          </button>
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
                onClick={() => setIsOpen(false)}
                aria-current={isActive ? "page" : undefined}
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                  isActive
                    ? "bg-white/10 text-white"
                    : "text-slate-300 hover:bg-white/5 hover:text-white"
                )}
              >
                <Icon
                  className={cn("size-4", isActive && "text-teal-400")}
                />
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
    </>
  )
}
