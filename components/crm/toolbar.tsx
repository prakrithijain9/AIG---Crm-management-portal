import type { ReactNode } from "react"
import { Search } from "lucide-react"
import { Input } from "@/components/ui/input"

type ToolbarProps = {
  search: string
  onSearchChange: (value: string) => void
  placeholder?: string
  children?: ReactNode
}

export function Toolbar({
  search,
  onSearchChange,
  placeholder = "Search",
  children,
}: ToolbarProps) {
  return (
    <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div className="relative w-full sm:max-w-sm">
        <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={search}
          onChange={(event) => onSearchChange(event.target.value)}
          placeholder={placeholder}
          className="pl-8"
        />
      </div>
      {children ? (
        <div className="flex flex-wrap gap-2 *:max-sm:w-full">{children}</div>
      ) : null}
    </div>
  )
}
