import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Activity,
    ActivityStatus,
    ActivityType,
    Company,
    CompanyStatus,
    Contact,
    Deal,
    DealStage,
)


def make_company(name: str = "Northwind Logistics", **overrides) -> Company:
    fields = dict(
        name=name,
        industry="Transportation",
        email="partnerships@northwind.example",
        phone="+1 (415) 555-0142",
        location="San Francisco, CA",
        status=CompanyStatus.ACTIVE,
    )
    return Company(**(fields | overrides))


def make_contact(company: Company, email: str = "priya@northwind.example") -> Contact:
    return Contact(
        name="Priya Raman",
        company=company,
        email=email,
        phone="+1 (415) 555-2210",
        job_title="VP of Operations",
    )


def assert_violates(db: Session, constraint: str, sql: str, **params) -> None:
    """Run raw SQL and assert PostgreSQL rejects it with the named constraint."""
    with pytest.raises(IntegrityError) as exc_info:
        with db.begin_nested():
            db.execute(text(sql), params)
    assert exc_info.value.orig.diag.constraint_name == constraint


@pytest.fixture
def company(db: Session) -> Company:
    c = make_company()
    db.add(c)
    db.flush()
    return c


# --- Creating and relating records -------------------------------------------------


def test_create_full_graph_with_defaults(db: Session, company: Company):
    contact = make_contact(company)
    deal = Deal(
        title="Fleet expansion",
        company=company,
        value=Decimal("125000.50"),
        expected_close_date=date(2026, 12, 1),
    )
    activity = Activity(
        type=ActivityType.FOLLOW_UP,
        subject="Send proposal",
        company=company,
        contact=contact,
        due_date=date(2026, 10, 20),
    )
    db.add_all([contact, deal, activity])
    db.flush()
    db.expire_all()

    loaded = db.get(Company, company.id)
    assert isinstance(loaded.id, uuid.UUID)
    assert loaded.created_at is not None and loaded.updated_at is not None
    assert [c.email for c in loaded.contacts] == ["priya@northwind.example"]
    assert loaded.deals[0].value == Decimal("125000.50")
    assert loaded.deals[0].stage == DealStage.LEAD  # default
    assert loaded.activities[0].status == ActivityStatus.PENDING  # default
    assert loaded.activities[0].type == "Follow-up"  # stored as the frontend's value
    assert loaded.activities[0].contact.id == contact.id


def test_activity_contact_is_optional(db: Session, company: Company):
    db.add(Activity(type=ActivityType.TASK, subject="Prep", company=company, due_date=date(2026, 11, 1)))
    db.flush()


# --- Delete behaviour (mirrors the frontend's crm-provider) -------------------------


def test_deleting_company_cascades_to_children(db: Session, company: Company):
    contact = make_contact(company)
    db.add_all(
        [
            contact,
            Deal(title="D", company=company, value=1, expected_close_date=date(2026, 12, 1)),
            Activity(type=ActivityType.CALL, subject="S", company=company, contact=contact, due_date=date(2026, 12, 1)),
        ]
    )
    db.flush()

    # Delete in SQL so the database's ON DELETE CASCADE is what's being tested.
    db.execute(text("DELETE FROM companies WHERE id = :id"), {"id": company.id})
    for model in (Contact, Deal, Activity):
        assert db.scalar(select(model).where(model.company_id == company.id)) is None


def test_deleting_contact_keeps_activity_and_clears_contact(db: Session, company: Company):
    contact = make_contact(company)
    activity = Activity(type=ActivityType.MEETING, subject="Kickoff", company=company, contact=contact, due_date=date(2026, 12, 1))
    db.add_all([contact, activity])
    db.flush()

    db.execute(text("DELETE FROM contacts WHERE id = :id"), {"id": contact.id})
    db.expire_all()
    remaining = db.get(Activity, activity.id)
    assert remaining is not None
    assert remaining.contact_id is None


# --- Constraints enforced by PostgreSQL --------------------------------------------

INSERT_COMPANY = (
    "INSERT INTO companies (name, industry, email, phone, location, status) "
    "VALUES (:name, 'X', :email, '1', 'Y', :status)"
)


def test_company_name_unique_case_insensitive(db: Session, company: Company):
    assert_violates(db, "uq_companies_name_lower", INSERT_COMPANY, name="NORTHWIND logistics", email="a@b.c", status="Active")


def test_company_name_not_blank(db: Session):
    assert_violates(db, "ck_companies_name_not_blank", INSERT_COMPANY, name="   ", email="a@b.c", status="Active")


def test_company_email_needs_at_sign(db: Session):
    assert_violates(db, "ck_companies_email_has_at", INSERT_COMPANY, name="Acme", email="not-an-email", status="Active")


def test_company_status_must_be_known(db: Session):
    assert_violates(db, "ck_companies_status", INSERT_COMPANY, name="Acme", email="a@b.c", status="Archived")


def test_contact_email_unique_case_insensitive(db: Session, company: Company):
    db.add(make_contact(company, email="priya@northwind.example"))
    db.flush()
    assert_violates(
        db,
        "uq_contacts_email_lower",
        "INSERT INTO contacts (name, company_id, email, phone, job_title) VALUES ('P', :cid, 'PRIYA@Northwind.example', '1', 'T')",
        cid=company.id,
    )


def test_contact_requires_existing_company(db: Session):
    assert_violates(
        db,
        "fk_contacts_company_id_companies",
        "INSERT INTO contacts (name, company_id, email, phone, job_title) VALUES ('P', :cid, 'p@x.y', '1', 'T')",
        cid=uuid.uuid4(),
    )


INSERT_DEAL = (
    "INSERT INTO deals (title, company_id, value, stage, expected_close_date) "
    "VALUES ('Deal', :cid, :value, :stage, '2026-12-01')"
)


def test_deal_value_cannot_be_negative(db: Session, company: Company):
    assert_violates(db, "ck_deals_value_non_negative", INSERT_DEAL, cid=company.id, value=-1, stage="Lead")


def test_deal_stage_must_be_known(db: Session, company: Company):
    assert_violates(db, "ck_deals_stage", INSERT_DEAL, cid=company.id, value=10, stage="Closed")


def test_activity_type_must_be_known(db: Session, company: Company):
    assert_violates(
        db,
        "ck_activities_type",
        "INSERT INTO activities (type, subject, company_id, due_date) VALUES ('Lunch', 'S', :cid, '2026-12-01')",
        cid=company.id,
    )


def test_activity_requires_existing_contact(db: Session, company: Company):
    assert_violates(
        db,
        "fk_activities_contact_id_contacts",
        "INSERT INTO activities (type, subject, company_id, contact_id, due_date) VALUES ('Call', 'S', :cid, :ctid, '2026-12-01')",
        cid=company.id,
        ctid=uuid.uuid4(),
    )


def test_required_fields_are_not_null(db: Session, company: Company):
    with pytest.raises(IntegrityError) as exc_info:
        with db.begin_nested():
            db.execute(
                text("INSERT INTO deals (title, company_id, value) VALUES ('D', :cid, 5)"),
                {"cid": company.id},
            )
    assert exc_info.value.orig.diag.column_name == "expected_close_date"
