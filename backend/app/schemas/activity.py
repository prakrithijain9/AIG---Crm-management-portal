import uuid
from datetime import date
from typing import ClassVar

from app.models.enums import ActivityStatus, ActivityType
from app.schemas.common import InputModel, OutputModel, UpdateModel, text_field

Subject = text_field(300)


class ActivityCreate(InputModel):
    type: ActivityType
    subject: Subject
    company_id: uuid.UUID
    contact_id: uuid.UUID | None = None
    due_date: date
    status: ActivityStatus = ActivityStatus.PENDING


class ActivityUpdate(UpdateModel):
    # Sending "contactId": null unlinks the contact.
    NULLABLE_FIELDS: ClassVar[frozenset[str]] = frozenset({"contact_id"})

    type: ActivityType | None = None
    subject: Subject | None = None
    company_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    due_date: date | None = None
    status: ActivityStatus | None = None


class ActivityRead(OutputModel):
    type: ActivityType
    subject: str
    company_id: uuid.UUID
    contact_id: uuid.UUID | None
    due_date: date
    status: ActivityStatus
