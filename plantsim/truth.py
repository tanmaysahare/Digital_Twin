"""The ground truth channel. T-024.

What actually happened on the simulated line: every station's real cycle time,
including at the six stations no sensor watches, every blocked and starved
second, every buffer level, and the cause of every defect.

None of it reaches the twin. It is held in memory during a run and written to
the `truth` database schema, which the application role has no grant on and
cannot read (AC-104, verified by a test rather than assumed). If the twin could
join against this, every number in the evidence pack would be worthless, and an
accidental join is exactly the mistake that happens at 2 am before a deadline.

The evaluation harness reads it, connecting as the truth role, after the twin
has committed to its predictions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import Connection, Table

from twin.db.schema import (
    TRUTH_SCHEMA,
    buffer_occupancy,
    gate_result,
    scenario_injection,
    station_visit,
    unit_outcome,
)


@dataclass(frozen=True)
class VisitTruth:
    """What one unit's visit to one station really consisted of.

    `cycle_time_s` is processing time, which includes any repair that
    interrupted the work. The twin cannot separate a slow station from a broken
    one at a dark station, and defining truth this way says so rather than
    holding the twin to a distinction it has no evidence for.
    """

    line_id: str
    unit_id: str
    station_id: str
    seq: int
    variant_id: str
    shift_id: str
    arrived_at_s: float
    work_started_at_s: float
    work_ended_at_s: float
    departed_at_s: float
    cycle_time_s: float
    blocked_s: float
    # How long this unit sat on the conveyor or in the buffer feeding this
    # station, having arrived and waiting to be picked up. Blocking is the
    # station's wait; this is the unit's, and the two together are the whole of
    # the non-work time a virtual sensor has to bound.
    queued_before_s: float
    # How long the station waited for this unit after it was free. Station
    # level rather than unit level, but recorded here because this is the visit
    # that ended the wait.
    starved_before_s: float
    down_s: float
    is_dark: bool


@dataclass(frozen=True)
class GateTruth:
    """One inspection result and the causes that produced it.

    `cause_odds` carries each contributing factor and the odds multiplier it
    applied, so that a retro-trace hypothesis can be scored against what
    actually drove the failure rather than against a label.
    """

    line_id: str
    unit_id: str
    gate_id: str
    at_s: float
    passed: bool
    failure_probability: float
    defect_class: str | None
    cause_odds: dict[str, float]


@dataclass(frozen=True)
class UnitTruth:
    """One unit's life on the line."""

    line_id: str
    unit_id: str
    variant_id: str
    released_at_s: float
    completed_at_s: float | None
    status: str
    rework_passes: int
    lots: tuple[str, ...]


@dataclass(frozen=True)
class BufferTruth:
    """A buffer's occupancy at the moment it changed."""

    line_id: str
    buffer_id: str
    at_s: float
    occupancy: int


@dataclass(frozen=True)
class InjectionTruth:
    """What a scenario injected, where and when. PRD.md Section 6."""

    scenario_id: str
    line_id: str
    station_id: str | None
    injected_at_s: float
    ends_at_s: float | None
    mechanism: str
    parameters: dict[str, object]


@dataclass
class GroundTruth:
    """Everything the simulator knows about a run.

    Mutable by design: it is an accumulator, not a domain object. It leaves the
    simulator by exactly two routes, the evaluation harness and the truth
    schema, and neither of them is reachable from the twin.
    """

    line_id: str
    run_id: UUID
    epoch: datetime
    visits: list[VisitTruth] = field(default_factory=list)
    gate_results: list[GateTruth] = field(default_factory=list)
    units: list[UnitTruth] = field(default_factory=list)
    buffer_levels: list[BufferTruth] = field(default_factory=list)
    injections: list[InjectionTruth] = field(default_factory=list)

    def visits_at(self, station_id: str) -> tuple[VisitTruth, ...]:
        """Every visit to one station, in the order they happened."""
        return tuple(visit for visit in self.visits if visit.station_id == station_id)

    def cycle_times_at(self, station_id: str) -> tuple[float, ...]:
        """Every true cycle time at one station."""
        return tuple(visit.cycle_time_s for visit in self.visits_at(station_id))

    def completed_units(self) -> int:
        """How many units finished the line."""
        return sum(1 for unit in self.units if unit.status == "COMPLETED")

    def schema(self) -> str:
        """The database schema this truth belongs in."""
        return TRUTH_SCHEMA


def write_ground_truth(connection: Connection, truth: GroundTruth) -> dict[str, int]:
    """Write a run's ground truth to the truth schema. Returns the row counts.

    The caller connects as the truth role. Connecting as the application role
    raises a permission error, which is the point: the separation is grants
    rather than convention, and a test asserts it rather than assuming it
    (AC-104).
    """
    epoch = truth.epoch
    written: dict[str, int] = {}

    def at(seconds: float) -> datetime:
        return epoch + timedelta(seconds=seconds)

    written["station_visit"] = _insert(
        connection,
        station_visit,
        [
            {
                "visit_id": uuid4(),
                "run_id": truth.run_id,
                "line_id": visit.line_id,
                "unit_id": visit.unit_id,
                "station_id": visit.station_id,
                "seq": visit.seq,
                "variant_id": visit.variant_id,
                "shift_id": visit.shift_id or None,
                "arrived_at": at(visit.arrived_at_s),
                "work_ended_at": at(visit.work_ended_at_s),
                "departed_at": at(visit.departed_at_s),
                "cycle_time_s": visit.cycle_time_s,
                "blocked_s": visit.blocked_s,
                "queued_before_s": visit.queued_before_s,
                "starved_before_s": visit.starved_before_s,
                "down_s": visit.down_s,
                "is_dark": visit.is_dark,
            }
            for visit in truth.visits
        ],
    )
    written["unit_outcome"] = _insert(
        connection,
        unit_outcome,
        [
            {
                "unit_id": unit.unit_id,
                "run_id": truth.run_id,
                "line_id": unit.line_id,
                "variant_id": unit.variant_id,
                "released_at": at(unit.released_at_s),
                "completed_at": (
                    at(unit.completed_at_s) if unit.completed_at_s is not None else None
                ),
                "status": unit.status,
                "rework_passes": unit.rework_passes,
                "lots": list(unit.lots),
            }
            for unit in truth.units
        ],
    )
    written["gate_result"] = _insert(
        connection,
        gate_result,
        [
            {
                "result_id": uuid4(),
                "run_id": truth.run_id,
                "line_id": result.line_id,
                "unit_id": result.unit_id,
                "gate_id": result.gate_id,
                "at": at(result.at_s),
                "passed": result.passed,
                "failure_probability": result.failure_probability,
                "defect_class": result.defect_class,
                "cause_odds": result.cause_odds,
            }
            for result in truth.gate_results
        ],
    )
    written["buffer_occupancy"] = _insert(
        connection,
        buffer_occupancy,
        [
            {
                "run_id": truth.run_id,
                "line_id": level.line_id,
                "buffer_id": level.buffer_id,
                "at": at(level.at_s),
                "occupancy": level.occupancy,
            }
            for level in truth.buffer_levels
        ],
    )
    written["scenario_injection"] = _insert(
        connection,
        scenario_injection,
        [
            {
                "injection_id": uuid4(),
                "run_id": truth.run_id,
                "scenario_id": injection.scenario_id,
                "line_id": injection.line_id,
                "station_id": injection.station_id,
                "injected_at": at(injection.injected_at_s),
                "ends_at": (
                    at(injection.ends_at_s) if injection.ends_at_s is not None else None
                ),
                "mechanism": injection.mechanism,
                "parameters": injection.parameters,
            }
            for injection in truth.injections
        ],
    )
    return written


def _insert(connection: Connection, table: Table, rows: list[dict[str, object]]) -> int:
    """Insert a batch, or nothing if the batch is empty."""
    if not rows:
        return 0
    connection.execute(table.insert(), rows)
    return len(rows)
