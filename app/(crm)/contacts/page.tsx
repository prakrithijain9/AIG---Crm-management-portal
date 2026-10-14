"use client"

import { Plus } from "lucide-react"
import { useMemo, useState } from "react"
import { ConfirmDialog } from "@/components/crm/confirm-dialog"
import { ContactDialog } from "@/components/crm/contact-dialog"
import { useCrm } from "@/components/crm/crm-provider"
import { DataTable, type Column } from "@/components/crm/data-table"
import { RowActions } from "@/components/crm/row-actions"
import { Toolbar } from "@/components/crm/toolbar"
import { PageHeader } from "@/components/layout/page-header"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { companyNameById } from "@/lib/format"
import type { Contact } from "@/lib/types"

type DialogState =
  | { open: false }
  | { open: true; mode: "create" }
  | { open: true; mode: "view" | "edit"; contact: Contact }

export default function ContactsPage() {
  const { companies, contacts, addContact, updateContact, deleteContact } =
    useCrm()
  const [search, setSearch] = useState("")
  const [dialog, setDialog] = useState<DialogState>({ open: false })
  const [pendingDelete, setPendingDelete] = useState<Contact | null>(null)

  const filtered = useMemo(() => {
    const query = search.toLowerCase()
    return contacts.filter((contact) =>
      [
        contact.name,
        contact.email,
        contact.phone,
        contact.jobTitle,
        companyNameById(companies, contact.companyId),
      ]
        .join(" ")
        .toLowerCase()
        .includes(query)
    )
  }, [companies, contacts, search])

  const columns: Column<Contact>[] = [
    {
      header: "Name",
      cell: (contact) => <span className="font-medium">{contact.name}</span>,
    },
    {
      header: "Company",
      cell: (contact) => companyNameById(companies, contact.companyId),
    },
    { header: "Job title", cell: (contact) => contact.jobTitle },
    { header: "Email", cell: (contact) => contact.email },
    { header: "Phone", cell: (contact) => contact.phone },
    {
      header: "",
      className: "w-12",
      cell: (contact) => (
        <RowActions
          onView={() => setDialog({ open: true, mode: "view", contact })}
          onEdit={() => setDialog({ open: true, mode: "edit", contact })}
          onDelete={() => setPendingDelete(contact)}
        />
      ),
    },
  ]

  return (
    <div>
      <PageHeader
        title="Contacts"
        description="People associated with your accounts."
        actions={
          <Button onClick={() => setDialog({ open: true, mode: "create" })}>
            <Plus data-icon="inline-start" />
            Add Contact
          </Button>
        }
      />

      <Card>
        <CardContent>
          <Toolbar
            search={search}
            onSearchChange={setSearch}
            placeholder="Search contacts"
          />
          <DataTable
            columns={columns}
            data={filtered}
            getRowId={(contact) => contact.id}
            emptyTitle="No contacts found"
            emptyDescription="Try another search or add a new contact."
          />
        </CardContent>
      </Card>

      <ContactDialog
        open={dialog.open}
        mode={dialog.open ? dialog.mode : "create"}
        companies={companies}
        contact={dialog.open && dialog.mode !== "create" ? dialog.contact : undefined}
        onOpenChange={(open) => {
          if (!open) setDialog({ open: false })
        }}
        onSubmit={async (input) => {
          if (!dialog.open) return
          // Throws on API errors; the dialog then stays open and shows them.
          if (dialog.mode === "create") await addContact(input)
          if (dialog.mode === "edit") await updateContact(dialog.contact.id, input)
          setDialog({ open: false })
        }}
      />

      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title="Delete contact?"
        description="This contact will be removed from the workspace."
        onOpenChange={(open) => {
          if (!open) setPendingDelete(null)
        }}
        onConfirm={async () => {
          if (pendingDelete) await deleteContact(pendingDelete.id)
        }}
      />
    </div>
  )
}
