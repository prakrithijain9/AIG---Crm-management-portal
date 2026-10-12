"use client"

import { Plus } from "lucide-react"
import { useMemo, useState } from "react"
import { ActivityDialog } from "@/components/crm/activity-dialog"
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
import {
  companyNameById,
  contactNameById,
  formatDate,
} from "@/lib/format"
import type { Activity, ActivityStatus } from "@/lib/types"
import { activityStatuses } from "@/lib/types"

type DialogState =
  | { open: false }
  | { open: true; mode: "create" }
  | { open: true; mode: "view" | "edit"; activity: Activity }

export default function ActivitiesPage() {
  const {
    companies,
    contacts,
    activities,
    addActivity,
    updateActivity,
    deleteActivity,
  } = useCrm()
  const [search, setSearch] = useState("")
  const [status, setStatus] = useState("all")
  const [dialog, setDialog] = useState<DialogState>({ open: false })
  const [pendingDelete, setPendingDelete] = useState<Activity | null>(null)

  const filtered = useMemo(() => {
    const query = search.toLowerCase()
    return activities
      .filter((activity) => {
        const matchesQuery = [
          activity.subject,
          activity.type,
          companyNameById(companies, activity.companyId),
          contactNameById(contacts, activity.contactId),
        ]
          .join(" ")
          .toLowerCase()
          .includes(query)
        const matchesStatus = status === "all" || activity.status === status
        return matchesQuery && matchesStatus
      })
      .sort(
        (a, b) => new Date(a.dueDate).getTime() - new Date(b.dueDate).getTime()
      )
  }, [activities, companies, contacts, search, status])

  const columns: Column<Activity>[] = [
    {
      header: "Activity",
      cell: (activity) => (
        <div>
          <p className="font-medium">{activity.subject}</p>
          <p className="text-xs text-muted-foreground">{activity.type}</p>
        </div>
      ),
    },
    {
      header: "Company",
      cell: (activity) => companyNameById(companies, activity.companyId),
    },
    {
      header: "Contact",
      cell: (activity) => contactNameById(contacts, activity.contactId),
    },
    {
      header: "Due date",
      cell: (activity) => formatDate(activity.dueDate),
    },
    {
      header: "Status",
      cell: (activity) => <StatusBadge value={activity.status} />,
    },
    {
      header: "",
      className: "w-12",
      cell: (activity) => (
        <RowActions
          onView={() => setDialog({ open: true, mode: "view", activity })}
          onEdit={() => setDialog({ open: true, mode: "edit", activity })}
          onDelete={() => setPendingDelete(activity)}
        />
      ),
    },
  ]

  return (
    <div>
      <PageHeader
        title="Activities"
        description="Calls, meetings, and follow-ups across your accounts."
        actions={
          <Button onClick={() => setDialog({ open: true, mode: "create" })}>
            <Plus data-icon="inline-start" />
            Add Activity
          </Button>
        }
      />

      <Card>
        <CardContent>
          <Toolbar
            search={search}
            onSearchChange={setSearch}
            placeholder="Search activities"
          >
            <SelectField
              value={status}
              className="w-44"
              options={[
                { value: "all", label: "All statuses" },
                ...activityStatuses.map((item) => ({
                  value: item,
                  label: item,
                })),
              ]}
              onChange={(value) => setStatus(value as ActivityStatus | "all")}
            />
          </Toolbar>
          <DataTable
            columns={columns}
            data={filtered}
            getRowId={(activity) => activity.id}
            emptyTitle="No activities found"
            emptyDescription="Try another search or add a new activity."
          />
        </CardContent>
      </Card>

      <ActivityDialog
        open={dialog.open}
        mode={dialog.open ? dialog.mode : "create"}
        companies={companies}
        contacts={contacts}
        activity={
          dialog.open && dialog.mode !== "create" ? dialog.activity : undefined
        }
        onOpenChange={(open) => {
          if (!open) setDialog({ open: false })
        }}
        onSubmit={async (input) => {
          if (!dialog.open) return
          // Throws on API errors; the dialog then stays open and shows them.
          if (dialog.mode === "create") await addActivity(input)
          if (dialog.mode === "edit") await updateActivity(dialog.activity.id, input)
          setDialog({ open: false })
        }}
      />

      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title="Delete activity?"
        description="This follow-up will be removed from the workspace."
        onOpenChange={(open) => {
          if (!open) setPendingDelete(null)
        }}
        onConfirm={async () => {
          if (pendingDelete) await deleteActivity(pendingDelete.id)
        }}
      />
    </div>
  )
}
