"use client"

import { Plus } from "lucide-react"
import { useMemo, useState } from "react"
import { ConfirmDialog } from "@/components/crm/confirm-dialog"
import { useCrm } from "@/components/crm/crm-provider"
import { DataTable, type Column } from "@/components/crm/data-table"
import { DealDialog } from "@/components/crm/deal-dialog"
import { RowActions } from "@/components/crm/row-actions"
import { SelectField } from "@/components/crm/form-fields"
import { StatusBadge } from "@/components/crm/status-badge"
import { Toolbar } from "@/components/crm/toolbar"
import { PageHeader } from "@/components/layout/page-header"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { companyNameById, formatCurrency, formatDate } from "@/lib/format"
import { dealStages, type Deal, type DealStage } from "@/lib/types"

type DialogState =
  | { open: false }
  | { open: true; mode: "create"; stage?: DealStage }
  | { open: true; mode: "view" | "edit"; deal: Deal }

export default function DealsPage() {
  const { companies, deals, addDeal, updateDeal, deleteDeal } = useCrm()
  const [search, setSearch] = useState("")
  const [stage, setStage] = useState("all")
  const [dialog, setDialog] = useState<DialogState>({ open: false })
  const [pendingDelete, setPendingDelete] = useState<Deal | null>(null)

  const filtered = useMemo(() => {
    const query = search.toLowerCase()
    return deals.filter((deal) => {
      const matchesQuery = [
        deal.title,
        companyNameById(companies, deal.companyId),
        deal.stage,
      ]
        .join(" ")
        .toLowerCase()
        .includes(query)
      const matchesStage = stage === "all" || deal.stage === stage
      return matchesQuery && matchesStage
    })
  }, [companies, deals, search, stage])

  const columns: Column<Deal>[] = [
    {
      header: "Deal",
      cell: (deal) => <span className="font-medium">{deal.title}</span>,
    },
    {
      header: "Company",
      cell: (deal) => companyNameById(companies, deal.companyId),
    },
    { header: "Value", cell: (deal) => formatCurrency(deal.value) },
    {
      header: "Stage",
      cell: (deal) => <StatusBadge value={deal.stage} />,
    },
    {
      header: "Expected close",
      cell: (deal) => formatDate(deal.expectedCloseDate),
    },
    {
      header: "",
      className: "w-12",
      cell: (deal) => (
        <RowActions
          onView={() => setDialog({ open: true, mode: "view", deal })}
          onEdit={() => setDialog({ open: true, mode: "edit", deal })}
          onDelete={() => setPendingDelete(deal)}
        />
      ),
    },
  ]

  return (
    <div>
      <PageHeader
        title="Deals"
        description="Track opportunities from first conversation through close."
        actions={
          <Button onClick={() => setDialog({ open: true, mode: "create" })}>
            <Plus data-icon="inline-start" />
            Add Deal
          </Button>
        }
      />

      <Tabs defaultValue="pipeline">
        <TabsList>
          <TabsTrigger value="pipeline">Pipeline</TabsTrigger>
          <TabsTrigger value="table">Table</TabsTrigger>
        </TabsList>

        <TabsContent value="pipeline" className="mt-4">
          <div className="max-w-sm">
            <Toolbar
              search={search}
              onSearchChange={setSearch}
              placeholder="Search deals"
            />
          </div>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {dealStages.map((item) => {
              const stageDeals = filtered.filter((deal) => deal.stage === item)
              const total = stageDeals.reduce((sum, deal) => sum + deal.value, 0)

              return (
                <Card key={item}>
                  <CardHeader className="border-b">
                    <div className="flex items-center justify-between gap-2">
                      <CardTitle className="text-sm">{item}</CardTitle>
                      <span className="text-xs text-muted-foreground">
                        {stageDeals.length} · {formatCurrency(total)}
                      </span>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    {stageDeals.length === 0 ? (
                      <p className="py-6 text-center text-sm text-muted-foreground">
                        No deals in this stage.
                      </p>
                    ) : (
                      stageDeals.map((deal) => (
                        <button
                          key={deal.id}
                          type="button"
                          className="w-full rounded-lg border bg-background p-3 text-left transition-colors hover:bg-muted/60"
                          onClick={() =>
                            setDialog({ open: true, mode: "view", deal })
                          }
                        >
                          <p className="font-medium">{deal.title}</p>
                          <p className="mt-1 text-sm text-muted-foreground">
                            {companyNameById(companies, deal.companyId)}
                          </p>
                          <div className="mt-3 flex items-center justify-between text-sm">
                            <span>{formatCurrency(deal.value)}</span>
                            <span className="text-muted-foreground">
                              {formatDate(deal.expectedCloseDate)}
                            </span>
                          </div>
                        </button>
                      ))
                    )}
                  </CardContent>
                </Card>
              )
            })}
          </div>
        </TabsContent>

        <TabsContent value="table" className="mt-4">
          <Card>
            <CardContent>
              <Toolbar
                search={search}
                onSearchChange={setSearch}
                placeholder="Search deals"
              >
                <SelectField
                  value={stage}
                  className="w-44"
                  options={[
                    { value: "all", label: "All stages" },
                    ...dealStages.map((item) => ({
                      value: item,
                      label: item,
                    })),
                  ]}
                  onChange={(value) => setStage(value)}
                />
              </Toolbar>
              <DataTable
                columns={columns}
                data={filtered}
                getRowId={(deal) => deal.id}
                emptyTitle="No deals found"
                emptyDescription="Try another search or add a new deal."
              />
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <DealDialog
        open={dialog.open}
        mode={dialog.open ? dialog.mode : "create"}
        companies={companies}
        deal={dialog.open && dialog.mode !== "create" ? dialog.deal : undefined}
        onOpenChange={(open) => {
          if (!open) setDialog({ open: false })
        }}
        onSubmit={(input) => {
          if (!dialog.open) return
          if (dialog.mode === "create") addDeal(input)
          if (dialog.mode === "edit") updateDeal(dialog.deal.id, input)
          setDialog({ open: false })
        }}
      />

      <ConfirmDialog
        open={Boolean(pendingDelete)}
        title="Delete deal?"
        description="This opportunity will be removed from the pipeline."
        onOpenChange={(open) => {
          if (!open) setPendingDelete(null)
        }}
        onConfirm={() => {
          if (pendingDelete) deleteDeal(pendingDelete.id)
          setPendingDelete(null)
        }}
      />
    </div>
  )
}
