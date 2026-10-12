"""Allowed values, matching the frontend's lib/types.ts."""

from enum import StrEnum


class CompanyStatus(StrEnum):
    ACTIVE = "Active"
    PROSPECT = "Prospect"
    INACTIVE = "Inactive"


class DealStage(StrEnum):
    LEAD = "Lead"
    QUALIFIED = "Qualified"
    PROPOSAL = "Proposal"
    NEGOTIATION = "Negotiation"
    WON = "Won"
    LOST = "Lost"


class ActivityType(StrEnum):
    CALL = "Call"
    MEETING = "Meeting"
    EMAIL = "Email"
    TASK = "Task"
    FOLLOW_UP = "Follow-up"


class ActivityStatus(StrEnum):
    PENDING = "Pending"
    COMPLETED = "Completed"
