"""Helpers shared by the CRUD routers: sessions, pagination, search, lookups, errors."""

import logging
import uuid
from dataclasses import dataclass
from typing import Annotated, NoReturn, TypeVar

from fastapi import Depends, HTTPException, Query, Response, status
from pydantic.alias_generators import to_camel
from sqlalchemy import ColumnElement, Select, String, cast, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Base  # importing app.models registers every table on Base.metadata
from app.db.session import get_db

logger = logging.getLogger(__name__)

DbSession = Annotated[Session, Depends(get_db)]

T = TypeVar("T", bound=Base)


# --- Pagination ---------------------------------------------------------------------


@dataclass
class Page:
    limit: int
    offset: int


def page_params(
    limit: Annotated[int, Query(ge=1, le=500, description="Max items to return")] = 100,
    offset: Annotated[int, Query(ge=0, description="Items to skip")] = 0,
) -> Page:
    return Page(limit=limit, offset=offset)


PageParams = Annotated[Page, Depends(page_params)]


def paginated(db: Session, stmt: Select, page: Page, response: Response) -> list:
    """Run a list query, putting the total (before limit/offset) in X-Total-Count."""
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    response.headers["X-Total-Count"] = str(total)
    return list(db.scalars(stmt.limit(page.limit).offset(page.offset)))


def contains_any(term: str, *columns) -> ColumnElement[bool]:
    """Case-insensitive 'contains' across columns; % and _ in the term are matched literally."""
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{escaped}%"
    return or_(*(cast(col, String).ilike(pattern, escape="\\") for col in columns))


# --- Lookups and errors -----------------------------------------------------------


def unprocessable(field: str, message: str) -> NoReturn:
    """422 in the same shape FastAPI uses for its own validation errors."""
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=[{"loc": ["body", field], "msg": message, "type": "value_error"}],
    )


def get_or_404(db: Session, model: type[T], obj_id: uuid.UUID, *, lock: bool | dict = False) -> T:
    """Fetch by primary key or raise 404. `lock` adds SELECT ... FOR UPDATE (or FOR SHARE via {"read": True})."""
    obj = db.get(model, obj_id, with_for_update=lock or None, populate_existing=bool(lock))
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{model.__name__} not found")
    return obj


def require_reference(db: Session, model: type[T], obj_id: uuid.UUID, field: str, *, lock: bool | dict = False) -> T:
    """Like get_or_404, but for an id inside the request body: a missing record is a 422."""
    obj = db.get(model, obj_id, with_for_update=lock or None, populate_existing=bool(lock))
    if obj is None:
        unprocessable(field, f"{model.__name__} {obj_id} does not exist.")
    return obj


UNIQUE_MESSAGES = {
    "uq_companies_name_lower": ("name", "A company with this name already exists."),
    "uq_contacts_email_lower": ("email", "A contact with this email already exists."),
}

# FK constraint name -> camelCase field it belongs to, derived from the models.
FK_FIELDS = {
    fk.name: to_camel(fk.column_keys[0])
    for table in Base.metadata.tables.values()
    for fk in table.foreign_key_constraints
}


def commit(db: Session) -> None:
    """Commit the request's transaction; turn integrity errors into clean HTTP errors.

    Python-side checks catch most problems first with friendlier messages; this is the
    safety net for races (e.g. two requests creating the same company at once) and for
    rules only the database knows, like case-insensitive uniqueness.
    """
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _http_error_for(exc) from None


def _http_error_for(exc: IntegrityError) -> HTTPException:
    orig = exc.orig
    sqlstate = getattr(orig, "sqlstate", None)
    constraint = getattr(getattr(orig, "diag", None), "constraint_name", None)
    # Log only the constraint name: never row values or connection details.
    logger.info("Integrity error sqlstate=%s constraint=%s", sqlstate, constraint)

    if sqlstate == "23505":  # unique_violation
        _, message = UNIQUE_MESSAGES.get(constraint, (None, "This conflicts with an existing record."))
        return HTTPException(status.HTTP_409_CONFLICT, message)
    if sqlstate == "23503":  # foreign_key_violation
        field = FK_FIELDS.get(constraint, "body")
        return HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            [{"loc": ["body", field], "msg": "Referenced record does not exist.", "type": "value_error"}],
        )
    if sqlstate in ("23502", "23514"):  # not_null_violation, check_violation
        return HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            [{"loc": ["body"], "msg": f"Value violates database rule '{constraint}'.", "type": "value_error"}],
        )
    return HTTPException(status.HTTP_409_CONFLICT, "This conflicts with an existing record.")
