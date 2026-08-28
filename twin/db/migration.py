"""Running and comparing migrations.

Kept out of `migrations/env.py` because that module runs its migrations on
import, which makes it unusable from a test. Both the Alembic environment and
the drift test read the object filter from here, so they cannot disagree about
what the application owns.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection

from twin.db.schema import HYPERTABLES, TRUTH_SCHEMA

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ALEMBIC_INI = REPO_ROOT / "alembic.ini"

# The application owns the public schema and the truth schema. Everything else
# in the database belongs to TimescaleDB and is not ours to compare.
OWNED_SCHEMAS: frozenset[str | None] = frozenset({None, "public", TRUTH_SCHEMA})

# create_hypertable adds a descending index on the partitioning column of each
# hypertable. It is TimescaleDB's, not ours, so it is not in the metadata and is
# not a difference when it turns up in a reflected database.
TIMESCALE_INDEXES = frozenset(
    f"{table}_{column}_idx" for table, column in HYPERTABLES.items()
)


def include_object(
    obj: object,
    name: str | None,
    type_: str,
    _reflected: bool,
    _compare_to: object,
) -> bool:
    """Report whether Alembic should consider this object."""
    if type_ == "index" and name in TIMESCALE_INDEXES:
        return False
    if type_ == "table":
        return getattr(obj, "schema", None) in OWNED_SCHEMAS
    parent = getattr(obj, "table", None)
    if parent is not None:
        return getattr(parent, "schema", None) in OWNED_SCHEMAS
    return True


def alembic_config(connection: Connection | None = None) -> Config:
    """Build an Alembic config, optionally bound to an open connection."""
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    if connection is not None:
        config.attributes["connection"] = connection
    return config


def upgrade_to_head(connection: Connection) -> None:
    """Apply every migration on an open connection."""
    command.upgrade(alembic_config(connection), "head")


def downgrade_to_base(connection: Connection) -> None:
    """Roll every migration back on an open connection."""
    command.downgrade(alembic_config(connection), "base")
