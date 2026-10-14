"""Seed logic, exercised inside the rolled-back test-database transaction.

The seed *script* refuses the test DB (see test_guard_*); these tests call the seed
*function* directly on the test session, so nothing persists after each test.
"""

import pytest
from sqlalchemy import func, select

from app.core.config import Settings
from app.models import Activity, Company, Contact, Deal
from app.seed.demo import SeedRefused, check_connection, check_target, load_demo_data, seed_demo_data

DATA = load_demo_data()
EXPECTED = {Company: 8, Contact: 10, Deal: 8, Activity: 8}


def counts(db):
    return {model: db.scalar(select(func.count()).select_from(model)) for model in EXPECTED}


def test_demo_data_file_matches_frontend_mock_sizes():
    assert {k: len(DATA[k]) for k in ("companies", "contacts", "deals", "activities")} == {
        "companies": 8, "contacts": 10, "deals": 8, "activities": 8,
    }


def test_apply_creates_all_records_with_correct_relationships(db):
    report = seed_demo_data(db, apply=True)
    assert counts(db) == EXPECTED
    assert report.warnings == []

    # Every contact/deal/activity is attached to the same company as in the mock data.
    mock_company_name = {c["id"]: c["name"] for c in DATA["companies"]}
    for row in DATA["contacts"]:
        contact = db.scalar(select(Contact).where(Contact.email == row["email"]))
        assert contact.company.name == mock_company_name[row["companyId"]]
    for row in DATA["activities"]:
        activity = db.scalar(select(Activity).where(Activity.subject == row["subject"]))
        assert activity.company.name == mock_company_name[row["companyId"]]
        assert activity.contact.company_id == activity.company_id


def test_second_run_creates_nothing(db):
    seed_demo_data(db, apply=True)
    report = seed_demo_data(db, apply=True)
    assert counts(db) == EXPECTED
    assert all(action.startswith("skip") for _, action, _ in report.lines)
    assert len(report.lines) == 34


def test_existing_records_are_never_modified(db):
    mine = Company(name="Helios Energy", industry="My own edit", email="me@helios.example",
                   phone="1", location="Here", status="Inactive")
    db.add(mine)
    db.flush()

    seed_demo_data(db, apply=True)
    db.refresh(mine)
    assert (mine.industry, mine.status) == ("My own edit", "Inactive")  # untouched
    assert db.scalar(select(func.count()).select_from(Company)) == 8  # reused, not duplicated
    # The demo contacts for Helios were attached to the existing company.
    assert {c.email for c in mine.contacts} == {
        r["email"] for r in DATA["contacts"] if r["companyId"] == "cmp-2"
    }


def test_dry_run_writes_nothing(db):
    report = seed_demo_data(db, apply=False)
    assert counts(db) == {model: 0 for model in EXPECTED}
    assert sum(1 for _, action, _ in report.lines if action == "would create") == 34


@pytest.mark.parametrize("db_name", ["aig_crm_test", "something_test"])
def test_guard_refuses_test_databases(db_name):
    settings = Settings(db_name=db_name, test_db_name="aig_crm_test")
    with pytest.raises(SeedRefused):
        check_target(settings)


def test_guard_accepts_dev_database():
    assert check_target(Settings(db_name="aig_crm_dev", test_db_name="aig_crm_test")) == "aig_crm_dev"


def test_guard_rejects_wrong_connected_database(db):
    # `db` is connected to aig_crm_test, so claiming it is aig_crm_dev must be refused.
    with pytest.raises(SeedRefused, match="Connected to 'aig_crm_test'"):
        check_connection(db, "aig_crm_dev")
