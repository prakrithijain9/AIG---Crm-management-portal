"""Describe database errors without the data that caused them.

str() of a SQLAlchemy/psycopg error can contain row values: PostgreSQL's DETAIL line
("Failing row contains (...)", "Key (...)=(...) already exists") and, on engines without
hide_parameters=True, the bound parameters. For sensitive tables such as admin_users those
values include password hashes, so error handling there must log and show only what these
helpers return, and re-raise with `from None` so the original error is not chained.
"""

from collections.abc import Mapping

from sqlalchemy.exc import DBAPIError


def db_error_details(exc: DBAPIError) -> tuple[str | None, str | None]:
    """(SQLSTATE code, constraint name). Neither ever contains row values."""
    orig = exc.orig
    sqlstate = getattr(orig, "sqlstate", None)
    constraint = getattr(getattr(orig, "diag", None), "constraint_name", None)
    return sqlstate, constraint


def safe_db_error_summary(exc: DBAPIError) -> str:
    """A one-line description that is safe to log, e.g. 'IntegrityError (sqlstate=23505, constraint=...)'."""
    sqlstate, constraint = db_error_details(exc)
    return f"{type(exc).__name__} (sqlstate={sqlstate}, constraint={constraint})"


def safe_db_error_message(exc: DBAPIError, messages: Mapping[str, str], default: str) -> str:
    """A user-facing message: the one registered for the violated constraint, else `default`."""
    _, constraint = db_error_details(exc)
    return messages.get(constraint or "", default)
