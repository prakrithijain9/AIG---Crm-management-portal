from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect

from app.models import Base
from tests.conftest import alembic_config

CRM_TABLES = {"companies", "contacts", "deals", "activities"}


def test_single_migration_head(test_engine):
    with test_engine.connect() as conn:
        heads = ScriptDirectory.from_config(alembic_config(conn)).get_heads()
    assert len(heads) == 1


def test_downgrade_and_upgrade_round_trip(test_engine):
    with test_engine.begin() as conn:
        cfg = alembic_config(conn)
        command.downgrade(cfg, "base")
        assert CRM_TABLES.isdisjoint(inspect(conn).get_table_names())
        command.upgrade(cfg, "head")
        assert CRM_TABLES <= set(inspect(conn).get_table_names())


def test_models_match_migrated_schema(test_engine):
    """Fails if a model was changed without a matching migration."""
    with test_engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == []
