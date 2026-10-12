import uuid

from fastapi import APIRouter, Response, status
from sqlalchemy import select

from app.api.common import DbSession, PageParams, commit, contains_any, get_or_404, paginated
from app.models import Company, CompanyStatus
from app.schemas.company import CompanyCreate, CompanyRead, CompanyUpdate

router = APIRouter(prefix="/companies", tags=["companies"])


@router.get("", response_model=list[CompanyRead])
def list_companies(
    db: DbSession,
    page: PageParams,
    response: Response,
    search: str | None = None,
    status: CompanyStatus | None = None,
):
    stmt = select(Company)
    if search:
        stmt = stmt.where(
            contains_any(search, Company.name, Company.industry, Company.email, Company.phone, Company.location)
        )
    if status:
        stmt = stmt.where(Company.status == status)
    stmt = stmt.order_by(Company.created_at.desc(), Company.id)
    return paginated(db, stmt, page, response)


@router.post("", response_model=CompanyRead, status_code=status.HTTP_201_CREATED)
def create_company(payload: CompanyCreate, db: DbSession):
    company = Company(**payload.model_dump())
    db.add(company)
    commit(db)
    db.refresh(company)
    return company


@router.get("/{company_id}", response_model=CompanyRead)
def get_company(company_id: uuid.UUID, db: DbSession):
    return get_or_404(db, Company, company_id)


@router.patch("/{company_id}", response_model=CompanyRead)
def update_company(company_id: uuid.UUID, payload: CompanyUpdate, db: DbSession):
    company = get_or_404(db, Company, company_id)
    for field, value in payload.changes().items():
        setattr(company, field, value)
    commit(db)
    db.refresh(company)
    return company


@router.delete("/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_company(company_id: uuid.UUID, db: DbSession) -> None:
    """Also deletes the company's contacts, deals and activities (ON DELETE CASCADE)."""
    company = get_or_404(db, Company, company_id)
    db.delete(company)
    commit(db)
