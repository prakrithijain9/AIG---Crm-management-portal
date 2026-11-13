"""Read-only tools the chat assistant can call, plus validated write *proposals*.

Nothing here writes to the database. Every number the assistant states must come from a
tool result: counts and sums are computed by SQL, never by the model. Write tools only
return a proposal; the user confirms it in the UI, which then calls the normal REST API.

Every tool is a plain function ``(db, args, today) -> dict``. A tool that cannot do what was
asked raises ToolError; ``run_tool`` turns that into ``{"error": ...}`` for the model.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Callable, Literal
from urllib.parse import urlencode

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pydantic.alias_generators import to_camel
from sqlalchemy import ColumnElement, Select, func, select
from sqlalchemy.orm import Session

from app.api.common import contains_any
from app.models import Activity, ActivityStatus, ActivityType, Company, CompanyStatus, Contact, Deal, DealStage
from app.schemas.activity import ActivityCreate, ActivityRead, ActivityUpdate
from app.schemas.common import InputModel
from app.schemas.company import CompanyCreate, CompanyRead, CompanyUpdate
from app.schemas.contact import ContactCreate, ContactRead, ContactUpdate
from app.schemas.deal import DealCreate, DealRead, DealUpdate

Entity = Literal["company", "contact", "deal", "activity"]
ENTITIES = ("company", "contact", "deal", "activity")
MODELS = {"company": Company, "contact": Contact, "deal": Deal, "activity": Activity}
READ = {"company": CompanyRead, "contact": ContactRead, "deal": DealRead, "activity": ActivityRead}
CREATE = {"company": CompanyCreate, "contact": ContactCreate, "deal": DealCreate, "activity": ActivityCreate}
UPDATE = {"company": CompanyUpdate, "contact": ContactUpdate, "deal": DealUpdate, "activity": ActivityUpdate}
OPEN_STAGES = (DealStage.LEAD, DealStage.QUALIFIED, DealStage.PROPOSAL, DealStage.NEGOTIATION)

SEARCH_LIMIT = 10
MAX_ROWS = 25


class ToolError(Exception):
    """A problem the model can fix or explain. Never contains raw user input values."""

    def __init__(self, message: str, field_errors: dict[str, str] | None = None):
        super().__init__(message)
        self.message = message
        self.field_errors = field_errors or {}


def _money(value: Decimal | None) -> str:
    return f"{(value or Decimal('0')).quantize(Decimal('0.01')):.2f}"


def _validation_error(exc: ValidationError, what: str) -> ToolError:
    """Field errors without echoing the values that were sent."""
    fields: dict[str, str] = {}
    for err in exc.errors(include_input=False, include_url=False, include_context=False):
        loc = ".".join(str(part) for part in err["loc"]) or "body"
        fields[loc] = err["msg"]
    return ToolError(f"Invalid {what}.", fields)


# --- Argument models ----------------------------------------------------------------


class ToolArgs(BaseModel):
    """Tool arguments: unknown keys rejected, camelCase or snake_case accepted."""

    model_config = ConfigDict(
        extra="forbid", alias_generator=to_camel, validate_by_alias=True, validate_by_name=True
    )


class CompanyFilters(InputModel):
    status: CompanyStatus | None = None
    industry: str | None = None
    location: str | None = None
    search: str | None = None


class ContactFilters(InputModel):
    company_id: uuid.UUID | None = None
    search: str | None = None


class DealFilters(InputModel):
    stage: list[DealStage] | None = None
    company_id: uuid.UUID | None = None
    value_min: Decimal | None = None
    value_max: Decimal | None = None
    close_from: date | None = None
    close_to: date | None = None
    search: str | None = None


class ActivityFilters(InputModel):
    type: ActivityType | None = None
    status: ActivityStatus | None = None
    company_id: uuid.UUID | None = None
    contact_id: uuid.UUID | None = None
    due_from: date | None = None
    due_to: date | None = None
    overdue: bool | None = None
    search: str | None = None


FILTERS = {"company": CompanyFilters, "contact": ContactFilters, "deal": DealFilters, "activity": ActivityFilters}

FILTER_HELP = (
    "company: status (Active|Prospect|Inactive), industry, location, search. "
    "contact: companyId, search. "
    "deal: stage (list of Lead|Qualified|Proposal|Negotiation|Won|Lost), companyId, valueMin, valueMax, "
    "closeFrom, closeTo (ISO dates), search. "
    "activity: type (Call|Meeting|Email|Task|Follow-up), status (Pending|Completed), companyId, contactId, "
    "dueFrom, dueTo (ISO dates), overdue (true = Pending and due before today), search."
)


class SearchArgs(ToolArgs):
    query: str = Field(min_length=1, max_length=100, description="Name, email, title or subject text to look for.")
    entity: Entity | None = Field(default=None, description="Limit to one record type; omit to search all four.")


class GetRecordArgs(ToolArgs):
    entity: Entity
    id: uuid.UUID


SORTS = {
    "company": {"name", "-name", "created", "-created"},
    "contact": {"name", "-name", "created", "-created"},
    "deal": {"title", "-title", "value", "-value", "closeDate", "-closeDate", "created", "-created"},
    "activity": {"dueDate", "-dueDate", "created", "-created"},
}


class ListArgs(ToolArgs):
    entity: Entity
    filters: dict[str, Any] = Field(default_factory=dict, description=f"Allowed filter keys. {FILTER_HELP}")
    sort: str | None = Field(
        default=None,
        description="Prefix '-' for descending. company/contact: name, created. deal: title, value, closeDate, "
        "created. activity: dueDate, created.",
    )
    limit: int = Field(default=10, ge=1, le=MAX_ROWS)


class AggregateArgs(ToolArgs):
    entity: Entity
    metric: Literal["count", "sum_value", "avg_value"] = Field(
        description="sum_value and avg_value are for deals only (sum/average of deal value, USD)."
    )
    group_by: str | None = Field(
        default=None,
        description="company: status|industry|location. contact: company. deal: stage|company|close_month. "
        "activity: type|status|company|due_month.",
    )
    filters: dict[str, Any] = Field(default_factory=dict, description=f"Allowed filter keys. {FILTER_HELP}")


class ProposeCreateArgs(ToolArgs):
    entity: Entity
    fields: dict[str, Any] = Field(
        description="camelCase fields of the new record, e.g. deal: title, companyId, value, stage, "
        "expectedCloseDate. Use ids from search results, never names."
    )


class ProposeUpdateArgs(ToolArgs):
    entity: Entity
    id: uuid.UUID
    changes: dict[str, Any] = Field(description="Only the camelCase fields to change.")


class ProposeDeleteArgs(ToolArgs):
    entity: Entity
    id: uuid.UUID


PAGE_ENTITY = {"companies": "company", "contacts": "contact", "deals": "deal", "activities": "activity"}
# Must match the URL params the pages read (Phase 5).
PAGE_FILTERS: dict[str, dict[str, Callable[[str], str]]] = {
    "dashboard": {},
    "companies": {"search": str, "status": lambda v: CompanyStatus(v).value},
    "contacts": {"search": str},
    "deals": {"search": str, "stage": lambda v: DealStage(v).value},
    "activities": {"search": str, "status": lambda v: ActivityStatus(v).value},
}


class NavigateArgs(ToolArgs):
    page: Literal["dashboard", "companies", "contacts", "deals", "activities"]
    filters: dict[str, str] = Field(
        default_factory=dict,
        description="companies: search, status. contacts: search. deals: search, stage. activities: search, status.",
    )
    open_id: uuid.UUID | None = Field(default=None, description="Open this record's detail dialog on the page.")


# --- Query building -----------------------------------------------------------------


def _base(entity: str) -> Select:
    if entity == "company":
        return select(Company)
    if entity == "contact":
        return select(Contact).join(Contact.company)
    if entity == "deal":
        return select(Deal).join(Deal.company)
    return select(Activity).join(Activity.company).outerjoin(Activity.contact)


def _parse_filters(entity: str, raw: dict[str, Any]) -> BaseModel:
    try:
        return FILTERS[entity].model_validate(raw)
    except ValidationError as exc:
        raise _validation_error(exc, f"{entity} filters") from None


def _filtered(entity: str, f: Any, today: date) -> Select:
    stmt = _base(entity)
    where: list[ColumnElement[bool]] = []
    if entity == "company":
        if f.status:
            where.append(Company.status == f.status)
        if f.industry:
            where.append(contains_any(f.industry, Company.industry))
        if f.location:
            where.append(contains_any(f.location, Company.location))
        if f.search:
            where.append(
                contains_any(f.search, Company.name, Company.industry, Company.email, Company.phone, Company.location)
            )
    elif entity == "contact":
        if f.company_id:
            where.append(Contact.company_id == f.company_id)
        if f.search:
            where.append(
                contains_any(f.search, Contact.name, Contact.email, Contact.phone, Contact.job_title, Company.name)
            )
    elif entity == "deal":
        if f.stage:
            where.append(Deal.stage.in_(f.stage))
        if f.company_id:
            where.append(Deal.company_id == f.company_id)
        if f.value_min is not None:
            where.append(Deal.value >= f.value_min)
        if f.value_max is not None:
            where.append(Deal.value <= f.value_max)
        if f.close_from:
            where.append(Deal.expected_close_date >= f.close_from)
        if f.close_to:
            where.append(Deal.expected_close_date <= f.close_to)
        if f.search:
            where.append(contains_any(f.search, Deal.title, Deal.stage, Company.name))
    else:
        if f.type:
            where.append(Activity.type == f.type)
        if f.status:
            where.append(Activity.status == f.status)
        if f.company_id:
            where.append(Activity.company_id == f.company_id)
        if f.contact_id:
            where.append(Activity.contact_id == f.contact_id)
        if f.due_from:
            where.append(Activity.due_date >= f.due_from)
        if f.due_to:
            where.append(Activity.due_date <= f.due_to)
        if f.overdue:
            where.append(Activity.due_date < today)
            where.append(Activity.status == ActivityStatus.PENDING)
        if f.search:
            where.append(contains_any(f.search, Activity.subject, Activity.type, Company.name, Contact.name))
    return stmt.where(*where)


def _order(entity: str, sort: str | None) -> list:
    model = MODELS[entity]
    if sort is None:
        if entity == "activity":
            return [Activity.due_date, Activity.created_at, Activity.id]
        return [model.created_at.desc(), model.id]
    if sort not in SORTS[entity]:
        raise ToolError(f"Invalid sort for {entity}. Allowed: {', '.join(sorted(SORTS[entity]))}.")
    desc = sort.startswith("-")
    key = sort.lstrip("-")
    attribute = {
        "name": "name",
        "title": "title",
        "value": "value",
        "closeDate": "expected_close_date",
        "dueDate": "due_date",
        "created": "created_at",
    }[key]
    column = getattr(model, attribute)
    return [column.desc() if desc else column, model.id]


# --- Row shaping --------------------------------------------------------------------


def _label(entity: str, obj: Any) -> str:
    if entity in ("company", "contact"):
        return obj.name
    if entity == "deal":
        return obj.title
    return obj.subject


def _source(entity: str, obj: Any) -> dict:
    return {"type": entity, "id": str(obj.id), "label": _label(entity, obj)}


def _names(db: Session, model: type, ids: set) -> dict:
    if not ids:
        return {}
    return {row.id: row.name for row in db.execute(select(model.id, model.name).where(model.id.in_(ids)))}


def _rows(db: Session, entity: str, objs: list) -> list[dict]:
    companies = _names(db, Company, {o.company_id for o in objs if hasattr(o, "company_id")})
    contacts = _names(db, Contact, {o.contact_id for o in objs if getattr(o, "contact_id", None)})
    rows = []
    for obj in objs:
        data = READ[entity].model_validate(obj).model_dump(mode="json", by_alias=True)
        data.pop("createdAt", None)
        data.pop("updatedAt", None)
        if entity == "deal":
            data["value"] = _money(obj.value)
        if entity != "company":
            data["companyName"] = companies.get(obj.company_id)
        if entity == "activity":
            data["contactName"] = contacts.get(obj.contact_id) if obj.contact_id else None
        rows.append(data)
    return rows


def _count(db: Session, stmt: Select) -> int:
    return db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0


# --- Read tools ---------------------------------------------------------------------


def search(db: Session, args: SearchArgs, today: date) -> dict:
    wanted = [args.entity] if args.entity else list(ENTITIES)
    columns = {
        "company": (Company.name,),
        "contact": (Contact.name, Contact.email),
        "deal": (Deal.title, Company.name),  # "the Summit deal" names the company
        "activity": (Activity.subject, Company.name),
    }
    matches: list[dict] = []
    sources: list[dict] = []
    truncated = False
    for entity in wanted:
        stmt = _base(entity).where(contains_any(args.query, *columns[entity])).order_by(*_order(entity, None))
        for obj in db.scalars(stmt.limit(SEARCH_LIMIT + 1)):
            if len(matches) >= SEARCH_LIMIT:
                truncated = True
                break
            company = obj if entity == "company" else db.get(Company, obj.company_id)
            label = f"{obj.name} <{obj.email}>" if entity == "contact" else _label(entity, obj)
            matches.append({"type": entity, "id": str(obj.id), "label": label, "companyName": company.name})
            sources.append(_source(entity, obj))
    return {"matches": matches, "truncated": truncated, "sources": sources}


def get_record(db: Session, args: GetRecordArgs, today: date) -> dict:
    obj = db.get(MODELS[args.entity], args.id)
    if obj is None:
        raise ToolError(f"No {args.entity} with that id.")
    record = _rows(db, args.entity, [obj])[0]
    related: dict[str, Any] = {}
    if args.entity == "company":
        open_deals = (Deal.company_id == obj.id, Deal.stage.in_(OPEN_STAGES))
        pipeline = db.scalar(select(func.coalesce(func.sum(Deal.value), 0)).where(*open_deals))
        related = {
            "contacts": _count(db, select(Contact).where(Contact.company_id == obj.id)),
            "deals": _count(db, select(Deal).where(Deal.company_id == obj.id)),
            "openDeals": _count(db, select(Deal).where(*open_deals)),
            "openPipelineValue": _money(pipeline),
            "pendingActivities": _count(
                db,
                select(Activity).where(Activity.company_id == obj.id, Activity.status == ActivityStatus.PENDING),
            ),
        }
    elif args.entity == "contact":
        related = {
            "activities": _count(db, select(Activity).where(Activity.contact_id == obj.id)),
            "pendingActivities": _count(
                db,
                select(Activity).where(Activity.contact_id == obj.id, Activity.status == ActivityStatus.PENDING),
            ),
        }
    return {"record": record, "related": related, "sources": [_source(args.entity, obj)]}


def list_records(db: Session, args: ListArgs, today: date) -> dict:
    stmt = _filtered(args.entity, _parse_filters(args.entity, args.filters), today)
    total = _count(db, stmt)  # SQL COUNT of every match; ignores limit
    objs = list(db.scalars(stmt.order_by(*_order(args.entity, args.sort)).limit(args.limit)))
    return {
        "total": total,
        "returned": len(objs),
        "rows": _rows(db, args.entity, objs),
        "sources": [_source(args.entity, o) for o in objs],
    }


GROUPS = {
    "company": {"status": Company.status, "industry": Company.industry, "location": Company.location},
    "contact": {"company": Company.name},
    "deal": {
        "stage": Deal.stage,
        "company": Company.name,
        "close_month": func.to_char(Deal.expected_close_date, "YYYY-MM"),
    },
    "activity": {
        "type": Activity.type,
        "status": Activity.status,
        "company": Company.name,
        "due_month": func.to_char(Activity.due_date, "YYYY-MM"),
    },
}


def aggregate(db: Session, args: AggregateArgs, today: date) -> dict:
    if args.metric != "count" and args.entity != "deal":
        raise ToolError(f"{args.metric} is only available for deals; use count for {args.entity} records.")
    if args.group_by is not None and args.group_by not in GROUPS[args.entity]:
        raise ToolError(f"Invalid group_by for {args.entity}. Allowed: {', '.join(GROUPS[args.entity])}.")
    base = _filtered(args.entity, _parse_filters(args.entity, args.filters), today)
    model = MODELS[args.entity]
    if args.metric == "count":
        metric = func.count(model.id)
    elif args.metric == "sum_value":
        metric = func.coalesce(func.sum(Deal.value), 0)
    else:
        metric = func.avg(Deal.value)
    group = GROUPS[args.entity][args.group_by] if args.group_by else None
    columns = [metric, func.count(model.id)] if group is None else [group, metric, func.count(model.id)]
    stmt = base.with_only_columns(*columns, maintain_column_froms=True).order_by(None)
    if group is not None:
        stmt = stmt.group_by(group).order_by(group)
    rows = []
    for row in db.execute(stmt):
        key, value, count = (None, row[0], row[1]) if group is None else (row[0], row[1], row[2])
        if hasattr(key, "value"):
            key = key.value
        if args.metric == "count":
            shown: Any = int(value)
        else:
            shown = _money(value) if value is not None else None
        rows.append({"group": key, "value": shown, "count": int(count)})
    return {"metric": args.metric, "groupBy": args.group_by, "rows": rows}


# --- Proposals ----------------------------------------------------------------------


def _input_of(entity: str, obj: Any) -> dict:
    """The record in the shape the frontend's create/update input takes (camelCase)."""
    keys = {to_camel(k) for k in CREATE[entity].model_fields}
    data = READ[entity].model_validate(obj).model_dump(mode="json", by_alias=True)
    return {k: v for k, v in data.items() if k in keys}


def _check_rules(db: Session, entity: str, data: Any, self_id: uuid.UUID | None) -> None:
    """The same rules the REST API enforces, without locking or writing."""
    if entity == "company":
        taken = db.scalar(
            select(Company.id).where(func.lower(Company.name) == data.name.lower(), Company.id != self_id)
        )
        if taken:
            raise ToolError("Invalid company.", {"name": "A company with this name already exists."})
        return
    if entity == "contact":
        taken = db.scalar(
            select(Contact.id).where(func.lower(Contact.email) == str(data.email).lower(), Contact.id != self_id)
        )
        if taken:
            raise ToolError("Invalid contact.", {"email": "A contact with this email already exists."})
    if db.get(Company, data.company_id) is None:
        raise ToolError(f"Invalid {entity}.", {"companyId": "That company does not exist."})
    if entity == "activity" and data.contact_id is not None:
        contact = db.get(Contact, data.contact_id)
        if contact is None:
            raise ToolError("Invalid activity.", {"contactId": "That contact does not exist."})
        if contact.company_id != data.company_id:
            raise ToolError(
                "Invalid activity.", {"contactId": "Contact belongs to a different company than the activity."}
            )


def _validated(db: Session, entity: str, merged: dict, self_id: uuid.UUID | None) -> dict:
    try:
        data = CREATE[entity].model_validate(merged)
    except ValidationError as exc:
        raise _validation_error(exc, entity) from None
    _check_rules(db, entity, data, self_id)
    return data.model_dump(mode="json", by_alias=True)


def _show(db: Session, key: str, value: Any) -> str:
    if value is None:
        return "none"
    if key == "companyId":
        company = db.get(Company, uuid.UUID(str(value)))
        return company.name if company else "unknown company"
    if key == "contactId":
        contact = db.get(Contact, uuid.UUID(str(value)))
        return contact.name if contact else "unknown contact"
    if key == "value":
        return _money(Decimal(str(value)))
    return str(value)


def _impact(db: Session, entity: str, obj: Any) -> dict | None:
    if entity == "company":
        return {
            "contacts": _count(db, select(Contact).where(Contact.company_id == obj.id)),
            "deals": _count(db, select(Deal).where(Deal.company_id == obj.id)),
            "activities": _count(db, select(Activity).where(Activity.company_id == obj.id)),
        }
    if entity == "contact":
        return {"activitiesLosingContact": _count(db, select(Activity).where(Activity.contact_id == obj.id))}
    return None


def propose_create(db: Session, args: ProposeCreateArgs, today: date) -> dict:
    new = _validated(db, args.entity, args.fields, None)
    shown = ", ".join(f"{k} {_show(db, k, v)}" for k, v in new.items() if v is not None)
    label = new.get("name") or new.get("title") or new.get("subject")
    return {
        "proposalId": str(uuid.uuid4()),
        "op": "create",
        "entity": args.entity,
        "input": new,
        "summary": f'Create {args.entity} "{label}": {shown}',
    }


def propose_update(db: Session, args: ProposeUpdateArgs, today: date) -> dict:
    obj = db.get(MODELS[args.entity], args.id)
    if obj is None:
        raise ToolError(f"No {args.entity} with that id.")
    try:
        update = UPDATE[args.entity].model_validate(args.changes)
    except ValidationError as exc:
        raise _validation_error(exc, f"{args.entity} changes") from None
    before = _input_of(args.entity, obj)
    changes = update.model_dump(mode="json", by_alias=True, exclude_unset=True)
    new = _validated(db, args.entity, before | changes, obj.id)
    diff = [k for k in new if new[k] != before.get(k)]
    if not diff:
        raise ToolError("No changes: the record already has these values.")
    parts = "; ".join(f"{k} {_show(db, k, before.get(k))} → {_show(db, k, new[k])}" for k in diff)
    return {
        "proposalId": str(uuid.uuid4()),
        "op": "update",
        "entity": args.entity,
        "id": str(obj.id),
        "input": new,
        "before": before,
        "summary": f'Update {args.entity} "{_label(args.entity, obj)}": {parts}',
    }


def _plural(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def propose_delete(db: Session, args: ProposeDeleteArgs, today: date) -> dict:
    obj = db.get(MODELS[args.entity], args.id)
    if obj is None:
        raise ToolError(f"No {args.entity} with that id.")
    impact = _impact(db, args.entity, obj)
    summary = f'Delete {args.entity} "{_label(args.entity, obj)}"'
    if args.entity == "company":
        summary += (
            f" (also deletes {_plural(impact['contacts'], 'contact', 'contacts')}, "
            f"{_plural(impact['deals'], 'deal', 'deals')}, "
            f"{_plural(impact['activities'], 'activity', 'activities')})"
        )
    elif args.entity == "contact":
        lose = impact["activitiesLosingContact"]
        summary += f" ({_plural(lose, 'activity', 'activities')} will lose this contact)"
    return {
        "proposalId": str(uuid.uuid4()),
        "op": "delete",
        "entity": args.entity,
        "id": str(obj.id),
        "before": _input_of(args.entity, obj),
        "impact": impact,
        "summary": summary,
    }


# --- Navigation ---------------------------------------------------------------------


def navigate(db: Session, args: NavigateArgs, today: date) -> dict:
    allowed = PAGE_FILTERS[args.page]
    params: dict[str, str] = {}
    for key, value in args.filters.items():
        if key not in allowed:
            raise ToolError(f"Filter '{key}' is not available on {args.page}. Allowed: {', '.join(allowed) or 'none'}.")
        try:
            params[key] = allowed[key](value)
        except ValueError:
            raise ToolError(f"Invalid value for filter '{key}' on {args.page}.") from None
    label = f"Open {args.page.capitalize()}"
    if params:
        label += " (" + ", ".join(f"{k}: {v}" for k, v in params.items()) + ")"
    if args.open_id is not None:
        if args.page == "dashboard":
            raise ToolError("The dashboard has no records to open.")
        entity = PAGE_ENTITY[args.page]
        obj = db.get(MODELS[entity], args.open_id)
        if obj is None:
            raise ToolError(f"No {entity} with that id.")
        params["open"] = str(obj.id)
        label = f'Open {entity} "{_label(entity, obj)}"'
    href = "/" if args.page == "dashboard" else f"/{args.page}"
    if params:
        href += "?" + urlencode(params)
    return {"action": {"type": "navigate", "label": label, "href": href}}


# --- Registry -----------------------------------------------------------------------


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args: type[ToolArgs]
    fn: Callable[[Session, Any, date], dict]


TOOLS: dict[str, Tool] = {
    t.name: t
    for t in (
        Tool(
            "search",
            "Find records by name/email/title/subject text. Always use this to resolve a name to an id before "
            "calling other tools. If several records match, ask the user which one.",
            SearchArgs,
            search,
        ),
        Tool("get_record", "Get one record by id, with related counts.", GetRecordArgs, get_record),
        Tool(
            "list_records",
            "List records with filters. `total` is the exact number of matches (ignores limit); quote it "
            "for 'how many'.",
            ListArgs,
            list_records,
        ),
        Tool(
            "aggregate",
            "Exact counts, sums and averages computed by the database, optionally grouped. Use this for any "
            "number, total or breakdown; never add numbers yourself.",
            AggregateArgs,
            aggregate,
        ),
        Tool(
            "propose_create",
            "Propose creating a record. Nothing is saved until the user confirms in the UI.",
            ProposeCreateArgs,
            propose_create,
        ),
        Tool(
            "propose_update",
            "Propose changing fields of a record. Nothing is saved until the user confirms in the UI.",
            ProposeUpdateArgs,
            propose_update,
        ),
        Tool(
            "propose_delete",
            "Propose deleting a record (shows what else gets deleted). Nothing is deleted until the user confirms.",
            ProposeDeleteArgs,
            propose_delete,
        ),
        Tool(
            "navigate",
            "Give the user a button that opens a CRM page, optionally filtered or with one record open. "
            "Never write URLs yourself.",
            NavigateArgs,
            navigate,
        ),
    )
}


def tool_specs() -> list[dict]:
    """The tools in the OpenAI function-calling format."""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.args.model_json_schema(by_alias=True),
            },
        }
        for t in TOOLS.values()
    ]


def run_tool(db: Session, name: str, raw_args: dict | str | None, today: date) -> dict:
    """Run one tool call. Always returns a dict; failures become {"error": ...} for the model."""
    tool = TOOLS.get(name)
    if tool is None:
        return {"error": f"Unknown tool '{name}'. Available: {', '.join(TOOLS)}."}
    try:
        if isinstance(raw_args, str):
            raw_args = json.loads(raw_args) if raw_args.strip() else {}
        args = tool.args.model_validate(raw_args or {})
        return tool.fn(db, args, today)
    except json.JSONDecodeError:
        return {"error": "Tool arguments were not valid JSON."}
    except ValidationError as exc:
        err = _validation_error(exc, f"arguments for {name}")
        return {"error": err.message, "fieldErrors": err.field_errors}
    except ToolError as exc:
        out: dict[str, Any] = {"error": exc.message}
        if exc.field_errors:
            out["fieldErrors"] = exc.field_errors
        return out
