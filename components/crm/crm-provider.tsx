"use client"

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react"
import { api, errorMessage } from "@/lib/api"
import type {
  Activity,
  ActivityInput,
  Company,
  CompanyInput,
  Contact,
  ContactInput,
  Deal,
  DealInput,
} from "@/lib/types"

type LoadState =
  | { status: "loading" }
  | { status: "ready" }
  | { status: "error"; message: string }

type CrmContextValue = {
  companies: Company[]
  contacts: Contact[]
  deals: Deal[]
  activities: Activity[]
  loadState: LoadState
  reload: () => void
  // Mutations resolve after the server confirms, and throw ApiError on failure
  // so dialogs can stay open and show the problem.
  addCompany: (input: CompanyInput) => Promise<void>
  updateCompany: (id: string, input: CompanyInput) => Promise<void>
  deleteCompany: (id: string) => Promise<void>
  addContact: (input: ContactInput) => Promise<void>
  updateContact: (id: string, input: ContactInput) => Promise<void>
  deleteContact: (id: string) => Promise<void>
  addDeal: (input: DealInput) => Promise<void>
  updateDeal: (id: string, input: DealInput) => Promise<void>
  deleteDeal: (id: string) => Promise<void>
  addActivity: (input: ActivityInput) => Promise<void>
  updateActivity: (id: string, input: ActivityInput) => Promise<void>
  deleteActivity: (id: string) => Promise<void>
}

const CrmContext = createContext<CrmContextValue | null>(null)

function replaceById<T extends { id: string }>(items: T[], updated: T) {
  return items.map((item) => (item.id === updated.id ? updated : item))
}

export function CrmProvider({ children }: { children: ReactNode }) {
  const [companies, setCompanies] = useState<Company[]>([])
  const [contacts, setContacts] = useState<Contact[]>([])
  const [deals, setDeals] = useState<Deal[]>([])
  const [activities, setActivities] = useState<Activity[]>([])
  const [loadState, setLoadState] = useState<LoadState>({ status: "loading" })
  const [reloadCount, setReloadCount] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    Promise.all([
      api.companies.listAll(controller.signal),
      api.contacts.listAll(controller.signal),
      api.deals.listAll(controller.signal),
      api.activities.listAll(controller.signal),
    ])
      .then(([companies, contacts, deals, activities]) => {
        setCompanies(companies)
        setContacts(contacts)
        setDeals(deals)
        setActivities(activities)
        setLoadState({ status: "ready" })
      })
      .catch((error) => {
        if (controller.signal.aborted) return
        setLoadState({ status: "error", message: errorMessage(error) })
      })
    return () => controller.abort()
  }, [reloadCount])

  const reload = useCallback(() => {
    setLoadState({ status: "loading" })
    setReloadCount((count) => count + 1)
  }, [])

  const value = useMemo<CrmContextValue>(
    () => ({
      companies,
      contacts,
      deals,
      activities,
      loadState,
      reload,
      addCompany: async (input) => {
        const created = await api.companies.create(input)
        setCompanies((current) => [created, ...current])
      },
      updateCompany: async (id, input) => {
        const updated = await api.companies.update(id, input)
        setCompanies((current) => replaceById(current, updated))
      },
      deleteCompany: async (id) => {
        await api.companies.remove(id)
        // Mirror the database's ON DELETE CASCADE locally.
        setCompanies((current) => current.filter((item) => item.id !== id))
        setContacts((current) => current.filter((item) => item.companyId !== id))
        setDeals((current) => current.filter((item) => item.companyId !== id))
        setActivities((current) => current.filter((item) => item.companyId !== id))
      },
      addContact: async (input) => {
        const created = await api.contacts.create(input)
        setContacts((current) => [created, ...current])
      },
      updateContact: async (id, input) => {
        const updated = await api.contacts.update(id, input)
        setContacts((current) => replaceById(current, updated))
      },
      deleteContact: async (id) => {
        await api.contacts.remove(id)
        // Mirror ON DELETE SET NULL: activities stay, without the contact.
        setContacts((current) => current.filter((item) => item.id !== id))
        setActivities((current) =>
          current.map((item) =>
            item.contactId === id ? { ...item, contactId: null } : item
          )
        )
      },
      addDeal: async (input) => {
        const created = await api.deals.create(input)
        setDeals((current) => [created, ...current])
      },
      updateDeal: async (id, input) => {
        const updated = await api.deals.update(id, input)
        setDeals((current) => replaceById(current, updated))
      },
      deleteDeal: async (id) => {
        await api.deals.remove(id)
        setDeals((current) => current.filter((item) => item.id !== id))
      },
      addActivity: async (input) => {
        const created = await api.activities.create(input)
        setActivities((current) => [created, ...current])
      },
      updateActivity: async (id, input) => {
        const updated = await api.activities.update(id, input)
        setActivities((current) => replaceById(current, updated))
      },
      deleteActivity: async (id) => {
        await api.activities.remove(id)
        setActivities((current) => current.filter((item) => item.id !== id))
      },
    }),
    [activities, companies, contacts, deals, loadState, reload]
  )

  return <CrmContext.Provider value={value}>{children}</CrmContext.Provider>
}

export function useCrm() {
  const context = useContext(CrmContext)
  if (!context) {
    throw new Error("useCrm must be used within CrmProvider")
  }
  return context
}
