from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect

from app.models import Base
from tests.conftest import alembic_config

CRM_TABLES = {"companies", "contacts", "deals", "activities"}
AUTH_TABLES = {"admin_users"}
ALL_TABLES = CRM_TABLES | AUTH_TABLES

CRM_TABLES_REVISION = "09d6732c3643"  # the revision before admin_users was added


def test_single_migration_head(test_engine):
    with test_engine.connect() as conn:
        heads = ScriptDirectory.from_config(alembic_config(conn)).get_heads()
    assert len(heads) == 1


def test_downgrade_and_upgrade_round_trip(test_engine):
    # DDL is transactional in PostgreSQL: if an assertion fails, the schema is rolled back.
    with test_engine.begin() as conn:
        cfg = alembic_config(conn)
        command.downgrade(cfg, "base")
        assert ALL_TABLES.isdisjoint(inspect(conn).get_table_names())
        command.upgrade(cfg, "head")
        assert ALL_TABLES <= set(inspect(conn).get_table_names())


def test_admin_users_revision_removes_only_its_own_table(test_engine):
    with test_engine.begin() as conn:
        cfg = alembic_config(conn)
        command.downgrade(cfg, CRM_TABLES_REVISION)
        tables = set(inspect(conn).get_table_names())
        assert AUTH_TABLES.isdisjoint(tables)
        assert CRM_TABLES <= tables  # the CRM tables are untouched
        command.upgrade(cfg, "head")
        assert ALL_TABLES <= set(inspect(conn).get_table_names())


def test_admin_users_constraints_index_and_defaults(test_engine):
    """What compare_metadata does not check: CHECK constraints, the lower() index, server defaults."""
    with test_engine.connect() as conn:
        insp = inspect(conn)
        checks = {c["name"] for c in insp.get_check_constraints("admin_users")}
        indexes = {i["name"]: i for i in insp.get_indexes("admin_users")}
        defaults = {c["name"]: c["default"] for c in insp.get_columns("admin_users")}

    assert checks == {
        "ck_admin_users_username_not_blank",
        "ck_admin_users_username_trimmed",
        "ck_admin_users_username_valid_characters",
        "ck_admin_users_password_hash_not_blank",
        "ck_admin_users_password_hash_phc_format",
        "ck_admin_users_token_version_non_negative",
    }
    index = indexes["uq_admin_users_username_lower"]
    assert index["unique"]
    # PostgreSQL renders it as e.g. lower((username)::text); check the shape, not the exact text.
    [expression] = index["expressions"]
    assert expression.startswith("lower(") and "username" in expression
    assert defaults["is_active"] == "true"
    assert defaults["token_version"] == "0"
    assert defaults["id"] == "gen_random_uuid()"


def test_models_match_migrated_schema(test_engine):
    """Fails if a model was changed without a matching migration."""
    with test_engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []
