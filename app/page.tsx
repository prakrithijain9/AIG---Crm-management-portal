"use client"

import { Building2, CalendarCheck2, Handshake, Users } from "lucide-react"
import { useMemo } from "react"
import { useCrm } from "@/components/crm/crm-provider"
import { DataTable, type Column } from "@/components/crm/data-table"
import { PageHeader } from "@/components/layout/page-header"
import { StatCard } from "@/components/crm/stat-card"
import { StatusBadge } from "@/components/crm/status-badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  companyNameById,
  contactNameById,
  formatCurrency,
  formatDate,
} from "@/lib/format"
import { dealStages, type Activity, type Deal } from "@/lib/types"

export default function DashboardPage() {
  const { companies, contacts, deals, activities } = useCrm()

  const activeDeals = deals.filter(
    (deal) => deal.stage !== "Won" && deal.stage !== "Lost"
  )
  const pendingActivities = activities.filter(
    (activity) => activity.status === "Pending"
  )

  const stageSummary = useMemo(() => {
    const max = Math.max(
      ...dealStages.map(
        (stage) => deals.filter((deal) => deal.stage === stage).length
      ),
      1
    )

    return dealStages.map((stage) => {
      const count = deals.filter((deal) => deal.stage === stage).length
      const value = deals
        .filter((deal) => deal.stage === stage)
        .reduce((sum, deal) => sum + deal.value, 0)

      return { stage, count, value, width: `${(count / max) * 100}%` }
    })
  }, [deals])

  const recentDeals = [...deals]
    .sort(
      (a, b) =>
        new Date(b.expectedCloseDate).getTime() -
        new Date(a.expectedCloseDate).getTime()
    )
    .slice(0, 5)

  const recentActivities = [...activities]
    .sort((a, b) => new Date(b.dueDate).getTime() - new Date(a.dueDate).getTime())
    .slice(0, 6)

  const dealColumns: Column<Deal>[] = [
    {
      header: "Deal",
      cell: (deal) => <span className="font-medium">{deal.title}</span>,
    },
    {
      header: "Company",
      cell: (deal) => companyNameById(companies, deal.companyId),
    },
    {
      header: "Value",
      cell: (deal) => formatCurrency(deal.value),
    },
    {
      header: "Stage",
      cell: (deal) => <StatusBadge value={deal.stage} />,
    },
    {
      header: "Close date",
      cell: (deal) => formatDate(deal.expectedCloseDate),
    },
  ]

  const activityColumns: Column<Activity>[] = [
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
      header: "Related to",
      cell: (activity) => (
        <div>
          <p>{companyNameById(companies, activity.companyId)}</p>
          <p className="text-xs text-muted-foreground">
            {contactNameById(contacts, activity.contactId)}
          </p>
        </div>
      ),
    },
    {
      header: "Due",
      cell: (activity) => formatDate(activity.dueDate),
    },
    {
      header: "Status",
      cell: (activity) => <StatusBadge value={activity.status} />,
    },
  ]

  return (
    <div>
      <PageHeader
        title="Dashboard"
        description="A snapshot of accounts, pipeline, and follow-ups."
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Total Companies"
          value={companies.length}
          icon={Building2}
        />
        <StatCard
          label="Total Contacts"
          value={contacts.length}
          icon={Users}
        />
        <StatCard
          label="Active Deals"
          value={activeDeals.length}
          hint={formatCurrency(
            activeDeals.reduce((sum, deal) => sum + deal.value, 0)
          )}
          icon={Handshake}
        />
        <StatCard
          label="Pending Activities"
          value={pendingActivities.length}
          icon={CalendarCheck2}
        />
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader className="border-b">
            <CardTitle>Recent deals</CardTitle>
          </CardHeader>
          <CardContent className="px-0">
            <DataTable
              columns={dealColumns}
              data={recentDeals}
              getRowId={(deal) => deal.id}
              emptyTitle="No deals yet"
              emptyDescription="New opportunities will appear here."
            />
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="border-b">
            <CardTitle>Deals by stage</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {stageSummary.map((item) => (
              <div key={item.stage}>
                <div className="mb-1 flex items-center justify-between text-sm">
                  <span>{item.stage}</span>
                  <span className="text-muted-foreground">
                    {item.count} · {formatCurrency(item.value)}
                  </span>
                </div>
                <div className="h-2 rounded-full bg-slate-100">
                  <div
                    className="h-2 rounded-full bg-slate-900"
                    style={{ width: item.width }}
                  />
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      <Card className="mt-6">
        <CardHeader className="border-b">
          <CardTitle>Recent activities</CardTitle>
        </CardHeader>
        <CardContent className="px-0">
          <DataTable
            columns={activityColumns}
            data={recentActivities}
            getRowId={(activity) => activity.id}
            emptyTitle="No activities yet"
            emptyDescription="Follow-ups and meetings will appear here."
          />
        </CardContent>
      </Card>
    </div>
  )
}
