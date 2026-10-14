"""Sign-in, sessions, CSRF, logout and route protection, against the test database."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from pydantic import SecretStr
from sqlalchemy import select, update

from app.api.auth import CSRF_FAILED, INVALID_CREDENTIALS, NOT_AUTHENTICATED, ORIGIN_NOT_ALLOWED
from app.core.config import get_settings
from app.core.security import (
    CSRF_HEADER_NAME,
    MAX_PASSWORD_LENGTH,
    SESSION_COOKIE_NAME,
    create_session_token,
    verify_password,
)
from app.main import app
from app.models import AdminUser
from tests.api_helpers import company_payload
from tests.conftest import TEST_ADMIN_PASSWORD, TEST_ADMIN_USERNAME, sign_in

LOGIN, LOGOUT, ME = "/api/auth/login", "/api/auth/logout", "/api/auth/me"
EVIL_ORIGIN = "https://evil.example"


def login(client, username=TEST_ADMIN_USERNAME, password=TEST_ADMIN_PASSWORD, **kwargs):
    return client.post(LOGIN, json={"username": username, "password": password}, **kwargs)


def use_settings(api_app, settings):
    """Swap the settings the app sees for the rest of this test (api_app restores them)."""
    api_app.dependency_overrides[get_settings] = lambda: settings


def set_admin(db, admin, **values):
    db.execute(update(AdminUser).where(AdminUser.id == admin.id).values(**values))
    db.commit()


# --- Login -----------------------------------------------------------------------------


def test_login_sets_an_httponly_session_cookie(anon_client, admin, auth_settings):
    response = login(anon_client)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["username"] == TEST_ADMIN_USERNAME
    assert set(body) == {"username", "csrfToken", "expiresAt"}
    assert response.headers["cache-control"] == "no-store"

    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{SESSION_COOKIE_NAME}=")
    attributes = [part.strip().lower() for part in cookie.split(";")]
    assert "httponly" in attributes
    assert "samesite=lax" in attributes
    assert "path=/" in attributes
    assert f"max-age={auth_settings.jwt_expire_minutes * 60}" in attributes
    assert "secure" not in attributes  # test settings: plain http
    token = cookie.split(";")[0].split("=", 1)[1]
    assert token not in response.text  # the JWT is only in the HttpOnly cookie

    me = anon_client.get(ME)  # the TestClient now sends the cookie
    assert me.status_code == 200
    assert me.json()["csrfToken"] == body["csrfToken"]


def test_cookie_is_secure_when_configured(api_app, anon_client, admin, auth_settings):
    use_settings(api_app, auth_settings.model_copy(update={"cookie_secure": True}))
    cookie = login(anon_client).headers["set-cookie"].lower()
    assert "secure" in [part.strip() for part in cookie.split(";")]


def test_login_username_is_case_insensitive(anon_client, admin):
    assert login(anon_client, username=TEST_ADMIN_USERNAME.upper()).status_code == 200


@pytest.mark.parametrize(
    "body",
    [
        {"username": TEST_ADMIN_USERNAME, "password": "wrong-password-123"},
        {"username": "nobody", "password": TEST_ADMIN_PASSWORD},
        {"username": f" {TEST_ADMIN_USERNAME}", "password": TEST_ADMIN_PASSWORD},
        {"username": f"{TEST_ADMIN_USERNAME}\t", "password": TEST_ADMIN_PASSWORD},
        {"username": TEST_ADMIN_USERNAME, "password": TEST_ADMIN_PASSWORD + " "},
        {"username": TEST_ADMIN_USERNAME, "password": TEST_ADMIN_PASSWORD + "x" * MAX_PASSWORD_LENGTH},
        {"username": TEST_ADMIN_USERNAME},
        {"password": TEST_ADMIN_PASSWORD},
        {},
    ],
)
def test_failed_logins_look_identical(anon_client, admin, body):
    response = anon_client.post(LOGIN, json=body)
    assert response.status_code == 401
    assert response.json() == {"detail": INVALID_CREDENTIALS}
    assert "set-cookie" not in response.headers
    assert TEST_ADMIN_PASSWORD not in response.text


def test_inactive_admin_cannot_log_in(anon_client, admin, db):
    set_admin(db, admin, is_active=False)
    response = login(anon_client)
    assert response.status_code == 401
    assert response.json() == {"detail": INVALID_CREDENTIALS}


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": EVIL_ORIGIN},
        {"Origin": "null"},
        {"Referer": f"{EVIL_ORIGIN}/login"},
        {"Sec-Fetch-Site": "cross-site"},
        {"Sec-Fetch-Site": "same-site"},
    ],
)
def test_login_rejects_cross_site_requests(anon_client, admin, headers):
    response = login(anon_client, headers=headers)
    assert response.status_code == 403
    assert response.json() == {"detail": ORIGIN_NOT_ALLOWED}
    assert "set-cookie" not in response.headers


def test_login_accepts_trusted_origin(anon_client, admin, auth_settings):
    origin = auth_settings.trusted_origin_list[0]
    headers = {"Origin": origin, "Referer": f"{origin}/login", "Sec-Fetch-Site": "same-origin"}
    assert login(anon_client, headers=headers).status_code == 200


def test_login_without_a_signing_secret_is_unavailable(api_app, anon_client, admin, auth_settings):
    use_settings(api_app, auth_settings.model_copy(update={"jwt_secret_key": None}))
    response = login(anon_client)
    assert response.status_code == 503
    assert "set-cookie" not in response.headers


def test_login_upgrades_an_outdated_hash(anon_client, admin, db):
    weak = PasswordHash((Argon2Hasher(time_cost=1, memory_cost=8192, parallelism=1),)).hash(TEST_ADMIN_PASSWORD)
    set_admin(db, admin, password_hash=weak)
    assert login(anon_client).status_code == 200
    stored = db.scalar(select(AdminUser.password_hash).where(AdminUser.id == admin.id))
    assert stored != weak
    assert verify_password(TEST_ADMIN_PASSWORD, stored) == (True, None)


# --- Current session (/me) ------------------------------------------------------------


def test_me_returns_the_admin_and_csrf_token(client):
    response = client.get(ME)
    assert response.status_code == 200
    body = response.json()
    assert body["username"] == TEST_ADMIN_USERNAME
    assert body["csrfToken"] == client.headers[CSRF_HEADER_NAME]
    assert response.headers["cache-control"] == "no-store"


def test_me_without_a_session(anon_client):
    response = anon_client.get(ME)
    assert response.status_code == 401
    assert response.json() == {"detail": NOT_AUTHENTICATED}


def _client_with_token(anon_client, token):
    anon_client.cookies.set(SESSION_COOKIE_NAME, token)
    return anon_client


@pytest.mark.parametrize("token", ["", "garbage", "a.b.c"])
def test_garbage_session_cookie(anon_client, token):
    assert _client_with_token(anon_client, token).get(ME).status_code == 401


def test_expired_session(anon_client, admin, auth_settings):
    past = datetime.now(UTC) - timedelta(minutes=auth_settings.jwt_expire_minutes + 1)
    token, _ = create_session_token(admin.id, admin.token_version, auth_settings, now=past)
    response = _client_with_token(anon_client, token).get(ME)
    assert response.status_code == 401
    assert response.json() == {"detail": NOT_AUTHENTICATED}


@pytest.mark.parametrize(
    "update",
    [
        {"jwt_secret_key": SecretStr("test-only-a-different-signing-secret-" + "d" * 32)},
        {"jwt_issuer": "someone-else"},
        {"jwt_audience": "another-app"},
    ],
)
def test_token_signed_for_something_else(anon_client, admin, auth_settings, update):
    token, _ = create_session_token(admin.id, admin.token_version, auth_settings.model_copy(update=update))
    assert _client_with_token(anon_client, token).get(ME).status_code == 401


def test_token_for_a_missing_admin(anon_client, auth_settings, admin):
    token, _ = create_session_token(uuid.uuid4(), 0, auth_settings)
    assert _client_with_token(anon_client, token).get(ME).status_code == 401


def test_deactivated_admin_loses_existing_sessions(client, admin, db):
    assert client.get(ME).status_code == 200
    set_admin(db, admin, is_active=False)
    assert client.get(ME).status_code == 401
    assert client.get("/api/companies").status_code == 401


def test_bumping_token_version_revokes_sessions(client, admin, db):
    set_admin(db, admin, token_version=AdminUser.token_version + 1)
    assert client.get(ME).status_code == 401
    assert client.get("/api/companies").status_code == 401


# --- CSRF on CRM writes ------------------------------------------------------------------


def test_reads_do_not_need_the_csrf_header(client):
    del client.headers[CSRF_HEADER_NAME]
    assert client.get("/api/companies").status_code == 200


@pytest.mark.parametrize("csrf", [None, "", "wrong-token"])
def test_writes_need_the_sessions_csrf_token(client, csrf):
    if csrf is None:
        del client.headers[CSRF_HEADER_NAME]
    else:
        client.headers[CSRF_HEADER_NAME] = csrf
    response = client.post("/api/companies", json=company_payload())
    assert response.status_code == 403
    assert response.json() == {"detail": CSRF_FAILED}


def test_csrf_applies_to_patch_and_delete(client):
    created = client.post("/api/companies", json=company_payload())
    assert created.status_code == 201
    company_id = created.json()["id"]
    good = client.headers[CSRF_HEADER_NAME]

    client.headers[CSRF_HEADER_NAME] = "wrong-token"
    assert client.patch(f"/api/companies/{company_id}", json={"industry": "X"}).status_code == 403
    assert client.delete(f"/api/companies/{company_id}").status_code == 403

    client.headers[CSRF_HEADER_NAME] = good
    assert client.patch(f"/api/companies/{company_id}", json={"industry": "X"}).status_code == 200
    assert client.delete(f"/api/companies/{company_id}").status_code == 204


def test_csrf_token_from_another_session_is_rejected(client, admin, auth_settings):
    _, other = create_session_token(admin.id, admin.token_version, auth_settings)
    client.headers[CSRF_HEADER_NAME] = other.csrf_token
    assert client.post("/api/companies", json=company_payload()).status_code == 403


@pytest.mark.parametrize("headers", [{"Origin": EVIL_ORIGIN}, {"Sec-Fetch-Site": "cross-site"}])
def test_cross_site_writes_are_rejected_even_with_the_token(client, headers):
    response = client.post("/api/companies", json=company_payload(), headers=headers)
    assert response.status_code == 403
    assert response.json() == {"detail": ORIGIN_NOT_ALLOWED}


def test_same_origin_writes_are_accepted(client, auth_settings):
    headers = {"Origin": auth_settings.trusted_origin_list[0], "Sec-Fetch-Site": "same-origin"}
    assert client.post("/api/companies", json=company_payload(), headers=headers).status_code == 201


# --- Logout ---------------------------------------------------------------------------


def test_logout_revokes_the_session_and_clears_the_cookie(client, admin, db):
    old_token = client.cookies.get(SESSION_COOKIE_NAME)
    response = client.post(LOGOUT)
    assert response.status_code == 204
    cookie = response.headers["set-cookie"].lower()
    assert cookie.startswith(f"{SESSION_COOKIE_NAME}=")
    assert "max-age=0" in cookie and "httponly" in cookie

    version = db.scalar(select(AdminUser.token_version).where(AdminUser.id == admin.id))
    assert version == admin.token_version + 1

    client.cookies.set(SESSION_COOKIE_NAME, old_token)  # a copied token no longer works
    assert client.get(ME).status_code == 401
    assert client.get("/api/companies").status_code == 401


def test_logout_without_a_session_just_clears_the_cookie(anon_client):
    response = anon_client.post(LOGOUT)
    assert response.status_code == 204
    assert "max-age=0" in response.headers["set-cookie"].lower()


def test_logout_needs_the_csrf_token(client):
    del client.headers[CSRF_HEADER_NAME]
    response = client.post(LOGOUT)
    assert response.status_code == 403
    assert "set-cookie" not in response.headers
    assert client.get(ME).status_code == 200  # still signed in


def test_logout_rejects_cross_site_requests(client):
    assert client.post(LOGOUT, headers={"Origin": EVIL_ORIGIN}).status_code == 403
    assert client.get(ME).status_code == 200


def test_login_after_logout_works(client):
    assert client.post(LOGOUT).status_code == 204
    del client.headers[CSRF_HEADER_NAME]
    assert login(client).status_code == 200
    assert client.get(ME).status_code == 200


# --- Every CRM route is protected -----------------------------------------------------

PUBLIC_API_ROUTES = {("POST", LOGIN), ("POST", LOGOUT), ("GET", ME)}  # ME is 401 without a session anyway


def _api_routes():
    # From the OpenAPI schema: FastAPI nests included routers, so app.routes is not flat.
    for path, operations in sorted(app.openapi()["paths"].items()):
        if path.startswith("/api/"):
            for method in sorted(operations):
                yield method.upper(), path


CRM_ROUTES = [(m, p) for m, p in _api_routes() if (m, p) not in PUBLIC_API_ROUTES]


def test_every_crm_router_is_covered():
    prefixes = {path.split("/")[2] for _, path in CRM_ROUTES}
    assert prefixes == {"companies", "contacts", "deals", "activities"}
    assert len(CRM_ROUTES) == 20  # list, create, get, update, delete for each


@pytest.mark.parametrize(("method", "path"), CRM_ROUTES)
def test_crm_routes_reject_anonymous_requests(anon_client, method, path):
    url = path.replace("{", "").replace("}", "")
    for name in ("company_id", "contact_id", "deal_id", "activity_id"):
        url = url.replace(name, str(uuid.uuid4()))
    response = anon_client.request(method, url, json={})
    assert response.status_code == 401, f"{method} {path} -> {response.status_code}"
    assert response.json() == {"detail": NOT_AUTHENTICATED}


def test_health_endpoints_stay_public(anon_client):
    assert anon_client.get("/health").status_code == 200
    response = anon_client.get("/health/db")
    assert response.status_code == 200
    assert response.json()["database"] == get_settings().test_db_name


def test_auth_errors_never_include_secrets(anon_client, admin, db, test_admin_password_hash):
    responses = [
        login(anon_client, password="wrong-password-123"),
        anon_client.get(ME),
        anon_client.get("/api/companies"),
    ]
    for response in responses:
        for secret in (test_admin_password_hash, TEST_ADMIN_PASSWORD, "SELECT", "sqlalchemy", "psycopg"):
            assert secret not in response.text


def test_no_registration_endpoint():
    paths = set(app.openapi()["paths"])
    assert not any("register" in p or "signup" in p for p in paths)
    assert {p for p in paths if p.startswith("/api/auth")} == {LOGIN, LOGOUT, ME}
