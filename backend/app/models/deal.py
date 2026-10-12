import uuid
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, str_enum
from app.models.enums import DealStage

if TYPE_CHECKING:
    from app.models.company import Company


class Deal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "deals"
    __table_args__ = (
        CheckConstraint("btrim(title) <> ''", name="title_not_blank"),
        CheckConstraint("value >= 0", name="value_non_negative"),
    )

    title: Mapped[str] = mapped_column(String(200))
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    # Exact decimal money (USD), never floating point.
    value: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    stage: Mapped[DealStage] = mapped_column(
        str_enum(DealStage, "stage"),
        default=DealStage.LEAD,
        server_default=DealStage.LEAD.value,
        index=True,
    )
    expected_close_date: Mapped[date]

    company: Mapped["Company"] = relationship(back_populates="deals")
