import { Fragment } from "react"
import { parseMarkdown, type Inline } from "@/lib/chat"

function Spans({ spans }: { spans: Inline[] }) {
  return (
    <>
      {spans.map((span, index) => {
        if (span.bold) return <strong key={index}>{span.text}</strong>
        if (span.code) {
          return (
            <code key={index} className="rounded bg-muted px-1 py-0.5 font-mono text-[0.8em]">
              {span.text}
            </code>
          )
        }
        return <Fragment key={index}>{span.text}</Fragment>
      })}
    </>
  )
}

/** A reply's text. Rendered as React text nodes only, so nothing in a reply can inject HTML. */
export function MarkdownText({ text }: { text: string }) {
  return (
    <div className="space-y-2 text-sm leading-relaxed [overflow-wrap:anywhere]">
      {parseMarkdown(text).map((block, index) => {
        if (block.kind === "paragraph") {
          return (
            <p key={index}>
              <Spans spans={block.inline} />
            </p>
          )
        }
        if (block.kind === "list") {
          const List = block.ordered ? "ol" : "ul"
          return (
            <List key={index} className={block.ordered ? "list-decimal pl-5" : "list-disc pl-5"}>
              {block.items.map((item, i) => (
                <li key={i}>
                  <Spans spans={item} />
                </li>
              ))}
            </List>
          )
        }
        return (
          <div key={index} className="overflow-x-auto rounded-md border">
            <table className="w-full text-left text-xs">
              <thead className="bg-muted/60">
                <tr>
                  {block.header.map((cell, i) => (
                    <th key={i} className="px-2 py-1.5 font-medium whitespace-nowrap">
                      <Spans spans={cell} />
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {block.rows.map((row, r) => (
                  <tr key={r} className="border-t">
                    {row.map((cell, c) => (
                      <td key={c} className="px-2 py-1.5 whitespace-nowrap">
                        <Spans spans={cell} />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      })}
    </div>
  )
}
