"""Settings validation: trusted origins, JWT secret, cookie security, database TLS, ENVIRONMENT warning.

No database and no backend/.env: every test runs with env_file disabled and the
settings-related environment variables removed, using dummy secrets only. These tests
need no fixtures from conftest.py, so they can run on their own with
    .venv\\Scripts\\python -m pytest tests/test_config.py --noconftest
"""

import logging
from pathlib import Path

import certifi
import pytest
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from pydantic import ValidationError
from sqlalchemy.dialects.postgresql.psycopg import dialect as psycopg_dialect

from app.core import config
from app.core.config import MIN_JWT_SECRET_LENGTH, Settings, canonical_origin, get_settings

# Obviously fake values, used only to check they never appear in error messages.
DUMMY_SECRET = "test-only-dummy-jwt-secret-" + "x" * 16
SHORT_SECRET = "test-only-short"
DUMMY_DB_PASSWORD = "test-only-dummy-db-password"


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch):
    """Never read backend/.env or real environment values; reset the get_settings cache."""
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    # Settings match variable names case-insensitively; on Linux/CI env names are case-sensitive.
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)
        monkeypatch.delenv(name.lower(), raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_isolation_uses_patched_env_file(monkeypatch, tmp_path):
    # Proves the fixture's mechanism works: Settings honours a patched env_file at runtime.
    env_file = tmp_path / ".env"
    env_file.write_text("DB_NAME=from_patched_env_file\n", encoding="utf-8")
    monkeypatch.setitem(Settings.model_config, "env_file", env_file)
    assert Settings().db_name == "from_patched_env_file"


# --- Trusted origins --------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("http://localhost:3000", "http://localhost:3000"),
        ("http://localhost:3000/", "http://localhost:3000"),
        ("  HTTP://LocalHost:3000  ", "http://localhost:3000"),
        ("http://127.0.0.1:8000", "http://127.0.0.1:8000"),
        ("http://[::1]:3000", "http://[::1]:3000"),
        ("https://crm.example.com", "https://crm.example.com"),
        ("https://my-crm.example.co.uk:8443", "https://my-crm.example.co.uk:8443"),
    ],
)
def test_canonical_origin_accepts_valid_origins(value, expected):
    assert canonical_origin(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "*",
        "null",
        "",
        "localhost:3000",  # no scheme
        "ftp://localhost",
        "http://",
        "http://*.example.com",
        "http://*",
        "http://user@localhost",
        "http://user:pass@localhost",
        "http://localhost/app",
        "http://localhost:3000//",
        "http://localhost?",
        "http://localhost?x=1",
        "http://localhost#",
        "http://localhost#x",
        "http://localhost:",
        "http://localhost:abc",
        "http://localhost:99999",
        "http://localhost:0",
        "http://localhost:03000",
        "http://exa mple.com",
        "http://-bad.example.com",
        "http://bad-.example.com",
        "http://a..example.com",
        "http://under_score.example.com",
        "http://[::1",
        "http://[not-an-ip]:3000",
    ],
)
def test_canonical_origin_rejects_everything_else(value):
    assert canonical_origin(value) is None


def test_trusted_origins_are_canonicalised_and_skip_empty_entries():
    settings = Settings(trusted_origins=" http://LOCALHOST:3000/ , ,https://crm.example.com")
    assert settings.trusted_origin_list == ["http://localhost:3000", "https://crm.example.com"]


def test_trusted_origins_default_to_cors_origins():
    settings = Settings(cors_origins="http://localhost:3000,http://127.0.0.1:3000")
    assert settings.trusted_origin_list == ["http://localhost:3000", "http://127.0.0.1:3000"]
    # CORS behaviour itself is unchanged.
    assert settings.cors_origin_list == ["http://localhost:3000", "http://127.0.0.1:3000"]


def test_invalid_trusted_origin_names_the_entry_but_not_its_value():
    with pytest.raises(ValidationError) as exc_info:
        Settings(trusted_origins="http://localhost:3000,http://admin:sentinel-credential@host")
    message = str(exc_info.value)
    assert "TRUSTED_ORIGINS entry 2 is not a valid origin" in message
    assert "sentinel-credential" not in message


# --- CORS origins (validated even when TRUSTED_ORIGINS is set) -----------------------


def test_default_cors_origin_is_the_local_frontend():
    assert Settings().cors_origin_list == ["http://localhost:3000"]


def test_cors_origins_are_canonicalised():
    settings = Settings(cors_origins=" HTTP://LocalHost:3000/ , ,https://crm.example.com,http://[::1]:3000")
    assert settings.cors_origin_list == ["http://localhost:3000", "https://crm.example.com", "http://[::1]:3000"]


def test_empty_cors_origins_disable_cross_origin_access():
    settings = Settings(cors_origins="", trusted_origins="http://localhost:3000")
    assert settings.cors_origin_list == []
    assert settings.trusted_origin_list == ["http://localhost:3000"]


@pytest.mark.parametrize(
    "cors_origins",
    [
        "*",
        "http://localhost:3000,*",
        " * ",
        "https://*.example.com",
        "http://*",
        "null",
    ],
)
def test_wildcard_cors_origins_are_rejected_even_with_trusted_origins_set(cors_origins):
    # With credentials allowed, "*" would make the CORS middleware echo any requesting origin.
    with pytest.raises(ValidationError, match="CORS_ORIGINS entry [0-9]+ is not a valid origin"):
        Settings(cors_origins=cors_origins, trusted_origins="http://localhost:3000")


@pytest.mark.parametrize(
    "cors_origins",
    [
        "localhost:3000",
        "http://localhost:3000/app",
        "http://localhost:3000?x=1",
        "http://localhost:abc",
        "ftp://localhost",
        "http://exa mple.com",
    ],
)
def test_malformed_cors_origins_are_rejected(cors_origins):
    with pytest.raises(ValidationError, match="CORS_ORIGINS entry 1 is not a valid origin"):
        Settings(cors_origins=cors_origins, trusted_origins="http://localhost:3000")


def test_invalid_cors_origin_error_does_not_echo_the_value():
    with pytest.raises(ValidationError) as exc_info:
        Settings(cors_origins="http://localhost:3000,http://admin:sentinel-credential@host")
    message = str(exc_info.value)
    assert "CORS_ORIGINS entry 2 is not a valid origin" in message
    assert "sentinel-credential" not in message


def test_cors_validation_also_applies_in_production():
    with pytest.raises(ValidationError, match="CORS_ORIGINS entry 1"):
        Settings(
            environment="production",
            jwt_secret_key="p" * MIN_JWT_SECRET_LENGTH,
            cors_origins="*",
            trusted_origins="https://crm.example.com",
        )


def test_invalid_cors_origin_is_reported_when_used_as_fallback():
    with pytest.raises(ValidationError, match="CORS_ORIGINS entry 1 is not a valid origin"):
        Settings(cors_origins="*")


# --- JWT secret -------------------------------------------------------------------


def test_development_without_secret_starts_but_cannot_sign():
    settings = Settings()
    assert not settings.is_production
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY is not set"):
        settings.jwt_signing_key()


def test_empty_secret_counts_as_missing():
    with pytest.raises(RuntimeError):
        Settings(jwt_secret_key="").jwt_signing_key()
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY is required"):
        Settings(environment="production", jwt_secret_key="")


@pytest.mark.parametrize("environment", ["development", "test", "production"])
def test_short_secret_is_rejected_in_every_environment(environment):
    assert len(SHORT_SECRET) < MIN_JWT_SECRET_LENGTH
    with pytest.raises(ValidationError, match="at least 32 characters"):
        Settings(environment=environment, jwt_secret_key=SHORT_SECRET)


def test_secret_of_minimum_length_is_accepted():
    secret = "s" * MIN_JWT_SECRET_LENGTH
    assert Settings(jwt_secret_key=secret).jwt_signing_key() == secret


@pytest.mark.parametrize("environment", ["production", "staging", "prod", "Production", ""])
def test_non_local_environment_requires_a_secret(environment):
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY is required"):
        Settings(environment=environment)


def test_production_with_secret_can_sign():
    settings = Settings(environment="production", jwt_secret_key=DUMMY_SECRET)
    assert settings.is_production
    assert settings.jwt_signing_key() == DUMMY_SECRET


def test_validation_errors_never_contain_secrets():
    with pytest.raises(ValidationError) as exc_info:
        Settings(environment="production", jwt_secret_key=SHORT_SECRET, db_password=DUMMY_DB_PASSWORD)
    message = str(exc_info.value)
    assert SHORT_SECRET not in message
    assert DUMMY_DB_PASSWORD not in message


def test_secret_is_masked_in_repr_and_dump():
    settings = Settings(jwt_secret_key=DUMMY_SECRET, db_password=DUMMY_DB_PASSWORD)
    for text in (repr(settings), str(settings.model_dump())):
        assert DUMMY_SECRET not in text
        assert DUMMY_DB_PASSWORD not in text


# --- Session cookie security --------------------------------------------------------


@pytest.mark.parametrize("environment", ["development", "test", " Development "])
def test_cookie_not_secure_by_default_locally(environment):
    assert Settings(environment=environment).session_cookie_secure is False


def test_cookie_secure_by_default_in_production():
    settings = Settings(environment="production", jwt_secret_key=DUMMY_SECRET)
    assert settings.session_cookie_secure is True


def test_production_refuses_insecure_cookie():
    with pytest.raises(ValidationError, match="COOKIE_SECURE cannot be false"):
        Settings(environment="production", jwt_secret_key=DUMMY_SECRET, cookie_secure=False)


def test_cookie_secure_can_be_forced_on_locally():
    assert Settings(cookie_secure=True).session_cookie_secure is True


# --- Database TLS -------------------------------------------------------------------


def _connect_kwargs(settings: Settings) -> dict:
    """What SQLAlchemy's psycopg dialect will pass to psycopg.connect() for this URL."""
    _, kwargs = psycopg_dialect().create_connect_args(settings.database_url)
    return kwargs


def test_local_default_leaves_libpq_ssl_defaults():
    # A local PostgreSQL without SSL keeps working: no sslmode is sent at all.
    settings = Settings()
    assert settings.effective_db_sslmode is None
    assert settings.db_ssl_params == {}
    assert not settings.database_url.query
    assert "sslmode" not in _connect_kwargs(settings)


def test_production_defaults_to_verify_full_with_certifi_bundle():
    settings = Settings(environment="production", jwt_secret_key=DUMMY_SECRET)
    assert settings.db_ssl_params == {"sslmode": "verify-full", "sslrootcert": certifi.where()}
    kwargs = _connect_kwargs(settings)
    assert kwargs["sslmode"] == "verify-full"
    assert kwargs["sslrootcert"] == certifi.where()


def test_ssl_params_apply_to_every_database_url():
    # url_for() is used by the app, Alembic and the admin/seed scripts alike.
    settings = Settings(environment="production", jwt_secret_key=DUMMY_SECRET)
    for url in (settings.database_url, settings.test_database_url, settings.url_for("other_db")):
        assert url.query == {"sslmode": "verify-full", "sslrootcert": certifi.where()}


def test_certifi_bundle_contains_neons_root_ca():
    # Neon's certificates chain to Let's Encrypt's ISRG Root X1; verify-full needs it in the bundle.
    bundle = Path(certifi.where())
    assert bundle.is_file()
    assert "CN=ISRG Root X1" in bundle.read_text(encoding="utf-8")


def test_ssl_params_are_valid_libpq_connection_parameters():
    # libpq parses the conninfo (rejecting unknown keywords); quoting survives paths with spaces.
    kwargs = _connect_kwargs(Settings(environment="production", jwt_secret_key=DUMMY_SECRET))
    parsed = conninfo_to_dict(make_conninfo(**kwargs))
    assert parsed["sslmode"] == "verify-full"
    assert parsed["sslrootcert"] == certifi.where()


@pytest.mark.parametrize("mode", ["disable", "allow", "prefer", "require", "verify-ca"])
def test_production_refuses_weaker_ssl_modes(mode):
    with pytest.raises(ValidationError, match="DB_SSLMODE must be verify-full"):
        Settings(environment="production", jwt_secret_key=DUMMY_SECRET, db_sslmode=mode)


@pytest.mark.parametrize("mode", ["verify-full", " VERIFY-FULL "])
def test_production_accepts_explicit_verify_full(mode):
    settings = Settings(environment="production", jwt_secret_key=DUMMY_SECRET, db_sslmode=mode)
    assert settings.effective_db_sslmode == "verify-full"


def test_production_refuses_weaker_ssl_mode_from_environment_variable(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", DUMMY_SECRET)
    monkeypatch.setenv("DB_SSLMODE", "require")
    with pytest.raises(ValidationError, match="DB_SSLMODE must be verify-full"):
        Settings()


@pytest.mark.parametrize("environment", ["development", "production"])
def test_unknown_ssl_mode_is_rejected(environment):
    with pytest.raises(ValidationError, match="DB_SSLMODE must be one of") as exc_info:
        Settings(environment=environment, jwt_secret_key=DUMMY_SECRET, db_sslmode="verify-everything")
    assert "verify-everything" not in str(exc_info.value)


def test_blank_ssl_settings_count_as_unset(monkeypatch):
    monkeypatch.setenv("DB_SSLMODE", "")
    monkeypatch.setenv("DB_SSLROOTCERT", "  ")
    settings = Settings()
    assert settings.db_sslmode is None
    assert settings.db_sslrootcert is None
    assert settings.db_ssl_params == {}


def test_local_require_encrypts_without_a_root_certificate():
    # require: encrypted but unverified, so no CA bundle is passed.
    assert Settings(db_sslmode="require").db_ssl_params == {"sslmode": "require"}


@pytest.mark.parametrize("mode", ["verify-ca", "verify-full"])
def test_local_verifying_modes_use_certifi_bundle(mode):
    assert Settings(db_sslmode=mode).db_ssl_params == {"sslmode": mode, "sslrootcert": certifi.where()}


def test_custom_root_certificate_file_is_used(tmp_path):
    cert = tmp_path / "root.pem"
    cert.write_text("placeholder: only the path is checked here\n", encoding="utf-8")
    settings = Settings(environment="production", jwt_secret_key=DUMMY_SECRET, db_sslrootcert=str(cert))
    assert settings.db_ssl_params["sslrootcert"] == str(cert)


def test_system_root_store_is_passed_through():
    settings = Settings(environment="production", jwt_secret_key=DUMMY_SECRET, db_sslrootcert="system")
    assert settings.db_ssl_params["sslrootcert"] == "system"


def test_missing_root_certificate_file_is_rejected_without_echoing_the_path(tmp_path):
    missing = str(tmp_path / "no-such-root.pem")
    with pytest.raises(ValidationError, match="DB_SSLROOTCERT must be") as exc_info:
        Settings(db_sslrootcert=missing)
    assert missing not in str(exc_info.value)


def test_ssl_settings_never_expose_the_database_password():
    settings = Settings(environment="production", jwt_secret_key=DUMMY_SECRET, db_password=DUMMY_DB_PASSWORD)
    assert DUMMY_DB_PASSWORD not in repr(settings.database_url)
    assert DUMMY_DB_PASSWORD not in str(settings.db_ssl_params)


def test_settings_read_from_environment_variables(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("JWT_SECRET_KEY", DUMMY_SECRET)
    monkeypatch.setenv("COOKIE_SECURE", "false")
    with pytest.raises(ValidationError, match="COOKIE_SECURE cannot be false"):
        Settings()


# --- Missing ENVIRONMENT warning ----------------------------------------------------


def test_warns_once_when_environment_is_not_set(caplog):
    with caplog.at_level(logging.WARNING, logger=config.__name__):
        settings = get_settings()
        get_settings()  # cached: no second warning
    assert settings.environment == "development"
    warnings = [r for r in caplog.records if "ENVIRONMENT is not set" in r.getMessage()]
    assert len(warnings) == 1
    assert "ENVIRONMENT=production" in warnings[0].getMessage()


@pytest.mark.parametrize("value", ["development", "test"])
def test_no_warning_when_environment_is_set(monkeypatch, caplog, value):
    monkeypatch.setenv("ENVIRONMENT", value)
    with caplog.at_level(logging.WARNING, logger=config.__name__):
        assert get_settings().environment == value
    assert not [r for r in caplog.records if "ENVIRONMENT is not set" in r.getMessage()]


@pytest.mark.parametrize(
    ("env_file_text", "expect_warning"),
    [
        ("ENVIRONMENT=development\n", False),
        ("DB_NAME=from_temp_env_file\n", True),  # control: a .env without ENVIRONMENT still warns
    ],
)
def test_environment_from_env_file_counts_as_set(monkeypatch, tmp_path, caplog, env_file_text, expect_warning):
    env_file = tmp_path / ".env"  # a temporary file, never backend/.env
    env_file.write_text(env_file_text, encoding="utf-8")
    monkeypatch.setitem(Settings.model_config, "env_file", env_file)
    with caplog.at_level(logging.WARNING, logger=config.__name__):
        settings = get_settings()
    assert settings.environment == "development"
    warned = any("ENVIRONMENT is not set" in r.getMessage() for r in caplog.records)
    assert warned is expect_warning


def test_get_settings_fails_closed_in_production_without_secret(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY is required"):
        get_settings()
