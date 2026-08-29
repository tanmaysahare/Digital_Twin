"""The discrete-event forecast. T-050, T-051, T-052.

TECHNICAL_SPEC.md Section 5.1. The twin runs the line forward from its current
state, many times, and reports what share of those runs went badly and where.

Three things here decide whether the forecast is worth reading.

**The line is simulated, not extrapolated.** Blocking propagates upstream and
starving propagates downstream, and neither is a formula. A station that goes
over takt does not slow the line by its own excess: it slows it by that excess
less whatever the buffer in front of it absorbs, until the buffer fills and the
loss arrives all at once. Only a flow model produces that shape.

**Drifting stations are extrapolated, not frozen.** Where the drift detector
reports a sustained shift at station k with slope m, the forecast samples that
station's cycle time from its recent window shifted forward by `m * t`. Without
this the forecast predicts from the drifting station's historical distribution
and systematically under-predicts the stall, which is the whole of what SC-01
asks the twin to do. It is the single most important detail in this module, and
`with_drift_disabled` exists so that a test can hold the forecast against a
control with extrapolation off (T-052).

**A dark station is sampled from its bound, not from its midpoint.** Six of Line
2's stations have no cycle time, only an interval per passage. A replication
draws one of those intervals and then a point inside it, so the forecast's
spread widens where the twin cannot see. Collapsing the interval to a midpoint
would make the dark stretch look as well understood as the instrumented one,
which is the failure this product exists to prevent.

**On the kernel.** ARCHITECTURE.md Section 9 chose SimPy for the forecast. It is
what `plantsim` uses and it is right there, where fidelity matters more than
speed. It is not usable here, and the reason is measured rather than assumed:
`plantsim` runs about 1,300 station visits a second, and one replication over a
120 minute horizon is about 6,000 visits, so 200 replications would take some
15 minutes against the 20 second budget in NFR-01. This module is a hand-written
event recursion for a tandem line with finite links, which is the standard
formulation for blocking-after-service and is exact for the same model
`plantsim` assembles out of SimPy primitives. The deviation and its measurement
are recorded in TECHNICAL_SPEC.md Section 5.1.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field, replace

import numpy as np

from twin.config.line import LineDefinition
from twin.domain.seeds import generator_for
from twin.domain.shifts import ProductionCalendar

# The forecast reports on five-minute buckets. Short enough that a supervisor can
# act inside one, long enough that a single cycle's noise does not fill it.
BUCKET_S = 300.0

# The slot between two stations where the line definition places no buffer. Two
# stations on an assembly line always have one conveyor position between them,
# and modelling that position as zero capacity would block every station on
# every cycle.
CONVEYOR_SLOTS = 1

# How far past the horizon the release schedule is built. A forecast that ran out
# of units to release would report a quiet last bucket the line will not have.
HORIZON_MARGIN_S = 3600.0

# How many uniform draws a replication takes in one call. Drawing them one at a
# time costs more than the rest of the inner loop together.
_DRAW_BLOCK = 16384

_NEVER = -1.0e18


@dataclass(frozen=True)
class StationPlan:
    """How one station's cycle time is drawn in a replication.

    `pools` holds the empirical window per variant, resampled. `bounds` holds the
    intervals a dark station's passages were bounded to, per variant, and a draw
    picks an interval and then a point inside it. The empty-string key is the
    pooled fallback for a variant that has not been seen often enough yet.
    """

    station_id: str
    pools: dict[str, tuple[float, ...]] = field(default_factory=dict)
    bounds: dict[str, tuple[tuple[float, float], ...]] = field(default_factory=dict)
    # The rare interruptions this station is subject to, and how often. Held
    # apart from the pool because a rolling window misrepresents a rare heavy
    # tail by a factor of twenty-five either way. See `CycleDistribution.core`.
    rare: tuple[float, ...] = ()
    rare_rate: float = 0.0
    # Seconds of cycle time added per second of forecast horizon, from the drift
    # detector. Zero for a station that is not drifting.
    drift_slope_s_per_s: float = 0.0
    # Why the plan had to fall back to takt, if it did. Two very different
    # cases, and conflating them was worth a wall of false alarms.
    #
    # `LEARNING` is a station that has not yet produced enough cycles for a
    # baseline. It is temporary, it happens on every cold start and after every
    # new variant, and while it holds there is no flow model: blocking and
    # starving propagate the length of the line, so one station running at an
    # assumed takt rather than its real cycle makes every station's forecast
    # wrong. No stall is claimed at all until it clears (EC-20).
    #
    # `UNRESOLVABLE` is a station that will never have a baseline, because
    # nothing observes it and nothing can bound it. On Line 2 that is S42, which
    # is dark and last. Takt is the assumption the forecast carries for it, it is
    # a pessimistic one, and it is named in every forecast's evidence and in the
    # evidence pack rather than absorbed silently (STA-07).
    fallback_reason: str = ""

    @property
    def is_fallback(self) -> bool:
        """Whether this station is being run at takt rather than at its own rate."""
        return bool(self.fallback_reason)

    @property
    def is_learning(self) -> bool:
        """Whether the fallback will clear once more cycles arrive."""
        return self.fallback_reason == "LEARNING"

    @property
    def is_dark(self) -> bool:
        """Whether this station is sampled from bounds rather than from a pool."""
        return not self.pools and bool(self.bounds)


@dataclass(frozen=True)
class WarmUnit:
    """A unit already on the line when the forecast starts.

    `at_station_index` is where it is. `remaining_s` is what is left of its cycle
    where a station is working on it, and is ignored for a unit waiting on a link.
    """

    unit_id: str
    variant_id: str
    at_station_index: int
    remaining_s: float
    in_station: bool


@dataclass(frozen=True)
class ForecastSeed:
    """The line as the forecast starts from it. ARCHITECTURE.md Section 4."""

    line_id: str
    # Seconds from the production calendar's epoch. The forecast keeps the
    # calendar's clock so that a break inside the horizon pauses the line rather
    # than being forecast through (EC-11).
    at_s: float
    plans: tuple[StationPlan, ...]
    warm_units: tuple[WarmUnit, ...]
    # Occupancy of the link feeding each station, in station order. Index 0 is
    # the release point and is always empty.
    link_occupancy: tuple[int, ...]
    # What the schedule says is coming, in release order.
    upcoming_variants: tuple[str, ...]

    def plan(self, station_id: str) -> StationPlan:
        """One station's sampling plan."""
        for item in self.plans:
            if item.station_id == station_id:
                return item
        message = f"no forecast plan for station {station_id}"
        raise KeyError(message)

    def with_drift_disabled(self) -> ForecastSeed:
        """The same seed with every drift slope set to zero.

        The control for T-052. A forecast that does not differ measurably from
        this one is not extrapolating, whatever the code says.
        """
        return replace(
            self,
            plans=tuple(replace(item, drift_slope_s_per_s=0.0) for item in self.plans),
        )

    @property
    def drifting(self) -> tuple[str, ...]:
        """Every station the forecast is carrying a drift slope for."""
        return tuple(plan.station_id for plan in self.plans if plan.drift_slope_s_per_s)


@dataclass(frozen=True)
class Replication:
    """What one run of the line forward produced.

    Every array is stations by buckets, except `completed`, which is line level.
    """

    blocked_s: np.ndarray
    starved_s: np.ndarray
    link_occupancy: np.ndarray
    completed: np.ndarray

    @property
    def lost_s(self) -> np.ndarray:
        """Production seconds a station could not work, per bucket."""
        total: np.ndarray = self.blocked_s + self.starved_s
        return total


@dataclass(frozen=True)
class LineShape:
    """The immutable shape of the line, unpacked once for the inner loop."""

    order: tuple[str, ...]
    transport_s: tuple[float, ...]
    slots: tuple[int, ...]
    takt_s: float

    @property
    def size(self) -> int:
        """How many stations the line has."""
        return len(self.order)


def build_shape(line: LineDefinition) -> LineShape:
    """Unpack a line definition into the arrays the kernel walks.

    Plant-specific values stay in configuration; this only rearranges them
    (CLAUDE.md rule 5).
    """
    capacity_after = {item.after: item.capacity for item in line.buffers}
    slots = [CONVEYOR_SLOTS]
    for station in line.stations[:-1]:
        slots.append(capacity_after.get(station.station_id, CONVEYOR_SLOTS))
    return LineShape(
        order=line.station_ids,
        transport_s=tuple(
            station.transport_to_next_s or 0.0 for station in line.stations
        ),
        slots=tuple(slots),
        takt_s=line.takt_s,
    )


class _Clock:
    """The production calendar, flattened to the windows the horizon touches.

    `ProductionCalendar.advance` searches and loops, and the inner loop calls it
    once per station visit, which is about a million calls in a full forecast.
    The windows over a two hour horizon are a handful, so a linear walk over a
    tuple is both simpler and two orders of magnitude faster. The answers are the
    same and a test asserts that they are.
    """

    def __init__(
        self, calendar: ProductionCalendar, start_s: float, end_s: float
    ) -> None:
        """Take the windows that overlap one span of the calendar."""
        windows = [
            (window.start_s, window.end_s)
            for window in calendar.windows_until(end_s)
            if window.end_s > start_s
        ]
        self._windows = tuple(windows)
        self._continuous = (
            len(self._windows) == 1
            and self._windows[0][0] <= start_s
            and self._windows[0][1] >= end_s
        )

    @property
    def is_continuous(self) -> bool:
        """Whether the line runs without a break for the whole span."""
        return self._continuous

    def producing(self, start_s: float, end_s: float) -> float:
        """How many production seconds lie between two instants.

        A station waiting through a shift break is not starved, it is off shift,
        and charging that time to it would make every break a line-wide stall
        (EC-11). Every duration the kernel records goes through here.
        """
        if end_s <= start_s:
            return 0.0
        if self._continuous:
            return end_s - start_s
        total = 0.0
        for window_start, window_end in self._windows:
            overlap = min(window_end, end_s) - max(window_start, start_s)
            if overlap > 0:
                total += overlap
        return total

    def advance(self, at_s: float, production_s: float) -> float:
        """The instant at which an amount of production time has elapsed."""
        if self._continuous:
            return at_s + production_s
        remaining = production_s
        now = at_s
        for start_s, end_s in self._windows:
            if end_s <= now:
                continue
            now = max(now, start_s)
            available = end_s - now
            if remaining <= available:
                return now + remaining
            remaining -= available
            now = end_s
        return now + remaining


class _Sampler:
    """Draws cycle times for one replication from one seeded generator.

    Every draw a replication will need is generated up front, per station and per
    variant, in one call each. Drawing one value at a time cost more than the rest
    of the inner loop put together, and the stream a bulk call yields is the same
    stream the generator would have produced value by value, so determinism is
    unaffected (NFR-07).
    """

    def __init__(
        self,
        plans: tuple[StationPlan, ...],
        variants: tuple[str, ...],
        takt_s: float,
        origin_s: float,
        rng: np.random.Generator,
        size: int,
        *,
        extrapolate: bool,
    ) -> None:
        """Pre-draw one replication's cycle times."""
        self._origin_s = origin_s
        self._extrapolate = extrapolate
        self._slopes = [plan.drift_slope_s_per_s for plan in plans]
        self._draws: list[list[list[float]]] = []
        self._cursors: list[list[int]] = []
        for plan in plans:
            per_variant: list[list[float]] = []
            for variant_id in variants:
                per_variant.append(_prepare(plan, variant_id, takt_s, rng, size))
            self._draws.append(per_variant)
            self._cursors.append([0] * len(variants))

    def draw(self, index: int, variant: int, at_s: float) -> float:
        """One cycle time at one station, for one variant, at one instant."""
        cursors = self._cursors[index]
        position = cursors[variant]
        values = self._draws[index][variant]
        if position >= len(values):
            # The horizon held more units than the plan allowed for, which
            # happens when the line runs faster than takt. Wrapping reuses the
            # same seeded draws rather than reaching for an unseeded one.
            position = 0
        cursors[variant] = position + 1
        base = values[position]
        if self._extrapolate:
            slope = self._slopes[index]
            if slope:
                # The window shifted forward by the estimated slope. The drift
                # has been running since before the forecast started, so the
                # shift is measured from the forecast origin and the detector's
                # onset is already inside the window the pool came from.
                elapsed = at_s - self._origin_s
                if elapsed > 0.0:
                    base += slope * elapsed
                    return base if base > 0.0 else 0.0
        return base


def _prepare(
    plan: StationPlan,
    variant_id: str,
    takt_s: float,
    rng: np.random.Generator,
    size: int,
) -> list[float]:
    """Every cycle time one station will need for one variant, drawn at once."""
    pool = plan.pools.get(variant_id) or plan.pools.get("")
    if pool:
        values = np.asarray(pool, dtype=float)
        drawn = values[rng.integers(0, values.shape[0], size)]
        if plan.rare and plan.rare_rate > 0.0:
            # The rare component, at the rate the station's whole history says
            # rather than the rate this window happens to show.
            rare = np.asarray(plan.rare, dtype=float)
            struck = rng.random(size) < plan.rare_rate
            if struck.any():
                picks = rare[rng.integers(0, rare.shape[0], int(struck.sum()))]
                drawn = drawn.copy()
                drawn[struck] = picks
        drawn_list: list[float] = drawn.tolist()
        return drawn_list
    bounds = plan.bounds.get(variant_id) or plan.bounds.get("")
    if bounds:
        pairs = np.asarray(bounds, dtype=float)
        chosen = pairs[rng.integers(0, pairs.shape[0], size)]
        low = chosen[:, 0]
        # One position inside the bound for the whole replication, not one per
        # unit. The width of a dark station's bound is what the twin does not
        # know about that station, and it is the same station all afternoon: it
        # is not a station whose cycle time swings across that range from unit to
        # unit. Drawing a fresh point per unit turns the twin's uncertainty into
        # the line's variability, and queueing is convex in variability, so the
        # forecast manufactures congestion inside the dark run that the real line
        # does not have. Measured on Line 2 it predicted about 170 seconds lost
        # per five-minute bucket at each of S33 to S37, on a line where those
        # stations were running perfectly well.
        #
        # Drawing the position once per replication is the right treatment: the
        # spread of the bound comes out as spread across replications, which is
        # where uncertainty belongs, rather than as spread within one.
        position = float(rng.random())
        spread: list[float] = (low + (chosen[:, 1] - low) * position).tolist()
        return spread
    # Nothing usable at all. Takt is the only honest placeholder, and the plan
    # carries `is_fallback` so the forecast is marked degraded and names the
    # station (EC-20).
    return [takt_s] * size


def _bucket_of(at_s: float, origin_s: float, buckets: int) -> int:
    """Which five-minute bucket an instant falls in, clamped to the horizon."""
    bucket = int((at_s - origin_s) // BUCKET_S)
    if bucket < 0:
        return 0
    if bucket >= buckets:
        return buckets - 1
    return bucket


def _spread(
    grid: list[list[float]],
    index: int,
    origin_s: float,
    start_s: float,
    end_s: float,
    clock: _Clock,
    buckets: int,
) -> None:
    """Add an episode's production seconds to the buckets it falls in.

    Two things happen here and both matter. An episode that straddles a bucket
    boundary is split between the buckets in proportion, because charging all of
    it to one would put a stall in a bucket where the line was running. And every
    part of it is measured in production seconds, because a station waiting
    through a shift break is off shift rather than starved, and a forecast that
    counted breaks would predict a line-wide stall at every lunch (EC-11).

    The accumulator is a list of lists rather than an array. One indexed
    increment into a NumPy array costs more than several station visits, and this
    runs twice a visit some thousands of times a replication. The arrays are
    built once at the end.
    """
    row = grid[index]
    first = _bucket_of(start_s, origin_s, buckets)
    last = _bucket_of(end_s, origin_s, buckets)
    if first == last:
        row[first] += clock.producing(start_s, end_s)
        return
    for bucket in range(first, last + 1):
        edge_lo = origin_s + bucket * BUCKET_S
        edge_hi = edge_lo + BUCKET_S
        overlap_lo = start_s if start_s > edge_lo else edge_lo
        overlap_hi = end_s if end_s < edge_hi else edge_hi
        if overlap_hi > overlap_lo:
            row[bucket] += clock.producing(overlap_lo, overlap_hi)


@dataclass(frozen=True)
class _Entry:
    """One unit as the kernel takes it up, and where it starts from.

    `variant` is an index into the seed's variant table rather than the
    identifier itself, so the inner loop indexes a list instead of hashing a
    string several thousand times a replication.
    """

    station_index: int
    available_at_s: float
    remaining_s: float
    variant: int
    in_station: bool


def _entry_queue(
    seed: ForecastSeed,
    shape: LineShape,
    clock: _Clock,
    horizon_s: float,
    variants: tuple[str, ...],
) -> list[_Entry]:
    """Every unit the forecast walks, in the order it will traverse the line.

    Warm units first, from the end of the line backwards, because the unit
    nearest the exit is ahead of every other unit everywhere it still has to go.
    A unit inside a station comes before the units waiting on the link that feeds
    that station, for the same reason. Then the release schedule, at takt, paused
    across breaks.
    """
    origin = seed.at_s
    index_of = {variant_id: position for position, variant_id in enumerate(variants)}
    fallback = index_of.get("", 0)
    warm = sorted(
        seed.warm_units,
        key=lambda unit: (-unit.at_station_index, not unit.in_station),
    )
    queue = [
        _Entry(
            station_index=unit.at_station_index,
            available_at_s=origin,
            remaining_s=max(0.0, unit.remaining_s) if unit.in_station else 0.0,
            variant=index_of.get(unit.variant_id, fallback),
            in_station=unit.in_station,
        )
        for unit in warm
    ]
    upcoming = seed.upcoming_variants or ("",)
    releases = int((horizon_s + HORIZON_MARGIN_S) / shape.takt_s) + 1
    for position in range(releases):
        queue.append(
            _Entry(
                station_index=0,
                available_at_s=clock.advance(origin, position * shape.takt_s),
                remaining_s=0.0,
                variant=index_of.get(upcoming[position % len(upcoming)], fallback),
                in_station=False,
            )
        )
    return queue


def variant_table(seed: ForecastSeed) -> tuple[str, ...]:
    """Every variant the forecast might see, with the pooled fallback last.

    The empty identifier is the pool across variants, which is what a warm unit
    on a link is drawn from: the twin knows a unit is between two stations
    without knowing which variant it is.
    """
    found: list[str] = []
    for variant_id in (
        *seed.upcoming_variants,
        *(unit.variant_id for unit in seed.warm_units),
    ):
        if variant_id and variant_id not in found:
            found.append(variant_id)
    found.append("")
    return tuple(found)


def simulate_once(
    shape: LineShape,
    seed: ForecastSeed,
    clock: _Clock,
    rng: np.random.Generator,
    horizon_s: float,
    *,
    extrapolate: bool = True,
) -> Replication:
    """Run the line forward once.

    The tandem-line recursion. Units are walked in the order they traverse the
    line, and each is carried from where it is to the end of the line before the
    next is taken up. Every quantity a unit needs from an earlier unit is
    therefore already computed, which is what makes a recursion valid here and an
    event queue unnecessary.
    """
    stations = shape.size
    buckets = max(1, math.ceil(horizon_s / BUCKET_S))
    origin = seed.at_s
    horizon_end = origin + horizon_s

    blocked = [[0.0] * buckets for _ in range(stations)]
    starved = [[0.0] * buckets for _ in range(stations)]
    occupancy = [[0.0] * buckets for _ in range(stations)]
    completed = [0.0] * buckets

    variants = variant_table(seed)
    queue = _entry_queue(seed, shape, clock, horizon_s, variants)
    sampler = _Sampler(
        seed.plans,
        variants,
        shape.takt_s,
        origin,
        rng,
        len(queue) + 8,
        extrapolate=extrapolate,
    )
    draw = sampler.draw
    advance = clock.advance
    producing = clock.producing
    # When each station last handed a unit on, which is when it began waiting.
    last_depart = [origin] * stations
    # The instants each station took each unit off the link in front of it. This
    # is when the slot that unit occupied was released, and it is the only thing
    # the blocking constraint needs.
    taken: list[list[float]] = [[] for _ in range(stations)]
    # How many units have been put onto each link, the warm ones included.
    put = list(seed.link_occupancy)
    level = list(seed.link_occupancy)
    transport = shape.transport_s
    slots = shape.slots
    final = stations - 1
    edge = buckets - 1

    for entry in queue:
        moment = entry.available_at_s
        index = entry.station_index
        remaining = entry.remaining_s
        inside = entry.in_station
        variant = entry.variant
        while index <= final:
            previous_depart = last_depart[index]
            start = moment if moment > previous_depart else previous_depart
            if start >= horizon_end:
                break
            if start > previous_depart:
                _spread(starved, index, origin, previous_depart, start, clock, buckets)
            if inside:
                # Already inside the station at the forecast origin. It never
                # occupied a slot on the link in front of this station after t0,
                # so it is not counted against that link.
                duration = remaining
                inside = False
            else:
                duration = draw(index, variant, start)
                taken[index].append(start)
                if level[index] > 0:
                    level[index] -= 1
                bucket = int((start - origin) // BUCKET_S)
                occupancy[index][edge if bucket > edge else bucket] = float(
                    level[index]
                )
            work_ended = advance(start, duration)

            if index < final:
                after = index + 1
                ahead = put[after]
                capacity = slots[after]
                depart = work_ended
                if ahead >= capacity:
                    position = ahead - capacity
                    if len(taken[after]) > position:
                        slot_free = taken[after][position]
                        depart = max(depart, slot_free)
                put[after] = ahead + 1
                level[after] += 1
                bucket = int((depart - origin) // BUCKET_S)
                occupancy[after][edge if bucket > edge else bucket] = float(
                    level[after]
                )
            else:
                depart = work_ended
                if depart < horizon_end:
                    bucket = int((depart - origin) // BUCKET_S)
                    completed[edge if bucket > edge else bucket] += 1.0

            if depart > work_ended:
                first = _bucket_of(work_ended, origin, buckets)
                last = _bucket_of(depart, origin, buckets)
                if first == last:
                    blocked[index][first] += producing(work_ended, depart)
                else:
                    _spread(blocked, index, origin, work_ended, depart, clock, buckets)
            last_depart[index] = depart
            moment = depart + transport[index]
            index += 1

    return Replication(
        blocked_s=np.asarray(blocked),
        starved_s=np.asarray(starved),
        link_occupancy=np.asarray(occupancy),
        completed=np.asarray(completed),
    )


@dataclass(frozen=True)
class ForecastRun:
    """Every replication of one forecast, before aggregation."""

    seed: ForecastSeed
    horizon_s: float
    replications: tuple[Replication, ...]
    runtime_s: float
    # True where the budget forced a reduction, which the interface states.
    degraded: bool = False
    fallback_stations: tuple[str, ...] = ()
    learning_stations: tuple[str, ...] = ()

    @property
    def is_forecastable(self) -> bool:
        """Whether the flow model rests on a baseline at every station. EC-20."""
        return not self.learning_stations

    @property
    def buckets(self) -> int:
        """How many five-minute buckets the horizon holds."""
        return int(self.replications[0].blocked_s.shape[1])

    @property
    def count(self) -> int:
        """How many replications ran."""
        return len(self.replications)


@dataclass
class Forecaster:
    """Runs the line forward R times from a seeded state. T-050, T-051."""

    line: LineDefinition
    calendar: ProductionCalendar
    _shape: LineShape = field(init=False)

    def __post_init__(self) -> None:
        """Unpack the line once, since every replication walks the same shape."""
        self._shape = build_shape(self.line)

    @property
    def shape(self) -> LineShape:
        """The unpacked line, for callers that need its slot capacities."""
        return self._shape

    def run(
        self,
        seed: ForecastSeed,
        cycle_id: str,
        *,
        replications: int | None = None,
        horizon_s: float | None = None,
        extrapolate: bool = True,
    ) -> ForecastRun:
        """Run R replications from one state.

        Args:
            seed: the line as the forecast starts from it.
            cycle_id: identifies this forecast cycle. Every draw in replication
                `r` comes from a generator seeded on `(cycle_id, r)`, so the whole
                forecast is reproducible on another machine (NFR-07).
            replications: how many runs. Defaults to the line's own policy.
            horizon_s: how far forward. Defaults to the line's own policy.
            extrapolate: whether drifting stations are carried forward. False is
                the control for T-052 and is never used in production.

        Returns:
            Every replication, unaggregated. `aggregate.py` turns them into the
            probabilities the interface reads.
        """
        count = replications or self.line.forecast.replications
        span = horizon_s or self.line.forecast.horizon_min * 60.0
        clock = _Clock(self.calendar, seed.at_s, seed.at_s + span + HORIZON_MARGIN_S)
        started = time.monotonic()
        runs = tuple(
            simulate_once(
                self._shape,
                seed,
                clock,
                generator_for(cycle_id, index),
                span,
                extrapolate=extrapolate,
            )
            for index in range(count)
        )
        return ForecastRun(
            seed=seed,
            horizon_s=span,
            replications=runs,
            runtime_s=time.monotonic() - started,
            degraded=count < self.line.forecast.replications,
            fallback_stations=tuple(
                plan.station_id for plan in seed.plans if plan.is_fallback
            ),
            learning_stations=tuple(
                plan.station_id for plan in seed.plans if plan.is_learning
            ),
        )
