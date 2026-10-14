"""Password hashing and session-token handling. No database needed.

Run on their own with:
    .venv\\Scripts\\python -m pytest tests/test_security.py --noconftest
"""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from pydantic import SecretStr

from app.core.config import Settings
from app.core.security import (
    ARGON2ID_PREFIX,
    JWT_ALGORITHM,
    MAX_PASSWORD_LENGTH,
    MIN_PASSWORD_LENGTH,
    AuthNotConfigured,
    InvalidSession,
    WeakPassword,
    check_new_password,
    create_session_token,
    csrf_tokens_match,
    decode_session_token,
    hash_password,
    verify_password,
)
from app.models.admin_user import is_phc_hash_format

# Dummy values only.
SECRET = "test-only-jwt-signing-secret-" + "s" * 32
OTHER_SECRET = "test-only-other-signing-secret-" + "o" * 32
PASSWORD = "test-only-password-1234"
ADMIN_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")


def settings(**overrides) -> Settings:
    values = {"environment": "test", "jwt_secret_key": SecretStr(SECRET)} | overrides
    return Settings(_env_file=None, **values)


@pytest.fixture(scope="module")
def stored_hash() -> str:
    return hash_password(PASSWORD)


# --- Password hashing ---------------------------------------------------------------


def test_hash_is_verified_argon2id(stored_hash):
    assert stored_hash.startswith(ARGON2ID_PREFIX)
    assert is_phc_hash_format(stored_hash)
    assert PASSWORD not in stored_hash


def test_same_password_hashes_differently(stored_hash):
    assert hash_password(PASSWORD) != stored_hash  # random salt


def test_verify_correct_and_wrong_password(stored_hash):
    assert verify_password(PASSWORD, stored_hash) == (True, None)
    assert verify_password(PASSWORD + "x", stored_hash) == (False, None)
    assert verify_password("", stored_hash) == (False, None)


def test_verify_without_a_stored_hash_fails():
    assert verify_password(PASSWORD, None) == (False, None)


@pytest.mark.parametrize("bad_hash", ["not-a-hash", "$2b$12$" + "T" * 53, "$argon2id$v=19$broken"])
def test_unrecognised_or_broken_hash_is_a_mismatch_not_an_error(bad_hash):
    assert verify_password(PASSWORD, bad_hash) == (False, None)


def test_outdated_parameters_are_upgraded_on_verify():
    weak = PasswordHash((Argon2Hasher(time_cost=1, memory_cost=8192, parallelism=1),)).hash(PASSWORD)
    matches, upgraded = verify_password(PASSWORD, weak)
    assert matches is True
    assert upgraded is not None and upgraded != weak
    assert upgraded.startswith(ARGON2ID_PREFIX)
    assert verify_password(PASSWORD, upgraded) == (True, None)


# --- New-password policy ------------------------------------------------------------


def test_acceptable_password():
    check_new_password("a" * MIN_PASSWORD_LENGTH, username="admin")
    check_new_password("p" * MAX_PASSWORD_LENGTH, username="admin")


@pytest.mark.parametrize(
    "password",
    ["", "short", "a" * (MIN_PASSWORD_LENGTH - 1), "p" * (MAX_PASSWORD_LENGTH + 1), " leading-space-pw", "trailing-space-pw "],
)
def test_weak_passwords_are_rejected(password):
    with pytest.raises(WeakPassword):
        check_new_password(password, username="admin")


def test_password_equal_to_username_is_rejected():
    with pytest.raises(WeakPassword):
        check_new_password("Administrator1", username="administrator1")


def test_weak_password_message_does_not_echo_it():
    with pytest.raises(WeakPassword) as exc_info:
        check_new_password("sekrit", username="admin")
    assert "sekrit" not in str(exc_info.value)


# --- Session tokens -------------------------------------------------------------------


def test_round_trip():
    s = settings()
    token, claims = create_session_token(ADMIN_ID, 3, s)
    decoded = decode_session_token(token, s)
    assert decoded == claims
    assert decoded.admin_id == ADMIN_ID and decoded.token_version == 3
    assert len(decoded.csrf_token) >= 32


def test_token_claims_and_header():
    s = settings(jwt_expire_minutes=60)
    token, _ = create_session_token(ADMIN_ID, 0, s)
    assert jwt.get_unverified_header(token)["alg"] == JWT_ALGORITHM
    payload = jwt.decode(token, options={"verify_signature": False})
    assert payload["iss"] == s.jwt_issuer and payload["aud"] == s.jwt_audience
    assert payload["exp"] - payload["iat"] == 3600
    assert {"sub", "iat", "nbf", "exp", "jti", "ver", "csrf"} <= payload.keys()


def test_each_token_has_its_own_csrf_token_and_id():
    s = settings()
    first, second = create_session_token(ADMIN_ID, 0, s)[0], create_session_token(ADMIN_ID, 0, s)[0]
    p1, p2 = (jwt.decode(t, options={"verify_signature": False}) for t in (first, second))
    assert p1["csrf"] != p2["csrf"] and p1["jti"] != p2["jti"]


def test_expired_token_is_rejected():
    s = settings(jwt_expire_minutes=5)
    token, _ = create_session_token(ADMIN_ID, 0, s, now=datetime.now(UTC) - timedelta(minutes=6))
    with pytest.raises(InvalidSession):
        decode_session_token(token, s)


def test_not_yet_valid_token_is_rejected():
    s = settings()
    token, _ = create_session_token(ADMIN_ID, 0, s, now=datetime.now(UTC) + timedelta(minutes=5))
    with pytest.raises(InvalidSession):
        decode_session_token(token, s)


@pytest.mark.parametrize(
    "verify_with",
    [
        {"jwt_secret_key": SecretStr(OTHER_SECRET)},
        {"jwt_issuer": "someone-else"},
        {"jwt_audience": "another-app"},
    ],
)
def test_wrong_key_issuer_or_audience_is_rejected(verify_with):
    token, _ = create_session_token(ADMIN_ID, 0, settings())
    with pytest.raises(InvalidSession):
        decode_session_token(token, settings(**verify_with))


def test_tampered_token_is_rejected():
    s = settings()
    token, _ = create_session_token(ADMIN_ID, 0, s)
    header, payload, signature = token.split(".")
    tampered = f"{header}.{payload}.{signature[:-2]}{'A' if signature[-2] != 'A' else 'B'}{signature[-1]}"
    with pytest.raises(InvalidSession):
        decode_session_token(tampered, s)


def _forge(payload: dict, *, key: str = SECRET, algorithm: str = JWT_ALGORITHM) -> str:
    return jwt.encode(payload, key, algorithm=algorithm)


def _valid_payload(s: Settings, **overrides) -> dict:
    now = datetime.now(UTC)
    return {
        "sub": str(ADMIN_ID), "iss": s.jwt_issuer, "aud": s.jwt_audience, "iat": now, "nbf": now,
        "exp": now + timedelta(minutes=5), "jti": "j", "ver": 0, "csrf": "c" * 43,
    } | overrides


def test_alg_none_is_rejected():
    s = settings()
    unsigned = jwt.encode(_valid_payload(s), None, algorithm="none")
    with pytest.raises(InvalidSession):
        decode_session_token(unsigned, s)


def test_other_hmac_algorithm_is_rejected():
    s = settings()
    with pytest.raises(InvalidSession):
        # A 64+ byte key, so PyJWT's key-length warning for SHA-512 does not fire.
        decode_session_token(_forge(_valid_payload(s), key=SECRET * 2, algorithm="HS512"), s)


@pytest.mark.parametrize("missing", ["sub", "iss", "aud", "iat", "nbf", "exp", "jti", "ver", "csrf"])
def test_missing_claims_are_rejected(missing):
    s = settings()
    payload = _valid_payload(s)
    del payload[missing]
    with pytest.raises(InvalidSession):
        decode_session_token(_forge(payload), s)


@pytest.mark.parametrize(
    "overrides",
    [{"sub": "not-a-uuid"}, {"ver": -1}, {"ver": "0"}, {"ver": True}, {"ver": 1.5}, {"csrf": ""}, {"csrf": 123}],
)
def test_malformed_claims_are_rejected(overrides):
    s = settings()
    with pytest.raises(InvalidSession):
        decode_session_token(_forge(_valid_payload(s, **overrides)), s)


@pytest.mark.parametrize("garbage", ["", "not.a.jwt", "a.b", "x" * 50])
def test_garbage_is_rejected(garbage):
    with pytest.raises(InvalidSession):
        decode_session_token(garbage, settings())


def test_no_secret_means_auth_is_unavailable():
    unconfigured = Settings(_env_file=None, environment="test")
    with pytest.raises(AuthNotConfigured):
        create_session_token(ADMIN_ID, 0, unconfigured)
    with pytest.raises(AuthNotConfigured):
        decode_session_token("anything", unconfigured)


# --- CSRF token comparison ---------------------------------------------------------


def test_csrf_tokens_match():
    assert csrf_tokens_match("abc", "abc")
    assert not csrf_tokens_match("abc", "abd")
    assert not csrf_tokens_match("abc", None)
    assert not csrf_tokens_match("abc", "")
    assert not csrf_tokens_match("abc", "abcé")
