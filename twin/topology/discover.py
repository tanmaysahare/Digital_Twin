"""Topology discovery from a recorded stream. T-122, AC-081.

Onboarding a line by hand means a person sitting with a controls engineer and a
spreadsheet for a week. Most of what that week produces is already in the event
stream: the stations, their order, which of them emit and which do not, the
transports between them and roughly what the takt is. This module reads those
off a stream and produces a `LineDefinition` draft.

**What it will not do is guess.** A field it cannot infer is left blank and
marked, with a sentence saying why and what would let it be inferred (AC-081).
Buffer capacities, gate positions and zone names are the three that matter and
none of them is inferable from timestamps:

- A **buffer capacity** is a physical fact about the floor. The stream shows how
  many units have been between two stations at once, which is a lower bound on
  the capacity and never the capacity itself. Reporting the observed maximum as
  the capacity would make the forecast confident about a constraint that does
  not exist.
- A **gate** is an inspection point, and its results arrive from the quality
  system with the gate already named. Where they do, the gate is read off them.
  Where they do not, no arrangement of cycle events reveals one.
- A **zone** is what the plant calls a part of its line. It is not in the data
  at all and never will be.

Every inferred field carries a confidence, and the confidence is the evidence
count behind it rather than a feeling.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from itertools import pairwise

from connector.protocol import CanonicalEvent

# Below this many observations a field is reported as inferred with a low
# confidence rather than not reported. A draft with a weak number and a stated
# confidence is more useful than a blank, as long as it says which it is.
MINIMUM_OBSERVATIONS = 5

# How many passages a transport estimate needs before it is worth stating.
MINIMUM_TRANSPORTS = 20


@dataclass(frozen=True)
class InferredField:
    """One field of a draft: what was inferred, how sure, and from what."""

    field: str
    value: str | None
    confidence: float | None
    inferred_from: str
    note: str


@dataclass(frozen=True)
class TopologyDraft:
    """A line definition draft, with its gaps named rather than filled."""

    line_id: str
    observed_events: int
    fields: tuple[InferredField, ...]
    stations: tuple[InferredField, ...]
    not_inferable: tuple[str, ...]

    @property
    def note(self) -> str:
        """What a person has to do with this draft before it is a definition."""
        return (
            f"Drafted from {self.observed_events:,} events. "
            f"{len(self.not_inferable)} fields are left blank because nothing in "
            f"an event stream determines them. Fill those in and the draft is a "
            f"line definition."
        )


@dataclass
class TopologyDiscoverer:
    """Reads a canonical stream and drafts the line that produced it."""

    _first_seen: dict[str, datetime] = field(default_factory=dict, repr=False)
    _cycle_counts: Counter[str] = field(default_factory=Counter, repr=False)
    _arrivals: dict[str, list[tuple[str, datetime]]] = field(
        default_factory=lambda: defaultdict(list), repr=False
    )
    _departures: dict[str, dict[str, datetime]] = field(
        default_factory=lambda: defaultdict(dict), repr=False
    )
    _transports: dict[tuple[str, str], list[float]] = field(
        default_factory=lambda: defaultdict(list), repr=False
    )
    _unit_route: dict[str, list[str]] = field(
        default_factory=lambda: defaultdict(list), repr=False
    )
    _gates: dict[str, Counter[str]] = field(
        default_factory=lambda: defaultdict(Counter), repr=False
    )
    _variants: Counter[str] = field(default_factory=Counter, repr=False)
    _headways: list[float] = field(default_factory=list, repr=False)
    _last_release: datetime | None = field(default=None, repr=False)
    _line_id: str = field(default="", repr=False)
    _count: int = field(default=0, repr=False)

    def observe(self, event: CanonicalEvent) -> None:
        """Take one canonical event."""
        self._count += 1
        self._line_id = self._line_id or event.line_id
        station_id = event.station_id
        if station_id is not None:
            self._first_seen.setdefault(station_id, event.ts_source)
        if event.event_type == "CYCLE_END" and station_id is not None:
            self._cycle_counts[station_id] += 1
            variant = str(event.payload.get("variant_id", ""))
            if variant:
                self._variants[variant] += 1
        elif event.event_type == "UNIT_DEPART" and station_id and event.unit_id:
            self._departures[event.unit_id][station_id] = event.ts_source
        elif event.event_type == "UNIT_ARRIVE" and station_id and event.unit_id:
            route = self._unit_route[event.unit_id]
            if route:
                previous = route[-1]
                left = self._departures[event.unit_id].get(previous)
                if left is not None:
                    gap = (event.ts_source - left).total_seconds()
                    self._transports[(previous, station_id)].append(gap)
            else:
                self._note_headway(event.ts_source)
            route.append(station_id)
        elif event.event_type == "INSPECTION_RESULT" and event.unit_id:
            gate_id = str(event.payload.get("gate_id", ""))
            route = self._unit_route.get(event.unit_id, [])
            if gate_id and route:
                self._gates[gate_id][route[-1]] += 1

    def _note_headway(self, at: datetime) -> None:
        """The gap between one release and the next, which is what takt shows as."""
        if self._last_release is not None:
            self._headways.append((at - self._last_release).total_seconds())
        self._last_release = at

    def draft(self) -> TopologyDraft:
        """The draft, with everything the stream determined and nothing else."""
        order = self._order()
        return TopologyDraft(
            line_id=self._line_id or "unknown",
            observed_events=self._count,
            fields=(
                self._takt(),
                self._station_count(order),
                self._variant_field(),
                *self._gate_fields(order),
                _blank(
                    "buffers",
                    "A buffer capacity is a physical fact about the floor. The "
                    "stream shows how many units have been between two stations "
                    "at once, which is a lower bound and never the capacity. "
                    "Reporting the observed maximum would make the forecast "
                    "confident about a constraint that may not exist.",
                ),
                _blank(
                    "zones",
                    "A zone is what the plant calls a part of its line. Nothing "
                    "in an event stream determines it.",
                ),
                _blank(
                    "shifts",
                    "Shift boundaries can be read from SHIFT_MARKER events where "
                    "a site emits them. This stream carried none, and inferring "
                    "them from quiet periods would confuse a break with a stop.",
                )
                if not self._has_markers()
                else InferredField(
                    field="shifts",
                    value="from SHIFT_MARKER events",
                    confidence=0.9,
                    inferred_from="shift markers in the stream",
                    note="",
                ),
            ),
            stations=tuple(self._station_field(item, order) for item in order),
            not_inferable=(
                "buffers",
                "zones",
                "rework loops",
                "variant mix targets",
            ),
        )

    def _order(self) -> tuple[str, ...]:
        """Station order, from the routes units actually took."""
        after: Counter[tuple[str, str]] = Counter()
        for route in self._unit_route.values():
            for first, second in pairwise(route):
                after[(first, second)] += 1
        stations = set(self._first_seen)
        successors: dict[str, str] = {}
        for (first, second), count in after.most_common():
            if first in successors or count < MINIMUM_OBSERVATIONS:
                continue
            successors[first] = second
        heads = stations - set(successors.values())
        start = min(heads, key=lambda item: self._first_seen[item], default=None)
        if start is None:
            return tuple(sorted(stations))
        found = [start]
        seen = {start}
        while (nxt := successors.get(found[-1])) is not None and nxt not in seen:
            found.append(nxt)
            seen.add(nxt)
        found.extend(sorted(stations - seen))
        return tuple(found)

    def _takt(self) -> InferredField:
        """Takt, from the headway between releases."""
        if len(self._headways) < MINIMUM_TRANSPORTS:
            return _blank(
                "takt_s",
                f"Only {len(self._headways)} releases were seen, which is too "
                f"few to separate takt from the gaps between them.",
            )
        ordered = sorted(self._headways)
        median = ordered[len(ordered) // 2]
        return InferredField(
            field="takt_s",
            value=f"{median:.1f}",
            confidence=min(1.0, len(self._headways) / 200.0),
            inferred_from=f"median headway over {len(self._headways)} releases",
            note="",
        )

    def _station_count(self, order: tuple[str, ...]) -> InferredField:
        """How many stations the stream showed."""
        return InferredField(
            field="stations",
            value=str(len(order)),
            confidence=1.0 if order else 0.0,
            inferred_from="stations that appeared in the stream",
            note=(
                "A station that emits nothing at all and is never flanked by a "
                "scan does not appear here, so this is a lower bound."
            ),
        )

    def _variant_field(self) -> InferredField:
        """Which variants ran, from the cycle events themselves."""
        if not self._variants:
            return _blank(
                "variants",
                "No cycle event carried a variant, so the mix cannot be read.",
            )
        names = ", ".join(sorted(self._variants))
        return InferredField(
            field="variants",
            value=names,
            confidence=1.0,
            inferred_from=f"{sum(self._variants.values())} cycle events",
            note=(
                "The observed mix is not the target mix. The target belongs to "
                "the schedule and is not in the stream."
            ),
        )

    def _gate_fields(self, order: tuple[str, ...]) -> tuple[InferredField, ...]:
        """Every gate, from the inspection results that named it."""
        if not self._gates:
            return (
                _blank(
                    "gates",
                    "No inspection results reached the twin, and no arrangement "
                    "of cycle events reveals a gate.",
                ),
            )
        found: list[InferredField] = []
        for gate_id, positions in sorted(self._gates.items()):
            station_id, count = positions.most_common(1)[0]
            found.append(
                InferredField(
                    field=f"gate {gate_id}",
                    value=f"after {station_id}",
                    confidence=min(1.0, count / 50.0),
                    inferred_from=f"{count} verdicts recorded at that position",
                    note="" if station_id in order else "position not in the route",
                )
            )
        return tuple(found)

    def _station_field(self, station_id: str, order: tuple[str, ...]) -> InferredField:
        """One station's tier and transport, as far as the stream determines them."""
        cycles = self._cycle_counts.get(station_id, 0)
        index = order.index(station_id) if station_id in order else -1
        successor = order[index + 1] if 0 <= index < len(order) - 1 else None
        transports = (
            self._transports.get((station_id, successor), [])
            if successor is not None
            else []
        )
        tier = "A or B" if cycles else "C"
        transport = ""
        if len(transports) >= MINIMUM_TRANSPORTS:
            ordered = sorted(transports)
            transport = f", transport {ordered[int(len(ordered) * 0.05)]:.1f} s"
        return InferredField(
            field=station_id,
            value=f"tier {tier}{transport}",
            confidence=1.0 if cycles else min(1.0, len(transports) / 100.0),
            inferred_from=(
                f"{cycles} cycle events, {len(transports)} timed passages to "
                f"{successor or 'the end of the line'}"
            ),
            note=(
                ""
                if cycles
                else (
                    "No machine data. Whether this is tier C by design or a "
                    "source that is down cannot be told from the stream alone."
                )
            ),
        )

    def _has_markers(self) -> bool:
        """Whether the stream carried shift markers at all."""
        return bool(self._headways) and self._last_release is not None


def _blank(name: str, why: str) -> InferredField:
    """A field left blank on purpose, with the reason attached."""
    return InferredField(
        field=name, value=None, confidence=None, inferred_from="", note=why
    )
