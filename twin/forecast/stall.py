"""The stall forecast, as it leaves the forecaster. T-056.

AC-010, AC-013, AC-015, AC-017, AC-018. What the forecaster hands to the ledger:
a target station, a window rather than an instant, a probability, the station
that is causing it, and what it is worth.

Four rules this module exists to enforce.

**A window, never an instant.** A forecast that says 10:04 is claiming a
precision the replications do not support. The window is the run of buckets in
which the probability stays above the line's threshold, and it is what the
outcome join scores against.

**The cause is not the target.** Under SC-01 the stall shows up at S22 and the
cause is S20, and reporting the target as the cause would send a supervisor to
the wrong station. The cause comes from the constraint attribution, which is a
separate method on separate evidence, and the attribution method is named beside
it so a reader can tell which of the two signals produced it.

**The loss is an interval.** It is the difference in output between the
replications in which this station stalled and those in which it did not, which
is a real conditional effect of this station rather than a share of a line total
apportioned by a rule of thumb. Where too few replications fall on one side of
that split the interval widens to the line's own loss and says so.

**Two faults are two forecasts.** SC-08 runs SC-01 and SC-03 together and the
test is that neither cause is folded into the other, so emission is per station
and ranking is by expected loss (AC-018).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from twin.config.line import LineDefinition
from twin.domain.estimate import Estimate, Interval
from twin.forecast.aggregate import HIGH_QUANTILE, LOW_QUANTILE, ForecastSummary
from twin.forecast.attribution import ConstraintAttribution
from twin.forecast.des import ForecastRun

# Below this many replications on either side of the stalled split, the
# conditional loss is the replication count talking rather than the station.
_MINIMUM_SPLIT = 10

# How many buckets at the head of the horizon are excluded from emission.
#
# The forecast is seeded from a snapshot, and a snapshot is incomplete in ways
# the twin cannot fix: it knows a station is working but not how far through the
# cycle it is, it knows how many units are inside a dark run but not which
# station each one is at, and it does not know the variant of a unit sitting on a
# conveyor. The replications settle out of that within about a takt. Deleting the
# initial transient is the standard treatment for a terminating simulation
# started from a warm state, and the cost here is five minutes of a 120 minute
# horizon.
WARM_UP_BUCKETS = 1


@dataclass(frozen=True)
class StallCause:
    """Which station is causing a forecast stall, and how that was decided."""

    station_id: str | None
    description: str
    methods: tuple[str, ...]
    agreement: bool


@dataclass(frozen=True)
class StallForecast:
    """One predicted stall. AC-010."""

    line_id: str
    station_id: str
    made_at_s: float
    window_from_s: float
    window_to_s: float
    probability: float
    cause: StallCause
    expected_unit_loss: Estimate
    evidence: dict[str, object]
    degraded: bool

    @property
    def lead_time_s(self) -> float:
        """How long before the window opens. AC-012 renders this largest."""
        return max(0.0, self.window_from_s - self.made_at_s)

    @property
    def lead_time_min(self) -> float:
        """The lead time in minutes, which is what the interface prints."""
        return self.lead_time_s / 60.0


def build_stall_forecasts(
    run: ForecastRun,
    summary: ForecastSummary,
    line: LineDefinition,
    attribution: ConstraintAttribution,
    observable: frozenset[str] | None = None,
) -> tuple[StallForecast, ...]:
    """Every stall the forecast is confident enough to claim, ranked by loss.

    Args:
        run: the replications, for the conditional loss split.
        summary: the aggregated probabilities.
        line: the line, for its own probability threshold.
        attribution: which station the two attribution methods name.
        observable: the stations whose waiting time something on the line
            records. A stall claimed at a station nothing watches can never be
            confirmed or refuted, and the ledger exists to make every claim
            checkable, so no claim is made there. The dark stations are still in
            the flow model and still cause stalls at the instrumented stations
            around them, which is where the claim is made instead.

    Returns:
        One forecast per station whose probability crosses the threshold, ranked
        by expected unit loss. Empty on a quiet line, which is the pass condition
        for SC-06 rather than the absence of one (AC-016).
    """
    if not summary.is_forecastable:
        # EC-20. A station without a baseline is run at takt, and a flow model
        # with an assumed station in it produces confident nonsense everywhere
        # downstream of the assumption. The interface says how many cycles remain
        # rather than showing a forecast.
        return ()
    threshold = line.forecast.stall_probability_threshold
    lost = np.stack([item.lost_s for item in run.replications])
    completed = np.stack([item.completed for item in run.replications]).sum(axis=1)
    found: list[StallForecast] = []

    watched = (
        observable
        if observable is not None
        else frozenset(item.station_id for item in line.stations if item.tier != "C")
    )
    for index, station_id in enumerate(line.station_ids):
        if station_id not in watched:
            continue
        station = summary.station(station_id)
        window = _first_window(station.stall_probability, threshold, WARM_UP_BUCKETS)
        if window is None:
            continue
        first, last = window
        probability = max(station.stall_probability[first : last + 1])
        loss = _conditional_loss(
            lost[:, index, first : last + 1],
            completed,
            line.forecast.stall_threshold_s,
            summary,
        )
        found.append(
            StallForecast(
                line_id=line.line_id,
                station_id=station_id,
                made_at_s=summary.at_s,
                window_from_s=summary.window_of(first).start_s,
                window_to_s=summary.window_of(last).end_s,
                probability=probability,
                cause=_cause(station_id, attribution),
                expected_unit_loss=loss,
                evidence={
                    "replications": summary.replications,
                    "horizon_min": summary.horizon_s / 60.0,
                    "bucket_probabilities": [
                        round(value, 4)
                        for value in station.stall_probability[first : last + 1]
                    ],
                    "mean_lost_s": [
                        round(value, 1)
                        for value in station.mean_lost_s[first : last + 1]
                    ],
                    "stall_threshold_s": line.forecast.stall_threshold_s,
                    "attribution": {
                        "by_active_period": attribution.by_active_period,
                        "by_buffer_trend": attribution.by_buffer_trend,
                        "agreement": attribution.agreement,
                        "basis": attribution.basis,
                    },
                    "drifting_stations": list(summary.drifting_stations),
                    "fallback_stations": list(summary.fallback_stations),
                    "line_output": {
                        "lo": summary.output.lo,
                        "hi": summary.output.hi,
                    },
                },
                degraded=summary.degraded,
            )
        )
    return tuple(sorted(found, key=lambda item: -item.expected_unit_loss.sort_key()))


def _first_window(
    probabilities: tuple[float, ...], threshold: float, skip: int = 0
) -> tuple[int, int] | None:
    """The first run of buckets whose probability stays above the threshold.

    The first `skip` buckets are the seeded transient and are not claimed.
    """
    first: int | None = None
    for index in range(skip, len(probabilities)):
        value = probabilities[index]
        if value > threshold:
            if first is None:
                first = index
        elif first is not None:
            return first, index - 1
    if first is not None:
        return first, len(probabilities) - 1
    return None


def _conditional_loss(
    lost_in_window: np.ndarray,
    completed: np.ndarray,
    threshold: float,
    summary: ForecastSummary,
) -> Estimate:
    """What this station stalling costs, from the replications that show it.

    The output in replications where the station stalled inside the window
    against the output in replications where it did not. Both sides come from the
    same forecast on the same seeds, so the difference is the station rather than
    simulation noise.
    """
    stalled = (lost_in_window > threshold).any(axis=1)
    quiet = ~stalled
    if int(stalled.sum()) < _MINIMUM_SPLIT or int(quiet.sum()) < _MINIMUM_SPLIT:
        return Estimate.derived(
            summary.expected_unit_loss.interval,
            basis=(
                f"too few replications on one side of the split to isolate this "
                f"station, so the figure is the whole line's shortfall against "
                f"takt over the horizon. {summary.expected_unit_loss.basis}"
            ),
            confidence=max(0.0, summary.expected_unit_loss.confidence - 0.2),
        )
    difference = completed[quiet].mean() - completed[stalled]
    low = float(np.quantile(difference, LOW_QUANTILE))
    high = float(np.quantile(difference, HIGH_QUANTILE))
    return Estimate.derived(
        Interval(max(0.0, low), max(0.0, high, low)),
        basis=(
            f"{int(stalled.sum())} of {len(completed)} replications stalled here, "
            f"and they built {completed[quiet].mean() - completed[stalled].mean():.1f} "
            f"units fewer on average than the ones that did not"
        ),
        confidence=summary.expected_unit_loss.confidence,
    )


def _cause(station_id: str, attribution: ConstraintAttribution) -> StallCause:
    """Which station to name as the cause of a stall at this one."""
    named = attribution.by_active_period or attribution.by_buffer_trend
    if named is None:
        return StallCause(
            station_id=None,
            description=attribution.basis,
            methods=(),
            agreement=False,
        )
    if named == station_id:
        description = (
            f"{station_id} is itself the station holding the line back. "
            f"{attribution.basis}"
        )
    else:
        description = (
            f"{named} is holding the line back and {station_id} is where it shows. "
            f"{attribution.basis}"
        )
    return StallCause(
        station_id=named,
        description=description,
        methods=attribution.methods,
        agreement=attribution.agreement,
    )
