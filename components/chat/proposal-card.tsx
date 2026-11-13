"use client"

import { Check, LoaderCircle, TriangleAlert } from "lucide-react"
import { useState } from "react"
import { useCrm } from "@/components/crm/crm-provider"
import { Button } from "@/components/ui/button"
import { ApiError, errorMessage } from "@/lib/api"
import { impactText, proposalRows, type ChatProposal } from "@/lib/chat"
import type { ActivityInput, CompanyInput, ContactInput, DealInput } from "@/lib/types"

type CardState =
  | { status: "pending" }
  | { status: "working" }
  | { status: "done" }
  | { status: "cancelled" }
  | { status: "failed"; message: string; fieldErrors: Record<string, string> }

/**
 * A change the assistant prepared. Nothing is saved until Confirm, which calls the same
 * mutation the pages use, so validation, cascades and local state behave identically.
 * Each proposal can be confirmed once.
 */
export function ProposalCard({ proposal }: { proposal: ChatProposal }) {
  const crm = useCrm()
  const [state, setState] = useState<CardState>({ status: "pending" })

  const rows = proposalRows(proposal, {
    company: (id) => crm.companies.find((company) => company.id === id)?.name,
    contact: (id) => crm.contacts.find((contact) => contact.id === id)?.name,
  })
  const impact = proposal.op === "delete" ? impactText(proposal.impact) : ""

  async function confirm() {
    setState({ status: "working" })
    try {
      await apply(proposal, crm)
      setState({ status: "done" })
    } catch (error) {
      setState({
        status: "failed",
        message: errorMessage(error),
        fieldErrors: error instanceof ApiError ? error.fieldErrors : {},
      })
    }
  }

  const working = state.status === "working"

  return (
    <div
      className={`rounded-lg border bg-background p-3 text-sm ${proposal.op === "delete" ? "border-red-200" : ""}`}
      data-testid="proposal-card"
    >
      <p className="font-medium [overflow-wrap:anywhere]">{proposal.summary}</p>

      {rows.length > 0 ? (
        <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
          {rows.map((row) => (
            <div key={row.label} className="contents">
              <dt className="text-muted-foreground">{row.label}</dt>
              <dd className="[overflow-wrap:anywhere]">
                {row.before !== undefined && row.after !== undefined ? (
                  <>
                    <span className="text-muted-foreground line-through">{row.before}</span>
                    {" → "}
                    <span className="font-medium">{row.after}</span>
                  </>
                ) : (
                  (row.after ?? row.before)
                )}
              </dd>
            </div>
          ))}
        </dl>
      ) : null}

      {impact ? (
        <p role="alert" className="mt-2 flex items-start gap-1.5 rounded-md bg-red-50 px-2 py-1.5 text-xs text-red-700">
          <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
          This also permanently deletes {impact}.
        </p>
      ) : null}

      {proposal.op === "delete" && proposal.impact?.activitiesLosingContact ? (
        <p className="mt-2 rounded-md bg-amber-50 px-2 py-1.5 text-xs text-amber-800">
          {proposal.impact.activitiesLosingContact} linked{" "}
          {proposal.impact.activitiesLosingContact === 1 ? "activity" : "activities"} will be kept but lose this contact.
        </p>
      ) : null}

      {state.status === "failed" ? (
        <div role="alert" className="mt-2 rounded-md bg-red-50 px-2 py-1.5 text-xs text-red-700">
          <p>{state.message}</p>
          {Object.entries(state.fieldErrors).map(([field, message]) => (
            <p key={field}>
              {field}: {message}
            </p>
          ))}
        </div>
      ) : null}

      <div className="mt-3 flex items-center gap-2">
        {state.status === "done" ? (
          <span className="flex items-center gap-1 text-xs font-medium text-teal-700">
            <Check className="size-3.5" /> Done
          </span>
        ) : state.status === "cancelled" ? (
          <span className="text-xs text-muted-foreground">Cancelled</span>
        ) : (
          <>
            <Button
              size="sm"
              variant={proposal.op === "delete" ? "destructive" : "default"}
              disabled={working}
              onClick={confirm}
            >
              {working ? <LoaderCircle className="animate-spin" data-icon="inline-start" /> : null}
              {state.status === "failed" ? "Try again" : proposal.op === "delete" ? "Delete" : "Confirm"}
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={working}
              onClick={() => setState({ status: "cancelled" })}
            >
              Cancel
            </Button>
          </>
        )}
      </div>
    </div>
  )
}

/** Calls the CRM mutation that matches the proposal. `input` is already the full *Input the server validated. */
async function apply(proposal: ChatProposal, crm: ReturnType<typeof useCrm>): Promise<void> {
  const { op, entity, id, input } = proposal
  if (op === "delete") {
    if (!id) throw new Error("This proposal has no record to delete.")
    if (entity === "company") return crm.deleteCompany(id)
    if (entity === "contact") return crm.deleteContact(id)
    if (entity === "deal") return crm.deleteDeal(id)
    return crm.deleteActivity(id)
  }
  if (!input) throw new Error("This proposal has no data to save.")
  if (op === "create") {
    if (entity === "company") return crm.addCompany(input as CompanyInput)
    if (entity === "contact") return crm.addContact(input as ContactInput)
    if (entity === "deal") return crm.addDeal(input as DealInput)
    return crm.addActivity(input as ActivityInput)
  }
  if (!id) throw new Error("This proposal has no record to update.")
  if (entity === "company") return crm.updateCompany(id, input as CompanyInput)
  if (entity === "contact") return crm.updateContact(id, input as ContactInput)
  if (entity === "deal") return crm.updateDeal(id, input as DealInput)
  return crm.updateActivity(id, input as ActivityInput)
}
