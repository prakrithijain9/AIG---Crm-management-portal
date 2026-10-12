import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status
from sqlalchemy import select

from app.api.common import (
    DbSession,
    PageParams,
    commit,
    contains_any,
    get_or_404,
    paginated,
    require_reference,
)
from app.models import Company, Deal, DealStage
from app.schemas.deal import DealCreate, DealRead, DealUpdate

router = APIRouter(prefix="/deals", tags=["deals"])


@router.get("", response_model=list[DealRead])
def list_deals(
    db: DbSession,
    page: PageParams,
    response: Response,
    search: str | None = None,
    stage: DealStage | None = None,
    company_id: Annotated[uuid.UUID | None, Query(alias="companyId")] = None,
):
    stmt = select(Deal).join(Deal.company)
    if search:
        stmt = stmt.where(contains_any(search, Deal.title, Deal.stage, Company.name))
    if stage:
        stmt = stmt.where(Deal.stage == stage)
    if company_id:
        stmt = stmt.where(Deal.company_id == company_id)
    stmt = stmt.order_by(Deal.created_at.desc(), Deal.id)
    return paginated(db, stmt, page, response)


@router.post("", response_model=DealRead, status_code=status.HTTP_201_CREATED)
def create_deal(payload: DealCreate, db: DbSession):
    require_reference(db, Company, payload.company_id, "companyId")
    deal = Deal(**payload.model_dump())
    db.add(deal)
    commit(db)
    db.refresh(deal)
    return deal


@router.get("/{deal_id}", response_model=DealRead)
def get_deal(deal_id: uuid.UUID, db: DbSession):
    return get_or_404(db, Deal, deal_id)


@router.patch("/{deal_id}", response_model=DealRead)
def update_deal(deal_id: uuid.UUID, payload: DealUpdate, db: DbSession):
    deal = get_or_404(db, Deal, deal_id)
    changes = payload.changes()
    if "company_id" in changes:
        require_reference(db, Company, changes["company_id"], "companyId")
    for field, value in changes.items():
        setattr(deal, field, value)
    commit(db)
    db.refresh(deal)
    return deal


@router.delete("/{deal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_deal(deal_id: uuid.UUID, db: DbSession) -> None:
    deal = get_or_404(db, Deal, deal_id)
    db.delete(deal)
    commit(db)
