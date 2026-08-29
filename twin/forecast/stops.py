"""What a stall is, and how the twin sees one happen.

One definition, used in three places: the forecast says how likely one is
(`aggregate.py`), this module says when one occurred, and the evaluation harness
computes the same quantity from the simulator's ground truth. If those three
disagreed, every precision figure in the evidence pack would be measuring three
different things.

**The definition.** A stall at station k is a five-minute bucket in which k lost
more than `stall_threshold_s` production seconds to blocking or starving.

**Why the accumulated reading rather than the continuous one.**
TECHNICAL_SPEC.md Section 5.1 says "any station BLOCKED or STARVED for longer
than `stop_threshold_s`", reported per bucket, and on a paced line those two
readings are not the same thing. A station on a line running to takt waits a few
seconds on every single cycle, because its work content is below takt and that
is what takt means. A *continuous* wait past 180 s therefore happens only inside
a long repair, and measured on Line 2 the only such episodes in a full day were
the line filling at the start of the run. The accumulated wait inside a bucket is
what a supervisor recognises as the line falling behind, and it is what a
drifting station actually produces. The finding is recorded in
TECHNICAL_SPEC.md Section 5.1 and in TASKS.md under Phase 2.

**Non-production time is not lost time.** A shift break is not a stall (EC-11).
Every duration here is measured in production seconds through the calendar, so a
lunch break inside a bucket removes that time from the bucket rather than
counting as the whole line stopping.

**Six stations cannot be observed at all.** S33 to S37 and S42 emit nothing, so
there is no arrival and no departure to measure a wait between. They are absent
from `episodes` and named in `unobservable`, rather than reporting zero lost time
and looking like the best-behaved stations on the line.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from connector.protocol import CanonicalEvent
from twin.config.line import LineDefinition
from twin.domain.shifts import ProductionCalendar
from twin.forecast.des import BUCKET_S


@dataclass(frozen=True)
class StallEpisode:
    """One bucket in which one station lost more than the threshold."""

    line_id: str
    station_id: str
    started_at: datetime
    ended_at: datetime
    lost_s: float
    blocked_s: float
    starved_s: float

    @property
    def dominant(self) -> str:
        """Whether the station was mostly blocked or mostly starved."""
        return "BLOCKED" if self.blocked_s >= self.starved_s else "STARVED"


@dataclass
class _Station:
    """One station's open intervals as its events arrive."""

    last_departed_at: datetime | None = None
    work_ended_at: datetime | None = None
    holding: bool = False


@dataclass
class StallObserver:
    """Accumulates each station's lost production time, bucket by bucket.

    Feed it the canonical stream. It reads blocking as the gap between a station
    finishing a cycle and the unit leaving, and starving as the gap between a
    unit leaving and the next arriving, both of which are visible at every tier A
    and tier B station and at neither tier C one.
    """

    line: LineDefinition
    calendar: ProductionCalendar
    _stations: dict[str, _Station] = field(default_factory=dict)
    _blocked: dict[tuple[str, int], float] = field(
        default_factory=lambda: defaultdict(float)
    )
    _starved: dict[tuple[str, int], float] = field(
        default_factory=lambda: defaultdict(float)
    )
    _at: datetime | None = field(default=None)

    def __post_init__(self) -> None:
        """One accumulator per station that emits anything at all."""
        for station in self.line.stations:
            if station.tier != "C":
                self._stations[station.station_id] = _Station()

    @property
    def unobservable(self) -> tuple[str, ...]:
        """Every station whose waiting time nothing on the line records."""
        return tuple(
            station.station_id for station in self.line.stations if station.tier == "C"
        )

    def observe(self, event: CanonicalEvent) -> None:
        """Take one canonical event."""
        self._at = event.ts_source
        station = (
            self._stations.get(event.station_id)
            if event.station_id is not None
            else None
        )
        if station is None or event.station_id is None:
            return
        station_id = event.station_id
        if event.event_type == "UNIT_ARRIVE":
            if station.last_departed_at is not None:
                self._add(
                    self._starved,
                    station_id,
                    station.last_departed_at,
                    event.ts_source,
                )
            station.holding = True
            station.work_ended_at = None
        elif event.event_type == "CYCLE_END":
            station.work_ended_at = event.ts_source
        elif event.event_type == "UNIT_DEPART":
            if station.work_ended_at is not None:
                self._add(
                    self._blocked,
                    station_id,
                    station.work_ended_at,
                    event.ts_source,
                )
            station.work_ended_at = None
            station.holding = False
            station.last_departed_at = event.ts_source

    def _add(
        self,
        grid: dict[tuple[str, int], float],
        station_id: str,
        start: datetime,
        end: datetime,
    ) -> None:
        """Charge an interval's production seconds to the buckets it falls in."""
        if end <= start:
            return
        epoch = self.calendar.epoch
        start_s = (start - epoch).total_seconds()
        end_s = (end - epoch).total_seconds()
        first = int(start_s // BUCKET_S)
        last = int(end_s // BUCKET_S)
        for bucket in range(first, last + 1):
            edge_lo = bucket * BUCKET_S
            overlap_lo = max(start_s, edge_lo)
            overlap_hi = min(end_s, edge_lo + BUCKET_S)
            if overlap_hi <= overlap_lo:
                continue
            producing = self.calendar.production_between(overlap_lo, overlap_hi)
            if producing > 0:
                grid[(station_id, bucket)] += producing

    def episodes(self, threshold_s: float | None = None) -> tuple[StallEpisode, ...]:
        """Every bucket in which a station lost more than the threshold."""
        limit = (
            threshold_s
            if threshold_s is not None
            else self.line.forecast.stall_threshold_s
        )
        epoch = self.calendar.epoch
        keys = set(self._blocked) | set(self._starved)
        found: list[StallEpisode] = []
        for station_id, bucket in sorted(keys, key=lambda key: (key[1], key[0])):
            blocked = self._blocked.get((station_id, bucket), 0.0)
            starved = self._starved.get((station_id, bucket), 0.0)
            if blocked + starved <= limit:
                continue
            found.append(
                StallEpisode(
                    line_id=self.line.line_id,
                    station_id=station_id,
                    started_at=epoch + timedelta(seconds=bucket * BUCKET_S),
                    ended_at=epoch + timedelta(seconds=(bucket + 1) * BUCKET_S),
                    lost_s=blocked + starved,
                    blocked_s=blocked,
                    starved_s=starved,
                )
            )
        return tuple(found)

    def lost_s(self, station_id: str, at: datetime) -> float:
        """How much one station lost in the bucket containing an instant."""
        bucket = int((at - self.calendar.epoch).total_seconds() // BUCKET_S)
        return self._blocked.get((station_id, bucket), 0.0) + self._starved.get(
            (station_id, bucket), 0.0
        )
