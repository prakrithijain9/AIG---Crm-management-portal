"""Application settings, loaded from environment variables (or backend/.env)."""

import ipaddress
import logging
import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

import certifi
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

BACKEND_DIR = Path(__file__).resolve().parents[2]

# Environments that may run without a JWT secret (auth then refuses to work, CRUD still does).
# Any other ENVIRONMENT value, including a typo, is treated as production and fails closed.
LOCAL_ENVIRONMENTS = frozenset({"development", "test"})

# HS256 key: at least 32 characters (e.g. secrets.token_urlsafe(64) gives 86).
MIN_JWT_SECRET_LENGTH = 32

# libpq sslmode values, weakest to strongest. Production accepts only verify-full: the connection
# is encrypted and the server's certificate and hostname are checked.
DB_SSL_MODES = ("disable", "allow", "prefer", "require", "verify-ca", "verify-full")
PRODUCTION_DB_SSLMODE = "verify-full"
_CERT_VERIFYING_SSL_MODES = frozenset({"verify-ca", "verify-full"})

# A DNS name or IPv4 address: dot-separated labels of letters, digits and inner hyphens.
_HOSTNAME = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*")

logger = logging.getLogger(__name__)


def canonical_origin(value: str) -> str | None:
    """`value` as a lower-case scheme://host[:port] origin, or None if it is anything else.

    The origin is rebuilt from its parsed parts and must equal the input, which rules out
    wildcards, user:password@, paths, queries and fragments (even empty "?" or "#"),
    and malformed hosts or ports. A single trailing slash is tolerated.
    """
    origin = value.strip().lower().removesuffix("/")
    try:
        parts = urlsplit(origin)
        port = parts.port  # raises ValueError for a non-numeric or out-of-range port
    except ValueError:
        return None
    host = parts.hostname
    if parts.scheme not in ("http", "https") or not host or port == 0:
        return None
    if ":" in host:  # IPv6 literal, e.g. http://[::1]:3000
        try:
            ipaddress.IPv6Address(host)
        except ValueError:
            return None
        host = f"[{host}]"
    elif not _HOSTNAME.fullmatch(host):
        return None
    canonical = f"{parts.scheme}://{host}" + (f":{port}" if port is not None else "")
    return canonical if canonical == origin else None


def _origin_list(raw: str, source: str) -> list[str]:
    """Parse a comma-separated origin setting; empty entries are skipped, anything invalid raises."""
    origins = []
    for position, item in enumerate(raw.split(","), start=1):
        if not item.strip():
            continue
        origin = canonical_origin(item)  # rejects "*", "null", paths, credentials, bad hosts/ports
        if origin is None:
            # Say which entry, never its value: a malformed entry may contain credentials.
            raise ValueError(f"{source} entry {position} is not a valid origin; expected scheme://host[:port].")
        origins.append(origin)
    return origins


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # Validation errors must never echo input values: they include secrets.
        hide_input_in_errors=True,
    )

    app_name: str = "AIG CRM API"
    environment: str = "development"

    db_host: str = "localhost"
    db_port: int = 5432
    db_user: str = "postgres"
    # SecretStr keeps the password out of logs and reprs.
    db_password: SecretStr = SecretStr("")
    db_name: str = "aig_crm_dev"
    # Separate database used only by the test suite (same server and role).
    test_db_name: str = "aig_crm_test"

    # PostgreSQL TLS (libpq sslmode). Unset: libpq's own default in development/test (works with
    # a local server without SSL), verify-full in production, where nothing weaker is accepted.
    db_sslmode: str | None = None
    # CA certificates for verify-ca/verify-full: a file path, or "system" for the OS store.
    # Unset: certifi's Mozilla bundle, which includes Let's Encrypt's ISRG Root X1 (Neon's CA).
    db_sslrootcert: str | None = None

    # Comma-separated list of origins allowed to call the API (the Next.js dev server).
    cors_origins: str = "http://localhost:3000"

    # --- Authentication ---------------------------------------------------------------

    # Signing key for session JWTs. Deliberately no default: required outside development/test,
    # and auth code reads it only through jwt_signing_key(), which raises while it is unset.
    jwt_secret_key: SecretStr | None = None
    jwt_issuer: str = Field(default="aig-crm-api", min_length=1)
    jwt_audience: str = Field(default="aig-crm-web", min_length=1)
    # Absolute session lifetime (no refresh tokens): 8 hours by default.
    jwt_expire_minutes: int = Field(default=480, ge=5, le=1440)

    # Send the session cookie over HTTPS only. Unset: on everywhere except development/test.
    cookie_secure: bool | None = None

    # Comma-separated origins allowed to send state-changing requests (CSRF Origin check).
    # Empty: same as CORS_ORIGINS.
    trusted_origins: str = ""

    @field_validator("db_sslmode", "db_sslrootcert", mode="before")
    @classmethod
    def _blank_is_unset(cls, value: object) -> object:
        # "DB_SSLMODE=" in a .env file means "not set", not an invalid empty mode.
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @model_validator(mode="after")
    def _check_db_ssl_settings(self) -> "Settings":
        if self.db_sslmode is not None:
            self.db_sslmode = self.db_sslmode.lower()
            if self.db_sslmode not in DB_SSL_MODES:
                raise ValueError(f"DB_SSLMODE must be one of: {', '.join(DB_SSL_MODES)}.")
        if self.is_production and self.effective_db_sslmode != PRODUCTION_DB_SSLMODE:
            raise ValueError(
                f"DB_SSLMODE must be {PRODUCTION_DB_SSLMODE} (or unset) when ENVIRONMENT is not development or test."
            )
        rootcert = self.db_sslrootcert
        if rootcert is not None and rootcert != "system" and not Path(rootcert).is_file():
            raise ValueError("DB_SSLROOTCERT must be 'system' or the path to an existing certificate file.")
        return self

    @model_validator(mode="after")
    def _check_auth_settings(self) -> "Settings":
        secret = self.jwt_secret_key.get_secret_value() if self.jwt_secret_key else ""
        if secret and len(secret) < MIN_JWT_SECRET_LENGTH:
            raise ValueError(f"JWT_SECRET_KEY must be at least {MIN_JWT_SECRET_LENGTH} characters.")
        if self.is_production:
            if not secret:
                raise ValueError("JWT_SECRET_KEY is required when ENVIRONMENT is not development or test.")
            if self.cookie_secure is False:
                raise ValueError("COOKIE_SECURE cannot be false when ENVIRONMENT is not development or test.")
        # Both raise on a wildcard or malformed origin, so a bad value stops startup.
        self.cors_origin_list
        self.trusted_origin_list
        return self

    def url_for(self, database: str) -> URL:
        # URL.create escapes special characters in the password safely.
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.db_user,
            password=self.db_password.get_secret_value() or None,
            host=self.db_host,
            port=self.db_port,
            database=database,
            query=self.db_ssl_params,
        )

    @property
    def effective_db_sslmode(self) -> str | None:
        """DB_SSLMODE, or the environment's default: verify-full in production, libpq's own locally."""
        if self.db_sslmode is not None:
            return self.db_sslmode
        return PRODUCTION_DB_SSLMODE if self.is_production else None

    @property
    def db_ssl_params(self) -> dict[str, str]:
        """libpq TLS parameters for the connection URL (empty: libpq defaults)."""
        mode = self.effective_db_sslmode
        if mode is None:
            return {}
        params = {"sslmode": mode}
        if mode in _CERT_VERIFYING_SSL_MODES:
            params["sslrootcert"] = self.db_sslrootcert or certifi.where()
        return params

    @property
    def database_url(self) -> URL:
        return self.url_for(self.db_name)

    @property
    def test_database_url(self) -> URL:
        return self.url_for(self.test_db_name)

    @property
    def cors_origin_list(self) -> list[str]:
        """Canonical CORS origins. Never "*": with credentials allowed, a wildcard would make
        the CORS middleware echo back any requesting origin."""
        return _origin_list(self.cors_origins, "CORS_ORIGINS")

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() not in LOCAL_ENVIRONMENTS

    @property
    def session_cookie_secure(self) -> bool:
        return self.is_production if self.cookie_secure is None else self.cookie_secure

    @property
    def trusted_origin_list(self) -> list[str]:
        """Canonical origins (scheme://host[:port], lower-case), compared against the Origin header."""
        if self.trusted_origins:
            return _origin_list(self.trusted_origins, "TRUSTED_ORIGINS")
        return self.cors_origin_list

    def jwt_signing_key(self) -> str:
        """The JWT secret. Raises while unset, so auth fails closed instead of using a weak key."""
        secret = self.jwt_secret_key.get_secret_value() if self.jwt_secret_key else ""
        if not secret:
            raise RuntimeError("JWT_SECRET_KEY is not set; authentication is unavailable (see backend/.env.example).")
        return secret


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    # Logged once per process (the result is cached). Values from the process environment
    # or backend/.env count as set; only the built-in default triggers the warning.
    if "environment" not in settings.model_fields_set:
        logger.warning(
            "ENVIRONMENT is not set; defaulting to 'development' (JWT secret optional, session "
            "cookie not HTTPS-only). Production deployments must set ENVIRONMENT=production."
        )
    return settings
