import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, str_enum
from app.models.enums import ActivityStatus, ActivityType

if TYPE_CHECKING:
    from app.models.company import Company
    from app.models.contact import Contact


class Activity(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "activities"
    __table_args__ = (CheckConstraint("btrim(subject) <> ''", name="subject_not_blank"),)

    type: Mapped[ActivityType] = mapped_column(str_enum(ActivityType, "type"))
    subject: Mapped[str] = mapped_column(String(300))
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    # Optional. It should belong to the same company; that rule is not enforced by
    # the database yet and will be validated in the API layer (see NOTES.md).
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("contacts.id", ondelete="SET NULL"), index=True
    )
    due_date: Mapped[date] = mapped_column(index=True)
    status: Mapped[ActivityStatus] = mapped_column(
        str_enum(ActivityStatus, "status"),
        default=ActivityStatus.PENDING,
        server_default=ActivityStatus.PENDING.value,
    )

    company: Mapped["Company"] = relationship(back_populates="activities")
    contact: Mapped["Contact | None"] = relationship(back_populates="activities")
