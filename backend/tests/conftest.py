"""Shared fixtures for database tests.

Database tests run against a separate database (TEST_DB_NAME, default aig_crm_test),
never the development database. The schema is built by running the real Alembic
migrations, and each test runs inside a transaction that is rolled back afterwards.
"""

from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, create_engine, pool, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.config import BACKEND_DIR, get_settings
from app.db.session import get_db
from app.main import app


def alembic_config(connection) -> Config:
    # No ini file: avoids reconfiguring logging during tests.
    cfg = Config()
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.attributes["connection"] = connection
    return cfg


@pytest.fixture(scope="session")
def test_engine() -> Iterator[Engine]:
    settings = get_settings()
    name = settings.test_db_name
    if name == settings.db_name or not name.endswith("_test"):
        pytest.exit(
            f"Refusing to run: TEST_DB_NAME '{name}' must differ from DB_NAME and end with '_test'.",
            returncode=1,
        )

    engine = create_engine(settings.test_database_url, poolclass=pool.NullPool)
    try:
        engine.connect().close()
        reachable = True
    except OperationalError:
        reachable = False
    if not reachable:
        pytest.fail(
            f"Test database '{name}' is not reachable. "
            "Create it with: .venv\\Scripts\\python scripts\\create_dev_db.py",
            pytrace=False,
        )

    # Rebuild the test schema from the migrations so every run starts clean.
    with engine.begin() as conn:
        cfg = alembic_config(conn)
        command.downgrade(cfg, "base")
        command.upgrade(cfg, "head")

    yield engine
    engine.dispose()


@pytest.fixture
def connection(test_engine: Engine) -> Iterator[Connection]:
    """A test-database connection inside a transaction that is always rolled back."""
    with test_engine.connect() as conn:
        outer = conn.begin()
        try:
            yield conn
        finally:
            outer.rollback()


def new_session(conn: Connection) -> Session:
    # commit() inside the app only releases a SAVEPOINT; the outer transaction stays open.
    return Session(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)


@pytest.fixture
def db(connection: Connection) -> Iterator[Session]:
    session = new_session(connection)
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(connection: Connection) -> Iterator[TestClient]:
    """API client whose requests use the rolled-back test-database connection.

    Each request gets its own session (as in production), so nothing is cached between requests.
    """
    current_db = connection.execute(text("SELECT current_database()")).scalar_one()
    assert current_db == get_settings().test_db_name, "API tests must run against the test database"

    def override_get_db() -> Iterator[Session]:
        session = new_session(connection)
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_db, None)
