"use client"

import { useEffect, useState } from "react"
import { DetailList, SelectField, TextField } from "@/components/crm/form-fields"
import { EntityDialog } from "@/components/crm/entity-dialog"
import { StatusBadge } from "@/components/crm/status-badge"
import type { Company, CompanyInput, CompanyStatus } from "@/lib/types"
import { companyStatuses } from "@/lib/types"

type CompanyDialogProps = {
  open: boolean
  mode: "view" | "edit" | "create"
  company?: Company
  onOpenChange: (open: boolean) => void
  onSubmit: (input: CompanyInput) => void
}

const emptyCompany: CompanyInput = {
  name: "",
  industry: "",
  email: "",
  phone: "",
  location: "",
  status: "Prospect",
}

export function CompanyDialog({
  open,
  mode,
  company,
  onOpenChange,
  onSubmit,
}: CompanyDialogProps) {
  const [form, setForm] = useState<CompanyInput>(emptyCompany)

  useEffect(() => {
    if (!open) return
    setForm(
      company
        ? {
            name: company.name,
            industry: company.industry,
            email: company.email,
            phone: company.phone,
            location: company.location,
            status: company.status,
          }
        : emptyCompany
    )
  }, [company, open])

  return (
    <EntityDialog
      open={open}
      mode={mode}
      title={
        mode === "create"
          ? "Add company"
          : mode === "edit"
            ? "Edit company"
            : "Company details"
      }
      description={
        mode === "view"
          ? "Review this company record."
          : "Capture the core account details used across deals and contacts."
      }
      onOpenChange={onOpenChange}
      onSubmit={() => onSubmit(form)}
    >
      {mode === "view" ? (
        <DetailList
          items={[
            { label: "Name", value: form.name },
            { label: "Industry", value: form.industry },
            { label: "Email", value: form.email },
            { label: "Phone", value: form.phone },
            { label: "Location", value: form.location },
            { label: "Status", value: <StatusBadge value={form.status} /> },
          ]}
        />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <TextField
              label="Company name"
              value={form.name}
              required
              onChange={(name) => setForm((current) => ({ ...current, name }))}
            />
          </div>
          <TextField
            label="Industry"
            value={form.industry}
            required
            onChange={(industry) =>
              setForm((current) => ({ ...current, industry }))
            }
          />
          <SelectField
            label="Status"
            value={form.status}
            options={companyStatuses.map((status) => ({
              value: status,
              label: status,
            }))}
            onChange={(status) =>
              setForm((current) => ({
                ...current,
                status: status as CompanyStatus,
              }))
            }
          />
          <TextField
            label="Email"
            type="email"
            value={form.email}
            required
            onChange={(email) => setForm((current) => ({ ...current, email }))}
          />
          <TextField
            label="Phone"
            value={form.phone}
            required
            onChange={(phone) => setForm((current) => ({ ...current, phone }))}
          />
          <div className="sm:col-span-2">
            <TextField
              label="Location"
              value={form.location}
              required
              onChange={(location) =>
                setForm((current) => ({ ...current, location }))
              }
            />
          </div>
        </div>
      )}
    </EntityDialog>
  )
}
