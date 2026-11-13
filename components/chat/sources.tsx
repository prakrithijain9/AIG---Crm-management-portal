import Link from "next/link"
import { sourceHref, type ChatSource } from "@/lib/chat"

const TYPE_LABEL = { company: "Company", contact: "Contact", deal: "Deal", activity: "Activity" } as const

/** The records the assistant actually looked at, from the server (not the model's prose). */
export function Sources({ sources, onNavigate }: { sources: ChatSource[]; onNavigate: () => void }) {
  if (sources.length === 0) return null
  return (
    <div>
      <p className="mb-1 text-xs text-muted-foreground">Records used</p>
      <ul className="flex flex-wrap gap-1.5">
        {sources.map((source) => (
          <li key={`${source.type}:${source.id}`}>
            <Link
              href={sourceHref(source)}
              onClick={onNavigate}
              className="inline-flex max-w-full items-center gap-1 rounded-full border bg-background px-2 py-0.5 text-xs transition-colors hover:bg-muted"
            >
              <span className="text-muted-foreground">{TYPE_LABEL[source.type]}</span>
              <span className="truncate">{source.label}</span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  )
}
