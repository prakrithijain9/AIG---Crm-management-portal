"use client"

import {
  createContext,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react"
import { createId } from "@/lib/format"
import {
  activities as seedActivities,
  companies as seedCompanies,
  contacts as seedContacts,
  deals as seedDeals,
} from "@/lib/mock-data"
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

type CrmContextValue = {
  companies: Company[]
  contacts: Contact[]
  deals: Deal[]
  activities: Activity[]
  addCompany: (input: CompanyInput) => void
  updateCompany: (id: string, input: CompanyInput) => void
  deleteCompany: (id: string) => void
  addContact: (input: ContactInput) => void
  updateContact: (id: string, input: ContactInput) => void
  deleteContact: (id: string) => void
  addDeal: (input: DealInput) => void
  updateDeal: (id: string, input: DealInput) => void
  deleteDeal: (id: string) => void
  addActivity: (input: ActivityInput) => void
  updateActivity: (id: string, input: ActivityInput) => void
  deleteActivity: (id: string) => void
}

const CrmContext = createContext<CrmContextValue | null>(null)

export function CrmProvider({ children }: { children: ReactNode }) {
  const [companies, setCompanies] = useState(seedCompanies)
  const [contacts, setContacts] = useState(seedContacts)
  const [deals, setDeals] = useState(seedDeals)
  const [activities, setActivities] = useState(seedActivities)

  const value = useMemo<CrmContextValue>(
    () => ({
      companies,
      contacts,
      deals,
      activities,
      addCompany: (input) =>
        setCompanies((current) => [
          { ...input, id: createId("cmp") },
          ...current,
        ]),
      updateCompany: (id, input) =>
        setCompanies((current) =>
          current.map((item) => (item.id === id ? { ...item, ...input } : item))
        ),
      deleteCompany: (id) => {
        setCompanies((current) => current.filter((item) => item.id !== id))
        setContacts((current) => current.filter((item) => item.companyId !== id))
        setDeals((current) => current.filter((item) => item.companyId !== id))
        setActivities((current) =>
          current.filter((item) => item.companyId !== id)
        )
      },
      addContact: (input) =>
        setContacts((current) => [
          { ...input, id: createId("ct") },
          ...current,
        ]),
      updateContact: (id, input) =>
        setContacts((current) =>
          current.map((item) => (item.id === id ? { ...item, ...input } : item))
        ),
      deleteContact: (id) => {
        setContacts((current) => current.filter((item) => item.id !== id))
        setActivities((current) =>
          current.map((item) =>
            item.contactId === id ? { ...item, contactId: null } : item
          )
        )
      },
      addDeal: (input) =>
        setDeals((current) => [{ ...input, id: createId("dl") }, ...current]),
      updateDeal: (id, input) =>
        setDeals((current) =>
          current.map((item) => (item.id === id ? { ...item, ...input } : item))
        ),
      deleteDeal: (id) =>
        setDeals((current) => current.filter((item) => item.id !== id)),
      addActivity: (input) =>
        setActivities((current) => [
          { ...input, id: createId("act") },
          ...current,
        ]),
      updateActivity: (id, input) =>
        setActivities((current) =>
          current.map((item) => (item.id === id ? { ...item, ...input } : item))
        ),
      deleteActivity: (id) =>
        setActivities((current) => current.filter((item) => item.id !== id)),
    }),
    [activities, companies, contacts, deals]
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
