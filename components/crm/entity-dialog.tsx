"use client"

import type { FormEvent, ReactNode } from "react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

type EntityDialogProps = {
  open: boolean
  title: string
  description: string
  mode: "view" | "edit" | "create"
  onOpenChange: (open: boolean) => void
  onSubmit?: () => void
  children: ReactNode
}

export function EntityDialog({
  open,
  title,
  description,
  mode,
  onOpenChange,
  onSubmit,
  children,
}: EntityDialogProps) {
  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    onSubmit?.()
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-lg">
        <form onSubmit={handleSubmit} className="grid gap-4">
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
            <DialogDescription>{description}</DialogDescription>
          </DialogHeader>
          {children}
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
            >
              {mode === "view" ? "Close" : "Cancel"}
            </Button>
            {mode !== "view" ? (
              <Button type="submit">
                {mode === "create" ? "Save" : "Save changes"}
              </Button>
            ) : null}
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
