"""Password hashing and session tokens for admin sign-in.

Passwords: Argon2id via pwdlib, with argon2-cffi's recommended parameters. A new hash is
verified before it is returned, and stored hashes are upgraded on sign-in when the
parameters change (see verify_password).

Sessions: HS256 JWTs signed with JWT_SECRET_KEY, carried in an HttpOnly cookie. Each token
holds the admin's token_version (bumping it revokes every session) and a random CSRF
token that the browser must echo in the X-CSRF-Token header on state-changing requests.
"""

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache

import jwt
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError
from pwdlib.hashers.argon2 import Argon2Hasher

from app.core.config import Settings
from app.models.admin_user import is_phc_hash_format

SESSION_COOKIE_NAME = "aig_crm_session"
CSRF_HEADER_NAME = "X-CSRF-Token"
JWT_ALGORITHM = "HS256"
ARGON2ID_PREFIX = "$argon2id$"

MIN_PASSWORD_LENGTH = 12
# Upper bound on what is hashed per request, so oversized input cannot be used to burn CPU.
MAX_PASSWORD_LENGTH = 256

# Argon2id is pwdlib's default Argon2 type; listed explicitly so it cannot change silently.
_password_hash = PasswordHash((Argon2Hasher(),))


# --- Passwords --------------------------------------------------------------------


class WeakPassword(ValueError):
    pass


def check_new_password(password: str, *, username: str) -> None:
    """Raise WeakPassword unless `password` is acceptable for a new account. Never echoes it."""
    if not isinstance(password, str) or not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        raise WeakPassword(f"Password must be {MIN_PASSWORD_LENGTH}-{MAX_PASSWORD_LENGTH} characters long.")
    if password != password.strip():
        raise WeakPassword("Password cannot start or end with whitespace.")
    if password.lower() == username.lower():
        raise WeakPassword("Password cannot be the same as the username.")


def hash_password(password: str) -> str:
    """Argon2id hash of `password`, checked (format and verification) before it is returned."""
    hashed = _password_hash.hash(password)
    if not (
        hashed.startswith(ARGON2ID_PREFIX)
        and is_phc_hash_format(hashed)
        and _password_hash.verify(password, hashed)
    ):
        raise RuntimeError("Password hashing produced an unusable hash.")
    return hashed


@lru_cache
def _dummy_hash() -> str:
    # A hash of a random value nobody knows, used when the username does not exist.
    return _password_hash.hash(secrets.token_urlsafe(32))


def verify_password(password: str, password_hash: str | None) -> tuple[bool, str | None]:
    """(matches, upgraded hash or None).

    With no stored hash (unknown user), a dummy hash is checked so the response takes as
    long as for a real user. A stored hash pwdlib does not recognise counts as a mismatch;
    its exception is not propagated because the message contains the stored hash.
    """
    if password_hash is None:
        _password_hash.verify(password, _dummy_hash())
        return False, None
    try:
        matches, updated = _password_hash.verify_and_update(password, password_hash)
    except UnknownHashError:
        return False, None
    if updated is not None and not (updated.startswith(ARGON2ID_PREFIX) and is_phc_hash_format(updated)):
        updated = None
    return matches, updated


# --- Session tokens ---------------------------------------------------------------


class AuthNotConfigured(Exception):
    """JWT_SECRET_KEY is not set: sign-in and protected endpoints are unavailable."""


class InvalidSession(Exception):
    """The token is missing a claim, malformed, expired, or signed for something else."""


@dataclass(frozen=True)
class SessionClaims:
    admin_id: uuid.UUID
    token_version: int
    csrf_token: str
    expires_at: datetime


def _signing_key(settings: Settings) -> str:
    try:
        return settings.jwt_signing_key()
    except RuntimeError:
        raise AuthNotConfigured() from None


def ensure_auth_configured(settings: Settings) -> None:
    _signing_key(settings)


def create_session_token(
    admin_id: uuid.UUID, token_version: int, settings: Settings, *, now: datetime | None = None
) -> tuple[str, SessionClaims]:
    issued_at = (now or datetime.now(UTC)).replace(microsecond=0)
    claims = SessionClaims(
        admin_id=admin_id,
        token_version=token_version,
        csrf_token=secrets.token_urlsafe(32),
        expires_at=issued_at + timedelta(minutes=settings.jwt_expire_minutes),
    )
    payload = {
        "sub": str(admin_id),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": issued_at,
        "nbf": issued_at,
        "exp": claims.expires_at,
        "jti": secrets.token_urlsafe(16),
        "ver": token_version,
        "csrf": claims.csrf_token,
    }
    return jwt.encode(payload, _signing_key(settings), algorithm=JWT_ALGORITHM), claims


def decode_session_token(token: str, settings: Settings) -> SessionClaims:
    """Verify signature, algorithm, expiry, not-before, issuer and audience; raise InvalidSession."""
    key = _signing_key(settings)
    try:
        payload = jwt.decode(
            token,
            key,
            algorithms=[JWT_ALGORITHM],  # never taken from the token header
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["sub", "iss", "aud", "iat", "nbf", "exp", "jti"]},
        )
        admin_id = uuid.UUID(payload["sub"])
        version, csrf_token = payload["ver"], payload["csrf"]
    except (jwt.InvalidTokenError, KeyError, TypeError, ValueError):
        raise InvalidSession() from None
    if type(version) is not int or version < 0 or not isinstance(csrf_token, str) or not csrf_token:
        raise InvalidSession()
    return SessionClaims(
        admin_id=admin_id,
        token_version=version,
        csrf_token=csrf_token,
        expires_at=datetime.fromtimestamp(payload["exp"], UTC),
    )


def csrf_tokens_match(expected: str, supplied: str | None) -> bool:
    return supplied is not None and secrets.compare_digest(expected.encode(), supplied.encode())
