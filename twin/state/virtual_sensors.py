"""Virtual sensors for dark stations. T-040, T-041, T-042.

TECHNICAL_SPEC.md Section 4.3. This module is the product's answer to uneven
sensor coverage, and it is the one place where getting the reasoning wrong would
undo everything downstream.

The problem. Six of Line 2's 42 stations emit no machine data. A unit enters the
run of them and is not seen again until it reaches the next instrumented
station. All the twin has is the departure timestamp at the last instrumented
station upstream, the arrival timestamp at the first one downstream, the nominal
transports from the line definition, and unit conservation: how many units are
inside the span at any moment is the count that went in less the count that came
out.

What is derived, and how.

```
transit      = ts_arrive(d, unit) - ts_depart(u, unit) - non-production overlap
transport    in [ nominal * (1 - tolerance), nominal * (1 + tolerance) ]
work         in [ transit - transport.upper, transit - transport.lower ]

sum of the dark stations' cycle times in [ lo, hi ]
    hi = work.upper
         because the unit's time in the span is work plus waiting, and waiting
         is never negative
    lo = the free-flow floor, or work.lower where free flow is certified
```

The upper bound is sound: a unit cannot have done more work than the time it
spent. The lower bound is the difficult half, and it is where the honesty of the
whole module sits. A unit that took 340 s across a span whose quickest recent
transit was 268 s may have worked for 340 s or for 268 s, and no timestamp at
either end can separate those. So the floor comes from the same reasoning
TECHNICAL_SPEC.md Section 11 uses for transport times: the quickest observed
passage is close to pure work. That is a statistical bound rather than a
guarantee, which is exactly why the target in PRD Section 5 is coverage in 90
percent of cycles and not in all of them.

Where the evidence is stronger the floor is not needed. If the span held only
this unit for its whole transit and the downstream station was never occupied,
the unit cannot have waited for anything, and the bound tightens to the
transport tolerance alone.

Several dark stations sharing a span. The bound applies to their sum. Each
station's own bound is then

```
[ max(0, sum.lower - (m - 1) * max_plausible), sum.upper ]
```

which widens fast with m. That is correct and it is shown. All of them are
marked `UNRESOLVED`, because a bound on a sum is not a bound on a member, and a
Sensor Value Card names the scan point that would split it. Nothing on such a
span is attributed to blocking or starving either: the station beyond it is
occupied for most of a takt on any line running to takt, so its occupancy says
nothing about which of several unobserved stations delayed a unit.

A dark station with no instrumented station downstream of it, which on Line 2 is
S42 at the end of the line, gets nothing at all. There is no second timestamp,
so there is no span, so there is no bound. It is reported as `UNRESOLVED` with
the sensor that would fix it, and no number is invented for it anywhere.

An inspection result is not a downstream anchor. Its timestamp says when a
verdict was recorded, not when a unit stopped moving, and using it as a timing
anchor would make the last dark station look monitored when it is not.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from connector.protocol import CanonicalEvent
from twin.config.line import LineDefinition
from twin.domain.estimate import Estimate, Interval
from twin.domain.shifts import ProductionCalendar
from twin.domain.state import UnresolvedStation

AttributionLabel = Literal["WORK", "BLOCKED", "STARVED", "UNKNOWN"]

# Two units in the span means one of them may have been waiting for the other.
_CROWDED = 2

# Below this, the span is accounted for by work and there is nothing left to
# attribute. Expressed as a share of takt so it moves with the line rather than
# being a constant in code.
_ATTRIBUTION_TOLERANCE_TAKTS = 0.05


@dataclass(frozen=True)
class DarkSpan:
    """A run of dark stations and the instrumented stations either side of it."""

    span_id: str
    upstream_id: str | None
    downstream_id: str | None
    dark_station_ids: tuple[str, ...]
    # The nominal transport across the whole span: out of the upstream station,
    # between each pair of dark stations, and into the downstream one.
    transport_s: float
    # A run longer than the line allows is not modelled at all (EC-18).
    is_modelled: bool

    @property
    def size(self) -> int:
        """How many dark stations share this span."""
        return len(self.dark_station_ids)

    @property
    def is_resolvable(self) -> bool:
        """Whether the span has an instrumented station at both ends."""
        return self.upstream_id is not None and self.downstream_id is not None

    @property
    def is_separable(self) -> bool:
        """Whether one station's own cycle time can be bounded."""
        return self.is_resolvable and self.is_modelled and self.size == 1

    def unresolvable_reason(self) -> str:
        """Why this span yields nothing, in plain language."""
        if self.downstream_id is None:
            return (
                "no instrumented station downstream, so nothing scans the unit "
                "again after it leaves"
            )
        if self.upstream_id is None:
            return (
                "no instrumented station upstream, so there is no timestamp for "
                "when the unit entered"
            )
        return (
            f"{self.size} dark stations in a row, which is longer than this line models"
        )

    def resolved_by(self) -> str:
        """The scan point that would make this span separable."""
        if self.downstream_id is None:
            return f"a unit scan point after {self.dark_station_ids[-1]}"
        if self.upstream_id is None:
            return f"a unit scan point before {self.dark_station_ids[0]}"
        middle = self.dark_station_ids[self.size // 2]
        return f"a unit scan point between {middle} and its neighbour"


def dark_spans(line: LineDefinition) -> tuple[DarkSpan, ...]:
    """Find every run of dark stations on a line, with what flanks it.

    Topology only. Which stations are dark and what sits either side of them is
    configuration, so onboarding a line with a different dark pattern needs no
    code (ONB-04).
    """
    order = line.station_ids
    tiers = {station.station_id: station.tier for station in line.stations}
    transports = {
        station.station_id: station.transport_to_next_s for station in line.stations
    }
    spans: list[DarkSpan] = []
    index = 0
    while index < len(order):
        if tiers[order[index]] != "C":
            index += 1
            continue
        start = index
        while index < len(order) and tiers[order[index]] == "C":
            index += 1
        end = index - 1
        dark = order[start : end + 1]
        upstream = order[start - 1] if start > 0 else None
        downstream = order[end + 1] if end + 1 < len(order) else None
        hops = order[start - 1 : end + 1] if upstream is not None else dark[:-1]
        transport_s = sum(transports[station_id] or 0.0 for station_id in hops)
        spans.append(
            DarkSpan(
                span_id=f"{upstream or 'line-start'}:{downstream or 'line-end'}",
                upstream_id=upstream,
                downstream_id=downstream,
                dark_station_ids=dark,
                transport_s=transport_s,
                is_modelled=len(dark) <= line.state.max_dark_span,
            )
        )
    return tuple(spans)


@dataclass(frozen=True)
class SpanObservation:
    """What the twin saw of one unit's passage through one dark span."""

    span_id: str
    unit_id: str
    variant_id: str
    entered_at: datetime
    exited_at: datetime
    # Wall seconds between the two flanking scans.
    observed_s: float
    # How much of that the line was not producing, from the shift pattern and
    # the shift markers. Subtracting it is what stops a lunch break reading as
    # slow work.
    stopped_s: float
    # How long the station at the far end of the span was occupied while this
    # unit was inside it. The unit could not enter while that was true, so this
    # is evidence of waiting rather than working.
    exit_blocked_s: float
    # How long another unit shared the span. A unit alone in the span with a
    # free exit cannot have been waiting for anything.
    crowded_s: float
    # Whether the span was empty just before this unit entered, which means its
    # first station had nothing to work on.
    was_starved: bool

    @property
    def transit_s(self) -> float:
        """The producing part of the passage."""
        return max(0.0, self.observed_s - self.stopped_s)

    @property
    def is_free_flow(self) -> bool:
        """Whether the unit demonstrably never waited inside the span."""
        return self.crowded_s <= 0.0 and self.exit_blocked_s <= 0.0


@dataclass(frozen=True)
class Attribution:
    """What the unaccounted part of a span was, where the twin can tell.

    TECHNICAL_SPEC.md Section 4.3. Where the flanking evidence separates the
    three states it says which; where it does not it says `UNKNOWN`, and the
    interface prints that rather than a plausible guess.
    """

    label: AttributionLabel
    non_work: Interval
    basis: str


@dataclass(frozen=True)
class _WorkBounds:
    """The work content of one passage, as far as the evidence pins it down."""

    lo: float
    hi: float
    # The quickest comparable passage recently seen, or None on a cold start.
    floor: float | None
    # The bound actually reported, after the floor and the clamp at zero.
    cycle: Interval


@dataclass(frozen=True)
class SpanEstimate:
    """One unit's passage through one dark span, as the twin understands it."""

    span: DarkSpan
    unit_id: str
    variant_id: str
    at: datetime
    # The bound on the dark stations' cycle times added together.
    total: Estimate
    # Each station's own bound. For a span of one this is the total; for a span
    # of several it is wider, and every entry is marked UNRESOLVED.
    per_station: dict[str, Estimate]
    attribution: Attribution
    observation: SpanObservation


class _SpanTracker:
    """Bookkeeping for one dark span as events arrive.

    The occupancy of the span is a timeline of checkpoints rather than two lists
    of instants, because the two have to be trimmed together. Dropping an entry
    whose matching exit is still held undercounts the units in the span, and an
    undercount here is the worst kind of error this module can make: it would
    certify a passage as free flowing when the unit was in fact queueing, and
    the bound would then exclude the truth.
    """

    def __init__(self, span: DarkSpan, line: LineDefinition) -> None:
        self._span = span
        self._line = line
        # Units currently inside the span, by the instant they entered.
        self._inside: dict[str, tuple[datetime, str]] = {}
        # Occupancy after each change, in time order. The stream reaches this
        # module sorted by source clock, so appending keeps it sorted.
        self._timeline: deque[tuple[datetime, int]] = deque()
        self._occupancy = 0
        # When the downstream station was occupied, as closed intervals.
        self._exit_busy: deque[tuple[datetime, datetime]] = deque()
        self._exit_since: datetime | None = None
        # Recent producing transits per variant, which is where the lower bound
        # comes from when free flow cannot be certified.
        self._recent: dict[str, deque[float]] = defaultdict(
            lambda: deque(maxlen=line.state.window_cycles)
        )

    # -- events --------------------------------------------------------

    def entered(self, unit_id: str, variant_id: str, at: datetime) -> None:
        """A unit left the upstream station and is now inside the span."""
        self._inside[unit_id] = (at, variant_id)
        self._occupancy += 1
        self._timeline.append((at, self._occupancy))

    def downstream_arrived(self, unit_id: str, at: datetime) -> SpanObservation | None:
        """A unit reached the downstream station. Close its passage."""
        # Close any interval left open by an out-of-order pair at the same
        # instant, so that the previous unit's occupancy of the downstream
        # station is not lost.
        self._close_exit(at)
        record = self._inside.pop(unit_id, None)
        if record is None:
            # A unit the twin never saw enter, usually because the run started
            # with it already inside the span. There is nothing to bound.
            self._exit_since = at
            return None
        entered_at, variant_id = record
        self._occupancy -= 1
        self._timeline.append((at, self._occupancy))
        observation = self._build(unit_id, variant_id, entered_at, at)
        self._recent[variant_id].append(
            max(0.0, observation.transit_s - self._span.transport_s)
        )
        self._exit_since = at
        self._trim()
        return observation

    def downstream_departed(self, at: datetime) -> None:
        """The downstream station handed its unit on and is free again."""
        self._close_exit(at)

    def _close_exit(self, at: datetime) -> None:
        if self._exit_since is not None and at > self._exit_since:
            self._exit_busy.append((self._exit_since, at))
        self._exit_since = None

    # -- derivation ----------------------------------------------------

    def floor_for(self, variant_id: str) -> float | None:
        """The quickest comparable passage recently seen, less a slack.

        None until the window holds enough cycles to say anything, which is the
        cold-start case the interface reports as a count of cycles remaining
        rather than as a broken station (EC-20).
        """
        samples = self._recent[variant_id]
        if len(samples) < self._line.state.min_cycles:
            return None
        ordered = sorted(samples)
        position = int(self._line.state.free_flow_quantile * (len(ordered) - 1))
        return ordered[position] * (1.0 - self._line.state.free_flow_slack)

    def _build(
        self, unit_id: str, variant_id: str, entered_at: datetime, exited_at: datetime
    ) -> SpanObservation:
        crowded_s, was_empty = self._occupancy_during(entered_at, exited_at)
        return SpanObservation(
            span_id=self._span.span_id,
            unit_id=unit_id,
            variant_id=variant_id,
            entered_at=entered_at,
            exited_at=exited_at,
            observed_s=(exited_at - entered_at).total_seconds(),
            stopped_s=0.0,
            exit_blocked_s=self._busy_overlap(entered_at, exited_at),
            crowded_s=crowded_s,
            was_starved=was_empty,
        )

    def _busy_overlap(self, start: datetime, end: datetime) -> float:
        total = 0.0
        for busy_from, busy_to in self._exit_busy:
            if busy_to <= start or busy_from >= end:
                continue
            total += (min(busy_to, end) - max(busy_from, start)).total_seconds()
        return total

    def _occupancy_during(self, start: datetime, end: datetime) -> tuple[float, bool]:
        """How long the span held two or more units, and whether it was empty.

        Unit conservation and nothing else: every entry is a departure scan at
        the upstream station and every exit is an arrival scan at the downstream
        one, so the count inside the span is exact wherever both flanking
        sources are complete.
        """
        crowded = 0.0
        was_empty = False
        previous_at: datetime | None = None
        previous_count = 0
        for at, count in self._timeline:
            if previous_at is not None and previous_count >= _CROWDED:
                window_from = max(previous_at, start)
                window_to = min(at, end)
                if window_to > window_from:
                    crowded += (window_to - window_from).total_seconds()
            if previous_count == 0 and at <= start:
                was_empty = True
            previous_at, previous_count = at, count
            if at >= end:
                break
        return crowded, was_empty

    def _trim(self) -> None:
        """Forget what no passage still open can refer to."""
        oldest = min((at for at, _ in self._inside.values()), default=None)
        if oldest is None:
            # Nothing is inside the span, so only the most recent checkpoint
            # still matters: it carries the occupancy the next passage starts at.
            while len(self._timeline) > 1:
                self._timeline.popleft()
            while len(self._exit_busy) > 1:
                self._exit_busy.popleft()
            return
        # Keep one checkpoint at or before the oldest open passage, because the
        # occupancy it carries is the level that passage started from.
        while len(self._timeline) > 1 and self._timeline[1][0] <= oldest:
            self._timeline.popleft()
        while self._exit_busy and self._exit_busy[0][1] < oldest:
            self._exit_busy.popleft()


@dataclass
class VirtualSensors:
    """Derives dark stations' cycle times from the flanking scans.

    Feed it the canonical event stream. It answers with a bound per unit per
    span, never with a number, and it says plainly which stations it cannot
    separate at all.
    """

    line: LineDefinition
    _spans: tuple[DarkSpan, ...] = field(init=False)
    _trackers: dict[str, _SpanTracker] = field(init=False, default_factory=dict)
    _by_upstream: dict[str, _SpanTracker] = field(init=False, default_factory=dict)
    _by_downstream: dict[str, _SpanTracker] = field(init=False, default_factory=dict)
    _estimates: list[SpanEstimate] = field(init=False, default_factory=list)
    _latest: dict[str, Estimate] = field(init=False, default_factory=dict)
    _calendar: ProductionCalendar | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        """Work out the line's dark spans and set up a tracker for each."""
        self._spans = dark_spans(self.line)
        for span in self._spans:
            if not (span.is_resolvable and span.is_modelled):
                continue
            tracker = _SpanTracker(span, self.line)
            self._trackers[span.span_id] = tracker
            assert span.upstream_id is not None
            assert span.downstream_id is not None
            self._by_upstream[span.upstream_id] = tracker
            self._by_downstream[span.downstream_id] = tracker

    @property
    def spans(self) -> tuple[DarkSpan, ...]:
        """Every dark span on this line."""
        return self._spans

    def estimates(self) -> tuple[SpanEstimate, ...]:
        """Every estimate made so far, in the order they were made."""
        return tuple(self._estimates)

    def latest(self, station_id: str) -> Estimate | None:
        """The most recent bound for one dark station, or None if there is none."""
        return self._latest.get(station_id)

    def unresolved(self) -> tuple[UnresolvedStation, ...]:
        """Every station the twin cannot separate, and what would fix it.

        Two kinds. A span with no scan at one end yields nothing at all. A span
        of several dark stations yields a bound on their sum but not on any one
        of them. Both are `UNRESOLVED`, and both name the scan point that would
        resolve them (STA-07, EC-17).
        """
        found: list[UnresolvedStation] = []
        for span in self._spans:
            unresolvable = not (span.is_resolvable and span.is_modelled)
            if not unresolvable and span.size == 1:
                continue
            reason = (
                span.unresolvable_reason()
                if unresolvable
                else (
                    f"{span.size} dark stations share the span between "
                    f"{span.upstream_id} and {span.downstream_id}, so their total "
                    f"is bounded but no single one of them is"
                )
            )
            found.extend(
                UnresolvedStation(
                    station_id=station_id,
                    reason=reason,
                    resolved_by=span.resolved_by(),
                )
                for station_id in span.dark_station_ids
            )
        return tuple(found)

    # -- ingest --------------------------------------------------------

    def observe(self, event: CanonicalEvent) -> SpanEstimate | None:
        """Take one canonical event, and return an estimate if one just closed."""
        self._ensure_calendar(event.ts_source)
        if event.unit_id is None or event.station_id is None:
            return None
        if event.event_type == "UNIT_DEPART":
            tracker = self._by_upstream.get(event.station_id)
            if tracker is not None:
                variant = str(event.payload.get("variant_id", ""))
                tracker.entered(event.unit_id, variant, event.ts_source)
            exit_tracker = self._by_downstream.get(event.station_id)
            if exit_tracker is not None:
                exit_tracker.downstream_departed(event.ts_source)
            return None
        if event.event_type != "UNIT_ARRIVE":
            return None
        tracker = self._by_downstream.get(event.station_id)
        if tracker is None:
            return None
        observation = tracker.downstream_arrived(event.unit_id, event.ts_source)
        if observation is None:
            return None
        estimate = self._derive(tracker, observation)
        self._estimates.append(estimate)
        for station_id, value in estimate.per_station.items():
            self._latest[station_id] = value
        return estimate

    def _ensure_calendar(self, at: datetime) -> None:
        if self._calendar is not None:
            return
        # Midnight of the first day seen. The shift pattern is written in the
        # plant's local time, so anchoring the calendar to a day boundary makes
        # its windows land on the same wall clock the plant uses.
        midnight = datetime.combine(at.date(), at.time().min, tzinfo=at.tzinfo)
        self._calendar = ProductionCalendar(self.line, midnight)

    # -- the derivation ------------------------------------------------

    def _derive(self, tracker: _SpanTracker, raw: SpanObservation) -> SpanEstimate:
        span = self._span_of(raw.span_id)
        observation = self._with_stopped_time(raw)
        tolerance = self.line.state.transport_tolerance
        transport_lo = span.transport_s * (1.0 - tolerance)
        transport_hi = span.transport_s * (1.0 + tolerance)
        work_lo = observation.transit_s - transport_hi
        work_hi = observation.transit_s - transport_lo

        floor = tracker.floor_for(observation.variant_id)
        if observation.is_free_flow:
            lower = work_lo
            floor_basis = (
                "the span held only this unit and the station beyond it was "
                "free throughout, so none of the passage was waiting"
            )
        elif floor is None:
            lower = 0.0
            floor_basis = (
                f"fewer than {self.line.state.min_cycles} comparable passages "
                f"so far, so the lower bound is only that work is not negative"
            )
        else:
            lower = min(work_lo, floor)
            floor_basis = (
                f"the quickest comparable passage recently seen was {floor:.0f} s"
            )
        # A negative lower bound means an assumption was wrong, usually the
        # transport time or the station order, and the clamp is recorded rather
        # than hidden (EC-09).
        clamped = lower < 0.0
        floor_at_zero = max(0.0, lower)
        # The width is never zero. Even where the clamp would collapse the two
        # bounds together, the transport is nominal rather than measured, so
        # there is real uncertainty left and the bound says so. This is what
        # makes "no point value for a dark station" structural rather than a
        # property that happens to hold on the runs we have looked at.
        least_width = span.transport_s * 2.0 * tolerance
        interval = Interval(
            floor_at_zero, max(0.0, work_hi, floor_at_zero + least_width)
        )

        total = Estimate.inferred(
            interval,
            basis=self._basis(span, observation, floor_basis, clamped=clamped),
            confidence=self._confidence(interval, span.size),
            resolution="RESOLVED",
        )
        return SpanEstimate(
            span=span,
            unit_id=observation.unit_id,
            variant_id=observation.variant_id,
            at=observation.exited_at,
            total=total,
            per_station=self._per_station(span, interval, clamped=clamped),
            attribution=self._attribute(
                span, observation, _WorkBounds(work_lo, work_hi, floor, interval)
            ),
            observation=observation,
        )

    def _span_of(self, span_id: str) -> DarkSpan:
        for span in self._spans:
            if span.span_id == span_id:
                return span
        message = f"no dark span {span_id} on line {self.line.line_id}"
        raise KeyError(message)

    def _with_stopped_time(self, observation: SpanObservation) -> SpanObservation:
        """Subtract the part of the passage when the line was not producing."""
        assert self._calendar is not None
        epoch = self._calendar.epoch
        start = (observation.entered_at - epoch).total_seconds()
        end = (observation.exited_at - epoch).total_seconds()
        stopped = self._calendar.stopped_between(start, end)
        if stopped <= 0.0:
            return observation
        return SpanObservation(
            span_id=observation.span_id,
            unit_id=observation.unit_id,
            variant_id=observation.variant_id,
            entered_at=observation.entered_at,
            exited_at=observation.exited_at,
            observed_s=observation.observed_s,
            stopped_s=stopped,
            # The exit cannot obstruct anything while the line is stopped, and
            # nothing is crowded out by a break either.
            exit_blocked_s=max(0.0, observation.exit_blocked_s - stopped),
            crowded_s=max(0.0, observation.crowded_s - stopped),
            was_starved=observation.was_starved,
        )

    def _per_station(
        self, span: DarkSpan, total: Interval, *, clamped: bool
    ) -> dict[str, Estimate]:
        """Each dark station's own bound. TECHNICAL_SPEC.md Section 4.3."""
        if span.size == 1:
            station_id = span.dark_station_ids[0]
            return {
                station_id: Estimate.inferred(
                    total,
                    basis=(
                        f"{station_id} is the only station without machine data "
                        f"between {span.upstream_id} and {span.downstream_id}, so "
                        f"the span bounds it directly"
                    ),
                    confidence=self._confidence(total, 1),
                    resolution="RESOLVED",
                )
            }
        max_plausible = self.line.takt_s * self.line.state.max_plausible_cycle_takts
        widened = Interval(
            max(0.0, total.lo - (span.size - 1) * max_plausible), total.hi
        )
        note = " The lower bound was clamped at zero." if clamped else ""
        return {
            station_id: Estimate.inferred(
                widened,
                basis=(
                    f"{span.size} stations without machine data share the span "
                    f"between {span.upstream_id} and {span.downstream_id}. Their "
                    f"total is bounded; {station_id} on its own is not."
                    f"{note}"
                ),
                confidence=self._confidence(widened, 1),
                resolution="UNRESOLVED",
            )
            for station_id in span.dark_station_ids
        }

    def _confidence(self, interval: Interval, stations: int) -> float:
        """How sure the twin is, from the width against the plausible range.

        A bound as wide as the station could possibly be says nothing, and reads
        as zero. A bound at the transport tolerance alone reads as close to one.
        """
        plausible = (
            self.line.takt_s * self.line.state.max_plausible_cycle_takts * stations
        )
        if plausible <= 0:
            return 0.0
        return max(0.0, min(1.0, 1.0 - interval.width / plausible))

    def _basis(
        self,
        span: DarkSpan,
        observation: SpanObservation,
        floor_basis: str,
        *,
        clamped: bool,
    ) -> str:
        parts = [
            f"{observation.transit_s:.0f} s between the scan out of "
            f"{span.upstream_id} and the scan into {span.downstream_id}, less "
            f"{span.transport_s:.0f} s nominal transport",
            floor_basis,
        ]
        if observation.stopped_s > 0:
            parts.append(f"{observation.stopped_s:.0f} s of it not producing")
        if clamped:
            parts.append(
                "the lower bound came out negative and was clamped at zero, which "
                "means a transport time or a station order is wrong"
            )
        return ". ".join(parts)

    def _attribute(
        self, span: DarkSpan, observation: SpanObservation, bounds: _WorkBounds
    ) -> Attribution:
        """Split the unaccounted part of the span, or say it cannot be split.

        TECHNICAL_SPEC.md Section 4.3. The bound on non-work always starts at
        zero, because no pair of flanking timestamps can prove that a unit
        waited. What can be established, where one dark station sits alone
        between two instrumented ones, is that a passage took longer than the
        quickest comparable one and that the station beyond it was occupied.
        """
        non_work = Interval(0.0, max(0.0, bounds.hi - bounds.cycle.lo))
        if span.size > 1:
            # Measured against the simulator, a blocked label on a span of five
            # stations agreed with the truth 73 percent of the time against a
            # base rate of 72 percent, which is to say it carried no information
            # at all. The station beyond the span is occupied for most of a takt
            # on any line running to takt, so its occupancy says nothing about
            # which of five unobserved stations delayed a unit, or whether any
            # of them did. Saying so is the whole point of the label.
            return Attribution(
                "UNKNOWN",
                non_work,
                f"{span.size} stations without machine data share this span, so "
                f"nothing at either end says which of them held the unit, or "
                f"whether it was working, blocked or starved",
            )
        return self._attribute_one(observation, bounds, non_work)

    def _attribute_one(
        self, observation: SpanObservation, bounds: _WorkBounds, non_work: Interval
    ) -> Attribution:
        """The attribution for a span holding exactly one dark station.

        - `WORK` where the passage is no longer than a free-flowing one.
        - `BLOCKED` where it is longer and the station beyond the span was
          occupied for at least the excess. The excess had somewhere to go.
        - `STARVED` where it is longer and the span was empty when the unit
          entered, so the station had been waiting for work.
        - `UNKNOWN` otherwise.
        """
        tolerance = self.line.takt_s * _ATTRIBUTION_TOLERANCE_TAKTS
        if observation.is_free_flow:
            return Attribution(
                "WORK",
                non_work,
                "the span held only this unit and the station beyond it was free "
                "throughout, so none of the passage was waiting",
            )
        if bounds.floor is None:
            return Attribution(
                "UNKNOWN",
                non_work,
                f"fewer than {self.line.state.min_cycles} comparable passages so "
                f"far, so there is nothing yet to judge this one against",
            )
        excess = bounds.lo - bounds.floor
        if excess <= tolerance:
            return Attribution(
                "WORK",
                non_work,
                f"the passage is no longer than the quickest comparable one, "
                f"which was {bounds.floor:.0f} s, so it is accounted for by work",
            )
        if observation.exit_blocked_s >= excess:
            return Attribution(
                "BLOCKED",
                non_work,
                f"the passage ran {excess:.0f} s longer than the quickest "
                f"comparable one, and the station beyond the span was occupied "
                f"for {observation.exit_blocked_s:.0f} s while this unit was "
                f"inside it",
            )
        if observation.was_starved and observation.crowded_s <= tolerance:
            return Attribution(
                "STARVED",
                non_work,
                f"the passage ran {excess:.0f} s longer than the quickest "
                f"comparable one, and the span was empty when this unit entered "
                f"it, so the station had been waiting for work",
            )
        return Attribution(
            "UNKNOWN",
            non_work,
            f"the passage ran {excess:.0f} s longer than the quickest comparable "
            f"one, and nothing at either end says whether this unit was working, "
            f"blocked or starved",
        )
