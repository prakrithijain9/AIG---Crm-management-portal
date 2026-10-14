"use client"

import { Plus } from "lucide-react"
import { useMemo, useState } from "react"
import { CompanyDialog } from "@/components/crm/company-dialog"
import { ConfirmDialog } from "@/components/crm/confirm-dialog"
import { useCrm } from "@/components/crm/crm-provider"
import { DataTable, type Column } from "@/components/crm/data-table"
import { RowActions } from "@/components/crm/row-actions"
import { SelectField } from "@/components/crm/form-fields"
import { StatusBadge } from "@/components/crm/status-badge"
import { Toolbar } from "@/components/crm/toolbar"
import { PageHeader } from "@/components/layout/page-header"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import type { Company, CompanyStatus } from "@/lib/types"
import { companyStatuses } from "@/lib/types"

type DialogState =
  | { open: false }
  | { open: true; mode: "create" }
  | { open: true; mode: "view" | "edit"; company: Company }

export default function CompaniesPage() {
  const { companies, addCompany, updateCompany, deleteCompany } = useCrm()
  const [search, setSearch] = useState("")
  const [status, setStatus] = useState("all")
  const [dialog, setDialog] = useState<DialogState>({ open: false })
  const [pendingDelete, setPendingDelete] = useState<Company | null>(null)

  const filtered = useMemo(() => {
    const query = search.toLowerCase()
    return companies.filter((company) => {
      const matchesQuery = [
        company.name,
        company.industry,
        company.email,
        company.phone,
        company.location,
      ]
        .join(" ")
        .toLowerCase()
        .includes(query)
      const matchesStatus = status === "all" || company.status === status
      return matchesQuery && matchesStatus
    })
  }, [companies, search, status])

  const columns: Column<Company>[] = [
    {
      header: "Company",
      cell: (company) => <span className="font-medium">{company.name}</span>,
    },
    { header: "Industry", cell: (company) => company.industry },
    { header: "Email", cell: (company) => company.email },
    { header: "Phone", cell: (company) => company.phone },
    { header: "Location", cell: (company) => company.location },
    {
      header: "Status",
      cell: (company) => <StatusBadge value={company.status} />,
    },
    {
      header: "",
      className: "w-12",
      cell: (company) => (
        <RowActions
          onView={() => setDialog({ open: true, mode: "view", company })}
          onEdit={() => setDialog({ open: true, mode: "edit", company })}
          onDelete={() => setPendingDelete(company)}
        />
      ),
    },
  ]

  return (
    <div>
      <PageHeader
        title="Companies"
        description="Manage accounts, industries, and relationship status."
        actions={
          <Button onClick={() => setDialog({ open: true, mode: "create" })}>
            <Plus data-icon="inline-start" />
            Add Company
          </Button>
        }
      />

      <Card>
        <CardContent>
          <Toolbar
            search={search}
            onSearchChange={setSearch}
            placeholder="Search companies"
          >
            <SelectField
              value={status}
              className="w-44"
              options={[
                { value: "all", label: "All statuses" },
                ...companyStatuses.map((item) => ({
                  value: item,
                  label: item,
                })),
              ]}
              onChange={(value) => setStatus(value as CompanyStatus | "all")}
            />
          </Toolbar>
          <DataTable
            columns={columns}
            data={filtered}
            getRowId={(company) => company.id}
            emptyTitle="No companies found"
            emptyDescription="Try another search or add a new company."
          />
        </CardContent>
      </Card>

      <CompanyDialog
        open={dialog.open}
        mode={dialog.open ? dialog.mode : "create"}
        company={dialog.open && dialog.mode !== "create" ? dialog.company : undefined}
        onOpenChange={(open) => {
          if (!open) setDialog({ open: false })
        }}
        onSubmit={async (input) => {
          if (!dialog.open) return
          // Throws on API errors; the dialog then stays open and shows them.
          if (dialog.mode === "create") await addCompany(input)
          if (dialog.mode === "edit") await updateCompany(dialog.company.id, input)
          setDialog({ open: false })
        }}
      />

      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title="Delete company?"
        description="This also removes related contacts, deals, and activities from this workspace."
        onOpenChange={(open) => {
          if (!open) setPendingDelete(null)
        }}
        onConfirm={async () => {
          if (pendingDelete) await deleteCompany(pendingDelete.id)
        }}
      />
    </div>
  )
}
