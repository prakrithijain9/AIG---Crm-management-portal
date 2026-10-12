import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import exists, select

from app.api.common import (
    DbSession,
    PageParams,
    commit,
    contains_any,
    get_or_404,
    paginated,
    require_reference,
)
from app.models import Activity, Company, Contact
from app.schemas.contact import ContactCreate, ContactRead, ContactUpdate

router = APIRouter(prefix="/contacts", tags=["contacts"])


@router.get("", response_model=list[ContactRead])
def list_contacts(
    db: DbSession,
    page: PageParams,
    response: Response,
    search: str | None = None,
    company_id: Annotated[uuid.UUID | None, Query(alias="companyId")] = None,
):
    stmt = select(Contact).join(Contact.company)
    if search:
        stmt = stmt.where(
            contains_any(search, Contact.name, Contact.email, Contact.phone, Contact.job_title, Company.name)
        )
    if company_id:
        stmt = stmt.where(Contact.company_id == company_id)
    stmt = stmt.order_by(Contact.created_at.desc(), Contact.id)
    return paginated(db, stmt, page, response)


@router.post("", response_model=ContactRead, status_code=status.HTTP_201_CREATED)
def create_contact(payload: ContactCreate, db: DbSession):
    require_reference(db, Company, payload.company_id, "companyId")
    contact = Contact(**payload.model_dump())
    db.add(contact)
    commit(db)
    db.refresh(contact)
    return contact


@router.get("/{contact_id}", response_model=ContactRead)
def get_contact(contact_id: uuid.UUID, db: DbSession):
    return get_or_404(db, Contact, contact_id)


@router.patch("/{contact_id}", response_model=ContactRead)
def update_contact(contact_id: uuid.UUID, payload: ContactUpdate, db: DbSession):
    # Row lock: stops an activity being linked to this contact while its company changes.
    contact = get_or_404(db, Contact, contact_id, lock=True)
    changes = payload.changes()

    new_company_id = changes.get("company_id")
    if new_company_id is not None and new_company_id != contact.company_id:
        require_reference(db, Company, new_company_id, "companyId")
        has_activities = db.scalar(select(exists().where(Activity.contact_id == contact.id)))
        if has_activities:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Contact has activities with its current company. "
                "Unlink or delete those activities before moving the contact.",
            )

    for field, value in changes.items():
        setattr(contact, field, value)
    commit(db)
    db.refresh(contact)
    return contact


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_contact(contact_id: uuid.UUID, db: DbSession) -> None:
    """Activities linked to the contact are kept, with contactId set to null (ON DELETE SET NULL)."""
    contact = get_or_404(db, Contact, contact_id)
    db.delete(contact)
    commit(db)
