"""The state estimator. T-038, T-039.

Reconstructs the line from the filtered event stream: what each station is
doing, how full each buffer is, and what has happened to each unit so far.

The thing to understand about this module is how much of it is inference. Only
24 of Line 2's 42 stations report a state word at all. Twelve report their clock
and nothing else, so whether one of them is blocked or starved is worked out
here from what its neighbours did. Six report nothing, so even the fact that a
unit is at one of them is a deduction from a scan further down the line.

Every one of those steps produces an `Estimate` carrying its provenance, and the
three cases stay visibly different on the screen:

- `MEASURED`: the station said so.
- `DERIVED`: worked out from measurements by a relation that holds exactly, such
  as a buffer level from the count in less the count out.
- `INFERRED`: reasoned to, with a bound rather than a value. Everything the
  virtual sensors produce is this.

Where the evidence does not decide between states, the answer is
`IDLE_UNKNOWN`. It is never collapsed into `IDLE` or `STARVED` to make a screen
look tidier, because the whole argument of the product is that a twin which
guesses is worth less than one which says what it does not know.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import datetime

from connector.normalise import Released
from connector.protocol import CanonicalEvent
from twin.config.line import LineDefinition, StationDefinition
from twin.domain.estimate import Estimate, Interval, Resolution
from twin.domain.signature import ProcessSignature, StationVisit
from twin.domain.state import (
    BufferSnapshot,
    LineState,
    StationSnapshot,
    StationState,
    Trend,
)
from twin.state.distributions import DistributionStore
from twin.state.virtual_sensors import VirtualSensors, dark_spans

# How many buffer readings back the trend looks. Three is enough to tell rising
# from noise at a two-minute cadence and short enough to still be current.
_TREND_WINDOW = 3


@dataclass
class _Station:
    """What the twin currently believes about one station."""

    definition: StationDefinition
    state: StationState = "IDLE_UNKNOWN"
    since: datetime | None = None
    current_unit_id: str | None = None
    arrived_at: datetime | None = None
    work_ended_at: datetime | None = None
    departed_at: datetime | None = None
    last_cycle: Estimate | None = None
    resolution: Resolution = "RESOLVED"
    observed_cycles: int = 0
    basis: str = "no events seen from this station yet"

    def set_state(self, state: StationState, at: datetime, basis: str) -> None:
        """Move to a state, remembering when and on what evidence."""
        if self.state != state:
            self.since = at
        self.state = state
        self.basis = basis


@dataclass
class _Unit:
    """One unit's route as it accumulates."""

    unit_id: str
    variant_id: str
    entered_at: datetime
    visits: list[StationVisit] = field(default_factory=list)
    open_visit: dict[str, object] = field(default_factory=dict)
    status: str = "IN_PROCESS"
    exited_at: datetime | None = None
    seq: int = 0


class StateEstimator:
    """Turns a canonical event stream into a live picture of the line."""

    def __init__(self, line: LineDefinition) -> None:
        """Build an estimator for one line, from that line's definition alone."""
        self.line = line
        self.distributions = DistributionStore(line)
        self.sensors = VirtualSensors(line)
        self._stations = {
            station.station_id: _Station(station) for station in line.stations
        }
        self._order = line.station_ids
        self._index_of = {
            station_id: index for index, station_id in enumerate(self._order)
        }
        self._units: dict[str, _Unit] = {}
        self._zone_of = self._zone_lookup()
        self._environment: dict[str, dict[str, float]] = {}
        self._shift_id: str | None = None
        self._at: datetime | None = None
        self._late_recomputes: list[str] = []
        # Counts in and out of each station, which is what a buffer level is
        # derived from. Unit conservation is the only arithmetic here.
        self._arrived: dict[str, int] = dict.fromkeys(self._order, 0)
        self._departed: dict[str, int] = dict.fromkeys(self._order, 0)
        self._buffer_history: dict[str, list[int]] = {
            item.buffer_id: [] for item in line.buffers
        }
        self._spans = dark_spans(line)
        self._tail_span = {
            span.upstream_id: span
            for span in self._spans
            if span.downstream_id is None and span.upstream_id is not None
        }

    # -- construction ----------------------------------------------------

    def _zone_lookup(self) -> dict[str, str]:
        lookup: dict[str, str] = {}
        for zone in self.line.zones:
            first, last = zone.span
            start, end = self._order.index(first), self._order.index(last)
            for station_id in self._order[start : end + 1]:
                lookup[station_id] = zone.zone_id
        return lookup

    # -- ingest ----------------------------------------------------------

    def apply_all(self, events: Iterable[CanonicalEvent]) -> None:
        """Take a whole stream."""
        for event in events:
            self.apply(event)

    def apply_released(self, released: Released) -> None:
        """Take one event from the normaliser, recomputing where it arrived late."""
        if released.recompute_station_id is not None:
            self._late_recomputes.append(released.recompute_station_id)
        self.apply(released.event)

    @property
    def pending_recomputes(self) -> tuple[str, ...]:
        """Stations whose state a late event has invalidated. EC-01."""
        return tuple(self._late_recomputes)

    def apply(self, event: CanonicalEvent) -> None:
        """Take one canonical event into the state."""
        self._at = event.ts_source
        self.sensors.observe(event)
        handler = getattr(self, f"_on_{event.event_type.lower()}", None)
        if handler is not None:
            handler(event)
        self._record_dark_visits(event)

    # -- event handlers --------------------------------------------------

    def _on_shift_marker(self, event: CanonicalEvent) -> None:
        marker = str(event.payload.get("marker", ""))
        self._shift_id = (
            str(event.payload.get("shift_id"))
            if marker in {"START", "BREAK_END"}
            else self._shift_id
        )

    def _on_env_reading(self, event: CanonicalEvent) -> None:
        zone_id = str(event.payload.get("zone_id", ""))
        self._environment[zone_id] = {
            key: float(value)
            for key, value in event.payload.items()
            if key != "zone_id" and isinstance(value, int | float)
        }

    def _on_unit_arrive(self, event: CanonicalEvent) -> None:
        if event.station_id is None or event.unit_id is None:
            return
        station = self._stations[event.station_id]
        station.current_unit_id = event.unit_id
        station.arrived_at = event.ts_source
        station.work_ended_at = None
        station.set_state(
            "RUNNING", event.ts_source, f"{event.station_id} has a unit and is working"
        )
        self._arrived[event.station_id] += 1
        unit = self._units.get(event.unit_id)
        if unit is None:
            unit = _Unit(
                unit_id=event.unit_id,
                variant_id=str(event.payload.get("variant_id", "")),
                entered_at=event.ts_source,
            )
            self._units[event.unit_id] = unit
        unit.seq += 1
        unit.open_visit = {
            "station_id": event.station_id,
            "seq": unit.seq,
            "arrived_at": event.ts_source,
            "process_values": {},
            "part_lots": [],
        }

    def _on_cycle_end(self, event: CanonicalEvent) -> None:
        if event.station_id is None:
            return
        station = self._stations[event.station_id]
        cycle_s = _as_float(event.payload.get("cycle_time_s"))
        variant_id = str(event.payload.get("variant_id", ""))
        station.last_cycle = Estimate.measured(
            cycle_s, f"{event.station_id} reported its own cycle time"
        )
        station.resolution = "RESOLVED"
        station.observed_cycles += 1
        station.work_ended_at = event.ts_source
        self.distributions.record(event.station_id, variant_id, cycle_s)
        station.set_state(
            "BLOCKED",
            event.ts_source,
            f"{event.station_id} finished its cycle and still holds the unit",
        )

    def _on_station_state(self, event: CanonicalEvent) -> None:
        """A tier A station reporting its own state word.

        The only place a station state is `MEASURED`. Everything else on this
        line is worked out from timing, and the interface shows the difference.
        """
        if event.station_id is None:
            return
        reported = str(event.payload.get("state", ""))
        if reported not in {
            "RUNNING",
            "BLOCKED",
            "STARVED",
            "DOWN",
            "CHANGEOVER",
            "IDLE",
        }:
            return
        state: StationState = reported  # type: ignore[assignment]
        self._stations[event.station_id].set_state(
            state, event.ts_source, f"{event.station_id} reported this state itself"
        )

    def _open_visit_at(self, event: CanonicalEvent) -> _Unit | None:
        """The unit this event is about, if the twin is tracking one."""
        if event.unit_id is None or event.station_id is None:
            return None
        return self._units.get(event.unit_id)

    def _last_visit_index(self, unit: _Unit, station_id: str) -> int | None:
        for index in range(len(unit.visits) - 1, -1, -1):
            if unit.visits[index].station_id == station_id:
                return index
        return None

    def _on_process_value(self, event: CanonicalEvent) -> None:
        """One process signal, against the visit it belongs to.

        A signal and the cycle it came from often carry the same timestamp, and
        a site is under no obligation to deliver them in a helpful order, so a
        signal that arrives after its visit has closed is attached to that visit
        rather than dropped.
        """
        unit = self._open_visit_at(event)
        if unit is None or event.station_id is None:
            return
        signal = str(event.payload.get("signal"))
        value = _as_float(event.payload.get("value"))
        if unit.open_visit.get("station_id") == event.station_id:
            values = unit.open_visit["process_values"]
            assert isinstance(values, dict)
            values[signal] = value
            return
        index = self._last_visit_index(unit, event.station_id)
        if index is None:
            return
        visit = unit.visits[index]
        unit.visits[index] = replace(
            visit, process_values={**visit.process_values, signal: value}
        )

    def _on_part_lot_scan(self, event: CanonicalEvent) -> None:
        """One part lot, against the visit that consumed it."""
        unit = self._open_visit_at(event)
        if unit is None or event.station_id is None:
            return
        lot_id = str(event.payload.get("lot_id"))
        if unit.open_visit.get("station_id") == event.station_id:
            lots = unit.open_visit["part_lots"]
            assert isinstance(lots, list)
            lots.append(lot_id)
            return
        index = self._last_visit_index(unit, event.station_id)
        if index is None:
            return
        visit = unit.visits[index]
        unit.visits[index] = replace(visit, part_lots=(*visit.part_lots, lot_id))

    def _on_manual_check(self, event: CanonicalEvent) -> None:
        """A checklist result from a dark station.

        Recorded against the unit as an observation. It is never used as a
        timing anchor: its timestamp says when a person filled in a form.
        """
        if event.unit_id is None or event.station_id is None:
            return
        unit = self._units.get(event.unit_id)
        if unit is None:
            return
        for index in range(len(unit.visits) - 1, -1, -1):
            visit = unit.visits[index]
            if visit.station_id != event.station_id:
                continue
            checks = dict(visit.environment)
            checks["manual_check_passed"] = float(event.payload.get("result") == "PASS")
            unit.visits[index] = replace(visit, environment=checks)

    def _on_inspection_result(self, event: CanonicalEvent) -> None:
        if event.unit_id is None:
            return
        unit = self._units.get(event.unit_id)
        if unit is None:
            return
        gate_id = str(event.payload.get("gate_id"))
        if self.line.gates and gate_id == self.line.gates[-1].gate_id:
            unit.status = "COMPLETED"
            unit.exited_at = event.ts_source

    def _on_unit_depart(self, event: CanonicalEvent) -> None:
        if event.station_id is None or event.unit_id is None:
            return
        station = self._stations[event.station_id]
        self._departed[event.station_id] += 1
        self._close_visit(event)
        station.current_unit_id = None
        station.departed_at = event.ts_source
        station.arrived_at = None
        self._settle_empty(station, event.ts_source)

    # -- inference -------------------------------------------------------

    def _settle_empty(self, station: _Station, at: datetime) -> None:
        """Decide what an empty station is doing, or say it cannot be decided.

        A station with nothing to work on is starved. A station that is between
        units, with one already on its way, is merely idle. Where the station
        upstream emits nothing at all, neither can be established and the answer
        is `IDLE_UNKNOWN` rather than the more flattering of the two.
        """
        station_id = station.definition.station_id
        index = self._index_of[station_id]
        if index == 0:
            station.set_state(
                "IDLE",
                at,
                f"{station_id} is at the head of the line, waiting on release",
            )
            return
        upstream_id = self._order[index - 1]
        if self._stations[upstream_id].definition.tier == "C":
            station.set_state(
                "IDLE_UNKNOWN",
                at,
                f"{upstream_id} emits no data, so whether {station_id} is starved "
                f"or simply between units cannot be established",
            )
            return
        in_flight = self._departed[upstream_id] - self._arrived[station_id]
        if in_flight > 0:
            station.set_state(
                "IDLE", at, f"a unit has left {upstream_id} and is on its way here"
            )
            return
        station.set_state(
            "STARVED", at, f"nothing has left {upstream_id}, so {station_id} is waiting"
        )

    def _dark_state(self, station_id: str) -> tuple[StationState, str]:
        """What a station that emits nothing is doing, as far as can be told."""
        span = next(
            (item for item in self._spans if station_id in item.dark_station_ids), None
        )
        if span is None or span.upstream_id is None or span.downstream_id is None:
            # With a scan at only one end, or neither, there is no conservation
            # to count and nothing can be said about what the station is doing.
            return (
                "IDLE_UNKNOWN",
                f"{station_id} emits no data and has no scan point on both sides, "
                f"so nothing establishes whether it is working",
            )
        entered = self._departed[span.upstream_id]
        left = self._arrived[span.downstream_id]
        if entered - left <= 0:
            return (
                "STARVED",
                f"nothing has entered the run of dark stations since the last unit "
                f"left it, so {station_id} has nothing to work on",
            )
        if span.size == 1:
            return (
                "RUNNING",
                f"a unit is between {span.upstream_id} and {span.downstream_id}, "
                f"and {station_id} is the only station there",
            )
        return (
            "IDLE_UNKNOWN",
            f"{entered - left} units are somewhere between {span.upstream_id} and "
            f"{span.downstream_id}. Which of the {span.size} stations there holds "
            f"which cannot be established without a scan point inside the run",
        )

    # -- signatures ------------------------------------------------------

    def _close_visit(self, event: CanonicalEvent) -> None:
        if event.unit_id is None or event.station_id is None:
            return
        unit = self._units.get(event.unit_id)
        if unit is None or not unit.open_visit:
            return
        open_visit = unit.open_visit
        arrived_at = open_visit["arrived_at"]
        assert isinstance(arrived_at, datetime)
        station = self._stations[event.station_id]
        dwell_s = (event.ts_source - arrived_at).total_seconds()
        blocked = None
        if station.work_ended_at is not None:
            blocked = Estimate.derived(
                Interval(
                    0.0, (event.ts_source - station.work_ended_at).total_seconds()
                ),
                basis=(
                    f"{event.station_id} finished its cycle before the unit left, "
                    f"so the difference is time it could not hand the unit on"
                ),
                confidence=0.9,
            )
        values = open_visit["process_values"]
        lots = open_visit["part_lots"]
        assert isinstance(values, dict)
        assert isinstance(lots, list)
        unit.visits.append(
            StationVisit(
                station_id=event.station_id,
                seq=int(open_visit["seq"]),  # type: ignore[call-overload]
                arrived_at=arrived_at,
                departed_at=event.ts_source,
                dwell_s=dwell_s,
                cycle_time=station.last_cycle,
                state_during="RUNNING",
                blocked_s=blocked,
                starved_s=None,
                process_values=dict(values),
                part_lots=tuple(lots),
                operator_group=None,
                shift_id=self._shift_id,
                environment=dict(
                    self._environment.get(self._zone_of[event.station_id], {})
                ),
            )
        )
        unit.open_visit = {}

    def _record_dark_visits(self, event: CanonicalEvent) -> None:
        """Add the dark stations a unit passed through to its signature.

        A unit that left S32 and reached S38 visited S33 to S37, and the route
        says so even though not one of those five stations emitted anything.
        Each visit carries the bound the virtual sensors derived and is marked
        `UNRESOLVED` where the span holds more than one station.
        """
        if event.unit_id is None or event.station_id is None:
            return
        unit = self._units.get(event.unit_id)
        if unit is None:
            return
        if event.event_type == "UNIT_ARRIVE":
            estimate = next(
                (
                    item
                    for item in reversed(self.sensors.estimates())
                    if item.unit_id == event.unit_id and item.at == event.ts_source
                ),
                None,
            )
            if estimate is None:
                return
            for station_id in estimate.span.dark_station_ids:
                unit.seq += 1
                unit.visits.append(
                    self._dark_visit(unit, station_id, estimate.per_station[station_id])
                )
            return
        if event.event_type != "UNIT_DEPART":
            return
        span = self._tail_span.get(event.station_id)
        if span is None:
            return
        # A dark run at the end of the line has no second scan, so there is no
        # bound at all and the visit records exactly that (STA-07).
        for station_id in span.dark_station_ids:
            unit.seq += 1
            unit.visits.append(self._dark_visit(unit, station_id, None))

    def _dark_visit(
        self, unit: _Unit, station_id: str, cycle: Estimate | None
    ) -> StationVisit:
        """One visit to a station that emitted nothing about it."""
        return StationVisit(
            station_id=station_id,
            seq=unit.seq,
            arrived_at=None,
            departed_at=None,
            dwell_s=None,
            cycle_time=cycle,
            state_during="IDLE_UNKNOWN",
            blocked_s=None,
            starved_s=None,
            process_values={},
            part_lots=(),
            operator_group=None,
            shift_id=self._shift_id,
            environment=dict(self._environment.get(self._zone_of[station_id], {})),
        )

    def signature(self, unit_id: str) -> ProcessSignature | None:
        """One unit's route so far, in order. STA-03."""
        unit = self._units.get(unit_id)
        if unit is None:
            return None
        return ProcessSignature(
            unit_id=unit.unit_id,
            line_id=self.line.line_id,
            variant_id=unit.variant_id,
            entered_at=unit.entered_at,
            exited_at=unit.exited_at,
            status=unit.status,
            visits=tuple(unit.visits),
        )

    def signatures(self) -> tuple[ProcessSignature, ...]:
        """Every unit the twin has seen, in the order they entered."""
        return tuple(
            signature
            for signature in (self.signature(unit_id) for unit_id in self._units)
            if signature is not None
        )

    # -- the live picture ------------------------------------------------

    def state(self, at: datetime | None = None) -> LineState:
        """The whole line as the twin currently understands it. STA-01."""
        now = at or self._at
        if now is None:
            message = "no events have been seen, so there is no state to report"
            raise ValueError(message)
        return LineState(
            line_id=self.line.line_id,
            at=now,
            stations=tuple(
                self._snapshot(station_id, now) for station_id in self._order
            ),
            buffers=tuple(self._buffer(item.buffer_id) for item in self.line.buffers),
            unresolved=self.sensors.unresolved(),
        )

    def _snapshot(self, station_id: str, now: datetime) -> StationSnapshot:
        station = self._stations[station_id]
        if station.definition.tier == "C":
            state, basis = self._dark_state(station_id)
            cycle = self.sensors.latest(station_id)
            return StationSnapshot(
                station_id=station_id,
                tier="C",
                state=state,
                since=station.since or now,
                current_unit_id=None,
                last_cycle=cycle,
                resolution=cycle.resolution if cycle is not None else "UNRESOLVED",
                observed_cycles=0,
                basis=basis if cycle is None else f"{basis}. {cycle.basis}",
            )
        return StationSnapshot(
            station_id=station_id,
            tier=station.definition.tier,
            state=station.state,
            since=station.since or now,
            current_unit_id=station.current_unit_id,
            last_cycle=station.last_cycle,
            resolution=station.resolution,
            observed_cycles=station.observed_cycles,
            basis=station.basis,
        )

    def units_between(self, upstream_id: str, downstream_id: str) -> int:
        """How many units are between two stations, by unit conservation.

        The count that left the upstream station less the count that reached the
        downstream one. Exact wherever both flanking sources are complete, which
        is what lets the twin say how many units are inside a dark run even
        though not one of the stations there emits anything.
        """
        return max(0, self._departed[upstream_id] - self._arrived[downstream_id])

    def link_occupancy(self) -> tuple[int, ...]:
        """How many units sit on the link feeding each station, in line order.

        Unit conservation, with one complication. Between two instrumented
        stations the count that left one less the count that reached the other is
        exact. Across a dark run there is no arrival scan at all, so the same
        subtraction across a single link would count every unit that has ever
        entered the run. What conservation gives there is the number of units
        inside the whole span, and where they sit inside it is exactly what the
        twin cannot know (STA-07). The span's units are spread over its links,
        oldest first, and the forecast seed records that this placement is an
        assumption rather than an observation.

        Index 0 is the release point, which holds nothing the twin can see.
        """
        levels = [0] * len(self._order)
        for index in range(1, len(self._order)):
            upstream = self._order[index - 1]
            here = self._order[index]
            if (
                self._stations[upstream].definition.tier != "C"
                and self._stations[here].definition.tier != "C"
            ):
                levels[index] = self.units_between(upstream, here)
        for span in self._spans:
            if span.upstream_id is None or span.downstream_id is None:
                continue
            inside = self.units_between(span.upstream_id, span.downstream_id)
            first = self._index_of[span.dark_station_ids[0]]
            last = self._index_of[span.dark_station_ids[-1]] + 1
            for position, link in enumerate(range(first, last + 1)):
                # One unit per link across the span, front to back. A span
                # holding more units than it has links is a span whose flanking
                # scans disagree, and the excess is dropped rather than piled on
                # to a link that cannot hold it.
                levels[link] = 1 if position < inside else 0
        return tuple(levels)

    def holding(self) -> dict[str, tuple[str, datetime]]:
        """Which stations hold a unit right now, and since when.

        A dark station is absent: nothing says when a unit reached it, which is
        why the forecast seeds the dark run from its link occupancy instead.
        """
        found: dict[str, tuple[str, datetime]] = {}
        for station_id, station in self._stations.items():
            if station.current_unit_id is not None and station.arrived_at is not None:
                found[station_id] = (station.current_unit_id, station.arrived_at)
        return found

    def variant_of(self, unit_id: str) -> str:
        """One unit's model variant, or an empty string if it is not known."""
        unit = self._units.get(unit_id)
        return unit.variant_id if unit is not None else ""

    def recent_variants(self, count: int) -> tuple[str, ...]:
        """The variants of the last units released, in the order they arrived.

        The upcoming mix in the prototype is the recent mix. A site with an MES
        schedule reads the schedule instead, and INTEGRATIONS.md carries that
        design; inventing a schedule here would make the forecast look better
        than the data supports.
        """
        recent = [unit.variant_id for unit in self._units.values()][-count:]
        return tuple(item for item in recent if item)

    def _buffer(self, buffer_id: str) -> BufferSnapshot:
        """One buffer's level, from unit conservation across it.

        Where both flanking stations report, the count in less the count out is
        exact and the level is `DERIVED`. Where the station feeding the buffer is
        dark, the twin knows how many units are somewhere in the dark run and
        the buffer together, but not how they are split, so the level is an
        interval and it is `INFERRED`.
        """
        definition = next(
            item for item in self.line.buffers if item.buffer_id == buffer_id
        )
        upstream = definition.after
        downstream = self._order[self._index_of[upstream] + 1]
        span = next(
            (item for item in self._spans if upstream in item.dark_station_ids), None
        )
        if span is None:
            level = self._departed[upstream] - self._arrived[downstream]
            level = max(0, min(definition.capacity, level))
            occupancy = Estimate.derived(
                Interval(float(level), float(level)),
                basis=(
                    f"{self._departed[upstream]} units have left {upstream} and "
                    f"{self._arrived[downstream]} have reached {downstream}"
                ),
                confidence=1.0,
            )
        else:
            entered = self._departed[span.upstream_id] if span.upstream_id else 0
            left = self._arrived[downstream]
            inside = max(0, entered - left)
            low = float(max(0, inside - span.size))
            high = float(min(definition.capacity, inside))
            occupancy = Estimate.inferred(
                Interval(min(low, high), high),
                basis=(
                    f"{inside} units are between {span.upstream_id} and "
                    f"{downstream}, shared between {buffer_id} and "
                    f"{span.size} stations that emit nothing"
                ),
                confidence=0.5,
            )
        history = self._buffer_history[buffer_id]
        history.append(int(occupancy.hi))
        del history[:-_TREND_WINDOW]
        return BufferSnapshot(
            buffer_id=buffer_id,
            after_station_id=upstream,
            occupancy=occupancy,
            capacity=definition.capacity,
            trend=_trend(history),
        )


def _as_float(value: object) -> float:
    """Read a payload number, or zero where a source sent something else.

    A malformed payload is a data-health matter rather than a crash: the twin
    degrades to less information, never to wrong information.
    """
    return float(value) if isinstance(value, int | float | str) else 0.0


def _trend(history: list[int]) -> Trend:
    """Which way a buffer is moving, over the last few readings."""
    if len(history) < _TREND_WINDOW:
        return "FLAT"
    if history[-1] > history[0]:
        return "RISING"
    if history[-1] < history[0]:
        return "FALLING"
    return "FLAT"
