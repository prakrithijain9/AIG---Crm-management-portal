export function formatCurrency(value: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value)
}

export function formatDate(isoDate: string) {
  const date = new Date(`${isoDate}T00:00:00`)
  if (Number.isNaN(date.getTime())) return isoDate

  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(date)
}

export function companyNameById(
  companies: { id: string; name: string }[],
  companyId: string
) {
  return companies.find((company) => company.id === companyId)?.name ?? "Unknown"
}

export function contactNameById(
  contacts: { id: string; name: string }[],
  contactId: string | null
) {
  if (!contactId) return "—"
  return contacts.find((contact) => contact.id === contactId)?.name ?? "Unknown"
}
