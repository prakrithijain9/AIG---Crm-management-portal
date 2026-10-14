"""Initial-admin creation (the logic behind scripts/create_admin.py), on the test database."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import admins
from app.core.admins import AdminCreationError, admin_exists, create_admin
from app.core.security import ARGON2ID_PREFIX, verify_password
from app.models import AdminUser

PASSWORD = "test-only-password-5678"


def count_admins(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(AdminUser))


def test_creates_an_admin_with_a_verified_argon2id_hash(db: Session):
    assert not admin_exists(db)
    admin = create_admin(db, "Admin.Ops", PASSWORD)
    db.flush()

    assert admin_exists(db)
    stored = db.scalar(select(AdminUser).where(AdminUser.id == admin.id))
    assert stored.username == "Admin.Ops"  # kept as typed; lookups are case-insensitive
    assert stored.is_active is True and stored.token_version == 0
    assert stored.password_hash.startswith(ARGON2ID_PREFIX)
    assert PASSWORD not in stored.password_hash
    assert verify_password(PASSWORD, stored.password_hash)[0] is True


def test_refuses_a_second_admin_by_default(db: Session):
    create_admin(db, "admin", PASSWORD)
    with pytest.raises(AdminCreationError, match="already exists"):
        create_admin(db, "another", PASSWORD)
    assert count_admins(db) == 1


def test_duplicate_username_is_case_insensitive(db: Session):
    create_admin(db, "admin", PASSWORD)
    with pytest.raises(AdminCreationError, match="An admin with this username already exists."):
        create_admin(db, "ADMIN", PASSWORD, allow_additional=True)
    assert count_admins(db) == 1


@pytest.mark.parametrize("username", ["", " admin", "admin ", "ad min", "admin\t", "аdmin"])
def test_invalid_usernames_are_rejected(db: Session, username: str):
    with pytest.raises(AdminCreationError, match="Username must be"):
        create_admin(db, username, PASSWORD)
    assert count_admins(db) == 0


@pytest.mark.parametrize("password", ["short", " " + PASSWORD, PASSWORD + " ", "administrator-1"])
def test_weak_passwords_are_rejected_without_echoing_them(db: Session, password: str):
    with pytest.raises(AdminCreationError) as exc_info:
        create_admin(db, "administrator-1", password)
    assert password.strip() not in str(exc_info.value)
    assert count_admins(db) == 0


def test_database_rejection_gives_a_safe_message(db: Session, monkeypatch):
    # Simulate a broken hasher: the database CHECK must reject the value, and the error
    # must not contain it (PostgreSQL's own message repeats the whole row).
    monkeypatch.setattr(admins, "hash_password", lambda password: "plaintext-" + password)
    with pytest.raises(AdminCreationError) as exc_info:
        create_admin(db, "admin", PASSWORD)
    assert str(exc_info.value) == "Password hash is not in the expected format."
    assert exc_info.value.__cause__ is None and exc_info.value.__suppress_context__
    assert count_admins(db) == 0

    # The savepoint was rolled back, so the same session can still create the admin.
    monkeypatch.undo()
    create_admin(db, "admin", PASSWORD)
    assert count_admins(db) == 1
