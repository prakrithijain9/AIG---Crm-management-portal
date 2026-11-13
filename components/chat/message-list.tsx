import { LoaderCircle } from "lucide-react"
import type { ChatAction, ChatProposal, ChatSource } from "@/lib/chat"
import { ActionButtons } from "./action-buttons"
import { MarkdownText } from "./markdown-text"
import { ProposalCard } from "./proposal-card"
import { Sources } from "./sources"

export type ChatMessage = {
  id: string
  role: "user" | "assistant"
  content: string
  proposals?: ChatProposal[]
  actions?: ChatAction[]
  sources?: ChatSource[]
}

type MessageListProps = {
  messages: ChatMessage[]
  sending: boolean
  onNavigate: () => void
}

/** `role="log"` + aria-live: screen readers announce each new reply as it arrives. */
export function MessageList({ messages, sending, onNavigate }: MessageListProps) {
  return (
    <div role="log" aria-live="polite" aria-label="Conversation" className="flex flex-col gap-4">
      {messages.map((message) =>
        message.role === "user" ? (
          <div key={message.id} className="flex justify-end">
            <p className="max-w-[85%] rounded-2xl rounded-br-sm bg-teal-700 px-3 py-2 text-sm whitespace-pre-wrap text-white [overflow-wrap:anywhere]">
              {message.content}
            </p>
          </div>
        ) : (
          <div key={message.id} className="flex flex-col gap-2">
            <div className="max-w-[95%] rounded-2xl rounded-bl-sm bg-muted px-3 py-2">
              <MarkdownText text={message.content} />
            </div>
            {message.proposals?.map((proposal) => (
              <ProposalCard key={proposal.proposalId} proposal={proposal} />
            ))}
            <ActionButtons actions={message.actions ?? []} onNavigate={onNavigate} />
            <Sources sources={message.sources ?? []} onNavigate={onNavigate} />
          </div>
        ),
      )}
      {sending ? (
        <div role="status" className="flex items-center gap-2 text-sm text-muted-foreground">
          <LoaderCircle className="size-4 animate-spin text-teal-700" />
          Looking that up…
        </div>
      ) : null}
    </div>
  )
}
