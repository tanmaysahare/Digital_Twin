"""Normalisation: reordering, late events, clock skew and source health.

T-034 to T-036. ING-05, ING-06, ING-07, EC-01, EC-03.

Three jobs, and each of them exists because of a specific way a plant's data
arrives wrong.

**Reordering.** Two sources with two network paths deliver events out of order.
They buffer for `reorder_window_s` and release in source-clock order. An event
that arrives after its window has passed is not discarded: it is accepted,
flagged `LATE`, and it names the station whose state has to be recomputed.
Discarding it would be the silent kind of wrong this product exists to avoid.

**Clock skew.** Two adapters that see the same unit handoff disagree about when
it happened. The disagreement is estimated as a rolling median and reported.
It is never applied as a correction: a correction applied to a genuinely slow
station would hide exactly the thing the twin is looking for.

**Source health.** A source that stops talking is reported after three takt
periods and not before. Reporting sooner would fire on every gap in a line that
is simply between units.
"""

from __future__ import annotations

import statistics
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from heapq import heappop, heappush

from connector.protocol import CanonicalEvent, SourceHealth, SourceState
from twin.config.line import LineDefinition


@dataclass(frozen=True)
class Released:
    """One event leaving the normaliser, and what it obliges the twin to redo."""

    event: CanonicalEvent
    # Set when the event arrived after its reordering window closed. The state
    # estimator recomputes this station from the point the event belongs at.
    recompute_station_id: str | None = None

    @property
    def is_late(self) -> bool:
        """Whether this event missed its reordering window."""
        return self.event.quality_flag == "LATE"


class ReorderWindow:
    """Buffers events for a bounded window and releases them in source order."""

    def __init__(self, window_s: float) -> None:
        """Build a window of the configured length."""
        self._window = timedelta(seconds=window_s)
        self._heap: list[tuple[datetime, str, CanonicalEvent]] = []
        self._high_water: datetime | None = None
        self._released_to: datetime | None = None
        self._late = 0

    @property
    def late_count(self) -> int:
        """How many events have arrived after their window closed."""
        return self._late

    @property
    def buffered(self) -> int:
        """How many events are waiting for their window to close."""
        return len(self._heap)

    def push(self, event: CanonicalEvent) -> list[Released]:
        """Accept one event and return whatever is now safe to release."""
        if self._released_to is not None and event.ts_source < self._released_to:
            self._late += 1
            return [
                Released(
                    event.with_quality("LATE"),
                    recompute_station_id=event.station_id,
                )
            ]
        if self._high_water is None or event.ts_source > self._high_water:
            self._high_water = event.ts_source
        heappush(self._heap, (event.ts_source, str(event.event_id), event))
        return self._drain(self._high_water - self._window)

    def flush(self) -> list[Released]:
        """Release everything still buffered, in source order."""
        return self._drain(None)

    def _drain(self, until: datetime | None) -> list[Released]:
        out: list[Released] = []
        while self._heap and (until is None or self._heap[0][0] <= until):
            _, _, event = heappop(self._heap)
            self._released_to = event.ts_source
            out.append(Released(event))
        return out


@dataclass
class SkewEstimator:
    """Estimates the clock difference between pairs of adapters. ING-06.

    A unit leaving one station and arriving at the next is one physical event
    seen by two clocks. The difference between the two timestamps, less the
    nominal transport, is a sample of their disagreement. The median over a
    rolling window is robust to the one handoff that was genuinely slow.
    """

    line: LineDefinition
    window: int = 50
    _pending: dict[str, tuple[str, str, datetime]] = field(default_factory=dict)
    _samples: dict[tuple[str, str], list[float]] = field(default_factory=dict)

    def observe(self, event: CanonicalEvent) -> None:
        """Take one event into the estimate, if it is part of a handoff."""
        if event.unit_id is None or event.station_id is None:
            return
        if event.event_type == "UNIT_DEPART":
            self._pending[event.unit_id] = (
                event.station_id,
                event.source_adapter,
                event.ts_source,
            )
            return
        if event.event_type != "UNIT_ARRIVE":
            return
        handoff = self._pending.pop(event.unit_id, None)
        if handoff is None:
            return
        from_station, from_adapter, departed_at = handoff
        if from_adapter == event.source_adapter:
            return
        transport_s = self._transport_between(from_station, event.station_id)
        if transport_s is None:
            return
        observed = (event.ts_source - departed_at).total_seconds()
        self._record(from_adapter, event.source_adapter, observed - transport_s)

    def _transport_between(self, upstream: str, downstream: str) -> float | None:
        """The nominal transport for one handoff, or None if it is not one.

        Only adjacent stations count. A departure from S32 followed by an
        arrival at S38 spans five stations that emit nothing, and the work done
        at them would enter the estimate as if it were clock disagreement. Skew
        is estimated where two clocks see the same movement and nowhere else.
        """
        order = self.line.station_ids
        try:
            start, end = order.index(upstream), order.index(downstream)
        except ValueError:
            return None
        if end != start + 1:
            return None
        return self.line.station(upstream).transport_to_next_s

    def _record(self, first: str, second: str, difference_s: float) -> None:
        key, value = self._ordered(first, second, difference_s)
        samples = self._samples.setdefault(key, [])
        samples.append(value)
        if len(samples) > self.window:
            del samples[0]

    @staticmethod
    def _ordered(
        first: str, second: str, difference_s: float
    ) -> tuple[tuple[str, str], float]:
        """Key a pair in a stable order, flipping the sign to match."""
        if first <= second:
            return (first, second), difference_s
        return (second, first), -difference_s

    def between(self, first: str, second: str) -> float | None:
        """The estimated skew between two adapters, or None if not yet seen."""
        key, _ = self._ordered(first, second, 0.0)
        samples = self._samples.get(key)
        if not samples:
            return None
        median = statistics.median(samples)
        return median if key[0] == first else -median

    def worst(self) -> float:
        """The largest estimated skew across every pair, as a magnitude."""
        return max(
            (abs(statistics.median(values)) for values in self._samples.values()),
            default=0.0,
        )

    def exceeds_warning(self) -> bool:
        """Whether any pair is drifting further apart than the line allows."""
        return self.worst() > self.line.ingest.skew_warn_s


@dataclass(frozen=True)
class SourceGap:
    """A stretch during which a source said nothing. ING-07, EC-01.

    A first-class record rather than a colour on a panel, because a forecast
    made during a gap has to be interpretable afterwards, and because the
    evidence pack reports how much of an evaluation window was degraded.
    """

    adapter: str
    line_id: str
    started_at: datetime
    ended_at: datetime | None
    affected_stations: tuple[str, ...]
    events_lost_estimate: int

    @property
    def is_open(self) -> bool:
        """Whether the source is still silent."""
        return self.ended_at is None

    def duration_s(self, now: datetime) -> float:
        """How long the gap has lasted, so far or in total."""
        return ((self.ended_at or now) - self.started_at).total_seconds()


@dataclass
class SourceMonitor:
    """Reports a source as silent after the configured number of takt periods."""

    line: LineDefinition
    _last_seen: dict[str, datetime] = field(default_factory=dict)
    _first_seen: dict[str, datetime] = field(default_factory=dict)
    _counts: dict[str, int] = field(default_factory=dict)
    _stations: dict[str, set[str]] = field(default_factory=dict)
    _gaps: list[SourceGap] = field(default_factory=list)

    @property
    def gap_threshold_s(self) -> float:
        """How long a source may say nothing before it is reported silent."""
        return self.line.ingest.source_gap_takts * self.line.takt_s

    def observe(self, event: CanonicalEvent) -> None:
        """Record that a source is still talking, and close any open gap."""
        adapter = event.source_adapter
        seen = self._last_seen.get(adapter)
        if seen is None or event.ts_source > seen:
            self._last_seen[adapter] = event.ts_source
        self._first_seen.setdefault(adapter, event.ts_source)
        self._counts[adapter] = self._counts.get(adapter, 0) + 1
        if event.station_id is not None:
            self._stations.setdefault(adapter, set()).add(event.station_id)
        self._close_gap(adapter, event.ts_source)

    def tick(self, now: datetime) -> tuple[SourceGap, ...]:
        """Open a gap for any source that has gone quiet. Returns the new ones.

        Called on the forecast cadence rather than on every event, because a
        source that has stopped talking produces nothing to react to.
        """
        opened: list[SourceGap] = []
        for adapter, seen in self._last_seen.items():
            if self.state_of(adapter, now) != "SILENT":
                continue
            if any(gap.adapter == adapter and gap.is_open for gap in self._gaps):
                continue
            gap = SourceGap(
                adapter=adapter,
                line_id=self.line.line_id,
                started_at=seen,
                ended_at=None,
                affected_stations=tuple(sorted(self._stations.get(adapter, set()))),
                events_lost_estimate=0,
            )
            self._gaps.append(gap)
            opened.append(gap)
        return tuple(opened)

    def _close_gap(self, adapter: str, at: datetime) -> None:
        for index, gap in enumerate(self._gaps):
            if gap.adapter != adapter or not gap.is_open:
                continue
            self._gaps[index] = SourceGap(
                adapter=gap.adapter,
                line_id=gap.line_id,
                started_at=gap.started_at,
                ended_at=at,
                affected_stations=gap.affected_stations,
                events_lost_estimate=self._lost_during(adapter, gap.started_at, at),
            )
            return

    def _lost_during(self, adapter: str, start: datetime, end: datetime) -> int:
        """How many events the gap probably swallowed, at this source's own rate.

        An estimate, and labelled as one wherever it is shown. The alternative
        is to report nothing, which would let a silent source look like a quiet
        line.
        """
        first = self._first_seen.get(adapter)
        if first is None:
            return 0
        observed_s = (start - first).total_seconds()
        if observed_s <= 0:
            return 0
        rate = self._counts.get(adapter, 0) / observed_s
        return max(0, round(rate * (end - start).total_seconds()))

    def gaps(self) -> tuple[SourceGap, ...]:
        """Every gap seen so far, open ones included."""
        return tuple(self._gaps)

    def state_of(self, adapter: str, now: datetime) -> SourceState:
        """Whether a source is live, degraded or silent at an instant."""
        seen = self._last_seen.get(adapter)
        if seen is None:
            return "SILENT"
        quiet_s = (now - seen).total_seconds()
        if quiet_s > self.gap_threshold_s:
            return "SILENT"
        # Past one takt with nothing is not yet a fault, but it is worth saying
        # so rather than showing a confident green.
        if quiet_s > self.line.takt_s:
            return "DEGRADED"
        return "LIVE"

    def health(
        self, now: datetime, skew: SkewEstimator | None = None
    ) -> tuple[SourceHealth, ...]:
        """The health of every source seen so far."""
        return tuple(
            SourceHealth(
                adapter=adapter,
                line_id=self.line.line_id,
                state=self.state_of(adapter, now),
                last_event_at=self._last_seen[adapter],
                events_last_min=self._counts[adapter],
                estimated_skew_s=skew.worst() if skew is not None else None,
                checked_at=now,
            )
            for adapter in sorted(self._last_seen)
        )


class Normaliser:
    """Reordering, skew estimation and source health over one line's stream."""

    def __init__(self, line: LineDefinition) -> None:
        """Build a normaliser for one line, from that line's ingest policy."""
        self.line = line
        self.window = ReorderWindow(line.ingest.reorder_window_s)
        self.skew = SkewEstimator(line)
        self.sources = SourceMonitor(line)

    def push(self, event: CanonicalEvent) -> list[Released]:
        """Take one event in, and return whatever is now safe to release."""
        self.sources.observe(event)
        released = self.window.push(event)
        for item in released:
            self.skew.observe(item.event)
        return released

    def flush(self) -> list[Released]:
        """Release everything still buffered."""
        released = self.window.flush()
        for item in released:
            self.skew.observe(item.event)
        return released

    def normalise(self, events: Iterable[CanonicalEvent]) -> Iterator[Released]:
        """Run a whole stream through, releasing in source order."""
        for event in events:
            yield from self.push(event)
        yield from self.flush()
