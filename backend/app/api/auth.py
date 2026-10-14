"""Admin sign-in: login, logout and the current session, plus the guard for CRM routes.

Sessions live in an HttpOnly cookie, so browsers send them automatically; state-changing
requests are therefore also checked for CSRF:
  * Origin (or Referer) must be a trusted origin when present, and Sec-Fetch-Site, when
    present, must be same-origin or none. This also guards login and logout.
  * Authenticated writes must echo the session's CSRF token in X-CSRF-Token. A cross-site
    page cannot read that token, and cannot set custom headers without a CORS preflight.
Errors are fixed strings: no tokens, hashes, SQL or database details.
"""

import logging
from dataclasses import dataclass
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError

from app.api.common import DbSession
from app.core.config import Settings, canonical_origin, get_settings
from app.core.security import (
    CSRF_HEADER_NAME,
    MAX_PASSWORD_LENGTH,
    SESSION_COOKIE_NAME,
    AuthNotConfigured,
    InvalidSession,
    SessionClaims,
    create_session_token,
    csrf_tokens_match,
    decode_session_token,
    ensure_auth_configured,
    verify_password,
)
from app.db.errors import safe_db_error_summary
from app.models import AdminUser
from app.models.admin_user import InvalidUsername, username_lookup_key
from app.schemas.auth import LoginRequest, SessionRead

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

AppSettings = Annotated[Settings, Depends(get_settings)]

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

NOT_AUTHENTICATED = "Not authenticated."
INVALID_CREDENTIALS = "Invalid username or password."
CSRF_FAILED = "CSRF check failed."
ORIGIN_NOT_ALLOWED = "Request origin is not allowed."
AUTH_UNAVAILABLE = "Sign-in is not configured on the server."


def _unauthorized(detail: str = NOT_AUTHENTICATED) -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail)


def _forbidden(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_403_FORBIDDEN, detail)


def _unavailable() -> HTTPException:
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, AUTH_UNAVAILABLE)


# --- CSRF: origin checks --------------------------------------------------------------


def _request_origin(request: Request) -> str | None:
    """The browser-supplied origin: Origin, else the origin part of Referer, else None."""
    origin = request.headers.get("origin")
    if origin is not None:
        return origin
    referer = request.headers.get("referer")
    if referer:
        parts = urlsplit(referer)
        return f"{parts.scheme}://{parts.netloc}" if parts.scheme and parts.netloc else "null"
    return None


def check_request_origin(request: Request, settings: Settings) -> None:
    """Reject cross-site requests. Requests without browser origin headers (CLI tools, tests)
    pass this check; for authenticated writes the CSRF token still applies to them."""
    fetch_site = request.headers.get("sec-fetch-site")
    if fetch_site is not None and fetch_site not in ("same-origin", "none"):
        raise _forbidden(ORIGIN_NOT_ALLOWED)
    origin = _request_origin(request)
    if origin is not None and canonical_origin(origin) not in settings.trusted_origin_list:
        raise _forbidden(ORIGIN_NOT_ALLOWED)


# --- Session dependencies ---------------------------------------------------------------


@dataclass(frozen=True)
class CurrentSession:
    admin: AdminUser
    claims: SessionClaims


def _load_session(token: str | None, db, settings: Settings) -> CurrentSession:
    if not token:
        raise _unauthorized()
    try:
        claims = decode_session_token(token, settings)
    except AuthNotConfigured:
        raise _unavailable() from None
    except InvalidSession:
        raise _unauthorized() from None
    admin = db.get(AdminUser, claims.admin_id)
    # Deleted, deactivated, or revoked (token_version bumped by logout or a password change).
    if admin is None or not admin.is_active or admin.token_version != claims.token_version:
        raise _unauthorized()
    return CurrentSession(admin=admin, claims=claims)


def get_current_session(request: Request, db: DbSession, settings: AppSettings) -> CurrentSession:
    """Any valid session (reads included). Use require_admin for routes."""
    return _load_session(request.cookies.get(SESSION_COOKIE_NAME), db, settings)


def require_admin(
    request: Request,
    session: Annotated[CurrentSession, Depends(get_current_session)],
    settings: AppSettings,
) -> CurrentSession:
    """Guard for every CRM route: a valid session, plus CSRF checks on state-changing methods."""
    if request.method not in SAFE_METHODS:
        check_request_origin(request, settings)
        if not csrf_tokens_match(session.claims.csrf_token, request.headers.get(CSRF_HEADER_NAME)):
            raise _forbidden(CSRF_FAILED)
    return session


# --- Cookie helpers ---------------------------------------------------------------------


def _cookie_options(settings: Settings) -> dict:
    # Path=/ so Next.js's proxy can see it on page requests; SameSite=Lax blocks it on
    # cross-site subresource and form POSTs while still allowing top-level navigation.
    return {"httponly": True, "secure": settings.session_cookie_secure, "samesite": "lax", "path": "/"}


def _set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        SESSION_COOKIE_NAME, token, max_age=settings.jwt_expire_minutes * 60, **_cookie_options(settings)
    )


def _clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME, **_cookie_options(settings))


def _session_body(session_claims: SessionClaims, username: str) -> SessionRead:
    return SessionRead(username=username, csrf_token=session_claims.csrf_token, expires_at=session_claims.expires_at)


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


# --- Endpoints ------------------------------------------------------------------------


@router.post("/login", response_model=SessionRead)
def login(payload: LoginRequest, request: Request, response: Response, db: DbSession, settings: AppSettings):
    _no_store(response)
    check_request_origin(request, settings)
    try:
        ensure_auth_configured(settings)
    except AuthNotConfigured:
        raise _unavailable() from None

    admin = None
    if len(payload.password) <= MAX_PASSWORD_LENGTH:
        try:
            key = username_lookup_key(payload.username)
        except InvalidUsername:
            key = None
        if key is not None:
            admin = db.scalar(select(AdminUser).where(func.lower(AdminUser.username) == key))

    # Always verify against something (a dummy hash for unknown users) so timing is uniform.
    password = payload.password[:MAX_PASSWORD_LENGTH]
    matches, upgraded_hash = verify_password(password, admin.password_hash if admin else None)
    if admin is None or not matches or not admin.is_active or len(payload.password) > MAX_PASSWORD_LENGTH:
        raise _unauthorized(INVALID_CREDENTIALS)

    if upgraded_hash is not None:
        admin.password_hash = upgraded_hash
        try:
            db.commit()
        except DBAPIError as exc:
            # Not fatal: the old hash still works. Log the code/constraint only, never the row.
            db.rollback()
            logger.warning("Could not upgrade an admin password hash: %s", safe_db_error_summary(exc))

    token, claims = create_session_token(admin.id, admin.token_version, settings)
    _set_session_cookie(response, token, settings)
    return _session_body(claims, admin.username)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: DbSession, settings: AppSettings) -> None:
    """End the session everywhere (token_version is bumped), then clear the cookie.

    Without a valid session this just clears the cookie. With one, the CSRF token is
    required, so a cross-site page cannot sign the admin out.
    """
    _no_store(response)
    check_request_origin(request, settings)
    try:
        session = _load_session(request.cookies.get(SESSION_COOKIE_NAME), db, settings)
    except HTTPException as exc:
        if exc.status_code != status.HTTP_401_UNAUTHORIZED:
            raise
        session = None

    if session is not None:
        if not csrf_tokens_match(session.claims.csrf_token, request.headers.get(CSRF_HEADER_NAME)):
            raise _forbidden(CSRF_FAILED)
        # Atomic increment: revokes every outstanding token for this admin.
        session.admin.token_version = AdminUser.token_version + 1
        try:
            db.commit()
        except DBAPIError as exc:
            db.rollback()
            logger.warning("Could not revoke admin sessions: %s", safe_db_error_summary(exc))
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Could not sign out. Try again.") from None

    _clear_session_cookie(response, settings)


@router.get("/me", response_model=SessionRead)
def me(response: Response, session: Annotated[CurrentSession, Depends(get_current_session)]):
    """The current admin and the CSRF token for this session (the browser keeps it in memory)."""
    _no_store(response)
    return _session_body(session.claims, session.admin.username)
