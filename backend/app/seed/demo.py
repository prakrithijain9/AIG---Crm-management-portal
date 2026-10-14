"""Insert-only, repeatable demo data for the development database.

Data comes from demo_data.json, a one-time JSON export of the frontend's lib/mock-data.ts.
Each record is matched by a natural key; anything that already exists is skipped and never
modified, and nothing is ever deleted. Running it twice creates nothing the second time.

Natural keys:
  company  -> lower(name)                          (unique in the DB)
  contact  -> lower(email)                         (unique in the DB)
  deal     -> company + lower(title)
  activity -> company + lower(subject) + due date
"""

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import BACKEND_DIR, Settings
from app.models import Activity, Company, Contact, Deal
from app.schemas.activity import ActivityCreate
from app.schemas.company import CompanyCreate
from app.schemas.contact import ContactCreate
from app.schemas.deal import DealCreate

DATA_FILE = Path(__file__).with_name("demo_data.json")

# Arbitrary constant: serialises concurrent seed runs (deals/activities have no unique constraint).
ADVISORY_LOCK_KEY = 0x41494743524D  # "AIGCRM"


class SeedRefused(Exception):
    pass


def check_target(settings: Settings) -> str:
    """Return the database to seed, or refuse if it could be the test database."""
    target = settings.db_name
    if target == settings.test_db_name or target.endswith("_test"):
        raise SeedRefused(f"Refusing to seed '{target}': it is (or looks like) the test database.")
    return target


def check_connection(db: Session, target: str) -> None:
    connected = db.execute(text("SELECT current_database()")).scalar_one()
    if connected != target:
        raise SeedRefused(f"Connected to '{connected}', expected '{target}'.")

    cfg = Config()
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    head = ScriptDirectory.from_config(cfg).get_current_head()
    current = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
    if current != head:
        raise SeedRefused(f"Database is at migration {current}, expected {head}. Run: alembic upgrade head")


@dataclass
class SeedReport:
    applied: bool
    lines: list[tuple[str, str, str]] = field(default_factory=list)  # (entity, action, label)
    warnings: list[str] = field(default_factory=list)

    def add(self, entity: str, action: str, label: str) -> None:
        self.lines.append((entity, action, label))

    def count(self, entity: str, action: str) -> int:
        return sum(1 for e, a, _ in self.lines if e == entity and a == action)


def load_demo_data() -> dict:
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def _fields(row: dict, **replacements) -> dict:
    """Drop the mock 'id' and swap mock reference ids for real UUIDs."""
    return {k: v for k, v in row.items() if k != "id"} | {k: str(v) if v else v for k, v in replacements.items()}


def seed_demo_data(db: Session, *, apply: bool) -> SeedReport:
    """Plan (apply=False) or insert (apply=True) the demo data using `db`'s transaction.

    The caller owns the transaction: commit to keep the data, roll back to discard.
    With apply=False this function only reads.
    """
    data = load_demo_data()
    report = SeedReport(applied=apply)
    action = "create" if apply else "would create"

    if apply:
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": ADVISORY_LOCK_KEY})

    # mock id -> real (or, in a dry run, placeholder) UUID
    company_ids: dict[str, uuid.UUID] = {}
    contact_ids: dict[str, uuid.UUID] = {}
    contact_company: dict[uuid.UUID, uuid.UUID] = {}
    new_company_ids: set[uuid.UUID] = set()

    def insert(obj):
        if apply:
            db.add(obj)
            db.flush()  # assigns the id and surfaces constraint errors immediately
        else:
            obj.id = uuid.uuid4()  # placeholder only; never written
        return obj.id

    for row in data["companies"]:
        p = CompanyCreate.model_validate(_fields(row))
        existing = db.scalar(select(Company).where(func.lower(Company.name) == p.name.lower()))
        if existing:
            company_ids[row["id"]] = existing.id
            report.add("company", "skip (exists)", p.name)
        else:
            company_ids[row["id"]] = insert(Company(**p.model_dump()))
            new_company_ids.add(company_ids[row["id"]])
            report.add("company", action, p.name)

    for row in data["contacts"]:
        p = ContactCreate.model_validate(_fields(row, companyId=company_ids[row["companyId"]]))
        existing = db.scalar(select(Contact).where(func.lower(Contact.email) == p.email.lower()))
        if existing:
            contact_ids[row["id"]] = existing.id
            contact_company[existing.id] = existing.company_id
            report.add("contact", "skip (exists)", p.email)
            if existing.company_id != p.company_id:
                report.warnings.append(f"Contact {p.email} already exists under a different company; left unchanged.")
        else:
            contact_ids[row["id"]] = insert(Contact(**p.model_dump()))
            contact_company[contact_ids[row["id"]]] = p.company_id
            report.add("contact", action, f"{p.name} <{p.email}>")

    for row in data["deals"]:
        p = DealCreate.model_validate(_fields(row, companyId=company_ids[row["companyId"]]))
        existing = None
        if p.company_id not in new_company_ids:
            existing = db.scalar(
                select(Deal.id).where(Deal.company_id == p.company_id, func.lower(Deal.title) == p.title.lower())
            )
        if existing:
            report.add("deal", "skip (exists)", p.title)
        else:
            insert(Deal(**p.model_dump()))
            report.add("deal", action, f"{p.title} (${p.value:,.0f}, {p.stage})")

    for row in data["activities"]:
        contact_id = contact_ids.get(row["contactId"]) if row["contactId"] else None
        p = ActivityCreate.model_validate(
            _fields(row, companyId=company_ids[row["companyId"]], contactId=contact_id)
        )
        if p.contact_id is not None and contact_company[p.contact_id] != p.company_id:
            report.warnings.append(f"Activity '{p.subject}' skipped: its contact belongs to another company.")
            report.add("activity", "skip (conflict)", p.subject)
            continue
        existing = None
        if p.company_id not in new_company_ids:
            existing = db.scalar(
                select(Activity.id).where(
                    Activity.company_id == p.company_id,
                    func.lower(Activity.subject) == p.subject.lower(),
                    Activity.due_date == p.due_date,
                )
            )
        if existing:
            report.add("activity", "skip (exists)", p.subject)
        else:
            insert(Activity(**p.model_dump()))
            report.add("activity", action, f"{p.subject} (due {p.due_date}, {p.status})")

    return report
