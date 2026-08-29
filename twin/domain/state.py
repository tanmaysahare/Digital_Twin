"""The live picture of the line. STA-01, STA-02, STA-03.

Every quantity in here that the twin worked out rather than read arrives as an
`Estimate`, so a consumer cannot use a number without seeing where it came from.
A dark station's cycle time is an interval and there is no field on any of these
types that could hold a single value for one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from twin.config.line import Tier
from twin.domain.estimate import Estimate, Resolution

StationState = Literal[
    "RUNNING",
    "BLOCKED",
    "STARVED",
    "DOWN",
    "CHANGEOVER",
    "IDLE",
    # A station with no flanking evidence may be idle for a reason the twin
    # cannot determine. It is shown as this and never collapsed into one of the
    # known states, because guessing here is how a screen starts lying.
    "IDLE_UNKNOWN",
]

Trend = Literal["RISING", "FALLING", "FLAT"]


@dataclass(frozen=True)
class StationSnapshot:
    """One station, as the twin currently understands it."""

    station_id: str
    tier: Tier
    state: StationState
    since: datetime
    current_unit_id: str | None
    # None where the twin has no basis for one at all: a dark station with no
    # instrumented station downstream of it has nothing to bound its work with.
    last_cycle: Estimate | None
    resolution: Resolution
    # How many cycles have accumulated. Below the line's minimum the station is
    # excluded from forecasting and the interface says how many remain (EC-20).
    observed_cycles: int
    # Why the twin believes what it believes, in one line, shown beside the
    # value it explains.
    basis: str

    @property
    def is_dark(self) -> bool:
        """Whether this station emits no machine data at all."""
        return self.tier == "C"


@dataclass(frozen=True)
class BufferSnapshot:
    """One buffer's occupancy against its capacity."""

    buffer_id: str
    after_station_id: str
    occupancy: Estimate
    capacity: int
    trend: Trend


@dataclass(frozen=True)
class UnresolvedStation:
    """A station the twin cannot estimate at all, and what would fix it.

    STA-07 and EC-17. The pair matters: saying a station is unresolved without
    saying what would resolve it is a complaint rather than a finding, and the
    Sensor Value Card is built from the second half of this record.
    """

    station_id: str
    reason: str
    resolved_by: str


@dataclass(frozen=True)
class LineState:
    """The whole line at one instant. STA-01."""

    line_id: str
    at: datetime
    stations: tuple[StationSnapshot, ...]
    buffers: tuple[BufferSnapshot, ...]
    unresolved: tuple[UnresolvedStation, ...] = ()

    def station(self, station_id: str) -> StationSnapshot:
        """One station's snapshot by identifier."""
        for snapshot in self.stations:
            if snapshot.station_id == station_id:
                return snapshot
        message = f"no station {station_id} in this line state"
        raise KeyError(message)

    def dark_stations(self) -> tuple[StationSnapshot, ...]:
        """Every station that emits no machine data."""
        return tuple(snapshot for snapshot in self.stations if snapshot.is_dark)

    def running(self) -> int:
        """How many stations are working right now."""
        return sum(1 for snapshot in self.stations if snapshot.state == "RUNNING")
