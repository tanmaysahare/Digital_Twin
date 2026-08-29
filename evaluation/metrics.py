"""Every metric the evidence pack reports. T-069.

PRD Section 5 lists what has to be measured. This computes it, and it reports the
denominator beside every ratio, because a precision of 1.00 over two predictions
and a precision of 0.71 over two hundred are not the same claim and a table that
prints only the ratio hides which one it has.

**Recall comes from the missed events, never from the predictions alone.** A view
over predictions can say how often the twin was right when it spoke. It cannot
say how often it should have spoken, and reporting the first as if it were the
second is the failure this whole product argues against (T-062, EC-26).

**The null scenario travels with every figure.** `Summary.false_alerts_per_shift`
is computed on SC-06 and printed beside every accuracy number for the same
predictor (AC-091). A hit rate without the false alarm rate beside it is half a
measurement.

**The virtual sensor coverage is measured against ground truth**, which is the
one place in the evaluation where truth is read, and it is read after the twin
has committed to every bound it produced.
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from dataclasses import dataclass, field

from evaluation.harness import RunResult
from twin.defect.model import temporal_split
from twin.defect.risk import GateService
from twin.ledger.store import STALL_FORECASTER, LedgerStore

# The shift length the false alarm rate is expressed in, taken from the line's
# own calendar rather than assumed.
SECONDS_PER_HOUR = 3600.0


@dataclass(frozen=True)
class Counts:
    """One predictor's tally over a set of runs."""

    made: int = 0
    true_positive: int = 0
    false_positive: int = 0
    true_negative: int = 0
    false_negative: int = 0
    unscoreable: int = 0
    missed: int = 0
    lead_times_s: tuple[float, ...] = ()
    published: int = 0

    @property
    def scored(self) -> int:
        """Predictions that count towards precision."""
        return self.true_positive + self.false_positive

    @property
    def precision(self) -> float | None:
        """Hits over scored predictions."""
        return self.true_positive / self.scored if self.scored else None

    @property
    def recall(self) -> float | None:
        """Hits over everything that happened, from the missed-event rows."""
        denominator = self.true_positive + self.missed + self.false_negative
        return self.true_positive / denominator if denominator else None

    @property
    def f1(self) -> float | None:
        """The harmonic mean, where both halves exist."""
        precision, recall = self.precision, self.recall
        if precision is None or recall is None or precision + recall <= 0:
            return None
        return 2 * precision * recall / (precision + recall)

    @property
    def unscoreable_share(self) -> float | None:
        """How much of this record could not be scored either way."""
        return self.unscoreable / self.made if self.made else None

    @property
    def median_lead_min(self) -> float | None:
        """The middle of the lead-time distribution, in minutes."""
        if not self.lead_times_s:
            return None
        return statistics.median(self.lead_times_s) / 60.0

    def lead_quantile_min(self, share: float) -> float | None:
        """One quantile of the lead-time distribution, in minutes."""
        if not self.lead_times_s:
            return None
        ordered = sorted(self.lead_times_s)
        position = min(len(ordered) - 1, max(0, round(share * (len(ordered) - 1))))
        return ordered[position] / 60.0

    def plus(self, other: Counts) -> Counts:
        """Two tallies added together."""
        return Counts(
            made=self.made + other.made,
            true_positive=self.true_positive + other.true_positive,
            false_positive=self.false_positive + other.false_positive,
            true_negative=self.true_negative + other.true_negative,
            false_negative=self.false_negative + other.false_negative,
            unscoreable=self.unscoreable + other.unscoreable,
            missed=self.missed + other.missed,
            lead_times_s=self.lead_times_s + other.lead_times_s,
            published=self.published + other.published,
        )


def tally(store: LedgerStore, predictor: str) -> Counts:
    """One predictor's record in one ledger."""
    counts: dict[str, int] = defaultdict(int)
    leads: list[float] = []
    published = 0
    for prediction in store.predictions:
        if prediction.predictor != predictor:
            continue
        counts["made"] += 1
        if prediction.published:
            published += 1
        outcome = store.outcome_of(prediction.prediction_id)
        if outcome is None:
            continue
        counts[outcome.result.lower()] += 1
        if outcome.result == "TRUE_POSITIVE" and outcome.lead_time_s is not None:
            leads.append(outcome.lead_time_s)
    missed = len(store.missed_for(predictor))
    return Counts(
        made=counts["made"],
        true_positive=counts["true_positive"],
        false_positive=counts["false_positive"],
        true_negative=counts["true_negative"],
        false_negative=counts["false_negative"],
        unscoreable=counts["unscoreable"],
        missed=missed,
        lead_times_s=tuple(leads),
        published=published,
    )


@dataclass(frozen=True)
class SensorCoverage:
    """How often the derived interval contained the truth. AC-005."""

    cycles: int
    covered: int
    span_cycles: int
    span_covered: int

    @property
    def coverage(self) -> float | None:
        """The share of cycles whose bound held the true value."""
        return self.covered / self.cycles if self.cycles else None

    @property
    def span_coverage(self) -> float | None:
        """The same, for the whole dark span's total rather than one station."""
        return self.span_covered / self.span_cycles if self.span_cycles else None


def sensor_coverage(run: RunResult) -> SensorCoverage:
    """Check every derived bound against what really happened.

    The one place the harness reads ground truth. It reads it after the twin has
    produced every bound it is going to produce, which is what makes this a
    measurement rather than a calibration.
    """
    by_unit: dict[str, dict[str, float]] = defaultdict(dict)
    for visit in run.truth.visits:
        by_unit[visit.unit_id][visit.station_id] = visit.cycle_time_s
    cycles = covered = span_cycles = span_covered = 0
    for estimate in run.pipeline.estimator.sensors.estimates():
        visits = by_unit.get(estimate.unit_id, {})
        stations = estimate.span.dark_station_ids
        if not set(stations) <= set(visits):
            continue
        total = sum(visits[station_id] for station_id in stations)
        span_cycles += 1
        if estimate.total.interval.contains(total):
            span_covered += 1
        for station_id, bound in estimate.per_station.items():
            cycles += 1
            if bound.interval.contains(visits[station_id]):
                covered += 1
    return SensorCoverage(cycles, covered, span_cycles, span_covered)


@dataclass(frozen=True)
class DefectMetrics:
    """One gate's model, as the held-out fold measured it."""

    gate_id: str
    trained: bool
    reason: str
    base_rate: float = math.nan
    pr_auc: float = math.nan
    expected_calibration_error: float = math.nan
    conformal_coverage: float = math.nan
    conformal_alpha: float = math.nan
    holdout_units: int = 0
    reliability_predicted: tuple[float, ...] = ()
    reliability_observed: tuple[float, ...] = ()
    reliability_counts: tuple[int, ...] = ()
    median_lead_stations: float | None = None
    median_lead_min: float | None = None


def _number(value: object) -> float:
    """Read a quantity out of a ledger record, which the ledger stores untyped."""
    if isinstance(value, int | float):
        return float(value)
    return float(str(value))


def defect_metrics(run: RunResult) -> tuple[DefectMetrics, ...]:
    """Every gate's model quality, and the lead time its predictions carried."""
    found: list[DefectMetrics] = []
    for gate_id, service in run.pipeline.defect.gates.items():
        leads_stations: list[float] = []
        leads_minutes: list[float] = []
        for prediction in run.store.predictions:
            if prediction.claim.get("gate_id") != gate_id:
                continue
            if prediction.claim.get("kind") != "DEFECT_RISK":
                continue
            leads_stations.append(_number(prediction.claim["stations_remaining"]))
            leads_minutes.append(_number(prediction.claim["minutes_remaining"]))
        model = service.model
        if model is None or not service.is_trained:
            found.append(
                DefectMetrics(
                    gate_id=gate_id,
                    trained=False,
                    reason=run.training_report.get(gate_id, "not fitted"),
                    base_rate=service.base_rate,
                    median_lead_stations=(
                        statistics.median(leads_stations) if leads_stations else None
                    ),
                    median_lead_min=(
                        statistics.median(leads_minutes) if leads_minutes else None
                    ),
                )
            )
            continue
        diagram = model.reliability_holdout
        found.append(
            DefectMetrics(
                gate_id=gate_id,
                trained=True,
                reason=run.training_report.get(gate_id, "fitted"),
                base_rate=model.base_rate,
                pr_auc=_pr_auc_for(run, service),
                expected_calibration_error=(
                    diagram.expected_calibration_error if diagram else math.nan
                ),
                conformal_coverage=service.coverage,
                conformal_alpha=(
                    service.conformal.alpha if service.conformal else math.nan
                ),
                holdout_units=model.split_sizes[2],
                reliability_predicted=diagram.predicted if diagram else (),
                reliability_observed=diagram.observed if diagram else (),
                reliability_counts=diagram.counts if diagram else (),
                median_lead_stations=(
                    statistics.median(leads_stations) if leads_stations else None
                ),
                median_lead_min=(
                    statistics.median(leads_minutes) if leads_minutes else None
                ),
            )
        )
    return tuple(found)


def _pr_auc_for(run: RunResult, service: GateService) -> float:
    """Average precision on the held-out fold. PRD Section 5."""
    rows = tuple(row for row in service.rows if row.failed is not None)
    if not rows:
        return math.nan
    split = temporal_split(rows)
    if not split.holdout:
        return math.nan
    model = service.model
    if model is None:
        return math.nan
    scores = model.predict(split.holdout)
    labels = [1 if row.failed else 0 for row in split.holdout]
    del run
    return average_precision(scores.tolist(), labels)


def average_precision(scores: list[float], labels: list[int]) -> float:
    """Area under the precision-recall curve, by the step-wise definition.

    Written out rather than imported so that the evidence pack does not depend on
    a library version for a number a reader may want to check by hand.
    """
    positives = sum(labels)
    if positives == 0 or not scores:
        return math.nan
    ordered = sorted(zip(scores, labels, strict=True), key=lambda item: -item[0])
    hits = 0
    total = 0.0
    for index, (_, label) in enumerate(ordered, start=1):
        if label:
            hits += 1
            total += hits / index
    return total / positives


@dataclass(frozen=True)
class RunMetrics:
    """One run, measured. Everything here crosses a process boundary.

    The pipeline that produced these numbers stays in the worker: it is large,
    it holds closures, and nothing downstream needs it. What the report needs is
    the tally, and this is it.
    """

    scenario_id: str
    seed: int
    line_id: str
    units: int
    cycles: int
    wall_s: float
    shifts: float
    units_built: int
    observed_stalls: int
    stall: Counts
    drift: Counts
    coverage: SensorCoverage
    forecast_seconds: tuple[float, ...]
    onset_lags_min: tuple[float, ...]
    defects: tuple[DefectMetrics, ...]
    training_report: dict[str, str]

    @property
    def key(self) -> str:
        """A stable name for this run."""
        return f"{self.scenario_id}-{self.seed}"


def measure(run: RunResult) -> RunMetrics:
    """Reduce one run to the numbers the report is built from."""
    lags = [
        _number(outcome.actual["onset_lag_s"]) / 60.0
        for outcome in run.store.outcomes.values()
        if isinstance(outcome.actual.get("onset_lag_s"), int | float)
    ]
    return RunMetrics(
        scenario_id=run.scenario_id,
        seed=run.seed,
        line_id=run.line_id,
        units=run.units,
        cycles=run.cycles,
        wall_s=run.wall_s,
        shifts=_shifts_in(run),
        units_built=run.truth.completed_units(),
        observed_stalls=len(run.pipeline.observed.episodes()),
        stall=tally(run.store, STALL_FORECASTER),
        drift=tally(run.store, "drift_detector"),
        coverage=sensor_coverage(run),
        forecast_seconds=run.forecast_runtime_s,
        onset_lags_min=tuple(lags),
        defects=defect_metrics(run),
        training_report=dict(run.training_report),
    )


@dataclass(frozen=True)
class ScenarioMetrics:
    """One scenario across its seeds."""

    scenario_id: str
    runs: int
    shifts: float
    stall: Counts
    drift: Counts
    coverage: SensorCoverage
    observed_stalls: int
    forecast_seconds: tuple[float, ...]
    cycles: int
    units_built: int
    onset_lags_min: tuple[float, ...] = ()
    defects: tuple[DefectMetrics, ...] = ()

    @property
    def false_alerts_per_shift(self) -> float | None:
        """False stall alerts a supervisor would have seen per shift. AC-043."""
        if self.shifts <= 0:
            return None
        return self.stall.false_positive / self.shifts

    @property
    def alerts_per_shift(self) -> float | None:
        """Every stall alert, right or wrong, per shift."""
        if self.shifts <= 0:
            return None
        return self.stall.made / self.shifts

    @property
    def median_onset_lag_min(self) -> float | None:
        """How long a drift ran before both charts caught it. AC-014."""
        if not self.onset_lags_min:
            return None
        return statistics.median(self.onset_lags_min)

    @property
    def forecast_p95_s(self) -> float | None:
        """The slowest forecast cycle, near enough. NFR-01."""
        if not self.forecast_seconds:
            return None
        ordered = sorted(self.forecast_seconds)
        return ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]


def scenario_metrics(scenario_id: str, runs: tuple[RunMetrics, ...]) -> ScenarioMetrics:
    """Everything one scenario's runs say, added up."""
    stall = Counts()
    drift = Counts()
    coverage = SensorCoverage(0, 0, 0, 0)
    observed = 0
    seconds: list[float] = []
    lags: list[float] = []
    cycles = 0
    built = 0
    shifts = 0.0
    for run in runs:
        stall = stall.plus(run.stall)
        drift = drift.plus(run.drift)
        piece = run.coverage
        coverage = SensorCoverage(
            coverage.cycles + piece.cycles,
            coverage.covered + piece.covered,
            coverage.span_cycles + piece.span_cycles,
            coverage.span_covered + piece.span_covered,
        )
        observed += run.observed_stalls
        seconds.extend(run.forecast_seconds)
        cycles += run.cycles
        built += run.units_built
        shifts += run.shifts
        lags.extend(run.onset_lags_min)
    return ScenarioMetrics(
        scenario_id=scenario_id,
        runs=len(runs),
        shifts=shifts,
        stall=stall,
        drift=drift,
        coverage=coverage,
        observed_stalls=observed,
        forecast_seconds=tuple(seconds),
        cycles=cycles,
        units_built=built,
        onset_lags_min=tuple(lags),
        defects=runs[0].defects if runs else (),
    )


def _shifts_in(run: RunResult) -> float:
    """How many shifts of production one run covered, from its own calendar."""
    line = run.pipeline.line
    shift_s = sum(
        (
            (shift.end.hour * 3600 + shift.end.minute * 60)
            - (shift.start.hour * 3600 + shift.start.minute * 60)
        )
        % (24 * 3600)
        for shift in line.shifts
    ) / max(1, len(line.shifts))
    return run.result.finished_at_s / max(1.0, shift_s)


@dataclass
class Summary:
    """The whole evaluation, ready to be written out."""

    scenarios: dict[str, ScenarioMetrics] = field(default_factory=dict)

    @property
    def null_scenario(self) -> ScenarioMetrics | None:
        """The quiet shift, which travels beside every accuracy figure."""
        return self.scenarios.get("SC-06")

    @property
    def fault_scenarios(self) -> tuple[ScenarioMetrics, ...]:
        """Every scenario that injected something."""
        return tuple(
            metrics
            for scenario_id, metrics in sorted(self.scenarios.items())
            if scenario_id != "SC-06"
        )

    def overall_stall(self) -> Counts:
        """The stall forecaster across every scenario, the null one included."""
        total = Counts()
        for metrics in self.scenarios.values():
            total = total.plus(metrics.stall)
        return total

    def overall_drift(self) -> Counts:
        """The drift detector across every scenario."""
        total = Counts()
        for metrics in self.scenarios.values():
            total = total.plus(metrics.drift)
        return total

    def overall_coverage(self) -> SensorCoverage:
        """Virtual sensor coverage across every scenario."""
        total = SensorCoverage(0, 0, 0, 0)
        for metrics in self.scenarios.values():
            total = SensorCoverage(
                total.cycles + metrics.coverage.cycles,
                total.covered + metrics.coverage.covered,
                total.span_cycles + metrics.coverage.span_cycles,
                total.span_covered + metrics.coverage.span_covered,
            )
        return total


def summarise(runs: tuple[RunMetrics, ...]) -> Summary:
    """Group every run by scenario and reduce it."""
    grouped: dict[str, list[RunMetrics]] = defaultdict(list)
    for run in runs:
        grouped[run.scenario_id].append(run)
    return Summary(
        scenarios={
            scenario_id: scenario_metrics(scenario_id, tuple(items))
            for scenario_id, items in sorted(grouped.items())
        }
    )
