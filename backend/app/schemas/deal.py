import uuid
from datetime import date

from app.models.enums import DealStage
from app.schemas.common import InputModel, Money, OutputModel, UpdateModel, text_field

Title = text_field(200)


class DealCreate(InputModel):
    title: Title
    company_id: uuid.UUID
    value: Money
    stage: DealStage = DealStage.LEAD
    expected_close_date: date


class DealUpdate(UpdateModel):
    title: Title | None = None
    company_id: uuid.UUID | None = None
    value: Money | None = None
    stage: DealStage | None = None
    expected_close_date: date | None = None


class DealRead(OutputModel):
    title: str
    company_id: uuid.UUID
    value: Money
    stage: DealStage
    expected_close_date: date
