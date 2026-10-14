import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.activity import Activity
    from app.models.company import Company


class Contact(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "contacts"
    __table_args__ = (
        CheckConstraint("btrim(name) <> ''", name="name_not_blank"),
        CheckConstraint("position('@' in email) > 1", name="email_has_at"),
    )

    name: Mapped[str] = mapped_column(String(200))
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    email: Mapped[str] = mapped_column(String(320))
    phone: Mapped[str] = mapped_column(String(50))
    job_title: Mapped[str] = mapped_column(String(150))

    company: Mapped["Company"] = relationship(back_populates="contacts")
    # Deleting a contact keeps its activities but clears activity.contact_id (ON DELETE SET NULL).
    activities: Mapped[list["Activity"]] = relationship(
        back_populates="contact", passive_deletes=True
    )


# One contact per email address, case-insensitive.
Index("uq_contacts_email_lower", func.lower(Contact.email), unique=True)
