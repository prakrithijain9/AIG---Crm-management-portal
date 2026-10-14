from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness: the API process is up. Does not touch the database."""
    return {"status": "ok"}


@router.get("/health/db")
def health_db(db: Session = Depends(get_db)) -> dict[str, str]:
    """Readiness: run a real query against PostgreSQL."""
    try:
        db.execute(text("SELECT 1")).scalar_one()
        version = db.execute(text("SHOW server_version")).scalar_one()
        database = db.execute(text("SELECT current_database()")).scalar_one()
    except SQLAlchemyError as exc:
        # Report the error type only; never echo connection details.
        raise HTTPException(
            status_code=503,
            detail=f"database unavailable ({type(exc).__name__})",
        ) from exc
    return {"status": "ok", "database": database, "server_version": version}
