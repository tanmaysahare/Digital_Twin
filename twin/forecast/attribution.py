"""Constraint attribution by average active period. T-054.

TECHNICAL_SPEC.md Section 5.2, following Roser, Nakano and Tanaka and the
data-driven extension by Subramaniyan et al. (RESEARCH_SOURCES S-06 to S-09).

**The method.** An active period for station k is a maximal interval during which
k is neither blocked nor starved: it is working, changing over, or down under its
own fault, but it is not waiting on a neighbour. The station with the longest
average active period over a rolling window is the momentary constraint.

The reason this works, and the reason it is worth two engines rather than one, is
that it needs no model of the line at all. The bottleneck is the station that
never waits, because everything else on the line is waiting on it. On Line 2
under SC-01 the effect is unmistakable: S20's waiting time falls to nothing as it
crosses takt while every other station's rises, so its active periods merge
across cycles and its average multiplies while everything else stays at one
cycle. A discrete-event forecast says what the consequence will be; this says
what is causing it, and an industrial engineer can check it by standing at the
station with a stopwatch.

**Shift boundaries reset the accumulator rather than spanning it.** The original
method assumes continuous operation. A two-shift line does not satisfy that, and
an active period measured across a changeover would merge the last unit of one
crew with the first of the next.

**The buffer trend is a second opinion, not a tie-break.** The constraint should
also be the station whose downstream buffer is filling or whose upstream buffer
is emptying. Where the two signals agree the attribution is reported as agreed.
Where they disagree both are reported, because a disagreement is information: it
usually means the constraint has just moved and one of the two signals has not
caught up.

**A dark station cannot be attributed this way and the answer says so.** Nothing
observes when S33 to S37 start and stop working, so they have no active periods
to average. They are listed as unattributable rather than silently scoring zero,
which would rank them last and imply they had been assessed.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from connector.protocol import CanonicalEvent
from twin.config.line import LineDefinition
from twin.domain.state import BufferSnapshot

# Two working intervals separated by less than this are one active period. A
# station hands a unit on and takes the next in a few tenths of a second on a
# line that is not waiting, and treating that as a break would cap every active
# period at one cycle and destroy the method. Expressed as a share of takt so it
# moves with the line rather than being a constant in code.
_CONTINUITY_TOLERANCE_TAKTS = 0.02

# A station needs at least one active period overlapping the window before its
# average is reported. It used to need two, and that was wrong in the one case
# the method exists for: the constraint's active periods merge across cycles
# precisely because it never waits, so on a line where one station has been
# working without a break for three hours it has a single period, and requiring
# two dropped the bottleneck out of the ranking entirely. Measured on SC-01,
# S20's active period ran to 11,330 s and the method named S11 instead.
_MINIMUM_PERIODS = 1


@dataclass(frozen=True)
class ActivePeriod:
    """One maximal interval during which a station was not waiting."""

    station_id: str
    started_at: datetime
    ended_at: datetime
    cycles: int

    @property
    def duration_s(self) -> float:
        """How long the station worked without waiting."""
        return (self.ended_at - self.started_at).total_seconds()


@dataclass(frozen=True)
class StationActivity:
    """One station's active periods over the attribution window."""

    station_id: str
    average_active_s: float
    periods: int
    longest_s: float


@dataclass(frozen=True)
class ConstraintAttribution:
    """Which station is holding the line back, and on what evidence.

    Two methods, reported separately. `agreement` is false where they name
    different stations, and the interface shows both rather than choosing
    (TECHNICAL_SPEC.md Section 5.2).
    """

    at: datetime
    by_active_period: str | None
    by_buffer_trend: str | None
    agreement: bool
    ranked: tuple[StationActivity, ...]
    unattributable: tuple[str, ...]
    basis: str

    @property
    def methods(self) -> tuple[str, ...]:
        """The attribution methods that produced this answer, for the API."""
        found = []
        if self.by_active_period is not None:
            found.append("AVERAGE_ACTIVE_PERIOD")
        if self.by_buffer_trend is not None:
            found.append("BUFFER_TREND")
        return tuple(found)

    @property
    def constraint(self) -> str | None:
        """The single station to name, where the two methods agree.

        None where they disagree. A caller that wants a station anyway reads
        `by_active_period` and shows the disagreement beside it.
        """
        return self.by_active_period if self.agreement else None


@dataclass
class _Station:
    """The open active period at one station, as events arrive."""

    working_since: datetime | None = None
    last_work_ended: datetime | None = None
    open_started: datetime | None = None
    open_cycles: int = 0


@dataclass
class ActivePeriodTracker:
    """Accumulates active periods from the canonical stream. T-054."""

    line: LineDefinition
    _stations: dict[str, _Station] = field(default_factory=dict)
    _periods: dict[str, deque[ActivePeriod]] = field(default_factory=dict)
    _shift_id: str | None = field(default=None)
    _at: datetime | None = field(default=None)

    def __post_init__(self) -> None:
        """One accumulator per station, sized by the attribution window."""
        for station in self.line.stations:
            self._stations[station.station_id] = _Station()
            self._periods[station.station_id] = deque(
                maxlen=_window_capacity(self.line)
            )

    @property
    def tolerance_s(self) -> float:
        """How long a gap can be before it breaks an active period."""
        return self.line.takt_s * _CONTINUITY_TOLERANCE_TAKTS

    def observe(self, event: CanonicalEvent) -> None:
        """Take one canonical event."""
        self._at = event.ts_source
        if event.event_type == "SHIFT_MARKER":
            self._on_shift_marker(event)
            return
        if event.station_id is None:
            return
        station = self._stations.get(event.station_id)
        if station is None:
            return
        if event.event_type == "UNIT_ARRIVE":
            self._start_work(event.station_id, station, event.ts_source)
        elif event.event_type == "CYCLE_END":
            self._end_work(event.station_id, station, event.ts_source)

    def _on_shift_marker(self, event: CanonicalEvent) -> None:
        """Close every open period at a shift boundary rather than spanning it."""
        marker = str(event.payload.get("marker", ""))
        if marker not in {"END", "CHANGEOVER", "BREAK_START"}:
            self._shift_id = str(event.payload.get("shift_id", "")) or self._shift_id
            return
        for station_id, station in self._stations.items():
            self._close(station_id, station)

    def _start_work(self, station_id: str, station: _Station, at: datetime) -> None:
        if station.working_since is not None:
            return
        gap = (
            (at - station.last_work_ended).total_seconds()
            if station.last_work_ended is not None
            else None
        )
        if station.open_started is None or (gap is not None and gap > self.tolerance_s):
            self._close(station_id, station)
            station.open_started = at
            station.open_cycles = 0
        station.working_since = at

    def _end_work(self, station_id: str, station: _Station, at: datetime) -> None:
        if station.working_since is None:
            return
        station.working_since = None
        station.last_work_ended = at
        station.open_cycles += 1
        del station_id

    def _close(self, station_id: str, station: _Station) -> None:
        if station.open_started is None or station.last_work_ended is None:
            station.open_started = None
            station.open_cycles = 0
            return
        if station.last_work_ended > station.open_started:
            self._periods[station_id].append(
                ActivePeriod(
                    station_id=station_id,
                    started_at=station.open_started,
                    ended_at=station.last_work_ended,
                    cycles=station.open_cycles,
                )
            )
        station.open_started = None
        station.open_cycles = 0

    # -- the answer -------------------------------------------------------

    def activity(self, at: datetime | None = None) -> tuple[StationActivity, ...]:
        """Each station's average active period over the window, ranked.

        Two details decide whether this method works at all.

        **The period still open is counted.** A station that has been working
        without waiting for the last forty minutes has an active period of at
        least forty minutes, and that is the strongest evidence the method can
        produce. Counting only the periods that have closed loses exactly the
        station the method is looking for.

        **Every period is clipped to the window.** An average over a rolling
        window has to be an average over that window, or a station that ran
        without a break for three hours before it stopped would keep winning the
        ranking long after it had stopped being the constraint.
        """
        now = at or self._at
        if now is None:
            return ()
        since = now - timedelta(minutes=self.line.forecast.attribution_window_min)
        found: list[StationActivity] = []
        for station_id in self.line.station_ids:
            station = self._stations[station_id]
            spans = [
                (period.started_at, period.ended_at)
                for period in self._periods[station_id]
            ]
            if station.open_started is not None:
                spans.append((station.open_started, station.last_work_ended or now))
            durations = []
            for started_at, ended_at in spans:
                overlap = (min(ended_at, now) - max(started_at, since)).total_seconds()
                if overlap > 0:
                    durations.append(overlap)
            if len(durations) < _MINIMUM_PERIODS:
                continue
            found.append(
                StationActivity(
                    station_id=station_id,
                    average_active_s=sum(durations) / len(durations),
                    periods=len(durations),
                    longest_s=max(durations),
                )
            )
        return tuple(sorted(found, key=lambda item: -item.average_active_s))

    def attribute(
        self,
        buffers: tuple[BufferSnapshot, ...],
        at: datetime | None = None,
    ) -> ConstraintAttribution:
        """Name the constraint, by both methods, and say whether they agree."""
        now = at or self._at
        if now is None:
            message = "no events have been seen, so there is no constraint to name"
            raise ValueError(message)
        ranked = self.activity(now)
        leader = ranked[0].station_id if ranked else None
        by_buffer = self._by_buffer_trend(buffers)
        unattributable = tuple(
            station.station_id for station in self.line.stations if station.tier == "C"
        )
        agreement = leader is not None and leader == by_buffer
        return ConstraintAttribution(
            at=now,
            by_active_period=leader,
            by_buffer_trend=by_buffer,
            agreement=agreement,
            ranked=ranked,
            unattributable=unattributable,
            basis=_basis(ranked, leader, by_buffer, agreement=agreement),
        )

    def _by_buffer_trend(self, buffers: tuple[BufferSnapshot, ...]) -> str | None:
        """The station a filling buffer points at.

        A buffer that is filling is feeding a station that cannot keep up, so the
        station immediately after the buffer is the candidate. A buffer that is
        emptying is being drained faster than it is filled, so the candidate is
        upstream. Where several buffers point, the fullest one wins, because a
        buffer near its capacity is closer to passing the blockage on.
        """
        order = self.line.station_ids
        candidates: dict[str, float] = defaultdict(float)
        for snapshot in buffers:
            index = order.index(snapshot.after_station_id)
            if snapshot.trend == "RISING" and index + 1 < len(order):
                fullness = snapshot.occupancy.hi / max(1, snapshot.capacity)
                candidates[order[index + 1]] = max(
                    candidates[order[index + 1]], fullness
                )
            elif snapshot.trend == "FALLING":
                emptiness = 1.0 - snapshot.occupancy.hi / max(1, snapshot.capacity)
                candidates[snapshot.after_station_id] = max(
                    candidates[snapshot.after_station_id], emptiness * 0.5
                )
        if not candidates:
            return None
        return max(sorted(candidates), key=lambda station_id: candidates[station_id])


def _window_capacity(line: LineDefinition) -> int:
    """How many active periods a window could hold at worst.

    One per cycle is the worst case, which happens on a line where every station
    waits on every cycle. That is the normal case on a line running to takt.
    """
    return max(
        _MINIMUM_PERIODS,
        int(line.forecast.attribution_window_min * 60.0 / max(1.0, line.takt_s)) + 2,
    )


def _basis(
    ranked: tuple[StationActivity, ...],
    leader: str | None,
    by_buffer: str | None,
    *,
    agreement: bool,
) -> str:
    """One line a supervisor can read, saying what the attribution rests on."""
    if leader is None:
        return (
            "not enough completed cycles in the attribution window to average an "
            "active period at any station yet"
        )
    top = ranked[0]
    runner = ranked[1] if len(ranked) > 1 else None
    against = (
        f", against {runner.average_active_s:.0f} s at {runner.station_id}"
        if runner is not None
        else ""
    )
    core = (
        f"{leader} worked {top.average_active_s:.0f} s at a time without waiting "
        f"on a neighbour, over {top.periods} periods{against}"
    )
    if by_buffer is None:
        return (
            f"{core}. No buffer is trending either way, so only one method has spoken"
        )
    if agreement:
        return f"{core}. The buffer trend points at {leader} as well"
    return (
        f"{core}. The buffer trend points at {by_buffer} instead, so both are "
        f"reported. A disagreement here usually means the constraint has just "
        f"moved and one of the two signals has not caught up"
    )
