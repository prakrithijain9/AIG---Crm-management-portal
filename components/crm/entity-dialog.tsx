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
  saving?: boolean
  error?: string | null
  children: ReactNode
}

export function EntityDialog({
  open,
  title,
  description,
  mode,
  onOpenChange,
  onSubmit,
  saving = false,
  error,
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
          {error ? (
            <p
              role="alert"
              className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive"
            >
              {error}
            </p>
          ) : null}
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              disabled={saving}
              onClick={() => onOpenChange(false)}
            >
              {mode === "view" ? "Close" : "Cancel"}
            </Button>
            {mode !== "view" ? (
              <Button type="submit" disabled={saving}>
                {saving ? "Saving…" : mode === "create" ? "Save" : "Save changes"}
              </Button>
            ) : null}
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
