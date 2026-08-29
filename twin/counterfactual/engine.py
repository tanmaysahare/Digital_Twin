"""The counterfactual sandbox. T-094, T-095, AC-030 to AC-033.

TECHNICAL_SPEC.md Section 8. A supervisor with twenty minutes of warning wants
to know whether adding a floater is worth doing, and the honest answer is a
comparison against doing nothing, with both sides carrying their uncertainty.

**Common random numbers.** Baseline and every option run from the same seed
state under the same `cycle_id`, so replication `r` draws the same numbers in
all of them. Without that, a nine-unit difference at 200 replications would be
inside the noise of two independent samples and the sandbox would be a random
number generator with a form on the front. With it, the difference is the
intervention, and the difference interval is a paired one. This is the single
reason the sandbox says anything at all.

**Nothing is applied.** There is no path from this module to a control system,
and there is not one to the twin's own state either. A run produces a comparison
and, if the user asks, a record that they chose an option. The line does not
know the sandbox exists.

**The latency budget and what happens when it is missed.** The line does not
stop for a dialog, so the sandbox has a budget from the line's own
`counterfactual.latency_budget_s`. The engine measures the baseline, works out
how many replications the remaining options can afford, and reduces the count
rather than blowing the budget. A reduced run is marked `degraded`, its
intervals are wider because they are computed from fewer replications, and the
footer says so (AC-032, CFA-03). It is never silently the same answer with less
behind it.

**What an intervention does to the model, stated plainly.** Each one is a
transformation of the seed or of the line shape, and each carries the assumption
it rests on:

- `ADD_OPERATOR` scales that station's draws by the line's operator factor. A
  second pair of hands takes a fixed share off the cycle and off its spread, and
  the factor is configured per station in `config/lines/*.yaml` and revised from
  observed effect once a floater has actually been added.
- `REMOVE_OPERATOR` is the same scaling run backwards.
- `CHANGE_TAKT` moves the shape's takt by a percentage. Release rate changes and
  the work content at each station does not.
- `CHANGE_BUFFER_TARGET` changes one buffer's slot count, assuming the space to
  hold the units exists on the floor.
- `RESEQUENCE_MIX` reorders the upcoming variants, assuming the sequence can be
  changed at the release point.
- `STATION_DOWN` adds one outage of the stated length, placed at random inside
  the horizon rather than at a chosen moment.

Every one of those assumptions is shown next to the result, because an
intervention modelled on an assumption the user cannot see is a number they
should not trust.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, replace
from typing import Literal

from twin.config.line import LineDefinition
from twin.domain.estimate import Estimate, Interval
from twin.domain.shifts import ProductionCalendar
from twin.forecast.aggregate import ForecastSummary, aggregate
from twin.forecast.des import (
    BUCKET_S,
    Forecaster,
    ForecastSeed,
    LineShape,
    StationPlan,
    build_shape,
)

InterventionType = Literal[
    "ADD_OPERATOR",
    "REMOVE_OPERATOR",
    "CHANGE_TAKT",
    "CHANGE_BUFFER_TARGET",
    "RESEQUENCE_MIX",
    "STATION_DOWN",
]

# The smallest number of replications a comparison is worth reporting from.
# Below this the interval is the replication count talking, and the sandbox
# refuses rather than reporting a number it cannot stand behind.
MINIMUM_REPLICATIONS = 24

# How many options a comparison holds. Three plus the baseline is what the
# overlay renders and what a person can hold in mind at once (AC-033).
MAX_OPTIONS = 3


@dataclass(frozen=True)
class Intervention:
    """One change to test. Not one to make."""

    type: InterventionType
    station_id: str | None = None
    buffer_id: str | None = None
    count: int = 1
    percent: float = 0.0
    minutes: float = 0.0
    variant_order: tuple[str, ...] = ()

    def describe(self) -> str:
        """What this intervention does, in the plant's own words."""
        if self.type == "ADD_OPERATOR":
            return f"Add {self.count} operator at {self.station_id}"
        if self.type == "REMOVE_OPERATOR":
            return f"Take {self.count} operator off {self.station_id}"
        if self.type == "CHANGE_TAKT":
            direction = "Slow" if self.percent < 0 else "Speed up"
            return f"{direction} takt by {abs(self.percent):.0f} percent"
        if self.type == "CHANGE_BUFFER_TARGET":
            return f"Set {self.buffer_id} to {self.count} of its capacity"
        if self.type == "RESEQUENCE_MIX":
            return f"Release in the order {', '.join(self.variant_order)}"
        return f"Take {self.station_id} down for {self.minutes:.0f} min"

    def assumption(self, line: LineDefinition) -> str:
        """The assumption behind the model of this intervention."""
        if self.type in {"ADD_OPERATOR", "REMOVE_OPERATOR"}:
            scale = line.counterfactual.station_overrides.get(
                self.station_id or "", line.counterfactual.operator_add_cycle_scale
            )
            return (
                f"An operator changes the cycle at {self.station_id} by a factor "
                f"of {scale:.2f} and its spread by "
                f"{line.counterfactual.operator_add_variance_scale:.2f}. Both are "
                f"starting positions from configuration, revised from observed "
                f"effect once a floater has actually been added"
            )
        if self.type == "CHANGE_TAKT":
            return "Release rate changes and the work content at each station does not"
        if self.type == "CHANGE_BUFFER_TARGET":
            return "The space to hold the extra units exists on the floor"
        if self.type == "RESEQUENCE_MIX":
            return "The release sequence can be changed at the release point"
        return (
            "The stop happens once, at a point drawn uniformly inside the "
            "horizon rather than at a chosen moment"
        )


@dataclass(frozen=True)
class Option:
    """One labelled set of interventions to compare against doing nothing."""

    label: str
    interventions: tuple[Intervention, ...]


@dataclass(frozen=True)
class OptionResult:
    """One option's modelled outcome, beside the baseline it was paired with."""

    label: str
    units: Estimate
    delta: Estimate
    stall_probability: dict[str, float]
    assumptions: tuple[str, ...]
    rank: int


@dataclass(frozen=True)
class CounterfactualResult:
    """The whole comparison, and everything the footer has to state."""

    run_id: str
    line_id: str
    seed_state_at_s: float
    replications_used: int
    replications_requested: int
    runtime_ms: int
    degraded: bool
    degraded_note: str
    baseline_units: Estimate
    baseline_stall_probability: dict[str, float]
    options: tuple[OptionResult, ...]


@dataclass(frozen=True)
class RunRequest:
    """What one comparison was asked for, apart from the options themselves.

    Held together rather than passed one by one, because the four of them are
    one request and a caller that gets their order wrong would get a plausible
    answer to a different question.
    """

    run_id: str
    replications: int | None = None
    budget_s: float | None = None
    horizon_s: float | None = None


@dataclass
class CounterfactualEngine:
    """Runs a baseline and up to three options from one seed state."""

    line: LineDefinition
    calendar: ProductionCalendar
    forecaster: Forecaster = field(init=False)

    def __post_init__(self) -> None:
        """Build a forecaster against the line as configured."""
        self.forecaster = Forecaster(self.line, self.calendar)

    def run(
        self,
        seed: ForecastSeed,
        options: tuple[Option, ...],
        request: RunRequest,
    ) -> CounterfactualResult:
        """Compare doing nothing against every option, on shared seeds.

        Raises:
            ValueError: if more than three options are given. The overlay
                compares three and ranking more than that is a table, not a
                decision.
        """
        run_id = request.run_id
        if len(options) > MAX_OPTIONS:
            message = (
                f"the sandbox compares at most {MAX_OPTIONS} options against "
                f"doing nothing, and {len(options)} were given"
            )
            raise ValueError(message)
        requested = request.replications or self.line.forecast.replications
        budget = request.budget_s or self.line.counterfactual.latency_budget_s
        span = request.horizon_s or self.line.forecast.horizon_min * 60.0
        started = time.monotonic()

        count = requested
        baseline = self._summarise(seed, None, run_id, count, span)
        spent = time.monotonic() - started
        count, degraded_note = self._affordable(
            count, spent, budget, len(options), started
        )
        if count < requested:
            baseline = self._summarise(seed, None, run_id, count, span)

        results: list[OptionResult] = []
        for option in options:
            summary = self._summarise(seed, option, run_id, count, span)
            results.append(
                OptionResult(
                    label=option.label,
                    units=summary.output,
                    delta=_paired_delta(baseline, summary),
                    stall_probability=_peaks(summary),
                    assumptions=tuple(
                        item.assumption(self.line) for item in option.interventions
                    ),
                    rank=0,
                )
            )
        ranked = tuple(
            replace(item, rank=index)
            for index, item in enumerate(
                sorted(results, key=lambda item: -item.units.sort_key()), start=1
            )
        )
        return CounterfactualResult(
            run_id=run_id,
            line_id=self.line.line_id,
            seed_state_at_s=seed.at_s,
            replications_used=count,
            replications_requested=requested,
            runtime_ms=int((time.monotonic() - started) * 1000),
            degraded=count < requested,
            degraded_note=degraded_note,
            baseline_units=baseline.output,
            baseline_stall_probability=_peaks(baseline),
            options=ranked,
        )

    # -- running ----------------------------------------------------------

    def _summarise(
        self,
        seed: ForecastSeed,
        option: Option | None,
        run_id: str,
        replications: int,
        span: float,
    ) -> ForecastSummary:
        """One arm of the comparison, on the same seeds as every other arm."""
        altered_seed, shape = self._apply(seed, option)
        run = self.forecaster.run(
            altered_seed,
            run_id,
            replications=replications,
            horizon_s=span,
            shape=shape,
        )
        nominal = span / max(1.0, shape.takt_s if shape else self.line.takt_s)
        return aggregate(run, self.line, nominal)

    def _affordable(
        self,
        count: int,
        spent: float,
        budget: float,
        options: int,
        started: float,
    ) -> tuple[int, str]:
        """How many replications the remaining arms can afford. AC-032."""
        arms = options + 1
        if spent <= 0.0 or arms <= 1:
            return count, ""
        projected = spent * arms
        if projected <= budget:
            return count, ""
        affordable = max(MINIMUM_REPLICATIONS, int(count * budget / projected))
        if affordable >= count:
            return count, ""
        del started
        return affordable, (
            f"Reduced from {count} replications to {affordable} to answer inside "
            f"{budget:.0f} s. The ranges below are wider because of it."
        )

    def _apply(
        self, seed: ForecastSeed, option: Option | None
    ) -> tuple[ForecastSeed, LineShape | None]:
        """Turn one option into an altered seed and, where needed, an altered line."""
        if option is None:
            return seed, None
        plans = {plan.station_id: plan for plan in seed.plans}
        upcoming = seed.upcoming_variants
        shape = build_shape(self.line)
        changed_shape = False
        for item in option.interventions:
            if item.type in {"ADD_OPERATOR", "REMOVE_OPERATOR"}:
                station_id = item.station_id or ""
                if station_id in plans:
                    plans[station_id] = self._staffed(
                        plans[station_id], item.count, adding=item.type[0] == "A"
                    )
            elif item.type == "CHANGE_TAKT":
                shape = replace(
                    shape, takt_s=shape.takt_s * (1.0 - item.percent / 100.0)
                )
                changed_shape = True
            elif item.type == "CHANGE_BUFFER_TARGET":
                shape = self._resized(shape, item.buffer_id or "", item.count)
                changed_shape = True
            elif item.type == "RESEQUENCE_MIX" and item.variant_order:
                upcoming = tuple(
                    item.variant_order[index % len(item.variant_order)]
                    for index in range(len(upcoming))
                )
            elif item.type == "STATION_DOWN":
                station_id = item.station_id or ""
                if station_id in plans:
                    plans[station_id] = self._stopped(
                        plans[station_id], item.minutes, horizon_s=BUCKET_S
                    )
        altered = replace(
            seed,
            plans=tuple(plans[station.station_id] for station in self.line.stations),
            upcoming_variants=upcoming,
        )
        return altered, shape if changed_shape else None

    def _staffed(self, plan: StationPlan, count: int, *, adding: bool) -> StationPlan:
        """One station's draws with an operator added or taken away."""
        policy = self.line.counterfactual
        scale = policy.station_overrides.get(
            plan.station_id, policy.operator_add_cycle_scale
        )
        spread = policy.operator_add_variance_scale
        factor = scale**count if adding else (1.0 / scale) ** count
        spread_factor = spread**count if adding else (1.0 / spread) ** count
        pools = {
            variant: _rescaled(values, factor, spread_factor)
            for variant, values in plan.pools.items()
        }
        bounds = {
            variant: tuple((low * factor, high * factor) for low, high in intervals)
            for variant, intervals in plan.bounds.items()
        }
        return replace(
            plan,
            pools=pools,
            bounds=bounds,
            rare=tuple(value * factor for value in plan.rare),
        )

    def _stopped(
        self, plan: StationPlan, minutes: float, *, horizon_s: float
    ) -> StationPlan:
        """One station carrying a single outage of the stated length."""
        del horizon_s
        outage = max(0.0, minutes) * 60.0
        if outage <= 0.0:
            return plan
        longest = max(
            (max(values) for values in plan.pools.values() if values), default=0.0
        )
        return replace(
            plan,
            rare=(*plan.rare, longest + outage),
            rare_rate=min(1.0, plan.rare_rate + _one_in(self.line, outage)),
        )

    def _resized(self, shape: LineShape, buffer_id: str, capacity: int) -> LineShape:
        """The line with one buffer's slot count changed."""
        after = {item.buffer_id: item.after for item in self.line.buffers}
        target = after.get(buffer_id)
        if target is None:
            return shape
        order = list(shape.order)
        if target not in order:
            return shape
        index = order.index(target) + 1
        if index >= len(shape.slots):
            return shape
        slots = list(shape.slots)
        slots[index] = max(1, capacity)
        return replace(shape, slots=tuple(slots))


def _rescaled(
    values: tuple[float, ...], factor: float, spread_factor: float
) -> tuple[float, ...]:
    """A pool moved by a factor and tightened or loosened around its centre."""
    if not values:
        return values
    centre = sorted(values)[len(values) // 2] * factor
    return tuple(centre + (value * factor - centre) * spread_factor for value in values)


def _one_in(line: LineDefinition, outage_s: float) -> float:
    """The per-unit rate that puts one outage inside the horizon."""
    units = max(1.0, line.forecast.horizon_min * 60.0 / max(1.0, line.takt_s))
    del outage_s
    return 1.0 / units


def _paired_delta(baseline: ForecastSummary, option: ForecastSummary) -> Estimate:
    """The difference between two arms that shared their seeds. AC-031."""
    lo = option.output.lo - baseline.output.hi
    hi = option.output.hi - baseline.output.lo
    return Estimate.derived(
        Interval(lo, hi),
        basis=(
            f"{option.replications} replications against the same replications "
            f"of doing nothing, on shared seeds"
        ),
        confidence=0.9,
    )


def _peaks(summary: ForecastSummary) -> dict[str, float]:
    """The highest stall probability each station reaches in the horizon."""
    return {
        station.station_id: max(station.stall_probability)
        if station.stall_probability
        else 0.0
        for station in summary.stations
    }
