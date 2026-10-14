"""Creating admin accounts and resetting their passwords.

Used by scripts/create_admin.py and scripts/reset_admin_password.py; there are no HTTP
endpoints for either. Errors carry only safe, fixed messages: never the password, its
hash, or database details.
"""

from sqlalchemy import exists, func, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.security import WeakPassword, check_new_password, hash_password, verify_password
from app.db.errors import safe_db_error_message
from app.models import AdminUser
from app.models.admin_user import (
    ADMIN_USER_CONSTRAINT_MESSAGES,
    ADMIN_USER_SAVE_FAILED,
    InvalidUsername,
    username_lookup_key,
    validate_username,
)


class AdminCreationError(Exception):
    """Admin could not be created. str(exc) is safe to show and log."""


def admin_exists(db: Session) -> bool:
    return bool(db.scalar(select(exists().where(AdminUser.id.is_not(None)))))


def create_admin(db: Session, username: str, password: str, *, allow_additional: bool = False) -> AdminUser:
    """Validate, hash (Argon2id, verified) and insert an admin. The caller commits.

    By default refuses when any admin already exists: this creates the *initial* account.
    """
    try:
        validate_username(username)
        check_new_password(password, username=username)
    except (InvalidUsername, WeakPassword) as exc:
        raise AdminCreationError(str(exc)) from None

    if not allow_additional and admin_exists(db):
        raise AdminCreationError("An admin account already exists; this command only creates the first one.")
    if db.scalar(select(AdminUser.id).where(func.lower(AdminUser.username) == username_lookup_key(username))):
        raise AdminCreationError(ADMIN_USER_CONSTRAINT_MESSAGES["uq_admin_users_username_lower"])

    admin = AdminUser(username=username, password_hash=hash_password(password))
    try:
        # A savepoint, so a failed insert leaves the caller's session usable.
        with db.begin_nested():
            db.add(admin)
    except DBAPIError as exc:
        # `from None`: the original error's DETAIL line repeats the row, hash included.
        raise AdminCreationError(
            safe_db_error_message(exc, ADMIN_USER_CONSTRAINT_MESSAGES, ADMIN_USER_SAVE_FAILED)
        ) from None
    return admin


# --- Password reset ----------------------------------------------------------------

PASSWORD_RESET_FAILED = "The password could not be saved. Nothing was changed."


class PasswordResetError(Exception):
    """The password was not reset. str(exc) is safe to show and log."""


def find_admin_for_reset(db: Session, username: str, *, lock: bool = False) -> AdminUser:
    """The active admin with this username (case-insensitive), or PasswordResetError.

    With lock=True the row is locked (SELECT ... FOR UPDATE) until the transaction ends.
    """
    try:
        key = username_lookup_key(username)
    except InvalidUsername:
        raise PasswordResetError("No admin account has that username.") from None
    stmt = select(AdminUser).where(func.lower(AdminUser.username) == key)
    if lock:
        stmt = stmt.with_for_update()
    admin = db.scalar(stmt)
    if admin is None:
        raise PasswordResetError("No admin account has that username.")
    if not admin.is_active:
        raise PasswordResetError("That admin account is inactive. Its password was not changed.")
    return admin


def check_reset_password(admin: AdminUser, password: str) -> None:
    """Apply the new-password policy; also refuse the account's current password."""
    try:
        check_new_password(password, username=admin.username)
    except WeakPassword as exc:
        raise PasswordResetError(str(exc)) from None
    if verify_password(password, admin.password_hash)[0]:
        raise PasswordResetError("The new password must be different from the current one.")


def reset_admin_password(db: Session, username: str, password: str) -> None:
    """Set a new password for one active admin and revoke all of its sessions. The caller commits.

    The hash is Argon2id and verified before use (hash_password). The update touches only
    that admin's row and increments token_version in the same statement, so every
    existing session token for the account stops working.
    """
    admin = find_admin_for_reset(db, username, lock=True)
    check_reset_password(admin, password)
    new_hash = hash_password(password)

    stmt = (
        update(AdminUser)
        .where(AdminUser.id == admin.id, AdminUser.is_active.is_(True))
        .values(password_hash=new_hash, token_version=AdminUser.token_version + 1)
        .execution_options(synchronize_session=False)
    )
    try:
        # A savepoint, so a failed update leaves the caller's session usable.
        with db.begin_nested():
            if db.execute(stmt).rowcount != 1:
                raise PasswordResetError(PASSWORD_RESET_FAILED)
    except DBAPIError as exc:
        # `from None`: the original error's DETAIL line repeats the row, hash included.
        raise PasswordResetError(
            safe_db_error_message(exc, ADMIN_USER_CONSTRAINT_MESSAGES, PASSWORD_RESET_FAILED)
        ) from None
    db.expire(admin)  # the in-memory object still holds the old hash and version
