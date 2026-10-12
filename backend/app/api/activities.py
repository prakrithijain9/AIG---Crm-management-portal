import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.common import (
    DbSession,
    PageParams,
    commit,
    contains_any,
    get_or_404,
    paginated,
    require_reference,
    unprocessable,
)
from app.models import Activity, ActivityStatus, ActivityType, Company, Contact
from app.schemas.activity import ActivityCreate, ActivityRead, ActivityUpdate

router = APIRouter(prefix="/activities", tags=["activities"])


def check_links(db: Session, company_id: uuid.UUID, contact_id: uuid.UUID | None) -> None:
    """The company must exist; the contact (if any) must exist and belong to that company.

    The contact row is read with FOR SHARE so its company can't change until this
    request's transaction finishes.
    """
    require_reference(db, Company, company_id, "companyId")
    if contact_id is not None:
        contact = require_reference(db, Contact, contact_id, "contactId", lock={"read": True})
        if contact.company_id != company_id:
            unprocessable("contactId", "Contact belongs to a different company than the activity.")


@router.get("", response_model=list[ActivityRead])
def list_activities(
    db: DbSession,
    page: PageParams,
    response: Response,
    search: str | None = None,
    status: ActivityStatus | None = None,
    type: ActivityType | None = None,
    company_id: Annotated[uuid.UUID | None, Query(alias="companyId")] = None,
    contact_id: Annotated[uuid.UUID | None, Query(alias="contactId")] = None,
):
    stmt = select(Activity).join(Activity.company).outerjoin(Activity.contact)
    if search:
        stmt = stmt.where(contains_any(search, Activity.subject, Activity.type, Company.name, Contact.name))
    if status:
        stmt = stmt.where(Activity.status == status)
    if type:
        stmt = stmt.where(Activity.type == type)
    if company_id:
        stmt = stmt.where(Activity.company_id == company_id)
    if contact_id:
        stmt = stmt.where(Activity.contact_id == contact_id)
    # Soonest due first, like the Activities page.
    stmt = stmt.order_by(Activity.due_date, Activity.created_at, Activity.id)
    return paginated(db, stmt, page, response)


@router.post("", response_model=ActivityRead, status_code=status.HTTP_201_CREATED)
def create_activity(payload: ActivityCreate, db: DbSession):
    check_links(db, payload.company_id, payload.contact_id)
    activity = Activity(**payload.model_dump())
    db.add(activity)
    commit(db)
    db.refresh(activity)
    return activity


@router.get("/{activity_id}", response_model=ActivityRead)
def get_activity(activity_id: uuid.UUID, db: DbSession):
    return get_or_404(db, Activity, activity_id)


@router.patch("/{activity_id}", response_model=ActivityRead)
def update_activity(activity_id: uuid.UUID, payload: ActivityUpdate, db: DbSession):
    activity = get_or_404(db, Activity, activity_id)
    changes = payload.changes()
    if "company_id" in changes or "contact_id" in changes:
        # Validate the combination the activity will end up with, not just the sent fields.
        check_links(
            db,
            changes.get("company_id", activity.company_id),
            changes.get("contact_id", activity.contact_id),
        )
    for field, value in changes.items():
        setattr(activity, field, value)
    commit(db)
    db.refresh(activity)
    return activity


@router.delete("/{activity_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_activity(activity_id: uuid.UUID, db: DbSession) -> None:
    activity = get_or_404(db, Activity, activity_id)
    db.delete(activity)
    commit(db)
