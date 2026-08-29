"""The process signature: what happened to one unit, station by station. STA-03.

This is the record every defect question is answered from, and the reason its
cycle time is an `Estimate` rather than a float is that a third of this unit's
route may have been through stations that emit nothing. The signature says which
of its numbers were read and which were reasoned to, per station, and the defect
model reads that distinction as a feature rather than treating it as a hole
(DEF-03).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from twin.domain.estimate import Estimate
from twin.domain.state import StationState


@dataclass(frozen=True)
class StationVisit:
    """One unit's stay at one station."""

    station_id: str
    # Visit order for this unit, so a rework revisit is distinguishable from
    # the first pass rather than looking like a data error (EC-15).
    seq: int
    arrived_at: datetime | None
    departed_at: datetime | None
    dwell_s: float | None
    # None at a station the twin cannot bound at all.
    cycle_time: Estimate | None
    state_during: StationState
    blocked_s: Estimate | None
    starved_s: Estimate | None
    process_values: dict[str, float] = field(default_factory=dict)
    part_lots: tuple[str, ...] = ()
    operator_group: str | None = None
    shift_id: str | None = None
    environment: dict[str, float] = field(default_factory=dict)

    @property
    def is_measured(self) -> bool:
        """Whether the cycle time at this visit was read rather than reasoned to."""
        return self.cycle_time is not None and self.cycle_time.provenance == "MEASURED"


@dataclass(frozen=True)
class ProcessSignature:
    """One unit's whole route, in order."""

    unit_id: str
    line_id: str
    variant_id: str
    entered_at: datetime
    exited_at: datetime | None
    status: str
    visits: tuple[StationVisit, ...]

    def visit(self, station_id: str) -> StationVisit | None:
        """The unit's most recent visit to one station."""
        for item in reversed(self.visits):
            if item.station_id == station_id:
                return item
        return None

    def dark_visits(self) -> tuple[StationVisit, ...]:
        """Every visit whose cycle time the twin had to infer.

        Counted as a feature of its own. A unit that spent a third of its route
        where nothing is measured is a different unit from one that did not, and
        the model is told so rather than left to discover it (DEF-03).
        """
        return tuple(
            item
            for item in self.visits
            if item.cycle_time is None or item.cycle_time.provenance == "INFERRED"
        )

    def inferred_dwell_s(self) -> float:
        """Total time this unit spent where the twin could only infer."""
        return sum(item.dwell_s or 0.0 for item in self.dark_visits())
