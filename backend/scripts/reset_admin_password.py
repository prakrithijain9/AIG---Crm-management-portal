"""Reset one CRM admin's password from a trusted server terminal (account recovery).

Usage (from backend/, on the server, with access to backend/.env):
    .venv\\Scripts\\python scripts\\reset_admin_password.py

Prompts for the admin username, then the new password twice (hidden). There are no
command-line options: nothing sensitive can end up in shell history or process listings.

What it does:
  * Only the named, active admin is changed; nothing is created, and no other account is touched.
  * The new password must meet the sign-in policy (12-256 characters, no leading/trailing
    spaces, not the username) and differ from the current one.
  * Stores an Argon2id hash (verified before saving) and increments token_version in the same
    update, so every existing session for that account is signed out.
  * Asks for confirmation; commits only after everything succeeded, otherwise rolls back.
  * Never prints the password, the hash, secrets or raw database errors.

Safety: refuses the test database, and checks the connected database and migration head.
Exit status: 0 success, 1 failed or cancelled (nothing changed), 2 refused.
"""

import getpass
import sys
from collections.abc import Callable
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.exc import DBAPIError  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.admins import (  # noqa: E402
    PasswordResetError,
    check_reset_password,
    find_admin_for_reset,
    reset_admin_password,
)
from app.core.config import get_settings  # noqa: E402
from app.db.errors import safe_db_error_summary  # noqa: E402
from app.seed.demo import SeedRefused, check_connection, check_target  # noqa: E402

SUCCESS_MESSAGE = "Password reset complete. All existing sessions for this account have been signed out."


def run_reset(
    db: Session,
    target: str,
    *,
    ask: Callable[[str], str] = input,
    ask_secret: Callable[[str], str] = getpass.getpass,
    say: Callable[[str], None] = print,
) -> int:
    """The interactive reset on an open session. Commits on success, rolls back otherwise."""
    password = confirmation = None
    try:
        say(f"Resetting an admin password in database '{target}'.")
        admin = find_admin_for_reset(db, ask("Admin username: "))
        username = admin.username  # a plain string, safe to use after commit

        password = ask_secret("New password (not shown): ")
        confirmation = ask_secret("Repeat new password: ")
        if password != confirmation:
            raise PasswordResetError("The passwords do not match.")
        check_reset_password(admin, password)  # fail before asking for confirmation

        answer = ask(
            f"Reset the password for '{username}' in '{target}' and sign out all of its sessions? "
            "Type 'yes' to confirm: "
        )
        if answer.strip().lower() != "yes":
            db.rollback()
            say("Cancelled. Nothing was changed.")
            return 1

        reset_admin_password(db, username, password)
        db.commit()
    except PasswordResetError as exc:
        db.rollback()
        say(f"ERROR: {exc}")
        return 1
    except DBAPIError as exc:
        db.rollback()
        # Only the error code and constraint name; never the row or parameters.
        say(f"ERROR: database error ({safe_db_error_summary(exc)}). Nothing was changed.")
        return 1
    except (KeyboardInterrupt, EOFError):
        db.rollback()
        say("Cancelled. Nothing was changed.")
        return 1
    finally:
        del password, confirmation

    say(SUCCESS_MESSAGE)
    return 0


def main() -> int:
    settings = get_settings()
    try:
        target = check_target(settings)
    except SeedRefused as exc:
        print(f"REFUSED: {exc}")
        return 2

    # hide_parameters: bound values (the hash) never appear in logs or error messages.
    engine = create_engine(settings.url_for(target), hide_parameters=True)
    try:
        with Session(engine) as db:
            try:
                check_connection(db, target)
            except SeedRefused as exc:
                print(f"REFUSED: {exc}")
                return 2
            except DBAPIError as exc:
                print(f"ERROR: database error ({safe_db_error_summary(exc)}). Nothing was changed.")
                return 1
            return run_reset(db, target)
    finally:
        engine.dispose()


if __name__ == "__main__":
    sys.exit(main())
