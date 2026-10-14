"""Admin username rules and safe database-error helpers. No database needed.

The matching database-side checks are in test_models.py and test_migrations.py.
Run on their own with:
    .venv\\Scripts\\python -m pytest tests/test_admin_user_rules.py --noconftest
"""

import pytest
from sqlalchemy import CheckConstraint
from sqlalchemy.exc import IntegrityError

from app.db.errors import db_error_details, safe_db_error_message, safe_db_error_summary
from app.models.admin_user import (
    ADMIN_USER_CONSTRAINT_MESSAGES,
    ADMIN_USER_SAVE_FAILED,
    PASSWORD_HASH_MAX_LENGTH,
    USERNAME_MAX_LENGTH,
    AdminUser,
    InvalidUsername,
    is_phc_hash_format,
    username_lookup_key,
    validate_username,
)

# Shaped like an Argon2id hash, but not a hash of anything.
FAKE_HASH = "$argon2id$v=19$m=65536,t=3,p=4$test-only-salt$test-only-not-a-real-hash"


# --- Username rules ------------------------------------------------------------------


@pytest.mark.parametrize(
    "username",
    ["admin", "Admin", "a", "admin.ops", "first_last", "ops-team", "admin@aig.example", "x" * USERNAME_MAX_LENGTH],
)
def test_valid_usernames_are_returned_unchanged(username):
    assert validate_username(username) == username


@pytest.mark.parametrize(
    "username",
    [
        "",
        " ",
        " admin",
        "admin ",
        "ad min",
        "\tadmin",
        "admin\t",
        "admin\n",
        "admin\r\n",
        "admin\x00",
        "admin\x1b[31m",  # terminal escape sequence
        "adm​in",  # zero-width space
        "admin ",  # non-breaking space
        "аdmin",  # Cyrillic look-alike "a"
        "admín",
        "admin!",
        "admin/../x",
        "x" * (USERNAME_MAX_LENGTH + 1),
    ],
)
def test_invalid_usernames_are_rejected_not_rewritten(username):
    with pytest.raises(InvalidUsername):
        validate_username(username)


@pytest.mark.parametrize("value", [None, 42, b"admin"])
def test_non_string_usernames_are_rejected(value):
    with pytest.raises(InvalidUsername):
        validate_username(value)


def test_invalid_username_message_does_not_echo_the_value():
    secret_looking = "Hunter2-typed-in-the-wrong-field "
    with pytest.raises(InvalidUsername) as exc_info:
        validate_username(secret_looking)
    assert secret_looking.strip() not in str(exc_info.value)


def test_invalid_username_is_a_value_error():
    assert issubclass(InvalidUsername, ValueError)


def test_lookup_key_is_lower_case_and_validated():
    assert username_lookup_key("Admin.OPS") == "admin.ops"
    with pytest.raises(InvalidUsername):
        username_lookup_key(" admin")


# --- Password hash format ----------------------------------------------------------

# Hash-shaped test values only: none of these is the hash of anything.
VALID_HASH_SHAPES = [
    FAKE_HASH,
    "$argon2id$v=19$m=19456,t=2,p=1$dGVzdC1vbmx5LXNhbHQ$dGVzdC1vbmx5LWhhc2gtdmFsdWU",
    "$argon2i$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA",  # other Argon2 variants still fit
    "$2b$12$" + "T" * 53,  # bcrypt shape: the schema does not lock in one algorithm
    "$scrypt$ln=16,r=8,p=1$c2FsdA$aGFzaA",
]

INVALID_HASH_SHAPES = [
    "",
    "plaintext-password",
    "hunter2",
    "argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA",  # missing leading $
    "$argon2id",
    "$argon2id$",
    "$argon2id$v=19",  # needs at least two segments after the algorithm
    "$argon2id$$c2FsdA$aGFzaA",  # empty segment
    "$argon2id$v=19$c2FsdA$aGFzaA$",  # trailing empty segment
    "$ARGON2ID$v=19$c2FsdA$aGFzaA",  # algorithm id is lower case
    "$argon2id$v=19$m=65536 t=3$c2FsdA$aGFzaA",  # space
    "$argon2id$v=19$c2FsdA$aGFzaA\n",
    "$argon2id$v=19$c2Fs:dA$aGFzaA",
    "$" + "a" * 33 + "$c2FsdA$aGFzaA",  # algorithm id too long
]


@pytest.mark.parametrize("value", VALID_HASH_SHAPES)
def test_phc_hash_shapes_are_accepted(value):
    assert is_phc_hash_format(value)


@pytest.mark.parametrize("value", INVALID_HASH_SHAPES)
def test_non_phc_values_are_rejected(value):
    assert not is_phc_hash_format(value)


def test_hash_length_limit_matches_the_column():
    prefix = "$argon2id$v=19$c2FsdA$"  # a valid shape, padded to the exact length under test
    at_limit = prefix + "h" * (PASSWORD_HASH_MAX_LENGTH - len(prefix))
    assert len(at_limit) == PASSWORD_HASH_MAX_LENGTH
    assert is_phc_hash_format(at_limit)
    assert not is_phc_hash_format(at_limit + "h")
    assert AdminUser.__table__.c.password_hash.type.length == PASSWORD_HASH_MAX_LENGTH


@pytest.mark.parametrize("value", [None, 42, b"$argon2id$v=19$c2FsdA$aGFzaA"])
def test_non_string_hashes_are_rejected(value):
    assert not is_phc_hash_format(value)


# --- No password hash in representations -------------------------------------------


def test_repr_never_includes_the_password_hash():
    admin = AdminUser(username="admin", password_hash=FAKE_HASH)
    assert FAKE_HASH not in repr(admin)
    assert FAKE_HASH not in str(admin)
    assert "admin" in repr(admin)


# --- Safe database-error helpers ----------------------------------------------------


class FakeDiag:
    def __init__(self, constraint_name):
        self.constraint_name = constraint_name


class FakePgError(Exception):
    """Mimics psycopg: PostgreSQL's DETAIL line repeats the failing row, hash included."""

    def __init__(self, sqlstate, constraint_name):
        super().__init__(f'new row violates check constraint\nDETAIL: Failing row contains (admin, {FAKE_HASH}, t, -1).')
        self.sqlstate = sqlstate
        self.diag = FakeDiag(constraint_name)


def integrity_error(sqlstate, constraint_name, *, hide_parameters=False):
    return IntegrityError(
        "INSERT INTO admin_users (username, password_hash) VALUES (%(u)s, %(h)s)",
        {"u": "admin", "h": FAKE_HASH},
        FakePgError(sqlstate, constraint_name),
        hide_parameters=hide_parameters,
    )


def test_raw_error_text_can_contain_the_hash():
    # Why the helpers exist: even with hide_parameters, PostgreSQL's DETAIL line has the row.
    assert FAKE_HASH in str(integrity_error("23514", "x"))
    assert FAKE_HASH in str(integrity_error("23514", "x", hide_parameters=True))
    assert "parameters hidden" in str(integrity_error("23514", "x", hide_parameters=True))


def test_details_and_summary_contain_only_code_and_constraint():
    exc = integrity_error("23505", "uq_admin_users_username_lower")
    assert db_error_details(exc) == ("23505", "uq_admin_users_username_lower")
    summary = safe_db_error_summary(exc)
    assert summary == "IntegrityError (sqlstate=23505, constraint=uq_admin_users_username_lower)"
    assert FAKE_HASH not in summary


@pytest.mark.parametrize("constraint", sorted(ADMIN_USER_CONSTRAINT_MESSAGES))
def test_known_admin_constraints_get_their_safe_message(constraint):
    message = safe_db_error_message(integrity_error("23514", constraint), ADMIN_USER_CONSTRAINT_MESSAGES, ADMIN_USER_SAVE_FAILED)
    assert message == ADMIN_USER_CONSTRAINT_MESSAGES[constraint]
    assert FAKE_HASH not in message


@pytest.mark.parametrize("constraint", [None, "pk_admin_users", "some_other_constraint"])
def test_unknown_constraints_get_the_generic_message(constraint):
    message = safe_db_error_message(integrity_error("23505", constraint), ADMIN_USER_CONSTRAINT_MESSAGES, ADMIN_USER_SAVE_FAILED)
    assert message == ADMIN_USER_SAVE_FAILED


def test_errors_without_diagnostics_are_handled():
    exc = IntegrityError("SELECT 1", None, Exception("no sqlstate or diag here"))
    assert db_error_details(exc) == (None, None)
    assert safe_db_error_summary(exc) == "IntegrityError (sqlstate=None, constraint=None)"


def test_every_admin_check_constraint_has_a_message():
    prefix = "ck_admin_users_"
    names = [str(c.name) for c in AdminUser.__table__.constraints if isinstance(c, CheckConstraint)]
    checks = {name if name.startswith(prefix) else prefix + name for name in names}
    assert len(checks) == 6
    assert checks <= set(ADMIN_USER_CONSTRAINT_MESSAGES)
    assert "uq_admin_users_username_lower" in ADMIN_USER_CONSTRAINT_MESSAGES
