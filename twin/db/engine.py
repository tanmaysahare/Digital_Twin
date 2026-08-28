"""Database connection settings and the engine.

Configuration is read once at startup and passed down, never read at call time
(CODING_STANDARDS.md Section 8). Credentials come from the environment and are
never committed.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import Engine, create_engine

DEFAULT_DATABASE_URL = (
    "postgresql+psycopg://postgres:postgres@localhost:5432/digitaltwin"
)


class DatabaseSettings(BaseSettings):
    """Where the database is and how the application connects to it."""

    model_config = SettingsConfigDict(env_prefix="DIGITALTWIN_", extra="ignore")

    database_url: str = Field(default=DEFAULT_DATABASE_URL)
    # Deliberately small. The api and the worker are separate processes and the
    # worker's parallelism is in a process pool, not in connections.
    pool_size: int = Field(default=5, ge=1, le=50)
    echo_sql: bool = Field(default=False)


@lru_cache(maxsize=1)
def settings() -> DatabaseSettings:
    """Read the database settings once."""
    return DatabaseSettings()


def create_database_engine(url: str | None = None) -> Engine:
    """Build an engine. Pass a url to point at a test database."""
    resolved = url or settings().database_url
    return create_engine(
        resolved,
        pool_size=settings().pool_size,
        pool_pre_ping=True,
        echo=settings().echo_sql,
        future=True,
    )
