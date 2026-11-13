import assert from "node:assert/strict"
import test from "node:test"
import {
  buildHistory,
  impactText,
  isInternalHref,
  parseInline,
  parseMarkdown,
  proposalRows,
  sourceHref,
  type ChatProposal,
} from "./chat.ts"

const names = {
  company: (id: string) => (id === "c1" ? "Helios Energy" : undefined),
  contact: (id: string) => (id === "p1" ? "Marcus Chen" : undefined),
}

test("buildHistory keeps the last 12 turns and caps their length", () => {
  const turns = Array.from({ length: 15 }, (_, i) => ({ role: "user" as const, content: `m${i}` }))
  const history = buildHistory(turns)
  assert.equal(history.length, 12)
  assert.equal(history[0].content, "m3")
  assert.equal(buildHistory([{ role: "assistant", content: "x".repeat(5000) }])[0].content.length, 4000)
})

test("sourceHref points at the page's ?open= param", () => {
  assert.equal(sourceHref({ type: "deal", id: "a b" }), "/deals?open=a%20b")
  assert.equal(sourceHref({ type: "company", id: "1" }), "/companies?open=1")
})

test("isInternalHref only allows same-app paths", () => {
  assert.ok(isInternalHref("/deals?stage=Won"))
  assert.ok(isInternalHref("/"))
  for (const bad of ["https://evil.example", "//evil.example", "javascript:alert(1)", "deals", "/\\evil.example"]) {
    assert.equal(isInternalHref(bad), false, bad)
  }
})

test("update proposals show only changed fields, with names and money formatted", () => {
  const proposal: ChatProposal = {
    proposalId: "p",
    op: "update",
    entity: "deal",
    id: "d1",
    input: { title: "Grid", companyId: "c1", value: 420000, stage: "Won" },
    before: { title: "Grid", companyId: "c1", value: 420000, stage: "Proposal" },
    summary: "",
  }
  assert.deepEqual(proposalRows(proposal, names), [{ label: "Stage", before: "Proposal", after: "Won" }])
  const moved = { ...proposal, input: { ...proposal.input, value: 500000, companyId: "zzz" } }
  const rows = proposalRows(moved as ChatProposal, names)
  assert.deepEqual(rows.find((r) => r.label === "Value"), { label: "Value", before: "$420,000.00", after: "$500,000.00" })
  assert.equal(rows.find((r) => r.label === "Company")?.after, "Unknown company")
})

test("create shows every field; delete shows the record; empty values become a dash", () => {
  const create: ChatProposal = {
    proposalId: "p",
    op: "create",
    entity: "activity",
    input: { type: "Call", companyId: "c1", contactId: null },
    summary: "",
  }
  assert.deepEqual(proposalRows(create, names), [
    { label: "Type", after: "Call" },
    { label: "Company", after: "Helios Energy" },
    { label: "Contact", after: "—" },
  ])
  const del: ChatProposal = { proposalId: "p", op: "delete", entity: "company", before: { name: "Helios" }, summary: "" }
  assert.deepEqual(proposalRows(del, names), [{ label: "Name", before: "Helios" }])
})

test("impactText pluralises and skips zeros", () => {
  assert.equal(impactText({ contacts: 2, deals: 1, activities: 1 }), "2 contacts, 1 deal, 1 activity")
  assert.equal(impactText({ contacts: 0, deals: 0, activities: 0 }), "")
  assert.equal(impactText(undefined), "")
})

test("parseInline handles bold and code, and leaves other markup alone", () => {
  assert.deepEqual(parseInline("a **b** `c` <script>"), [
    { text: "a " },
    { text: "b", bold: true },
    { text: " " },
    { text: "c", code: true },
    { text: " <script>" },
  ])
})

test("parseMarkdown: paragraphs, lists and tables", () => {
  const blocks = parseMarkdown(
    ["Intro **now**", "", "- one", "- two", "", "1. first", "2. second", "", "| A | B |", "|---|---|", "| 1 | 2 |"].join("\n"),
  )
  assert.deepEqual(blocks.map((b) => b.kind), ["paragraph", "list", "list", "table"])
  const table = blocks[3]
  assert.ok(table.kind === "table")
  assert.equal(table.header.length, 2)
  assert.deepEqual(table.rows[0].map((c) => c[0].text), ["1", "2"])
  const ordered = blocks[2]
  assert.ok(ordered.kind === "list" && ordered.ordered && ordered.items.length === 2)
})

test("a pipe-looking line without a separator row is just text", () => {
  assert.deepEqual(parseMarkdown("| not a table |").map((b) => b.kind), ["paragraph"])
})
