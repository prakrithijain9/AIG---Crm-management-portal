"use client"

import { useSearchParams } from "next/navigation"
import { useCallback, useEffect, useRef } from "react"
import { useCrm } from "@/components/crm/crm-provider"
import { withParams } from "@/lib/url-params"

/**
 * The page's URL query as the source of truth for its filters, so links (including the
 * assistant's buttons) open a page already filtered, and a filter change is shareable.
 *
 * `setParams` uses history.replaceState: Next.js syncs it into useSearchParams without a
 * navigation, so typing in the search box does not re-fetch or add history entries.
 */
export function usePageParams() {
  const searchParams = useSearchParams()
  const setParams = useCallback((updates: Record<string, string | null>) => {
    const next = withParams(window.location.search, updates)
    window.history.replaceState(null, "", `${window.location.pathname}${next}`)
  }, [])
  return { searchParams, setParams }
}

/**
 * Opens the record named by ?open=<id> once the CRM data has loaded, then drops the param so
 * closing the dialog does not reopen it. An unknown id is ignored (and dropped) without error.
 */
export function useOpenFromUrl<T extends { id: string }>(items: T[], onOpen: (item: T) => void) {
  const { loadState } = useCrm()
  const { searchParams, setParams } = usePageParams()
  const id = searchParams.get("open")
  const handled = useRef<string | null>(null)

  useEffect(() => {
    if (!id || loadState.status !== "ready" || handled.current === id) return
    handled.current = id
    const item = items.find((candidate) => candidate.id === id)
    if (item) onOpen(item)
    setParams({ open: null })
  }, [id, items, loadState.status, onOpen, setParams])

  useEffect(() => {
    if (!id) handled.current = null
  }, [id])
}
