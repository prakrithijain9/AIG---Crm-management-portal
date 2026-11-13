import { ArrowRight } from "lucide-react"
import Link from "next/link"
import { buttonVariants } from "@/components/ui/button"
import { isInternalHref, type ChatAction } from "@/lib/chat"

/** Buttons the server built (the model never writes URLs). Only same-app paths are rendered. */
export function ActionButtons({ actions, onNavigate }: { actions: ChatAction[]; onNavigate: () => void }) {
  const safe = actions.filter((action) => isInternalHref(action.href))
  if (safe.length === 0) return null
  return (
    <div className="flex flex-wrap gap-2">
      {safe.map((action) => (
        <Link
          key={action.href}
          href={action.href}
          onClick={onNavigate}
          className={buttonVariants({ variant: "outline", size: "sm" })}
        >
          {action.label}
          <ArrowRight data-icon="inline-end" />
        </Link>
      ))}
    </div>
  )
}
