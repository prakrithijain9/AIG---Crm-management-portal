export const companyStatuses = ["Active", "Prospect", "Inactive"] as const
export type CompanyStatus = (typeof companyStatuses)[number]

export const dealStages = [
  "Lead",
  "Qualified",
  "Proposal",
  "Negotiation",
  "Won",
  "Lost",
] as const
export type DealStage = (typeof dealStages)[number]

export const activityTypes = [
  "Call",
  "Meeting",
  "Email",
  "Task",
  "Follow-up",
] as const
export type ActivityType = (typeof activityTypes)[number]

export const activityStatuses = ["Pending", "Completed"] as const
export type ActivityStatus = (typeof activityStatuses)[number]

export type Company = {
  id: string
  name: string
  industry: string
  email: string
  phone: string
  location: string
  status: CompanyStatus
}

export type Contact = {
  id: string
  name: string
  companyId: string
  email: string
  phone: string
  jobTitle: string
}

export type Deal = {
  id: string
  title: string
  companyId: string
  value: number
  stage: DealStage
  expectedCloseDate: string
}

export type Activity = {
  id: string
  type: ActivityType
  subject: string
  companyId: string
  contactId: string | null
  dueDate: string
  status: ActivityStatus
}

export type CompanyInput = Omit<Company, "id">
export type ContactInput = Omit<Contact, "id">
export type DealInput = Omit<Deal, "id">
export type ActivityInput = Omit<Activity, "id">
