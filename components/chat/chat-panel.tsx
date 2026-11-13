"use client"

import { MessageCircle, RefreshCw, Send, SquarePen, TriangleAlert, X } from "lucide-react"
import { useEffect, useRef, useState, type KeyboardEvent } from "react"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { api, ApiError, errorMessage } from "@/lib/api"
import { buildHistory, MAX_MESSAGE_LENGTH, type ChatTurn } from "@/lib/chat"
import { MessageList, type ChatMessage } from "./message-list"

type Problem = { message: string; unavailable: boolean; retryText: string | null }

const EXAMPLES = [
  "How many open deals do we have, and what are they worth?",
  "Which activities are overdue?",
  "Show me all won deals",
]

function toTurns(messages: ChatMessage[]): ChatTurn[] {
  return messages.map(({ role, content }) => ({ role, content }))
}

let nextId = 0
const newId = () => `m${++nextId}`

/**
 * The assistant: a floating button plus a right-hand panel, mounted once in AppShell so the
 * conversation survives navigation. The panel stays mounted (hidden when closed) so a
 * proposal card that was already confirmed can never be confirmed again.
 */
export function ChatPanel() {
  const [open, setOpen] = useState(false)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [draft, setDraft] = useState("")
  const [sending, setSending] = useState(false)
  const [problem, setProblem] = useState<Problem | null>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const openerRef = useRef<HTMLButtonElement>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (open) inputRef.current?.focus()
  }, [open])

  useEffect(() => {
    const box = scrollRef.current
    if (box) box.scrollTop = box.scrollHeight
  }, [messages, sending, problem])

  function close() {
    setOpen(false)
    requestAnimationFrame(() => openerRef.current?.focus())
  }

  // Phones show the panel full screen, so leave it after following a link.
  function afterNavigate() {
    if (window.matchMedia("(max-width: 639px)").matches) close()
  }

  async function ask(text: string, earlier: ChatMessage[]) {
    setSending(true)
    setProblem(null)
    try {
      const reply = await api.chat.send(text, buildHistory(toTurns(earlier)))
      setMessages((current) => [
        ...current,
        {
          id: newId(),
          role: "assistant",
          content: reply.reply,
          proposals: reply.proposals,
          actions: reply.actions,
          sources: reply.sources,
        },
      ])
    } catch (error) {
      setProblem({
        message: errorMessage(error),
        unavailable: error instanceof ApiError && error.status === 503,
        retryText: text,
      })
    } finally {
      setSending(false)
    }
  }

  function submit(raw: string) {
    const text = raw.trim()
    if (!text || sending || text.length > MAX_MESSAGE_LENGTH) return
    const earlier = messages
    setMessages([...earlier, { id: newId(), role: "user", content: text }])
    setDraft("")
    void ask(text, earlier)
  }

  function retry() {
    if (!problem?.retryText || sending) return
    // The failed question is still the last message; send it again with the turns before it.
    void ask(problem.retryText, messages.slice(0, -1))
  }

  function onKeyDown(event: KeyboardEvent<HTMLElement>) {
    if (event.key === "Escape") close()
  }

  function onInputKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      submit(draft)
    }
  }

  const tooLong = draft.length > MAX_MESSAGE_LENGTH

  return (
    <>
      {open ? null : (
        <Button
          ref={openerRef}
          size="lg"
          className="fixed right-4 bottom-4 z-40 h-11 rounded-full bg-teal-700 px-4 text-white shadow-lg hover:bg-teal-800"
          onClick={() => setOpen(true)}
        >
          <MessageCircle data-icon="inline-start" />
          Ask CRM Assistant
        </Button>
      )}

      <aside
        hidden={!open}
        aria-label="CRM Assistant"
        onKeyDown={onKeyDown}
        className="fixed inset-y-0 right-0 z-40 flex w-full flex-col border-l bg-background shadow-xl sm:w-[26rem]"
      >
        <header className="flex items-center justify-between gap-2 border-b px-4 py-3">
          <div>
            <h2 className="text-sm font-semibold">CRM Assistant</h2>
            <p className="text-xs text-muted-foreground">Answers come from your live data.</p>
          </div>
          <div className="flex items-center gap-1">
            <Button
              variant="ghost"
              size="icon"
              aria-label="New conversation"
              title="New conversation"
              disabled={messages.length === 0 || sending}
              onClick={() => {
                setMessages([])
                setProblem(null)
              }}
            >
              <SquarePen />
            </Button>
            <Button variant="ghost" size="icon" aria-label="Close assistant" onClick={close}>
              <X />
            </Button>
          </div>
        </header>

        <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4">
          {messages.length === 0 && !sending ? (
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">
                Ask about companies, contacts, deals or activities. I can also prepare changes for you to
                confirm, and take you to the right page.
              </p>
              <div className="flex flex-col items-start gap-2">
                {EXAMPLES.map((example) => (
                  <Button
                    key={example}
                    variant="outline"
                    size="sm"
                    className="h-auto max-w-full py-1.5 text-left whitespace-normal"
                    disabled={problem?.unavailable}
                    onClick={() => submit(example)}
                  >
                    {example}
                  </Button>
                ))}
              </div>
            </div>
          ) : (
            <MessageList messages={messages} sending={sending} onNavigate={afterNavigate} />
          )}

          {problem ? (
            <div
              role="alert"
              className="mt-4 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700"
            >
              <TriangleAlert className="mt-0.5 size-4 shrink-0" />
              <div className="space-y-2">
                <p>{problem.message}</p>
                {problem.unavailable ? null : (
                  <Button variant="outline" size="sm" onClick={retry} disabled={sending}>
                    <RefreshCw data-icon="inline-start" />
                    Try again
                  </Button>
                )}
              </div>
            </div>
          ) : null}
        </div>

        <footer className="border-t p-3">
          <div className="flex items-end gap-2">
            <Textarea
              ref={inputRef}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={onInputKeyDown}
              rows={1}
              aria-label="Message to the assistant"
              aria-invalid={tooLong}
              placeholder={problem?.unavailable ? "The assistant is not available" : "Ask about your CRM…"}
              disabled={problem?.unavailable}
              className="max-h-32 min-h-9 resize-none"
            />
            <Button
              size="icon"
              aria-label="Send message"
              disabled={sending || !draft.trim() || tooLong || problem?.unavailable}
              onClick={() => submit(draft)}
            >
              <Send />
            </Button>
          </div>
          <p className="mt-1.5 text-xs text-muted-foreground">
            {tooLong
              ? `Too long: ${draft.length}/${MAX_MESSAGE_LENGTH} characters.`
              : "Enter to send, Shift+Enter for a new line. Changes are only saved after you confirm."}
          </p>
        </footer>
      </aside>
    </>
  )
}
