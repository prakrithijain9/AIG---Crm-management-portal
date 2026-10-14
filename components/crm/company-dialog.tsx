"use client"

import { DetailList, SelectField, TextField } from "@/components/crm/form-fields"
import { EntityDialog } from "@/components/crm/entity-dialog"
import { StatusBadge } from "@/components/crm/status-badge"
import { useDialogForm } from "@/components/crm/use-dialog-form"
import type { Company, CompanyInput, CompanyStatus } from "@/lib/types"
import { companyStatuses } from "@/lib/types"

type CompanyDialogProps = {
  open: boolean
  mode: "view" | "edit" | "create"
  company?: Company
  onOpenChange: (open: boolean) => void
  onSubmit: (input: CompanyInput) => Promise<void>
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
  const { form, setForm, saving, error, fieldErrors, submit } = useDialogForm<CompanyInput>(
    open,
    `${mode}:${company?.id ?? "new"}`,
    () =>
      company
        ? {
            name: company.name,
            industry: company.industry,
            email: company.email,
            phone: company.phone,
            location: company.location,
            status: company.status,
          }
        : emptyCompany,
    onSubmit
  )

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
      onSubmit={submit}
      saving={saving}
      error={error}
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
              error={fieldErrors.name}
              onChange={(name) => setForm((current) => ({ ...current, name }))}
            />
          </div>
          <TextField
            label="Industry"
            value={form.industry}
            required
            error={fieldErrors.industry}
            onChange={(industry) =>
              setForm((current) => ({ ...current, industry }))
            }
          />
          <SelectField
            label="Status"
            error={fieldErrors.status}
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
            error={fieldErrors.email}
            onChange={(email) => setForm((current) => ({ ...current, email }))}
          />
          <TextField
            label="Phone"
            value={form.phone}
            required
            error={fieldErrors.phone}
            onChange={(phone) => setForm((current) => ({ ...current, phone }))}
          />
          <div className="sm:col-span-2">
            <TextField
              label="Location"
              value={form.location}
              required
              error={fieldErrors.location}
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
