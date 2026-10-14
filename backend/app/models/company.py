from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, str_enum
from app.models.enums import CompanyStatus

if TYPE_CHECKING:
    from app.models.activity import Activity
    from app.models.contact import Contact
    from app.models.deal import Deal


class Company(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "companies"
    __table_args__ = (
        CheckConstraint("btrim(name) <> ''", name="name_not_blank"),
        CheckConstraint("position('@' in email) > 1", name="email_has_at"),
    )

    name: Mapped[str] = mapped_column(String(200))
    industry: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(320))
    phone: Mapped[str] = mapped_column(String(50))
    location: Mapped[str] = mapped_column(String(200))
    status: Mapped[CompanyStatus] = mapped_column(
        str_enum(CompanyStatus, "status"),
        default=CompanyStatus.PROSPECT,
        server_default=CompanyStatus.PROSPECT.value,
    )

    # Deleting a company deletes its contacts, deals and activities (as the UI does).
    # passive_deletes lets PostgreSQL's ON DELETE CASCADE do the work.
    contacts: Mapped[list["Contact"]] = relationship(
        back_populates="company", cascade="all, delete-orphan", passive_deletes=True
    )
    deals: Mapped[list["Deal"]] = relationship(
        back_populates="company", cascade="all, delete-orphan", passive_deletes=True
    )
    activities: Mapped[list["Activity"]] = relationship(
        back_populates="company", cascade="all, delete-orphan", passive_deletes=True
    )


# Company names are unique regardless of case ("Acme" == "ACME").
Index("uq_companies_name_lower", func.lower(Company.name), unique=True)
