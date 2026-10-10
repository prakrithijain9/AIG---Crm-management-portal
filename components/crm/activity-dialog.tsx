"use client"

import { useEffect, useMemo, useState } from "react"
import { DetailList, SelectField, TextField } from "@/components/crm/form-fields"
import { EntityDialog } from "@/components/crm/entity-dialog"
import { StatusBadge } from "@/components/crm/status-badge"
import {
  companyNameById,
  contactNameById,
  formatDate,
} from "@/lib/format"
import type {
  Activity,
  ActivityInput,
  ActivityStatus,
  ActivityType,
  Company,
  Contact,
} from "@/lib/types"
import { activityStatuses, activityTypes } from "@/lib/types"

type ActivityDialogProps = {
  open: boolean
  mode: "view" | "edit" | "create"
  activity?: Activity
  companies: Company[]
  contacts: Contact[]
  onOpenChange: (open: boolean) => void
  onSubmit: (input: ActivityInput) => void
}

function emptyActivity(companies: Company[]): ActivityInput {
  return {
    type: "Follow-up",
    subject: "",
    companyId: companies[0]?.id ?? "",
    contactId: null,
    dueDate: "",
    status: "Pending",
  }
}

export function ActivityDialog({
  open,
  mode,
  activity,
  companies,
  contacts,
  onOpenChange,
  onSubmit,
}: ActivityDialogProps) {
  const [form, setForm] = useState<ActivityInput>(emptyActivity(companies))

  useEffect(() => {
    if (!open) return
    setForm(
      activity
        ? {
            type: activity.type,
            subject: activity.subject,
            companyId: activity.companyId,
            contactId: activity.contactId,
            dueDate: activity.dueDate,
            status: activity.status,
          }
        : emptyActivity(companies)
    )
  }, [activity, companies, open])

  const companyContacts = useMemo(
    () => contacts.filter((contact) => contact.companyId === form.companyId),
    [contacts, form.companyId]
  )

  return (
    <EntityDialog
      open={open}
      mode={mode}
      title={
        mode === "create"
          ? "Add activity"
          : mode === "edit"
            ? "Edit activity"
            : "Activity details"
      }
      description={
        mode === "view"
          ? "Review this follow-up."
          : "Log a call, meeting, or task against an account."
      }
      onOpenChange={onOpenChange}
      onSubmit={() => onSubmit(form)}
    >
      {mode === "view" ? (
        <DetailList
          items={[
            { label: "Type", value: form.type },
            { label: "Subject", value: form.subject },
            {
              label: "Company",
              value: companyNameById(companies, form.companyId),
            },
            {
              label: "Contact",
              value: contactNameById(contacts, form.contactId),
            },
            {
              label: "Due date",
              value: form.dueDate ? formatDate(form.dueDate) : "—",
            },
            { label: "Status", value: <StatusBadge value={form.status} /> },
          ]}
        />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          <SelectField
            label="Type"
            value={form.type}
            options={activityTypes.map((type) => ({
              value: type,
              label: type,
            }))}
            onChange={(type) =>
              setForm((current) => ({
                ...current,
                type: type as ActivityType,
              }))
            }
          />
          <SelectField
            label="Status"
            value={form.status}
            options={activityStatuses.map((status) => ({
              value: status,
              label: status,
            }))}
            onChange={(status) =>
              setForm((current) => ({
                ...current,
                status: status as ActivityStatus,
              }))
            }
          />
          <div className="sm:col-span-2">
            <TextField
              label="Subject"
              value={form.subject}
              required
              onChange={(subject) =>
                setForm((current) => ({ ...current, subject }))
              }
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
              setForm((current) => ({
                ...current,
                companyId,
                contactId: null,
              }))
            }
          />
          <SelectField
            label="Contact"
            value={form.contactId ?? "none"}
            options={[
              { value: "none", label: "No specific contact" },
              ...companyContacts.map((contact) => ({
                value: contact.id,
                label: contact.name,
              })),
            ]}
            onChange={(contactId) =>
              setForm((current) => ({
                ...current,
                contactId: contactId === "none" ? null : contactId,
              }))
            }
          />
          <div className="sm:col-span-2">
            <TextField
              label="Due date"
              type="date"
              value={form.dueDate}
              required
              onChange={(dueDate) =>
                setForm((current) => ({ ...current, dueDate }))
              }
            />
          </div>
        </div>
      )}
    </EntityDialog>
  )
}
