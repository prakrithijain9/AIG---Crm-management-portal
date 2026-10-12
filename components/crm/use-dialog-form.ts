"use client"

import { useState, type Dispatch, type SetStateAction } from "react"
import { ApiError, errorMessage } from "@/lib/api"

type DialogForm<T> = {
  form: T
  setForm: Dispatch<SetStateAction<T>>
  saving: boolean
  /** General message for the whole form (e.g. a 409 conflict or a network error). */
  error: string | null
  /** camelCase field name -> message, from a 422 response. */
  fieldErrors: Record<string, string>
  submit: () => Promise<void>
}

/**
 * Form state for a create/edit dialog that saves to the API.
 *
 * Whenever the dialog opens (or switches to a different record), the form is reset from
 * `initial()` and old errors are cleared. This is done while rendering, by comparing with
 * the previous key, rather than in an effect, so there is no extra render with stale values.
 */
export function useDialogForm<T>(
  open: boolean,
  resetKey: string,
  initial: () => T,
  onSubmit: (input: T) => Promise<void>,
  /** Optional checks before calling the API; return camelCase field -> message. */
  validate?: (input: T) => Record<string, string>
): DialogForm<T> {
  const [form, setForm] = useState<T>(initial)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})

  const key = open ? resetKey : null
  const [lastKey, setLastKey] = useState(key)
  if (key !== lastKey) {
    setLastKey(key)
    if (key !== null) {
      setForm(initial())
      setError(null)
      setFieldErrors({})
    }
  }

  async function submit() {
    if (saving) return
    const problems = validate?.(form) ?? {}
    if (Object.keys(problems).length > 0) {
      setError("Please correct the highlighted fields.")
      setFieldErrors(problems)
      return
    }
    setSaving(true)
    setError(null)
    setFieldErrors({})
    try {
      await onSubmit(form)
    } catch (caught) {
      setError(errorMessage(caught))
      if (caught instanceof ApiError) setFieldErrors(caught.fieldErrors)
    } finally {
      setSaving(false)
    }
  }

  return { form, setForm, saving, error, fieldErrors, submit }
}

/** Shared check for dialogs whose record must belong to a company. */
export function requireCompany(input: { companyId: string }): Record<string, string> {
  return input.companyId ? {} : { companyId: "Add a company first, then select it here." }
}
