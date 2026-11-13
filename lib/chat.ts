/** Types and pure helpers for the CRM assistant. No React here, so they are unit-tested. */

export const MAX_HISTORY = 12 // the API rejects more
export const MAX_MESSAGE_LENGTH = 2000 // the API rejects more

export type ChatEntity = "company" | "contact" | "deal" | "activity"

/** A change the assistant prepared. Nothing is saved until the user confirms. */
export type ChatProposal = {
  proposalId: string
  op: "create" | "update" | "delete"
  entity: ChatEntity
  id?: string
  /** The full camelCase *Input the existing create/update mutations take. */
  input?: Record<string, unknown>
  before?: Record<string, unknown>
  /** For deletes: how many records go with it. */
  impact?: { contacts?: number; deals?: number; activities?: number; activitiesLosingContact?: number }
  summary: string
}

export type ChatAction = { type: "navigate"; label: string; href: string }
export type ChatSource = { type: ChatEntity; id: string; label: string }

export type ChatReply = {
  reply: string
  proposals: ChatProposal[]
  actions: ChatAction[]
  sources: ChatSource[]
}

export type ChatTurn = { role: "user" | "assistant"; content: string }

/** The last MAX_HISTORY user/assistant turns, text only. The server is stateless. */
export function buildHistory(turns: ChatTurn[]): ChatTurn[] {
  return turns.slice(-MAX_HISTORY).map(({ role, content }) => ({ role, content: content.slice(0, 4000) }))
}

const PAGE_FOR: Record<ChatEntity, string> = {
  company: "/companies",
  contact: "/contacts",
  deal: "/deals",
  activity: "/activities",
}

/** The page that opens this record's details (the pages read ?open=). */
export function sourceHref(source: Pick<ChatSource, "type" | "id">): string {
  return `${PAGE_FOR[source.type]}?open=${encodeURIComponent(source.id)}`
}

/** Only same-app paths are followed: the href came from the server, but never trust it blindly. */
export function isInternalHref(href: string): boolean {
  return href.startsWith("/") && !href.startsWith("//") && !href.includes("\\")
}

// --- Proposal card rows -------------------------------------------------------------

export type DiffRow = { label: string; before?: string; after?: string }

export type NameLookup = {
  company: (id: string) => string | undefined
  contact: (id: string) => string | undefined
}

const FIELD_LABELS: Record<string, string> = {
  name: "Name",
  industry: "Industry",
  email: "Email",
  phone: "Phone",
  location: "Location",
  status: "Status",
  jobTitle: "Job title",
  title: "Title",
  companyId: "Company",
  contactId: "Contact",
  value: "Value",
  stage: "Stage",
  expectedCloseDate: "Expected close",
  type: "Type",
  subject: "Subject",
  dueDate: "Due date",
}

function show(key: string, value: unknown, names: NameLookup): string {
  if (value === null || value === undefined || value === "") return "—"
  if (key === "companyId") return names.company(String(value)) ?? "Unknown company"
  if (key === "contactId") return names.contact(String(value)) ?? "Unknown contact"
  if (key === "value" && typeof value === "number") {
    return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(value)
  }
  return String(value)
}

/** What the card shows: the fields that change (update), all fields (create), or the record (delete). */
export function proposalRows(proposal: ChatProposal, names: NameLookup): DiffRow[] {
  const label = (key: string) => FIELD_LABELS[key] ?? key
  if (proposal.op === "create") {
    return Object.entries(proposal.input ?? {}).map(([key, value]) => ({
      label: label(key),
      after: show(key, value, names),
    }))
  }
  if (proposal.op === "delete") {
    return Object.entries(proposal.before ?? {}).map(([key, value]) => ({
      label: label(key),
      before: show(key, value, names),
    }))
  }
  const before = proposal.before ?? {}
  return Object.entries(proposal.input ?? {})
    .filter(([key, value]) => before[key] !== value)
    .map(([key, value]) => ({
      label: label(key),
      before: show(key, before[key], names),
      after: show(key, value, names),
    }))
}

/** "2 contacts, 1 deal, 1 activity" for a delete's cascade; empty when nothing else goes. */
export function impactText(impact: ChatProposal["impact"]): string {
  if (!impact) return ""
  const part = (n: number | undefined, one: string, many: string) =>
    n ? `${n} ${n === 1 ? one : many}` : null
  return [
    part(impact.contacts, "contact", "contacts"),
    part(impact.deals, "deal", "deals"),
    part(impact.activities, "activity", "activities"),
  ]
    .filter(Boolean)
    .join(", ")
}

// --- Minimal markdown ---------------------------------------------------------------
//
// Replies use a small subset: paragraphs, bullet and numbered lists, tables, **bold** and
// `code`. Parsed to plain data and rendered as React text nodes, so a reply can never inject
// HTML, and no markdown dependency is needed.

export type Inline = { text: string; bold?: boolean; code?: boolean }
export type Block =
  | { kind: "paragraph"; inline: Inline[] }
  | { kind: "list"; ordered: boolean; items: Inline[][] }
  | { kind: "table"; header: Inline[][]; rows: Inline[][][] }

export function parseInline(text: string): Inline[] {
  const out: Inline[] = []
  const pattern = /\*\*(.+?)\*\*|`([^`]+)`/g
  let last = 0
  for (const match of text.matchAll(pattern)) {
    if (match.index > last) out.push({ text: text.slice(last, match.index) })
    out.push(match[1] !== undefined ? { text: match[1], bold: true } : { text: match[2], code: true })
    last = match.index + match[0].length
  }
  if (last < text.length) out.push({ text: text.slice(last) })
  return out
}

const isTableRow = (line: string) => line.trim().startsWith("|") && line.trim().endsWith("|")
const isSeparator = (line: string) => /^\s*\|?[\s:|-]+\|?\s*$/.test(line) && line.includes("-")
const cells = (line: string) =>
  line
    .trim()
    .replace(/^\||\|$/g, "")
    .split("|")
    .map((cell) => parseInline(cell.trim()))

export function parseMarkdown(source: string): Block[] {
  const lines = source.replace(/\r\n/g, "\n").split("\n")
  const blocks: Block[] = []
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    if (!line.trim()) {
      i++
    } else if (isTableRow(line) && i + 1 < lines.length && isSeparator(lines[i + 1])) {
      const header = cells(line)
      i += 2
      const rows: Inline[][][] = []
      while (i < lines.length && isTableRow(lines[i])) rows.push(cells(lines[i++]))
      blocks.push({ kind: "table", header, rows })
    } else if (/^\s*([-*•]|\d+[.)])\s+/.test(line)) {
      const ordered = /^\s*\d+[.)]\s+/.test(line)
      const items: Inline[][] = []
      while (i < lines.length && /^\s*([-*•]|\d+[.)])\s+/.test(lines[i])) {
        items.push(parseInline(lines[i].replace(/^\s*([-*•]|\d+[.)])\s+/, "")))
        i++
      }
      blocks.push({ kind: "list", ordered, items })
    } else {
      // Always take the first line (it matched no other block), or a stray "| x |" line would loop forever.
      const text: string[] = [lines[i++].trim()]
      while (
        i < lines.length &&
        lines[i].trim() &&
        !isTableRow(lines[i]) &&
        !/^\s*([-*•]|\d+[.)])\s+/.test(lines[i])
      ) {
        text.push(lines[i++].trim())
      }
      blocks.push({ kind: "paragraph", inline: parseInline(text.join(" ")) })
    }
  }
  return blocks
}
