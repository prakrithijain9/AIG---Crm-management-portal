"""Create the initial CRM admin account in the DEVELOPMENT (or configured) database.

Usage (from backend/, after `alembic upgrade head`):
    .venv\\Scripts\\python scripts\\create_admin.py

The username and password are prompted for interactively; the password is typed twice
and never echoed. Nothing is accepted from command-line arguments or the environment, so
the password cannot end up in shell history or process listings. Only an Argon2id hash
(verified before saving) is stored, and nothing about the password or hash is printed.

Safety:
  * Refuses the test database (TEST_DB_NAME, or any name ending in "_test").
  * Verifies the connected database name and that migrations are at head.
  * Refuses if an admin already exists (it only creates the first account).
  * Asks for confirmation before writing; the insert is a single transaction.
"""

import getpass
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.exc import DBAPIError  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.admins import AdminCreationError, admin_exists, create_admin  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.db.errors import safe_db_error_summary  # noqa: E402
from app.seed.demo import SeedRefused, check_connection, check_target  # noqa: E402


def prompt_password() -> str:
    first = getpass.getpass("Password (not shown): ")
    second = getpass.getpass("Repeat password: ")
    if first != second:
        raise AdminCreationError("The passwords do not match.")
    return first


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
                if admin_exists(db):
                    print("REFUSED: an admin account already exists; this command only creates the first one.")
                    return 2

                print(f"Creating the initial admin account in database '{target}'.")
                username = input("Username: ")
                password = prompt_password()
                admin = create_admin(db, username, password)
                del password
                # A plain string: after commit and session close, ORM attributes can't be loaded.
                created_username = admin.username

                answer = input(f"Create admin '{created_username}' in '{target}'? Type 'yes' to confirm: ")
                if answer.strip().lower() != "yes":
                    db.rollback()
                    print("Cancelled. Nothing was written.")
                    return 1
                db.commit()
            except SeedRefused as exc:
                print(f"REFUSED: {exc}")
                return 2
            except AdminCreationError as exc:
                db.rollback()
                print(f"ERROR: {exc}")
                return 1
            except DBAPIError as exc:
                db.rollback()
                # Only the error code and constraint name; never the row or parameters.
                print(f"ERROR: database error ({safe_db_error_summary(exc)}). Nothing was written.")
                return 1
            except (KeyboardInterrupt, EOFError):
                db.rollback()
                print("\nCancelled. Nothing was written.")
                return 1
    finally:
        engine.dispose()

    print(f"Created admin '{created_username}'. Sign in at the CRM login page.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
