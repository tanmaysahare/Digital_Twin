"""The simulator's ground truth, and the twin's inability to read it.

T-024, AC-104.

The separation is grants, not convention, and this file asserts it rather than
assuming it. If the twin could join against the truth schema, every number in
the evidence pack would be worthless, and an accidental join is exactly the
mistake that happens at 2 am before a deadline.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Connection, text
from sqlalchemy.exc import ProgrammingError

from plantsim.model import SimulationDetail, SimulationRequest, run_simulation
from plantsim.parameters import load_plant_model
from plantsim.scenarios import load_scenarios
from plantsim.truth import write_ground_truth
from twin.config import load_line_definition
from twin.db.schema import TRUTH_TABLES

pytestmark = pytest.mark.database

REPO_ROOT = Path(__file__).resolve().parent.parent
APP_ROLE = "digitaltwin_app"
TRUTH_ROLE = "digitaltwin_truth"


@pytest.fixture(scope="module")
def written_truth() -> object:
    """A short run whose ground truth is worth writing down."""
    line = load_line_definition(REPO_ROOT / "config" / "lines" / "line2.yaml")
    plant = load_plant_model(REPO_ROOT / "config" / "plantsim" / "line2.yaml")
    scenarios = load_scenarios(REPO_ROOT / "config" / "plantsim" / "scenarios.yaml")
    return run_simulation(
        SimulationRequest(
            line=line,
            plant=plant,
            seed=1234,
            units=40,
            scenario=scenarios.build("SC-01", "line2"),
            detail=SimulationDetail(
                process_values=False, station_state=False, buffer_levels=True
            ),
        )
    )


def test_the_truth_channel_writes_every_kind_of_record(
    connection: Connection, written_truth: object
) -> None:
    """T-024. Cycle times, outcomes, verdicts, buffer levels and injections."""
    written = write_ground_truth(connection, written_truth.truth)  # type: ignore[attr-defined]
    assert set(written) == set(TRUTH_TABLES)
    assert written["station_visit"] > 0
    assert written["unit_outcome"] > 0
    assert written["gate_result"] > 0
    assert written["buffer_occupancy"] > 0
    assert written["scenario_injection"] == 1


def test_the_dark_stations_true_cycle_times_are_in_the_truth_schema(
    connection: Connection, written_truth: object
) -> None:
    """The answer the virtual sensors are graded against lives here and only here."""
    write_ground_truth(connection, written_truth.truth)  # type: ignore[attr-defined]
    dark = connection.execute(
        text(
            "SELECT count(*) FROM truth.station_visit "
            "WHERE is_dark AND cycle_time_s > 0"
        )
    ).scalar_one()
    assert dark > 0


@pytest.mark.parametrize("table", TRUTH_TABLES)
def test_the_application_role_has_no_grant_on_any_truth_table(
    connection: Connection, table: str
) -> None:
    """AC-104. Checked per table, so a new one cannot be added without a grant."""
    for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE"):
        assert (
            connection.execute(
                text("SELECT has_table_privilege(:role, :table, :privilege)"),
                {
                    "role": APP_ROLE,
                    "table": f"truth.{table}",
                    "privilege": privilege,
                },
            ).scalar_one()
            is False
        ), f"{APP_ROLE} holds {privilege} on truth.{table}"


@pytest.mark.parametrize("table", TRUTH_TABLES)
def test_the_application_role_is_denied_in_practice(
    connection: Connection, table: str
) -> None:
    """The grant check says what is configured. This says what happens."""
    connection.execute(text(f"SET LOCAL ROLE {APP_ROLE}"))
    with pytest.raises(ProgrammingError, match="permission denied"):
        connection.execute(text(f"SELECT * FROM truth.{table} LIMIT 1"))


def test_the_truth_role_owns_every_truth_table(connection: Connection) -> None:
    """Ownership, so a default privilege cannot quietly hand one over."""
    owners = dict(
        connection.execute(
            text(
                "SELECT tablename, tableowner FROM pg_tables WHERE schemaname = 'truth'"
            )
        ).all()
    )
    assert set(owners) == set(TRUTH_TABLES)
    assert set(owners.values()) == {TRUTH_ROLE}


def test_the_twin_never_imports_the_truth_channel() -> None:
    """A grant is the last defence. Nothing in twin/ reaches for this at all."""
    offenders = [
        path
        for path in (REPO_ROOT / "twin").rglob("*.py")
        if "plantsim.truth" in path.read_text(encoding="utf-8")
        or "from plantsim" in path.read_text(encoding="utf-8")
    ]
    assert offenders == [], (
        f"{[str(path) for path in offenders]} import the simulator. The twin runs "
        f"against a canonical event stream and knows nothing about what produced it"
    )
