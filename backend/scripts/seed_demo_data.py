"""Seed the DEVELOPMENT database with demo CRM data (insert-only, repeatable).

Usage (from backend/):
    .venv\\Scripts\\python scripts\\seed_demo_data.py           # dry run: shows the plan, writes nothing
    .venv\\Scripts\\python scripts\\seed_demo_data.py --apply   # inserts missing demo records

Safety:
  * Only ever targets DB_NAME; refuses if it equals TEST_DB_NAME or ends with "_test".
  * Verifies the connected database name and that migrations are at head.
  * Dry run uses a READ ONLY transaction (PostgreSQL rejects any write).
  * Insert-only: existing records are skipped, never updated; nothing is deleted.
  * All inserts happen in one transaction: either everything is saved or nothing is.
"""

import argparse
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.seed.demo import SeedRefused, check_connection, check_target, seed_demo_data  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="actually insert (default: dry run)")
    args = parser.parse_args()

    settings = get_settings()
    try:
        target = check_target(settings)
    except SeedRefused as exc:
        print(f"REFUSED: {exc}")
        return 2

    # hide_parameters: bound values never appear in logs or error messages.
    engine = create_engine(settings.url_for(target), hide_parameters=True)
    with Session(engine) as db:
        if not args.apply:
            db.execute(text("SET TRANSACTION READ ONLY"))
        try:
            check_connection(db, target)
            report = seed_demo_data(db, apply=args.apply)
        except SeedRefused as exc:
            db.rollback()
            print(f"REFUSED: {exc}")
            return 2

        mode = "APPLY" if args.apply else "DRY RUN (read-only, nothing will be written)"
        print(f"Target database: {target} on {settings.db_host}:{settings.db_port}   Mode: {mode}\n")
        for entity, action, label in report.lines:
            print(f"  {entity:9} {action:16} {label}")
        for warning in report.warnings:
            print(f"  WARNING: {warning}")

        print()
        for entity in ("company", "contact", "deal", "activity"):
            new = report.count(entity, "create" if args.apply else "would create")
            skipped = sum(1 for e, a, _ in report.lines if e == entity and a.startswith("skip"))
            print(f"  {entity:9} new={new:<3} skipped={skipped}")

        if args.apply:
            db.commit()
            print("\nCommitted.")
        else:
            db.rollback()
            print("\nDry run only. Re-run with --apply to insert.")
    engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
