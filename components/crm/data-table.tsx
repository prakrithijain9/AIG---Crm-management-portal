import type { ReactNode } from "react"
import { EmptyState } from "@/components/crm/empty-state"
import { cn } from "@/lib/utils"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

export type Column<T> = {
  header: string
  cell: (row: T) => ReactNode
  className?: string
}

const edgePadding = "px-3 first:pl-4 last:pr-4"

type DataTableProps<T> = {
  columns: Column<T>[]
  data: T[]
  getRowId: (row: T) => string
  emptyTitle: string
  emptyDescription: string
}

export function DataTable<T>({
  columns,
  data,
  getRowId,
  emptyTitle,
  emptyDescription,
}: DataTableProps<T>) {
  return (
    <Table>
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          {columns.map((column) => (
            <TableHead
              key={column.header}
              className={cn(edgePadding, column.className)}
            >
              {column.header}
            </TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {data.length === 0 ? (
          <TableRow className="hover:bg-transparent">
            <TableCell colSpan={columns.length}>
              <EmptyState title={emptyTitle} description={emptyDescription} />
            </TableCell>
          </TableRow>
        ) : (
          data.map((row) => (
            <TableRow key={getRowId(row)}>
              {columns.map((column) => (
                <TableCell
                  key={column.header}
                  className={cn(edgePadding, column.className)}
                >
                  {column.cell(row)}
                </TableCell>
              ))}
            </TableRow>
          ))
        )}
      </TableBody>
    </Table>
  )
}
