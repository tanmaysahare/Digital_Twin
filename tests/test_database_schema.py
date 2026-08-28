"""The schema, its migrations, and the two separations that carry the argument.

T-007, T-008, T-009. AC-104.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import DBAPIError, ProgrammingError

from twin.db.migration import downgrade_to_base, include_object, upgrade_to_head
from twin.db.schema import metadata

pytestmark = pytest.mark.database

APP_ROLE = "digitaltwin_app"


def _install_line(connection: Connection, line_id: str) -> None:
    connection.execute(
        text(
            "INSERT INTO line (line_id, name, takt_s, config, config_version, "
            "loaded_at) VALUES (:id, :name, 60, '{}'::jsonb, 1, now())"
        ),
        {"id": line_id, "name": "Line 2"},
    )


def test_migrations_reach_head_and_roll_back(engine: Engine) -> None:
    with engine.begin() as connection:
        upgrade_to_head(connection)
        downgrade_to_base(connection)
        remaining = connection.execute(
            text(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema IN ('public', 'truth') "
                "AND table_name <> 'alembic_version'"
            )
        ).scalar_one()
        assert remaining == 0
        upgrade_to_head(connection)


def test_schema_matches_the_metadata(connection: Connection) -> None:
    """A migrated database and twin/db/schema.py cannot drift apart."""
    context = MigrationContext.configure(
        connection,
        opts={
            "include_schemas": True,
            "include_object": include_object,
            "compare_type": True,
            "compare_server_default": True,
        },
    )
    assert compare_metadata(context, metadata) == []


def test_the_three_hypertables_exist(connection: Connection) -> None:
    installed = connection.execute(
        text("SELECT count(*) FROM pg_extension WHERE extname = 'timescaledb'")
    ).scalar_one()
    if not installed:
        pytest.skip("TimescaleDB is not installed; the tables stay ordinary")
    names = set(
        connection.execute(
            text("SELECT hypertable_name FROM timescaledb_information.hypertables")
        ).scalars()
    )
    assert {"event", "station_state", "buffer_state"} <= names


def test_a_measured_cycle_time_cannot_be_an_interval(connection: Connection) -> None:
    """The check that makes it impossible to store an inference as a reading."""
    _install_line(connection, "line_check")
    connection.execute(
        text(
            "INSERT INTO station (line_id, station_id, seq, zone_id, tier) "
            "VALUES ('line_check', 'S20', 20, 'body', 'A')"
        )
    )
    insert = text(
        "INSERT INTO station_state (ts, line_id, station_id, state, since, "
        "cycle_time_lo, cycle_time_hi, provenance, confidence, basis) "
        "VALUES (now(), 'line_check', 'S20', 'RUNNING', now(), :lo, :hi, "
        ":provenance, 1.0, 'cycle events')"
    )
    with pytest.raises(DBAPIError, match="measured_is_a_point"):
        connection.execute(insert, {"lo": 54, "hi": 71, "provenance": "MEASURED"})


def test_an_inferred_cycle_time_may_be_an_interval(connection: Connection) -> None:
    _install_line(connection, "line_interval")
    connection.execute(
        text(
            "INSERT INTO station (line_id, station_id, seq, zone_id, tier) "
            "VALUES ('line_interval', 'S34', 34, 'final', 'C')"
        )
    )
    connection.execute(
        text(
            "INSERT INTO station_state (ts, line_id, station_id, state, since, "
            "cycle_time_lo, cycle_time_hi, provenance, confidence, basis) "
            "VALUES (now(), 'line_interval', 'S34', 'RUNNING', now(), 54, 71, "
            "'INFERRED', 0.42, 'bounded from flanking arrivals at S33 and S38')"
        )
    )


@pytest.mark.parametrize("table", ["prediction", "prediction_outcome"])
def test_the_ledger_refuses_an_update(connection: Connection, table: str) -> None:
    _install_line(connection, f"line_{table}")
    prediction_id = uuid.uuid4()
    connection.execute(
        text(
            "INSERT INTO prediction (prediction_id, predictor, model_version, "
            "line_id, station_id, made_at, horizon_end, claim, confidence, "
            "evidence, inputs_hash, published) VALUES (:id, 'stall_forecaster', "
            "'0.1.0', :line, 'S20', :made, :horizon, '{}'::jsonb, 0.71, "
            "'{}'::jsonb, 'abc123', false)"
        ),
        {
            "id": prediction_id,
            "line": f"line_{table}",
            "made": datetime(2026, 8, 29, 9, 14, tzinfo=UTC),
            "horizon": datetime(2026, 8, 29, 11, 14, tzinfo=UTC),
        },
    )
    if table == "prediction_outcome":
        connection.execute(
            text(
                "INSERT INTO prediction_outcome (prediction_id, resolved_at, "
                "result, actual) VALUES (:id, now(), 'TRUE_POSITIVE', '{}'::jsonb)"
            ),
            {"id": prediction_id},
        )

    with pytest.raises(DBAPIError, match="append-only"):
        connection.execute(
            text(f"UPDATE {table} SET line_id = line_id WHERE prediction_id = :id")
            if table == "prediction"
            else text(
                "UPDATE prediction_outcome SET result = 'FALSE_POSITIVE' "
                "WHERE prediction_id = :id"
            ),
            {"id": prediction_id},
        )


@pytest.mark.parametrize("table", ["prediction", "prediction_outcome"])
def test_the_ledger_refuses_a_delete(connection: Connection, table: str) -> None:
    _install_line(connection, f"del_{table}")
    prediction_id = uuid.uuid4()
    connection.execute(
        text(
            "INSERT INTO prediction (prediction_id, predictor, model_version, "
            "line_id, station_id, made_at, horizon_end, claim, confidence, "
            "evidence, inputs_hash, published) VALUES (:id, 'drift_detector', "
            "'0.1.0', :line, 'S20', now(), now(), '{}'::jsonb, 0.5, "
            "'{}'::jsonb, 'abc123', false)"
        ),
        {"id": prediction_id, "line": f"del_{table}"},
    )
    if table == "prediction_outcome":
        connection.execute(
            text(
                "INSERT INTO prediction_outcome (prediction_id, resolved_at, "
                "result, actual) VALUES (:id, now(), 'UNSCOREABLE', '{}'::jsonb)"
            ),
            {"id": prediction_id},
        )
    with pytest.raises(DBAPIError, match="append-only"):
        connection.execute(
            text(f"DELETE FROM {table} WHERE prediction_id = :id"),
            {"id": prediction_id},
        )


def test_the_application_role_has_no_update_grant_on_the_ledger(
    connection: Connection,
) -> None:
    for table in ("prediction", "prediction_outcome"):
        for privilege in ("UPDATE", "DELETE"):
            granted = connection.execute(
                text("SELECT has_table_privilege(:role, :table, :privilege)"),
                {"role": APP_ROLE, "table": table, "privilege": privilege},
            ).scalar_one()
            assert granted is False, f"{APP_ROLE} still holds {privilege} on {table}"
        assert (
            connection.execute(
                text("SELECT has_table_privilege(:role, :table, 'INSERT')"),
                {"role": APP_ROLE, "table": table},
            ).scalar_one()
            is True
        )


def test_the_application_role_cannot_read_ground_truth(connection: Connection) -> None:
    """AC-104. Asserted rather than assumed."""
    assert (
        connection.execute(
            text("SELECT has_schema_privilege(:role, 'truth', 'USAGE')"),
            {"role": APP_ROLE},
        ).scalar_one()
        is False
    )
    assert (
        connection.execute(
            text(
                "SELECT has_table_privilege(:role, 'truth.scenario_injection', "
                "'SELECT')"
            ),
            {"role": APP_ROLE},
        ).scalar_one()
        is False
    )


def test_the_application_role_is_denied_in_practice(connection: Connection) -> None:
    """The grant check above says what is configured. This says what happens."""
    connection.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
    with pytest.raises(ProgrammingError, match="permission denied"):
        connection.execute(text("SELECT * FROM truth.scenario_injection"))
