"""Shared fixtures.

The database fixtures skip rather than fail when no database is reachable, so
that `make test` is useful on a machine with nothing running. The database tests
are marked, so `pytest -m "not database"` runs the rest.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import OperationalError

from twin.db.engine import DEFAULT_DATABASE_URL, create_database_engine
from twin.db.migration import upgrade_to_head


@pytest.fixture(scope="session")
def database_url() -> str:
    """The database under test."""
    return os.environ.get("DIGITALTWIN_DATABASE_URL", DEFAULT_DATABASE_URL)


@pytest.fixture(scope="session")
def engine(database_url: str) -> Iterator[Engine]:
    """An engine against a reachable database, or a skip."""
    built = create_database_engine(database_url)
    try:
        with built.connect() as connection:
            connection.execute(text("SELECT 1"))
    except OperationalError as unreachable:
        built.dispose()
        pytest.skip(
            f"No database at {database_url}. Start one with 'make db'. "
            f"({unreachable.orig})"
        )
    yield built
    built.dispose()


@pytest.fixture(scope="session")
def migrated(engine: Engine) -> Iterator[Engine]:
    """A database at head. Migrations run once for the session."""
    with engine.begin() as connection:
        upgrade_to_head(connection)
    yield engine


@pytest.fixture
def connection(migrated: Engine) -> Iterator[Connection]:
    """A connection whose work is rolled back at the end of the test."""
    with migrated.connect() as open_connection:
        transaction = open_connection.begin()
        try:
            yield open_connection
        finally:
            transaction.rollback()
