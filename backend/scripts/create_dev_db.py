"""Create the app role, development database and test database if they don't already exist.

Safe to run repeatedly: it only CREATEs missing objects and never drops,
alters or overwrites existing roles or databases.

Reads the app's DB_USER / DB_PASSWORD / DB_NAME from backend/.env, and prompts
(hidden input) for a PostgreSQL superuser password to perform the setup.

Usage (from backend/):
    .venv\Scripts\python scripts\create_dev_db.py
"""

import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg  # noqa: E402
from psycopg import sql  # noqa: E402

from app.core.config import get_settings  # noqa: E402


def main() -> None:
    s = get_settings()
    app_password = s.db_password.get_secret_value()
    if not app_password or app_password == "change-me":
        sys.exit("Set a real DB_PASSWORD in backend/.env first.")

    admin_user = os.environ.get("PG_ADMIN_USER", "postgres")
    admin_password = getpass.getpass(f"Password for PostgreSQL superuser '{admin_user}': ")

    with psycopg.connect(
        host=s.db_host,
        port=s.db_port,
        user=admin_user,
        password=admin_password,
        dbname="postgres",
        autocommit=True,  # CREATE DATABASE cannot run inside a transaction
    ) as conn:
        role_exists = conn.execute(
            "SELECT 1 FROM pg_roles WHERE rolname = %s", (s.db_user,)
        ).fetchone()
        if role_exists:
            print(f"Role '{s.db_user}' already exists - left unchanged.")
        else:
            conn.execute(
                sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                    sql.Identifier(s.db_user), sql.Literal(app_password)
                )
            )
            print(f"Created role '{s.db_user}'.")

        # Development database, plus a separate database used only by pytest.
        for db_name in (s.db_name, s.test_db_name):
            db_exists = conn.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (db_name,)
            ).fetchone()
            if db_exists:
                print(f"Database '{db_name}' already exists - left unchanged.")
            else:
                conn.execute(
                    sql.SQL("CREATE DATABASE {} OWNER {}").format(
                        sql.Identifier(db_name), sql.Identifier(s.db_user)
                    )
                )
                print(f"Created database '{db_name}' owned by '{s.db_user}'.")


if __name__ == "__main__":
    main()
