"""Admin password reset (scripts/reset_admin_password.py and app.core.admins), on the test database.

The interactive script is driven with a fake terminal; nothing here touches aig_crm_dev.
"""

import importlib.util
import inspect
import logging

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core import admins
from app.core.admins import PasswordResetError, reset_admin_password
from app.core.config import BACKEND_DIR
from app.core.security import ARGON2ID_PREFIX, verify_password
from app.models import AdminUser
from tests.conftest import TEST_ADMIN_PASSWORD, TEST_ADMIN_USERNAME

NEW_PASSWORD = "test-only-new-password-5678"
TARGET = "aig_crm_test"
ME = "/api/auth/me"


def _load_script():
    spec = importlib.util.spec_from_file_location(
        "reset_admin_password", BACKEND_DIR / "scripts" / "reset_admin_password.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


script = _load_script()


class FakeTerminal:
    """Stands in for input()/getpass()/print(); records every prompt and message."""

    def __init__(self, answers=(), secrets=()):
        self.answers, self.secrets = list(answers), list(secrets)
        self.prompts: list[str] = []
        self.secret_prompts: list[str] = []
        self.output: list[str] = []

    def ask(self, prompt):
        self.prompts.append(prompt)
        return self.answers.pop(0)

    def ask_secret(self, prompt):
        self.prompts.append(prompt)
        self.secret_prompts.append(prompt)
        value = self.secrets.pop(0)
        if isinstance(value, BaseException):
            raise value
        return value

    def say(self, message):
        self.output.append(message)

    @property
    def text(self) -> str:
        return "\n".join(self.prompts + self.output)

    def run(self, db: Session) -> int:
        return script.run_reset(db, TARGET, ask=self.ask, ask_secret=self.ask_secret, say=self.say)


def current(db: Session, username: str = TEST_ADMIN_USERNAME) -> tuple[str, int]:
    db.expire_all()
    row = db.execute(
        select(AdminUser.password_hash, AdminUser.token_version).where(AdminUser.username == username)
    ).one()
    return row.password_hash, row.token_version


def assert_nothing_sensitive(text: str, *values: str) -> None:
    for value in (NEW_PASSWORD, TEST_ADMIN_PASSWORD, *values):
        assert value not in text


@pytest.fixture
def all_logs(caplog):
    # Everything at DEBUG, including SQLAlchemy's SQL log, to prove nothing sensitive is logged.
    caplog.set_level(logging.DEBUG)
    caplog.set_level(logging.INFO, logger="sqlalchemy.engine")
    return caplog


# --- Success ------------------------------------------------------------------------


def test_successful_reset(db, admin, all_logs):
    old_hash, old_version = current(db)
    terminal = FakeTerminal(answers=[TEST_ADMIN_USERNAME, "yes"], secrets=[NEW_PASSWORD, NEW_PASSWORD])

    assert terminal.run(db) == 0

    new_hash, new_version = current(db)
    assert new_version == old_version + 1
    assert new_hash != old_hash and new_hash.startswith(ARGON2ID_PREFIX)
    assert verify_password(NEW_PASSWORD, new_hash)[0] is True
    assert verify_password(TEST_ADMIN_PASSWORD, new_hash)[0] is False
    assert terminal.output[-1] == script.SUCCESS_MESSAGE
    # The passwords were read only through the hidden prompt, and nothing sensitive was shown or logged.
    assert len(terminal.secret_prompts) == 2 and not terminal.secrets
    assert terminal.answers == []  # username and confirmation came through visible input only
    assert_nothing_sensitive(terminal.text, old_hash, new_hash)
    assert_nothing_sensitive(all_logs.text, old_hash, new_hash)


def test_username_is_case_insensitive(db, admin):
    terminal = FakeTerminal(answers=[TEST_ADMIN_USERNAME.upper(), "yes"], secrets=[NEW_PASSWORD, NEW_PASSWORD])
    assert terminal.run(db) == 0
    assert verify_password(NEW_PASSWORD, current(db)[0])[0] is True


def test_reset_signs_out_existing_sessions(db, admin, client, anon_client):
    assert client.get(ME).status_code == 200
    terminal = FakeTerminal(answers=[TEST_ADMIN_USERNAME, "yes"], secrets=[NEW_PASSWORD, NEW_PASSWORD])
    assert terminal.run(db) == 0

    assert client.get(ME).status_code == 401
    assert client.get("/api/companies").status_code == 401
    login = {"username": TEST_ADMIN_USERNAME}
    assert anon_client.post("/api/auth/login", json=login | {"password": TEST_ADMIN_PASSWORD}).status_code == 401
    assert anon_client.post("/api/auth/login", json=login | {"password": NEW_PASSWORD}).status_code == 200


def test_only_the_selected_admin_changes(db, admin, test_admin_password_hash):
    db.add(AdminUser(username="other-admin", password_hash=test_admin_password_hash))
    db.commit()
    other_before = current(db, "other-admin")
    count_before = db.scalar(select(func.count()).select_from(AdminUser))

    terminal = FakeTerminal(answers=[TEST_ADMIN_USERNAME, "yes"], secrets=[NEW_PASSWORD, NEW_PASSWORD])
    assert terminal.run(db) == 0

    assert current(db, "other-admin") == other_before
    assert db.scalar(select(func.count()).select_from(AdminUser)) == count_before


# --- Failures leave everything unchanged ---------------------------------------------


def run_and_expect_failure(db, terminal, message):
    before = current(db)
    assert terminal.run(db) == 1
    assert current(db) == before
    assert any(message in line for line in terminal.output), terminal.output
    assert script.SUCCESS_MESSAGE not in terminal.output
    assert_nothing_sensitive(terminal.text, before[0])


def test_passwords_that_do_not_match(db, admin):
    terminal = FakeTerminal(answers=[TEST_ADMIN_USERNAME], secrets=[NEW_PASSWORD, NEW_PASSWORD + "x"])
    run_and_expect_failure(db, terminal, "The passwords do not match.")
    assert not any("confirm" in p for p in terminal.prompts)  # never reached confirmation


@pytest.mark.parametrize("username", ["nobody", " test-admin", "test admin", ""])
def test_unknown_username(db, admin, username):
    count_before = db.scalar(select(func.count()).select_from(AdminUser))
    terminal = FakeTerminal(answers=[username])
    run_and_expect_failure(db, terminal, "No admin account has that username.")
    assert len(terminal.prompts) == 1  # no password was asked for
    assert db.scalar(select(func.count()).select_from(AdminUser)) == count_before  # nothing created


def test_inactive_admin(db, admin):
    db.execute(AdminUser.__table__.update().values(is_active=False))
    db.commit()
    terminal = FakeTerminal(answers=[TEST_ADMIN_USERNAME])
    run_and_expect_failure(db, terminal, "inactive")
    assert len(terminal.prompts) == 1


@pytest.mark.parametrize(
    ("password", "message"),
    [
        ("short-pw", "Password must be 12-256 characters long."),
        ("x" * 257, "Password must be 12-256 characters long."),
        (" " + NEW_PASSWORD, "cannot start or end with whitespace"),
        (NEW_PASSWORD + " ", "cannot start or end with whitespace"),
        (TEST_ADMIN_PASSWORD, "must be different from the current one"),
    ],
)
def test_password_policy_violations(db, admin, password, message):
    terminal = FakeTerminal(answers=[TEST_ADMIN_USERNAME], secrets=[password, password])
    run_and_expect_failure(db, terminal, message)
    assert password not in "\n".join(terminal.output)  # never echoed
    assert not any("confirm" in p for p in terminal.prompts)  # rejected before confirmation


def test_password_equal_to_the_username(db, admin):
    long_name = "test-admin-12"  # long enough that only the "same as username" rule applies
    db.execute(AdminUser.__table__.update().values(username=long_name))
    db.commit()
    terminal = FakeTerminal(answers=[long_name], secrets=[long_name.upper(), long_name.upper()])
    before = current(db, long_name)
    assert terminal.run(db) == 1
    assert current(db, long_name) == before
    assert "ERROR: Password cannot be the same as the username." in terminal.output


@pytest.mark.parametrize("answer", ["no", "", "y", "YES please"])
def test_anything_but_yes_cancels(db, admin, answer):
    terminal = FakeTerminal(answers=[TEST_ADMIN_USERNAME, answer], secrets=[NEW_PASSWORD, NEW_PASSWORD])
    run_and_expect_failure(db, terminal, "Cancelled. Nothing was changed.")


@pytest.mark.parametrize("interrupt", [KeyboardInterrupt(), EOFError()])
def test_interrupt_cancels(db, admin, interrupt):
    terminal = FakeTerminal(answers=[TEST_ADMIN_USERNAME], secrets=[interrupt])
    run_and_expect_failure(db, terminal, "Cancelled. Nothing was changed.")


def test_database_rejection_rolls_back_with_a_safe_message(db, admin, monkeypatch, all_logs):
    # A broken hasher: the database CHECK rejects the value; PostgreSQL's own message would
    # repeat the row, so the output must contain only the safe message.
    monkeypatch.setattr(admins, "hash_password", lambda password: "plaintext-" + password)
    terminal = FakeTerminal(answers=[TEST_ADMIN_USERNAME, "yes"], secrets=[NEW_PASSWORD, NEW_PASSWORD])
    run_and_expect_failure(db, terminal, "ERROR: Password hash is not in the expected format.")
    assert_nothing_sensitive(all_logs.text)

    # The session is still usable afterwards.
    monkeypatch.undo()
    assert FakeTerminal(answers=[TEST_ADMIN_USERNAME, "yes"], secrets=[NEW_PASSWORD, NEW_PASSWORD]).run(db) == 0


def test_commit_failure_rolls_back(db, admin, monkeypatch):
    def failing_commit():
        raise OperationalError("COMMIT", {}, Exception("connection lost (test double)"))

    monkeypatch.setattr(db, "commit", failing_commit)
    terminal = FakeTerminal(answers=[TEST_ADMIN_USERNAME, "yes"], secrets=[NEW_PASSWORD, NEW_PASSWORD])
    run_and_expect_failure(db, terminal, "database error (OperationalError")
    assert not any("connection lost" in line for line in terminal.output)  # raw error text not shown


# --- Core function and script safety -------------------------------------------------


def test_core_reset_verifies_and_bumps_version(db, admin):
    old_hash, old_version = current(db)
    reset_admin_password(db, TEST_ADMIN_USERNAME, NEW_PASSWORD)
    new_hash, new_version = current(db)
    assert new_version == old_version + 1
    assert verify_password(NEW_PASSWORD, new_hash)[0] is True


def test_core_reset_never_creates_an_account(db):
    with pytest.raises(PasswordResetError, match="No admin account has that username."):
        reset_admin_password(db, "nobody", NEW_PASSWORD)
    assert db.scalar(select(func.count()).select_from(AdminUser)) == 0


def test_script_refuses_the_test_database(monkeypatch, auth_settings, capsys):
    # main() must refuse before connecting when DB_NAME is (or looks like) the test database.
    unsafe = auth_settings.model_copy(update={"db_name": auth_settings.test_db_name})
    monkeypatch.setattr(script, "get_settings", lambda: unsafe)
    monkeypatch.setattr(script, "create_engine", lambda *a, **k: pytest.fail("must not connect"))
    assert script.main() == 2
    assert "REFUSED" in capsys.readouterr().out


def test_script_takes_no_command_line_arguments():
    source = inspect.getsource(script)
    assert "sys.argv" not in source and "argparse" not in source
    assert inspect.signature(script.main).parameters == {}
