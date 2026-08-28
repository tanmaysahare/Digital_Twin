"""Alembic environment.

The schema in `twin/db/schema.py` is the target. Both the public schema and the
truth schema are compared, so that a migration cannot quietly leave the ground
truth store behind.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection

from twin.db.engine import create_database_engine, settings
from twin.db.migration import include_object
from twin.db.schema import metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = metadata


def run_migrations_offline() -> None:
    """Emit SQL without a connection, for review or for a DBA to apply."""
    context.configure(
        url=settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        include_schemas=True,
        include_object=include_object,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _run(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_schemas=True,
        include_object=include_object,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Apply migrations against the configured database."""
    connectable = config.attributes.get("connection", None)
    if connectable is not None:
        _run(connectable)
        return

    engine = create_database_engine()
    with engine.connect() as connection:
        _run(connection)
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
