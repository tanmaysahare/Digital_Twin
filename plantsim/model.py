"""The SimPy line model. T-020 to T-026.

A mixed-model assembly line: stations in order, a store between each pair whose
capacity is the configured buffer where there is one and a single conveyor
position where there is not, transports, inspection gates, rework loops, a takt
release paced by the shift calendar, and operation-dependent breakdowns.

Three modelling choices carry weight and are not conveniences.

**A station holds its unit until the next position is free.** That is what makes
blocking propagate upstream, and blocking propagating upstream is the whole
subject of the forecast. Where the line definition places a buffer, the store
between two stations has that capacity; where it does not, the store holds one
unit, which is the conveyor position that physically exists between any two
stations.

**Failures are operation-dependent.** A station cannot fail while it is idle,
which is the standard assumption for paced assembly. It also means a repair
happens inside a cycle, so a station's true cycle time includes it. The twin
cannot separate a slow station from a briefly broken one at a dark station, and
defining truth this way says so rather than holding the twin to a distinction it
has no evidence for.

**Work counts production seconds, dwell counts wall seconds.** A cycle
interrupted by a shift break resumes after it. The difference between the two
clocks is exactly what the twin has to subtract from a span before it can read
it as work, and building the difference in here is what makes that a real test
rather than a formality.
"""

from __future__ import annotations

import math
from collections.abc import Generator
from dataclasses import dataclass, field
from typing import Any, cast
from uuid import UUID, uuid5

import numpy as np
import simpy

from connector.protocol import CanonicalEvent
from plantsim.emit import EVENT_NAMESPACE, EVENT_ORDER, EventEmitter
from plantsim.parameters import PlantModel
from plantsim.scenarios import NULL_SCENARIO, Scenario
from plantsim.truth import BufferTruth, GateTruth, GroundTruth, UnitTruth, VisitTruth
from twin.config.line import OFF_LINE, LineDefinition
from twin.domain.seeds import generator_for
from twin.domain.shifts import ProductionCalendar

# SimPy's events are untyped, so a process generator yields Any. This is the
# only place the project uses it and the alternative is a stub package for a
# library whose event objects genuinely have no useful common type.
Process = Generator[Any, None, None]


@dataclass(frozen=True)
class SimulationDetail:
    """Which optional signals a run emits.

    Process values and state words are what a tier A station reports beside its
    clock, and they multiply the event count by roughly nine. A run whose
    question is timing, such as the 5,000-cycle virtual sensor coverage check,
    turns them off and reads the same timing stream in a fraction of the time.
    """

    process_values: bool = True
    station_state: bool = True
    buffer_levels: bool = True


@dataclass(frozen=True)
class SimulationRequest:
    """One run of one line."""

    line: LineDefinition
    plant: PlantModel
    seed: int
    units: int
    scenario: Scenario = NULL_SCENARIO
    detail: SimulationDetail = SimulationDetail()

    @property
    def run_id(self) -> UUID:
        """A stable identifier for this run.

        Derived from the run's own parameters rather than drawn, so that two
        runs of the same scenario at the same seed are identical down to their
        event identifiers (NFR-07, T-026).
        """
        return uuid5(
            EVENT_NAMESPACE,
            f"{self.line.line_id}:{self.scenario.scenario_id}:{self.seed}:{self.units}",
        )


@dataclass(frozen=True)
class SimulationResult:
    """What a run produced: a filtered event stream, and the truth behind it."""

    run_id: UUID
    line_id: str
    scenario_id: str
    events: tuple[CanonicalEvent, ...]
    truth: GroundTruth
    emitted: int
    suppressed: int
    finished_at_s: float

    @property
    def observability(self) -> float:
        """The share of what happened that reached the twin."""
        total = self.emitted + self.suppressed
        return self.emitted / total if total else 0.0


@dataclass(frozen=True)
class Link:
    """The conveyor and buffer between two stations.

    Two parts, because a unit on a conveyor occupies a position without being
    available yet. `slots` is the capacity: the configured buffer where the line
    definition places one, and a single conveyor position where it does not. A
    station reserves a slot the moment it hands the unit over, which is what
    makes blocking propagate upstream correctly. `ready` holds the units that
    have finished travelling and can be picked up.

    Charging the transport to either station's occupancy would be wrong and it
    is not a small error: at a 60 s takt, adding a 5.5 s transport to a 58 s
    station puts it over takt and caps the whole line below its nominal rate.
    """

    slots: simpy.Container
    ready: simpy.Store
    transport_s: float
    buffer_id: str | None

    @property
    def occupancy(self) -> int:
        """How many units are on this link, travelling or waiting."""
        return int(self.slots.level)


@dataclass(frozen=True)
class HandOff:
    """Where a station puts a unit when it is done with it.

    `store_index` is None when the station does not have to wait for a slot at
    all, either because the unit has left the line or because it has been lifted
    off for rework and will be re-inserted by its own process.
    """

    store_index: int | None
    leaves_line: bool


@dataclass
class Unit:
    """One vehicle on the line, and what has happened to it so far."""

    unit_id: str
    variant_id: str
    index: int
    released_at_s: float
    seq: int = 0
    rework_passes: int = 0
    # When this unit finished travelling and became available to the station
    # ahead of it. The wait from here until the station picks it up is the
    # unit's own queueing, and it is not any station's blocked time.
    ready_at_s: float = 0.0
    lots: list[str] = field(default_factory=list)
    # Cycle-time z-scores by station, which is what the gate model reads when it
    # decides whether this unit fails.
    deviation: dict[str, float] = field(default_factory=dict)
    humidity_excess: dict[str, float] = field(default_factory=dict)
    status: str = "IN_PROCESS"


class LineSimulation:
    """A running line, its ground truth, and the filtered stream it emits."""

    def __init__(self, request: SimulationRequest) -> None:
        """Build the model. Nothing runs until `run` is called."""
        request.plant.validate_against(request.line)
        self._request = request
        self._line = request.line
        self._plant = request.plant
        self._scenario = request.scenario
        self._detail = request.detail
        self._run_id = request.run_id

        self._env = simpy.Environment()
        self._calendar = ProductionCalendar(self._line, self._plant.epoch)
        self._events: list[tuple[int, CanonicalEvent]] = []
        self._emitter = EventEmitter(
            self._line, self._run_id, self._plant.epoch, self._collect
        )
        self._truth = GroundTruth(
            line_id=self._line.line_id, run_id=self._run_id, epoch=self._plant.epoch
        )

        self._index_of = {
            station_id: index for index, station_id in enumerate(self._line.station_ids)
        }
        self._zone_of = self._zone_lookup()
        self._gate_after = {gate.after: gate for gate in self._line.gates}
        self._gate_span = self._gate_spans()
        self._rework_to = {loop.origin: loop.destination for loop in self._line.rework}
        self._material_at = {
            material.station_id: material for material in self._plant.materials
        }
        self._links = self._build_links()

        self._env_rng = generator_for(request.seed, "environment")
        self._lot_quality: dict[str, float] = {}
        self._humidity: dict[str, float] = {}
        self._temperature: dict[str, float] = {}
        self._completed = 0

    # -- randomness ------------------------------------------------------

    def _draw_for(self, *parts: object) -> np.random.Generator:
        """A generator keyed on what the draw is about, not on a running stream.

        Every stochastic quantity in this model is a property of one unit at one
        place: this unit's cycle time at this station, this unit's transport
        across this link, this unit's verdict at this gate. Seeding on that
        identity rather than on a per-station sequence is what makes a scenario
        run comparable with its control.

        With a sequential stream per station the comparison silently fails. A
        unit scrapped at G2 in one run and not the other shifts every subsequent
        draw at every station past S26, and the two runs then differ everywhere
        downstream of the divergence rather than only where the scenario was
        injected. Measured on SC-01 against its control, that showed as changed
        cycle times at seventeen stations when only S20 had been touched. Keyed
        on the unit, the same comparison changes exactly S20.

        This is the same reasoning the transport generators already carried, now
        applied to every draw rather than to one of them.
        """
        return generator_for(self._request.seed, *parts)

    # -- construction ----------------------------------------------------

    def _zone_lookup(self) -> dict[str, str]:
        """Which zone each station belongs to."""
        order = self._line.station_ids
        lookup: dict[str, str] = {}
        for zone in self._line.zones:
            first, last = zone.span
            for station_id in order[order.index(first) : order.index(last) + 1]:
                lookup[station_id] = zone.zone_id
        return lookup

    def _gate_spans(self) -> dict[str, tuple[str, ...]]:
        """Which stations a gate inspects the work of.

        A gate covers everything since the previous gate, because that is the
        stretch of line whose work it is the first opportunity to catch.
        """
        order = self._line.station_ids
        spans: dict[str, tuple[str, ...]] = {}
        start = 0
        for gate in self._line.gates:
            end = order.index(gate.after)
            spans[gate.gate_id] = order[start : end + 1]
            start = end + 1
        return spans

    def _build_links(self) -> list[Link]:
        """One link feeding each station, in line order.

        The link feeding station `i` carries what has left station `i - 1`. The
        link feeding the first station is the release point, which has no
        transport because nothing is upstream of it.
        """
        capacity_after = {item.after: item.capacity for item in self._line.buffers}
        buffer_id_after = {item.after: item.buffer_id for item in self._line.buffers}
        links = [
            Link(
                slots=simpy.Container(self._env, capacity=1, init=0),
                ready=simpy.Store(self._env),
                transport_s=0.0,
                buffer_id=None,
            )
        ]
        for index in range(1, len(self._line.stations)):
            upstream = self._line.stations[index - 1]
            links.append(
                Link(
                    slots=simpy.Container(
                        self._env,
                        capacity=capacity_after.get(upstream.station_id, 1),
                        init=0,
                    ),
                    ready=simpy.Store(self._env),
                    transport_s=upstream.transport_to_next_s or 0.0,
                    buffer_id=buffer_id_after.get(upstream.station_id),
                )
            )
        return links

    def _deliver(self, index: int, unit: Unit) -> Process:
        """Carry a unit along one link, then make it available to the station."""
        link = self._links[index]
        if link.transport_s > 0:
            yield from self._elapse(
                self._transport(
                    self._draw_for("transport", index, unit.unit_id, unit.seq),
                    link.transport_s,
                )
            )
        unit.ready_at_s = float(self._env.now)
        yield link.ready.put(unit)

    # -- running ---------------------------------------------------------

    def run(self) -> SimulationResult:
        """Run the line until every released unit has left it."""
        self._truth.injections.extend(self._scenario.truth())
        self._sample_environment(0.0)
        self._env.process(self._release())
        self._env.process(self._environment())
        self._env.process(self._shift_markers())
        for index in range(len(self._line.stations)):
            self._env.process(self._station(index))
        self._env.run()
        return SimulationResult(
            run_id=self._run_id,
            line_id=self._line.line_id,
            scenario_id=self._scenario.scenario_id,
            events=self._ordered_events(),
            truth=self._truth,
            emitted=self._emitter.emitted,
            suppressed=self._emitter.suppressed,
            finished_at_s=float(self._env.now),
        )

    def _collect(self, event: CanonicalEvent) -> None:
        self._events.append((len(self._events), event))

    def _ordered_events(self) -> tuple[CanonicalEvent, ...]:
        """The stream in source-clock order.

        A gate verdict is recorded after the unit has moved on, so events are
        produced slightly out of order. The simulator hands over a clean ordered
        stream and leaves disorder to the connector, which is where it actually
        arises on a site and where the reordering window is tested (EC-01).

        Events that share a timestamp are ordered by what they are, not by their
        identifier. A scan and the cycle it belongs to happen at the same
        instant often enough that leaving the tie to a hash would attach a part
        lot to the wrong visit about half the time.
        """
        return tuple(
            event
            for _, event in sorted(
                self._events,
                key=lambda item: (
                    item[1].ts_source,
                    EVENT_ORDER[item[1].event_type],
                    item[0],
                ),
            )
        )

    # -- processes -------------------------------------------------------

    def _release(self) -> Process:
        """Release units onto the line at takt, during production hours only."""
        schedule = self._variant_schedule(self._request.units)
        opened_at = self._calendar.next_open(0.0)
        for index in range(self._request.units):
            # The conveyor keeps takt whatever the line is doing, so the
            # schedule is absolute rather than measured from the last release.
            # Rebasing on the previous actual release would make every delay
            # permanent, and a real line catches up when the blockage clears.
            at = self._calendar.advance(opened_at, index * self._line.takt_s)
            if at > self._env.now:
                yield self._env.timeout(at - self._env.now)
            unit = Unit(
                unit_id=self._unit_id(index),
                variant_id=schedule[index],
                index=index,
                released_at_s=float(self._env.now),
            )
            yield self._links[0].slots.put(1)
            self._env.process(self._deliver(0, unit))

    def _variant_schedule(self, count: int) -> list[str]:
        """A level schedule that reproduces the configured mix exactly. T-021.

        Goal chasing rather than sampling: a mixed-model line is scheduled, not
        drawn, and a sampled sequence would make the observed mix differ from
        the configured one by a random amount that no test could pin down.
        """
        produced = dict.fromkeys(self._line.variants, 0)
        sequence: list[str] = []
        for position in range(1, count + 1):
            best = max(
                self._line.variants,
                key=lambda variant: (
                    self._line.mix[variant] * position - produced[variant],
                    -self._line.variants.index(variant),
                ),
            )
            produced[best] += 1
            sequence.append(best)
        return sequence

    def _unit_id(self, index: int) -> str:
        return f"{self._plant.unit_id_prefix}{self._plant.unit_id_start + index}"

    def _environment(self) -> Process:
        """Sample each zone's temperature and humidity on the configured cadence."""
        while self._completed < self._request.units:
            yield self._env.timeout(self._plant.env_sample_s)
            now = float(self._env.now)
            self._sample_environment(now)
            for zone in self._line.zones:
                self._emitter.emit(
                    "ENV_READING",
                    now,
                    {
                        "zone_id": zone.zone_id,
                        "temperature_c": round(self._temperature[zone.zone_id], 2),
                        "humidity_pct": round(self._humidity[zone.zone_id], 2),
                    },
                )

    def _sample_environment(self, now: float) -> None:
        for zone in self._plant.zones:
            offset = self._scenario.humidity_offset(zone.zone_id, now)
            self._temperature[zone.zone_id] = float(
                self._env_rng.normal(zone.temperature_c, zone.temperature_sd_c)
            )
            self._humidity[zone.zone_id] = float(
                min(
                    100.0,
                    max(
                        0.0,
                        self._env_rng.normal(zone.humidity_pct, zone.humidity_sd_pct)
                        + offset,
                    ),
                )
            )

    def _shift_markers(self) -> Process:
        """Publish every shift, break and changeover boundary as it passes."""
        index = 0
        while self._completed < self._request.units:
            markers = self._calendar.markers_until(float(self._env.now))
            while index < len(markers):
                marker = markers[index]
                self._emitter.emit(
                    "SHIFT_MARKER",
                    marker.at_s,
                    {"shift_id": marker.shift_id, "marker": marker.marker},
                )
                index += 1
            yield self._env.timeout(self._line.takt_s)

    def _station(self, index: int) -> Process:
        """One station: take a unit, work on it, hand it on."""
        station = self._line.stations[index]
        station_id = station.station_id
        inbound = self._links[index]
        # None until this station has handed a unit on. A station waiting for
        # the first unit of the run is not starved: the line has not started.
        # Recording that wait as starvation put a 20 minute stop in the ground
        # truth of every station on every run, which is the line fill walking
        # down the line, and it swamped every genuine stop the evaluation is
        # meant to count.
        free_at: float | None = None

        while True:
            unit = cast("Unit", (yield inbound.ready.get()))
            # The slot the unit reserved on the way in is released only now, as
            # it leaves the link. Releasing it earlier would let the upstream
            # station push into a position this unit still occupies.
            yield inbound.slots.get(1)
            queued_s = self._calendar.production_between(
                unit.ready_at_s, float(self._env.now)
            )
            self._record_buffer(index)
            starved_s = (
                0.0
                if free_at is None
                else self._calendar.production_between(free_at, float(self._env.now))
            )
            if starved_s > 0 and free_at is not None and self._detail.station_state:
                self._emit_state(station_id, free_at, "STARVED")
            arrived_at = float(self._env.now)
            unit.seq += 1
            # One generator for this unit's whole visit to this station. The
            # visit sequence is part of the key, so a unit that comes back
            # through a rework loop draws a fresh cycle rather than repeating
            # the one that sent it to the loop.
            rng = self._draw_for("station", station_id, unit.unit_id, unit.seq)
            self._emit_arrival(station_id, unit, arrived_at)

            if self._detail.station_state:
                self._emit_state(station_id, arrived_at, "RUNNING")
            self._emitter.emit(
                "CYCLE_START",
                arrived_at,
                {
                    "variant_id": unit.variant_id,
                    "shift_id": self._shift_id(arrived_at),
                    "operator_group": self._operator_group(arrived_at),
                },
                station_id=station_id,
                unit_id=unit.unit_id,
            )
            cycle_s, down_s = yield from self._process(station_id, rng, unit)
            work_ended_at = float(self._env.now)
            self._emitter.emit(
                "CYCLE_END",
                work_ended_at,
                {
                    "variant_id": unit.variant_id,
                    "shift_id": self._shift_id(work_ended_at),
                    "cycle_time_s": round(cycle_s, 3),
                    "operator_group": self._operator_group(work_ended_at),
                },
                station_id=station_id,
                unit_id=unit.unit_id,
            )
            self._emit_process_values(station_id, unit, rng, work_ended_at)
            self._emit_manual_check(station_id, unit, rng, work_ended_at)

            hand_off = self._hand_off(station_id, unit, work_ended_at)
            if hand_off.store_index is not None:
                yield self._links[hand_off.store_index].slots.put(1)
                self._env.process(self._deliver(hand_off.store_index, unit))
                self._record_buffer(hand_off.store_index)
            departed_at = float(self._env.now)
            # The state word says blocked only if the station actually waited.
            # Reporting it on every hand-off would put a blocked reading and a
            # departure on the same timestamp, and a reader with no way to order
            # the two would see a station that never recovers.
            if self._detail.station_state and departed_at > work_ended_at:
                self._emit_state(station_id, work_ended_at, "BLOCKED")
            blocked_s = self._calendar.production_between(work_ended_at, departed_at)
            self._emitter.emit(
                "UNIT_DEPART",
                departed_at,
                {"variant_id": unit.variant_id},
                station_id=station_id,
                unit_id=unit.unit_id,
            )
            self._truth.visits.append(
                VisitTruth(
                    line_id=self._line.line_id,
                    unit_id=unit.unit_id,
                    station_id=station_id,
                    seq=unit.seq,
                    variant_id=unit.variant_id,
                    shift_id=self._shift_id(arrived_at) or "",
                    arrived_at_s=arrived_at,
                    work_started_at_s=arrived_at,
                    work_ended_at_s=work_ended_at,
                    departed_at_s=departed_at,
                    cycle_time_s=cycle_s,
                    blocked_s=blocked_s,
                    queued_before_s=queued_s,
                    starved_before_s=starved_s,
                    down_s=down_s,
                    is_dark=station.tier == "C",
                )
            )
            if hand_off.leaves_line:
                self._finish(unit, departed_at)
            free_at = departed_at

    def _elapse(self, production_s: float) -> Process:
        """Spend an amount of production time, pausing across shift breaks."""
        now = float(self._env.now)
        until = self._calendar.advance(now, production_s)
        if until > now:
            yield self._env.timeout(until - now)

    def _process(
        self, station_id: str, rng: np.random.Generator, unit: Unit
    ) -> Generator[Any, None, tuple[float, float]]:
        """Work on a unit, interrupted by any failure that happens during it.

        Returns the true cycle time and the repair time inside it, both in
        production seconds.
        """
        started_at = float(self._env.now)
        duration = self._draw_cycle(station_id, unit, rng, started_at)
        mtbf = self._plant.mtbf_of(station_id)
        mttr_median = self._plant.mttr_median_of(station_id)
        mttr_sigma = self._plant.station_defaults.mttr_sigma
        remaining = duration
        down_s = 0.0
        while True:
            time_to_failure = float(rng.exponential(mtbf))
            if time_to_failure >= remaining:
                yield from self._elapse(remaining)
                break
            yield from self._elapse(time_to_failure)
            remaining -= time_to_failure
            repair_s = float(
                rng.lognormal(mean=math.log(mttr_median), sigma=mttr_sigma)
            )
            if self._detail.station_state:
                self._emit_state(station_id, float(self._env.now), "DOWN")
            yield from self._elapse(repair_s)
            down_s += repair_s
            if self._detail.station_state:
                self._emit_state(station_id, float(self._env.now), "RUNNING")
        self._record_deviation(station_id, unit, duration)
        return duration + down_s, down_s

    def _draw_cycle(
        self, station_id: str, unit: Unit, rng: np.random.Generator, at_s: float
    ) -> float:
        """Draw one processing time, before any failure is added to it."""
        parameters = self._plant.station(station_id)
        zone = self._plant.zone(self._zone_of[station_id])
        median = (
            parameters.base_cycle_s
            * zone.variant_cycle_factor[unit.variant_id]
            * self._scenario.cycle_scale(station_id, at_s)
        )
        spread = self._plant.cycle_cv_of(
            station_id
        ) * self._scenario.cycle_spread_scale(station_id, at_s)
        # Lognormal, because a cycle time is positive and its long tail is a
        # recovered fumble rather than a symmetric error.
        sigma = math.sqrt(math.log(1.0 + spread * spread))
        return float(rng.lognormal(mean=math.log(median), sigma=sigma))

    def _record_deviation(self, station_id: str, unit: Unit, duration: float) -> None:
        parameters = self._plant.station(station_id)
        zone = self._plant.zone(self._zone_of[station_id])
        nominal = parameters.base_cycle_s * zone.variant_cycle_factor[unit.variant_id]
        spread = nominal * self._plant.cycle_cv_of(station_id)
        unit.deviation[station_id] = (duration - nominal) / spread
        excess = self._humidity[zone.zone_id] - zone.humidity_pct
        previous = unit.humidity_excess.get(zone.zone_id, 0.0)
        unit.humidity_excess[zone.zone_id] = max(previous, excess)

    def _transport(self, rng: np.random.Generator, nominal_s: float) -> float:
        """Draw an actual transport time around the nominal one."""
        return max(
            0.0,
            float(rng.normal(nominal_s, nominal_s * self._plant.transport_cv)),
        )

    # -- routing ---------------------------------------------------------

    def _hand_off(self, station_id: str, unit: Unit, at_s: float) -> HandOff:
        """Where the unit goes next once the station has finished with it."""
        gate = self._gate_after.get(station_id)
        if gate is not None and not self._inspect(gate.gate_id, unit, at_s):
            return self._after_failure(gate.gate_id, unit)
        index = self._index_of[station_id]
        if index + 1 < len(self._links):
            return HandOff(store_index=index + 1, leaves_line=False)
        return HandOff(store_index=None, leaves_line=True)

    def _after_failure(self, gate_id: str, unit: Unit) -> HandOff:
        """What happens to a unit a gate has just failed.

        A unit going back for rework is lifted off the line and re-inserted when
        there is room upstream, which is what a plant does and which is also the
        only arrangement that cannot deadlock: a station holding a unit while it
        waits for a slot behind itself would be waiting on its own output.
        """
        destination = self._rework_to.get(gate_id)
        if destination is None:
            unit.status = "SCRAPPED"
            return HandOff(store_index=None, leaves_line=True)
        if destination == OFF_LINE:
            # A repair yard the twin cannot see. It says so rather than
            # modelling a place it has no data from.
            unit.status = "HELD"
            return HandOff(store_index=None, leaves_line=True)
        unit.rework_passes += 1
        if unit.rework_passes > self._plant.max_rework_passes:
            unit.status = "SCRAPPED"
            return HandOff(store_index=None, leaves_line=True)
        unit.status = "REWORK"
        self._env.process(self._reinsert(self._index_of[destination], unit))
        return HandOff(store_index=None, leaves_line=False)

    def _reinsert(self, store_index: int, unit: Unit) -> Process:
        """Put a reworked unit back on the line when a slot opens upstream."""
        yield self._links[store_index].slots.put(1)
        self._env.process(self._deliver(store_index, unit))
        # Back in process. The pass count is what records that it was reworked,
        # and it is a feature of the defect model rather than a terminal state.
        unit.status = "IN_PROCESS"
        self._record_buffer(store_index)

    def _finish(self, unit: Unit, at_s: float) -> None:
        if unit.status == "IN_PROCESS":
            unit.status = "COMPLETED"
        self._completed += 1
        self._truth.units.append(
            UnitTruth(
                line_id=self._line.line_id,
                unit_id=unit.unit_id,
                variant_id=unit.variant_id,
                released_at_s=unit.released_at_s,
                completed_at_s=at_s,
                status=unit.status,
                rework_passes=unit.rework_passes,
                lots=tuple(unit.lots),
            )
        )

    # -- the gate model --------------------------------------------------

    def _inspect(self, gate_id: str, unit: Unit, at_s: float) -> bool:
        """Decide whether a unit passes a gate, and record why it did not."""
        parameters = self._plant.gate(gate_id)
        defects = self._plant.defects
        base = parameters.base_failure_rate
        odds = base / (1.0 - base) if base < 1.0 else float("inf")
        causes: dict[str, float] = {"base": odds}

        span = self._gate_span[gate_id]
        worst_station = ""
        worst_z = 0.0
        for station_id in span:
            deviation = unit.deviation.get(station_id, 0.0)
            if deviation > worst_z:
                worst_z, worst_station = deviation, station_id
        excess_z = max(0.0, worst_z - defects.cycle_deviation_threshold_sigma)
        if excess_z > 0:
            factor = defects.cycle_deviation_odds_per_sigma**excess_z
            odds *= factor
            causes[f"cycle at {worst_station}"] = factor

        for zone_id, excess in unit.humidity_excess.items():
            if excess <= 0 or not self._zone_touches(zone_id, span):
                continue
            factor = defects.humidity_odds_per_pct_above**excess
            odds *= factor
            causes[f"humidity in {zone_id}"] = factor

        for lot_id in unit.lots:
            factor = self._lot_factor(lot_id) * self._scenario.lot_odds_scale(
                lot_id, gate_id
            )
            odds *= factor
            causes[f"lot {lot_id}"] = factor

        if unit.rework_passes > 0:
            odds *= defects.rework_odds_multiplier
            causes["prior rework"] = defects.rework_odds_multiplier

        probability = odds / (1.0 + odds)
        rng = self._draw_for("gate", gate_id, unit.unit_id, unit.rework_passes)
        failed = bool(rng.random() < probability)
        defect_class = None
        if failed:
            catches = self._line.gates[
                [gate.gate_id for gate in self._line.gates].index(gate_id)
            ].catches
            defect_class = (
                str(catches[int(rng.integers(len(catches)))]) if catches else None
            )
        self._truth.gate_results.append(
            GateTruth(
                line_id=self._line.line_id,
                unit_id=unit.unit_id,
                gate_id=gate_id,
                at_s=at_s,
                passed=not failed,
                failure_probability=probability,
                defect_class=defect_class,
                cause_odds=causes,
            )
        )
        self._env.process(
            self._publish_verdict(gate_id, unit, not failed, defect_class)
        )
        return not failed

    def _zone_touches(self, zone_id: str, span: tuple[str, ...]) -> bool:
        return any(self._zone_of[station_id] == zone_id for station_id in span)

    def _lot_factor(self, lot_id: str) -> float:
        """A lot's own quality multiplier, drawn once and remembered."""
        known = self._lot_quality.get(lot_id)
        if known is not None:
            return known
        rng = generator_for(self._request.seed, "lot", lot_id)
        factor = float(
            rng.lognormal(mean=0.0, sigma=self._plant.defects.lot_quality_sigma)
        )
        self._lot_quality[lot_id] = factor
        return factor

    def _publish_verdict(
        self, gate_id: str, unit: Unit, passed: bool, defect_class: str | None
    ) -> Process:
        """Record the verdict after the latency a real inspection carries."""
        yield self._env.timeout(self._plant.gate_latency_s)
        gate = self._line.gates[
            [item.gate_id for item in self._line.gates].index(gate_id)
        ]
        self._emitter.emit(
            "INSPECTION_RESULT",
            float(self._env.now),
            {
                "gate_id": gate_id,
                "passed": passed,
                "defect_class": defect_class,
            },
            station_id=gate.after,
            unit_id=unit.unit_id,
        )

    # -- emission helpers ------------------------------------------------

    def _emit_arrival(self, station_id: str, unit: Unit, at_s: float) -> None:
        self._emitter.emit(
            "UNIT_ARRIVE",
            at_s,
            {"variant_id": unit.variant_id},
            station_id=station_id,
            unit_id=unit.unit_id,
        )
        material = self._material_at.get(station_id)
        if material is None:
            return
        lot_id = (
            f"{material.lot_prefix}-"
            f"{material.lot_start + unit.index // material.lot_size}"
        )
        if lot_id not in unit.lots:
            unit.lots.append(lot_id)
        self._emitter.emit(
            "PART_LOT_SCAN",
            at_s,
            {"lot_id": lot_id, "part": material.part},
            station_id=station_id,
            unit_id=unit.unit_id,
        )

    def _emit_state(self, station_id: str, at_s: float, state: str) -> None:
        self._emitter.emit(
            "STATION_STATE", at_s, {"state": state}, station_id=station_id
        )

    def _emit_process_values(
        self, station_id: str, unit: Unit, rng: np.random.Generator, at_s: float
    ) -> None:
        if not self._detail.process_values:
            return
        if not self._emitter.can_emit("PROCESS_VALUE", station_id):
            return
        deviation = unit.deviation.get(station_id, 0.0)
        for signal in self._plant.signals:
            coupled = signal.cycle_coupling * deviation
            independent = math.sqrt(
                max(0.0, 1.0 - signal.cycle_coupling * signal.cycle_coupling)
            )
            value = signal.nominal + signal.sd * (
                coupled + independent * float(rng.normal())
            )
            self._emitter.emit(
                "PROCESS_VALUE",
                at_s,
                {"signal": signal.name, "value": round(value, 4), "unit": signal.unit},
                station_id=station_id,
                unit_id=unit.unit_id,
            )

    def _emit_manual_check(
        self, station_id: str, unit: Unit, rng: np.random.Generator, at_s: float
    ) -> None:
        """A dark station's only record of the unit, filled in some time later."""
        if not self._emitter.can_emit("MANUAL_CHECK", station_id):
            return
        recorded_at = at_s + self._plant.manual_check_latency_s * float(
            rng.uniform(0.5, 1.5)
        )
        self._emitter.emit(
            "MANUAL_CHECK",
            recorded_at,
            {"check_id": f"{station_id}-checklist", "result": "PASS"},
            station_id=station_id,
            unit_id=unit.unit_id,
        )

    def _record_buffer(self, index: int) -> None:
        if not self._detail.buffer_levels:
            return
        link = self._links[index]
        if link.buffer_id is None:
            return
        self._truth.buffer_levels.append(
            BufferTruth(
                line_id=self._line.line_id,
                buffer_id=link.buffer_id,
                at_s=float(self._env.now),
                occupancy=link.occupancy,
            )
        )

    def _shift_id(self, at_s: float) -> str | None:
        return self._calendar.shift_at(at_s)

    def _operator_group(self, at_s: float) -> str | None:
        shift_id = self._calendar.shift_at(at_s)
        if shift_id is None:
            return None
        return self._plant.operator_group_by_shift.get(shift_id)


def run_simulation(request: SimulationRequest) -> SimulationResult:
    """Build and run one simulation."""
    return LineSimulation(request).run()
