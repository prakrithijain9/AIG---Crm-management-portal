"use client"

import { useEffect, useState } from "react"
import { DetailList, SelectField, TextField } from "@/components/crm/form-fields"
import { EntityDialog } from "@/components/crm/entity-dialog"
import { StatusBadge } from "@/components/crm/status-badge"
import { companyNameById, formatCurrency, formatDate } from "@/lib/format"
import type { Company, Deal, DealInput, DealStage } from "@/lib/types"
import { dealStages } from "@/lib/types"

type DealDialogProps = {
  open: boolean
  mode: "view" | "edit" | "create"
  deal?: Deal
  companies: Company[]
  onOpenChange: (open: boolean) => void
  onSubmit: (input: DealInput) => void
}

function emptyDeal(companies: Company[]): DealInput {
  return {
    title: "",
    companyId: companies[0]?.id ?? "",
    value: 0,
    stage: "Lead",
    expectedCloseDate: "",
  }
}

export function DealDialog({
  open,
  mode,
  deal,
  companies,
  onOpenChange,
  onSubmit,
}: DealDialogProps) {
  const [form, setForm] = useState<DealInput>(emptyDeal(companies))

  useEffect(() => {
    if (!open) return
    setForm(
      deal
        ? {
            title: deal.title,
            companyId: deal.companyId,
            value: deal.value,
            stage: deal.stage,
            expectedCloseDate: deal.expectedCloseDate,
          }
        : emptyDeal(companies)
    )
  }, [companies, deal, open])

  return (
    <EntityDialog
      open={open}
      mode={mode}
      title={
        mode === "create"
          ? "Add deal"
          : mode === "edit"
            ? "Edit deal"
            : "Deal details"
      }
      description={
        mode === "view"
          ? "Review this opportunity."
          : "Track opportunity value, owner account, and pipeline stage."
      }
      onOpenChange={onOpenChange}
      onSubmit={() => onSubmit(form)}
    >
      {mode === "view" ? (
        <DetailList
          items={[
            { label: "Title", value: form.title },
            {
              label: "Company",
              value: companyNameById(companies, form.companyId),
            },
            { label: "Value", value: formatCurrency(form.value) },
            { label: "Stage", value: <StatusBadge value={form.stage} /> },
            {
              label: "Expected close",
              value: form.expectedCloseDate
                ? formatDate(form.expectedCloseDate)
                : "—",
            },
          ]}
        />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <TextField
              label="Deal title"
              value={form.title}
              required
              onChange={(title) => setForm((current) => ({ ...current, title }))}
            />
          </div>
          <SelectField
            label="Company"
            value={form.companyId}
            options={companies.map((company) => ({
              value: company.id,
              label: company.name,
            }))}
            onChange={(companyId) =>
              setForm((current) => ({ ...current, companyId }))
            }
          />
          <SelectField
            label="Stage"
            value={form.stage}
            options={dealStages.map((stage) => ({
              value: stage,
              label: stage,
            }))}
            onChange={(stage) =>
              setForm((current) => ({ ...current, stage: stage as DealStage }))
            }
          />
          <TextField
            label="Value (USD)"
            type="number"
            value={String(form.value)}
            required
            onChange={(value) =>
              setForm((current) => ({
                ...current,
                value: Number(value) || 0,
              }))
            }
          />
          <TextField
            label="Expected close date"
            type="date"
            value={form.expectedCloseDate}
            required
            onChange={(expectedCloseDate) =>
              setForm((current) => ({ ...current, expectedCloseDate }))
            }
          />
        </div>
      )}
    </EntityDialog>
  )
}
