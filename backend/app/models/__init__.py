"""Import every model so they are registered on Base.metadata (needed by Alembic)."""

from app.db.base import Base
from app.models.activity import Activity
from app.models.company import Company
from app.models.contact import Contact
from app.models.deal import Deal
from app.models.enums import ActivityStatus, ActivityType, CompanyStatus, DealStage

__all__ = [
    "Activity",
    "ActivityStatus",
    "ActivityType",
    "Base",
    "Company",
    "CompanyStatus",
    "Contact",
    "Deal",
    "DealStage",
]
