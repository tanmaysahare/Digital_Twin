"""Loss accounting, and the reconciliation that keeps it honest.

UX_SPEC.md Sections 2.5 and 3.3. The Line view shows what the shift has lost so
far, split by cause. Plan view shows the same split as a Pareto over a longer
range. Both come from here, and both carry the same reconciliation line.

**Why a reconciliation line is not optional.** A plant already counts its lost
minutes, and it counts them from the andon board and the shift report. If the
twin's accounting does not tie to that, the twin has produced a second set of
books, and a second set of books is worse than no books: the first argument in
the first meeting is about which number is right, and the twin loses that
argument because it is the newcomer. So the split is presented against the total
the line's own pace implies, and whatever the causes do not explain is shown as
unexplained rather than distributed across the causes to make them add up.

**The five causes, and where each one comes from.**

- `blocked` and `starved` come from the flow: the gap between a station
  finishing work and giving the unit up, and the gap between giving one up and
  receiving the next. Both are measured from timestamps at instrumented
  stations. At a dark station they cannot be separated at all, and that time is
  reported as unexplained rather than attributed to a cause the twin guessed.
- `down` comes from a station's own state word where it emits one, and from an
  andon call where it does not.
- `changeover` comes from the production calendar, which is where the plant's
  own changeover allowance lives.
- `quality` is the time units spent in rework after failing a gate.

A cause with no evidence behind it reads as zero and the unexplained share
carries the difference. That is the entire design.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from connector.protocol import CanonicalEvent
from twin.config.line import LineDefinition
from twin.domain.shifts import ProductionCalendar

# The order the causes appear in, everywhere. A stacked bar whose segments move
# between renders is a bar nobody can read across two screens.
CAUSES = ("blocked", "starved", "down", "changeover", "quality")


@dataclass(frozen=True)
class LossSplit:
    """Lost production time over one window, by cause, with what is unexplained."""

    from_at: datetime
    to_at: datetime
    minutes: dict[str, float]
    # What the line's own pace says was lost over the window, which is the
    # figure the split is reconciled against.
    implied_total_min: float
    # Production time the window held, across every station. The denominator
    # for the unexplained share: measuring the gap against the gap it is part of
    # made a small difference look enormous whenever the window was quiet.
    available_min: float
    per_station_min: dict[str, dict[str, float]]

    @property
    def accounted_min(self) -> float:
        """The sum of the causes."""
        return sum(self.minutes.values())

    @property
    def unexplained_min(self) -> float:
        """What the causes do not explain. Never distributed to make them tie."""
        return self.implied_total_min - self.accounted_min

    @property
    def unexplained_share(self) -> float:
        """The unexplained part as a share of the production time available."""
        if self.available_min <= 0.0:
            return 0.0
        return self.unexplained_min / self.available_min

    def reconciliation(self) -> str:
        """The sentence UX_SPEC.md Section 3.3 requires under the Pareto.

        The two sides can disagree in either direction and the sentence says
        which. A positive gap is time the twin could not attribute to a cause,
        which on this line is mostly the stations that emit nothing. A negative
        gap means the causes add to more than the production time available,
        which is a measurement problem in the twin rather than a fact about the
        line, and saying so is more use than hiding it.
        """
        gap = self.unexplained_min
        share = abs(self.unexplained_share) * 100
        if gap >= 0:
            tail = (
                "which nothing accounts for. Most of it is at the stations that "
                "emit neither a cycle time nor the timestamps blocked and "
                "starved are measured between."
            )
        else:
            tail = (
                "by which the causes exceed the production time the window "
                "held. Two of them are being counted over the same seconds "
                "somewhere and the twin has not established where, so the "
                "difference is shown rather than trimmed to make the two sides "
                "agree."
            )
        return (
            f"Sum of causes {self.accounted_min:,.0f} station min. Production "
            f"time not worked {self.implied_total_min:,.0f} station min, out of "
            f"{self.available_min:,.0f} available. Difference "
            f"{abs(gap):,.0f} min ({share:.1f} percent of the time available), "
            f"{tail}"
        )


@dataclass
class LossLedger:
    """Accumulates lost production time per station per cause as events arrive.

    Held apart from `StallObserver`, which answers a different question. That
    one asks whether a station lost more than a threshold inside a bucket, which
    is what a stall forecast is scored against. This one asks how the shift's
    lost minutes divide, which is what a supervisor and a plant manager read.
    """

    line: LineDefinition
    calendar: ProductionCalendar

    # Cause and station to the periods recorded against them, each period
    # kept with both of its ends so that a query window can clip it. Keeping
    # only the end and the duration credited a stoppage that began an hour
    # earlier entirely to the window it finished in, and the window's causes
    # then exceeded the production time it had.
    _seconds: dict[tuple[str, str], list[tuple[datetime, datetime, float]]] = field(
        default_factory=lambda: defaultdict(list), repr=False
    )
    _work_ended: dict[str, datetime] = field(default_factory=dict, repr=False)
    _departed: dict[str, datetime] = field(default_factory=dict, repr=False)
    _down_since: dict[str, datetime] = field(default_factory=dict, repr=False)
    _andon_since: dict[str, datetime] = field(default_factory=dict, repr=False)
    _rework_since: dict[str, datetime] = field(default_factory=dict, repr=False)
    _changeover_since: datetime | None = field(default=None, repr=False)
    _worked: list[tuple[datetime, float]] = field(default_factory=list, repr=False)
    _first_at: datetime | None = field(default=None, repr=False)
    _last_at: datetime | None = field(default=None, repr=False)

    def observe(self, event: CanonicalEvent) -> None:
        """Take one canonical event."""
        at = event.ts_source
        if self._first_at is None:
            self._first_at = at
        self._last_at = at
        station_id = event.station_id
        kind = event.event_type
        if kind == "SHIFT_MARKER":
            self._on_marker(event)
            return
        if kind == "INSPECTION_RESULT":
            self._on_inspection(event)
            return
        if station_id is None:
            return
        if kind == "CYCLE_END":
            self._work_ended[station_id] = at
            raw = event.payload.get("cycle_time_s")
            if isinstance(raw, int | float):
                self._worked.append((at, float(raw)))
        elif kind == "UNIT_DEPART":
            started = self._work_ended.pop(station_id, None)
            if started is not None:
                self._add("blocked", station_id, started, at)
            self._departed[station_id] = at
        elif kind == "UNIT_ARRIVE":
            started = self._departed.pop(station_id, None)
            if started is not None:
                self._add("starved", station_id, started, at)
            self._rework_since.pop(event.unit_id or "", None)
        elif kind == "STATION_STATE":
            self._on_state(event, station_id, at)
        elif kind == "ANDON":
            self._on_andon(event, station_id, at)

    def _on_state(self, event: CanonicalEvent, station_id: str, at: datetime) -> None:
        """A station's own state word opens or closes a down period."""
        state = str(event.payload.get("state", ""))
        if state in {"DOWN", "FAULT", "STOPPED"}:
            self._down_since.setdefault(station_id, at)
            return
        started = self._down_since.pop(station_id, None)
        if started is not None:
            self._add("down", station_id, started, at)

    def _on_andon(self, event: CanonicalEvent, station_id: str, at: datetime) -> None:
        """An andon call is the only down signal a dark station can give."""
        raised = bool(event.payload.get("raised", False))
        if raised:
            self._andon_since.setdefault(station_id, at)
            return
        started = self._andon_since.pop(station_id, None)
        if started is not None and station_id not in self._down_since:
            self._add("down", station_id, started, at)

    def _on_marker(self, event: CanonicalEvent) -> None:
        """A changeover opens on its marker and closes at the next shift start."""
        marker = str(event.payload.get("marker", ""))
        at = event.ts_source
        if marker == "CHANGEOVER":
            self._changeover_since = at
        elif marker == "START" and self._changeover_since is not None:
            first = self.line.station_ids[0]
            self._add("changeover", first, self._changeover_since, at)
            self._changeover_since = None

    def _on_inspection(self, event: CanonicalEvent) -> None:
        """A failed gate opens a rework period against the gate's station."""
        unit_id = event.unit_id or ""
        passed = bool(event.payload.get("passed", True))
        gate_id = str(event.payload.get("gate_id", ""))
        after = next(
            (gate.after for gate in self.line.gates if gate.gate_id == gate_id),
            self.line.station_ids[-1],
        )
        if not passed:
            self._rework_since[unit_id] = event.ts_source
            return
        started = self._rework_since.pop(unit_id, None)
        if started is not None:
            self._add("quality", after, started, event.ts_source)

    def _add(self, cause: str, station_id: str, start: datetime, end: datetime) -> None:
        """Record a period of lost production time, in production seconds only."""
        epoch = self.calendar.epoch
        producing = self.calendar.production_between(
            (start - epoch).total_seconds(), (end - epoch).total_seconds()
        )
        if producing <= 0.0:
            return
        self._seconds[(cause, station_id)].append((start, end, producing))

    # -- reading ----------------------------------------------------------

    def split(self, from_at: datetime, to_at: datetime) -> LossSplit:
        """The loss split over one window, with its reconciliation."""
        minutes = dict.fromkeys(CAUSES, 0.0)
        per_station: dict[str, dict[str, float]] = {}
        for (cause, station_id), entries in self._seconds.items():
            total = sum(
                self._inside(start, end, seconds, from_at, to_at)
                for start, end, seconds in entries
            )
            if total <= 0.0:
                continue
            minutes[cause] = minutes.get(cause, 0.0) + total / 60.0
            per_station.setdefault(station_id, dict.fromkeys(CAUSES, 0.0))
            per_station[station_id][cause] = total / 60.0
        return LossSplit(
            from_at=from_at,
            to_at=to_at,
            minutes=minutes,
            implied_total_min=self._implied(from_at, to_at),
            available_min=self._available(from_at, to_at) / 60.0,
            per_station_min=per_station,
        )

    def _inside(
        self,
        start: datetime,
        end: datetime,
        seconds: float,
        from_at: datetime,
        to_at: datetime,
    ) -> float:
        """How much of one period's lost production time falls in a window.

        A period wholly inside the window counts in full and a period wholly
        outside counts for nothing, which is almost all of them and costs
        nothing to decide. Only a period that straddles an edge goes back to the
        calendar, and there is at most one of those per cause per station.

        Pro rating by the period's own span instead was wrong in the one case
        that matters: a stoppage running through a changeover has a long span
        and very little production time in it, and pro rating credited the
        window with more lost production than the window contained. On a Line
        view window that opens at a shift start, that put the sum of causes
        above the production time available and the reconciliation went
        negative for a reason that was arithmetic rather than evidence.
        """
        if end < from_at or start > to_at:
            return 0.0
        if start >= from_at and end <= to_at:
            return seconds
        epoch = self.calendar.epoch
        lo = max(start, from_at)
        hi = min(end, to_at)
        return self.calendar.production_between(
            (lo - epoch).total_seconds(), (hi - epoch).total_seconds()
        )

    def _available(self, from_at: datetime, to_at: datetime) -> float:
        """Production seconds the window held, across every station."""
        epoch = self.calendar.epoch
        producing = self.calendar.production_between(
            (from_at - epoch).total_seconds(), (to_at - epoch).total_seconds()
        )
        return producing * len(self.line.stations)

    def _implied(self, from_at: datetime, to_at: datetime) -> float:
        """What the line's own pace says the window should have lost.

        Computed without reference to the causes, which is the whole point.
        Every station had the window's production time available to it; what it
        used is the sum of its measured cycle times. The difference is lost
        station time, and it is what a shift report counts.

        A reconciliation whose two sides are computed from the same evidence
        always ties, and a line that always ties tells a reader nothing. This
        one can disagree, and where it does the difference is reported as
        unexplained rather than distributed to make the causes add up.
        """
        worked = sum(seconds for at, seconds in self._worked if from_at <= at <= to_at)
        return max(0.0, self._available(from_at, to_at) - worked) / 60.0

    def dark_share(self) -> float:
        """What share of the line emits nothing, which is where the gap comes from.

        The unexplained column is dominated by the dark stations: they report no
        cycle time, so they are absent from what was worked, and they emit
        neither the arrival nor the departure timestamp that blocked and starved
        are measured between. The interface says so beside the number rather
        than leaving a reader to wonder where the difference went.
        """
        if not self.line.stations:
            return 0.0
        dark = sum(1 for item in self.line.stations if item.tier == "C")
        return dark / len(self.line.stations)
