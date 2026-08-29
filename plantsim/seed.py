"""Build the seeded demo database. T-024, and what `make seed` runs.

Runs the simulator once and writes two things to two places: the canonical event
stream to the `event` table, which is what the twin reads, and the ground truth
to the `truth` schema, which the twin's role cannot read at all.

The two writes go through the same connection here because a seeding script runs
as an administrator. In the running stack they never could: the api and worker
connect as `digitaltwin_app`, which holds no privilege in the truth schema, and
a test asserts that rather than assuming it (AC-104).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import Connection

from connector.protocol import CanonicalEvent
from plantsim.model import SimulationRequest, SimulationResult, run_simulation
from plantsim.parameters import load_plant_model
from plantsim.scenarios import load_scenarios
from plantsim.truth import write_ground_truth
from twin.config import load_line_definition
from twin.db.schema import event as event_table
from twin.db.schema import line as line_table
from twin.db.schema import station as station_table
from twin.db.schema import variant as variant_table

REPO_ROOT = Path(__file__).resolve().parent.parent

# Batched, because a per-event round trip through the ORM is the one way to miss
# the 50 events a second in NFR-03 by an order of magnitude.
INSERT_BATCH = 2000

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SeedSummary:
    """What one seeding run produced."""

    line_id: str
    scenario_id: str
    units: int
    events: int
    suppressed: int
    truth_rows: dict[str, int]

    @property
    def observability(self) -> float:
        """The share of what happened that the twin can see."""
        total = self.events + self.suppressed
        return self.events / total if total else 0.0


def simulate(
    line_name: str = "line2",
    scenario_id: str = "SC-01",
    seed: int = 20260302,
    units: int = 920,
) -> SimulationResult:
    """Run the simulator for the demo, from the configuration files alone."""
    line = load_line_definition(REPO_ROOT / "config" / "lines" / f"{line_name}.yaml")
    plant = load_plant_model(REPO_ROOT / "config" / "plantsim" / f"{line_name}.yaml")
    catalogue = load_scenarios(REPO_ROOT / "config" / "plantsim" / "scenarios.yaml")
    return run_simulation(
        SimulationRequest(
            line=line,
            plant=plant,
            seed=seed,
            units=units,
            scenario=catalogue.build(scenario_id, line_name),
        )
    )


def write_configuration(
    connection: Connection, loaded_at: datetime, line_name: str = "line2"
) -> None:
    """Load the line definition into the database, so a prediction can be read back.

    The full YAML is retained on the `line` row. A prediction made months ago has
    to be interpretable against the configuration in force when it was made, and
    the configuration is the only place the plant-specific facts live.
    """
    line = load_line_definition(REPO_ROOT / "config" / "lines" / f"{line_name}.yaml")
    payload = json.loads(line.model_dump_json(by_alias=True))
    connection.execute(
        line_table.insert(),
        [
            {
                "line_id": line.line_id,
                "name": line.name,
                "takt_s": line.takt_s,
                "config": payload,
                "config_version": 1,
                "loaded_at": loaded_at,
            }
        ],
    )
    zone_of: dict[str, str] = {}
    order = line.station_ids
    for zone in line.zones:
        first, last = zone.span
        for station_id in order[order.index(first) : order.index(last) + 1]:
            zone_of[station_id] = zone.zone_id
    connection.execute(
        station_table.insert(),
        [
            {
                "line_id": line.line_id,
                "station_id": station.station_id,
                "seq": index + 1,
                "zone_id": zone_of[station.station_id],
                "tier": station.tier,
                "transport_to_next_s": station.transport_to_next_s,
                "is_manual": station.is_manual,
            }
            for index, station in enumerate(line.stations)
        ],
    )
    connection.execute(
        variant_table.insert(),
        [
            {
                "line_id": line.line_id,
                "variant_id": variant_id,
                "name": variant_id,
                "nominal_mix_share": line.mix[variant_id],
            }
            for variant_id in line.variants
        ],
    )


def write_events(connection: Connection, events: tuple[CanonicalEvent, ...]) -> int:
    """Write the canonical stream the twin reads. Returns the row count."""
    rows = [
        {
            "ts_source": item.ts_source,
            "event_id": item.event_id,
            "event_type": item.event_type,
            "line_id": item.line_id,
            "station_id": item.station_id,
            "unit_id": item.unit_id,
            "ts_ingest": item.ts_ingest,
            "payload": item.payload,
            "source_adapter": item.source_adapter,
            "quality_flag": item.quality_flag,
        }
        for item in events
    ]
    for start in range(0, len(rows), INSERT_BATCH):
        connection.execute(event_table.insert(), rows[start : start + INSERT_BATCH])
    return len(rows)


def seed(
    connection: Connection,
    line_name: str = "line2",
    scenario_id: str = "SC-01",
    seed_value: int = 20260302,
    units: int = 920,
) -> SeedSummary:
    """Run the simulator and write everything it produced."""
    result = simulate(line_name, scenario_id, seed_value, units)
    write_configuration(connection, result.truth.epoch, line_name)
    written = write_events(connection, result.events)
    truth_rows = write_ground_truth(connection, result.truth)
    return SeedSummary(
        line_id=result.line_id,
        scenario_id=result.scenario_id,
        units=units,
        events=written,
        suppressed=result.suppressed,
        truth_rows=truth_rows,
    )
