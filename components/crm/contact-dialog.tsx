"use client"

import { useEffect, useState } from "react"
import { DetailList, SelectField, TextField } from "@/components/crm/form-fields"
import { EntityDialog } from "@/components/crm/entity-dialog"
import { companyNameById } from "@/lib/format"
import type { Company, Contact, ContactInput } from "@/lib/types"

type ContactDialogProps = {
  open: boolean
  mode: "view" | "edit" | "create"
  contact?: Contact
  companies: Company[]
  onOpenChange: (open: boolean) => void
  onSubmit: (input: ContactInput) => void
}

function emptyContact(companies: Company[]): ContactInput {
  return {
    name: "",
    companyId: companies[0]?.id ?? "",
    email: "",
    phone: "",
    jobTitle: "",
  }
}

export function ContactDialog({
  open,
  mode,
  contact,
  companies,
  onOpenChange,
  onSubmit,
}: ContactDialogProps) {
  const [form, setForm] = useState<ContactInput>(emptyContact(companies))

  useEffect(() => {
    if (!open) return
    setForm(
      contact
        ? {
            name: contact.name,
            companyId: contact.companyId,
            email: contact.email,
            phone: contact.phone,
            jobTitle: contact.jobTitle,
          }
        : emptyContact(companies)
    )
  }, [companies, contact, open])

  return (
    <EntityDialog
      open={open}
      mode={mode}
      title={
        mode === "create"
          ? "Add contact"
          : mode === "edit"
            ? "Edit contact"
            : "Contact details"
      }
      description={
        mode === "view"
          ? "Review this contact record."
          : "Link a person to an account and keep their details current."
      }
      onOpenChange={onOpenChange}
      onSubmit={() => onSubmit(form)}
    >
      {mode === "view" ? (
        <DetailList
          items={[
            { label: "Name", value: form.name },
            {
              label: "Company",
              value: companyNameById(companies, form.companyId),
            },
            { label: "Job title", value: form.jobTitle },
            { label: "Email", value: form.email },
            { label: "Phone", value: form.phone },
          ]}
        />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <TextField
              label="Full name"
              value={form.name}
              required
              onChange={(name) => setForm((current) => ({ ...current, name }))}
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
          <TextField
            label="Job title"
            value={form.jobTitle}
            required
            onChange={(jobTitle) =>
              setForm((current) => ({ ...current, jobTitle }))
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
        </div>
      )}
    </EntityDialog>
  )
}
