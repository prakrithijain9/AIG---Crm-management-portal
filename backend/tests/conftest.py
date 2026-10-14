"""Shared fixtures for database tests.

Database tests run against a separate database (TEST_DB_NAME, default aig_crm_test),
never the development database. The schema is built by running the real Alembic
migrations, and each test runs inside a transaction that is rolled back afterwards.

API tests use `client` (a signed-in admin) or `anon_client` (no session), with a
test-only JWT secret instead of the one in backend/.env.
"""

from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Connection, Engine, create_engine, pool, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.config import BACKEND_DIR, Settings, get_settings
from app.core.security import CSRF_HEADER_NAME, SESSION_COOKIE_NAME, create_session_token, hash_password
from app.db.session import get_db
from app.main import app
from app.models import AdminUser


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

    # hide_parameters, as in production: bound values never appear in logs or error messages.
    engine = create_engine(settings.test_database_url, poolclass=pool.NullPool, hide_parameters=True)
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


# --- API clients and authentication ------------------------------------------------

# Test-only values. API tests never use JWT_SECRET_KEY from backend/.env.
TEST_JWT_SECRET = "test-only-jwt-signing-secret-" + "x" * 32
TEST_ADMIN_USERNAME = "test-admin"
TEST_ADMIN_PASSWORD = "test-only-password-1234"


@pytest.fixture(scope="session")
def auth_settings() -> Settings:
    """App settings with a dummy signing secret; cookies are not Secure (plain-http TestClient)."""
    return get_settings().model_copy(
        update={"environment": "test", "jwt_secret_key": SecretStr(TEST_JWT_SECRET), "cookie_secure": None}
    )


@pytest.fixture(scope="session")
def test_admin_password_hash() -> str:
    # Hashed once per run: Argon2id is deliberately slow.
    return hash_password(TEST_ADMIN_PASSWORD)


@pytest.fixture
def api_app(connection: Connection, auth_settings: Settings) -> Iterator[FastAPI]:
    """The app wired to the rolled-back test-database connection and the test settings.

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
    app.dependency_overrides[get_settings] = lambda: auth_settings
    try:
        yield app
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_settings, None)


@pytest.fixture
def admin(connection: Connection, test_admin_password_hash: str) -> AdminUser:
    """An active admin in the test database (rolled back after the test)."""
    session = new_session(connection)
    try:
        user = AdminUser(username=TEST_ADMIN_USERNAME, password_hash=test_admin_password_hash)
        session.add(user)
        session.commit()
        return user
    finally:
        session.close()


def sign_in(client: TestClient, admin: AdminUser, settings: Settings) -> str:
    """Give `client` a real session for `admin` (cookie + CSRF header) without the slow login hash."""
    token, claims = create_session_token(admin.id, admin.token_version, settings)
    client.cookies.set(SESSION_COOKIE_NAME, token)
    client.headers[CSRF_HEADER_NAME] = claims.csrf_token
    return token


@pytest.fixture
def anon_client(api_app: FastAPI) -> Iterator[TestClient]:
    """No session: every CRM route must reject it."""
    with TestClient(api_app) as c:
        yield c


@pytest.fixture
def client(api_app: FastAPI, admin: AdminUser, auth_settings: Settings) -> Iterator[TestClient]:
    """Signed-in admin client. Goes through the real auth and CSRF checks (no overrides)."""
    with TestClient(api_app) as c:
        sign_in(c, admin, auth_settings)
        yield c
