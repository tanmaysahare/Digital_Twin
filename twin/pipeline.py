"""The whole twin, driven by one event stream.

ARCHITECTURE.md Section 4. The worker wakes on the cadence, reads the state the
ingest has already brought current, refits what has moved, runs the two
detectors, seeds the forecast from the live state, records every prediction to
the ledger, and only then decides what may be published. The order matters and it
is the order here:

```
  refit distributions   ->  drift charts     ->  seed the forecast
  run replications      ->  aggregate        ->  attribute the constraint
  emit stall forecasts  ->  score units      ->  write to the ledger
  join elapsed horizons ->  record misses    ->  evaluate the gates
```

Writing to the ledger before the publication decision is what makes shadow mode
measurable rather than decorative (AC-011, AC-041). Evaluating the gates last is
what makes a promotion depend on the outcomes that have just been joined rather
than on the ones that were available at the start of the cycle.

This module is the one place where the pieces meet, and it is deliberately the
only place. Every module it drives is testable on its own, and the evaluation
harness drives this rather than reimplementing the order of operations, so the
pipeline the evidence pack measures is the pipeline that runs.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from connector.protocol import CanonicalEvent
from twin.config.line import LineDefinition
from twin.defect.risk import DefectService, UnitRisk
from twin.domain.shifts import ProductionCalendar
from twin.forecast.aggregate import ForecastSummary, aggregate
from twin.forecast.attribution import ActivePeriodTracker, ConstraintAttribution
from twin.forecast.des import Forecaster, ForecastSeed, StationPlan, WarmUnit
from twin.forecast.drift import DriftDetector, DriftEstimate
from twin.forecast.stall import StallForecast, build_stall_forecasts
from twin.forecast.stops import StallObserver
from twin.ledger.gates import GateDecision, evaluate_gates
from twin.ledger.outcomes import GateOutcome, Observations, OutcomeJoiner
from twin.ledger.scorecard import Scorecard, build_scorecard
from twin.ledger.store import (
    DRIFT_DETECTOR,
    STALL_FORECASTER,
    LedgerStore,
    Prediction,
    defect_predictor,
    inputs_hash,
    make_prediction_id,
)
from twin.state.estimator import StateEstimator
from twin.state.losses import LossLedger

# How many recent passages a dark station's forecast pool is drawn from. Longer
# than the drift detector's reference window would let a dark station that has
# already slowed keep sampling from before it did.
DARK_POOL = 60

# The model version every predictor stamps on its predictions. Bumped when the
# behaviour of a predictor changes, so that a scorecard cannot silently mix two
# different predictors under one name.
MODEL_VERSION = "phase2.1"

# How many labelled units have to clear a gate before the defect models are
# fitted, and how many more before they are fitted again. Retraining is what
# keeps the model current as the line changes, and doing it on a count rather
# than on a clock means a quiet shift does not trigger one.
TRAIN_AFTER_UNITS = 240
RETRAIN_EVERY_UNITS = 400


@dataclass(frozen=True)
class CycleResult:
    """What one forecast cycle produced."""

    cycle_id: str
    at: datetime
    summary: ForecastSummary
    attribution: ConstraintAttribution
    forecasts: tuple[StallForecast, ...]
    drift: tuple[DriftEstimate, ...]
    risks: tuple[UnitRisk, ...]
    recorded: tuple[Prediction, ...]
    published: tuple[Prediction, ...]
    decisions: tuple[GateDecision, ...]

    @property
    def shadow_count(self) -> int:
        """How many predictions this cycle made that nothing may show."""
        return len(self.recorded) - len(self.published)


@dataclass
class TwinPipeline:
    """The twin, from canonical events to a scored ledger."""

    line: LineDefinition
    calendar: ProductionCalendar
    store: LedgerStore = field(default_factory=LedgerStore)
    replications: int | None = None
    horizon_min: int | None = None
    cadence_s: float | None = None

    estimator: StateEstimator = field(init=False)
    drift: DriftDetector = field(init=False)
    activity: ActivePeriodTracker = field(init=False)
    observed: StallObserver = field(init=False)
    losses: LossLedger = field(init=False)
    forecaster: Forecaster = field(init=False)
    joiner: OutcomeJoiner = field(init=False)
    defect: DefectService = field(init=False)

    _gate_results: list[GateOutcome] = field(default_factory=list, repr=False)
    _cycles: list[CycleResult] = field(default_factory=list, repr=False)
    _next_cycle_at: datetime | None = field(default=None, repr=False)
    _last_at: datetime | None = field(default=None, repr=False)
    _completed: set[str] = field(default_factory=set, repr=False)
    _completed_at: list[datetime] = field(default_factory=list, repr=False)
    _cycle_history: dict[str, list[tuple[datetime, float]]] = field(
        default_factory=dict, repr=False
    )
    _labelled: int = field(default=0, repr=False)
    _last_release_at: datetime | None = field(default=None, repr=False)
    # Which stations had a stall forecast open at the end of the last cycle.
    _open_stalls: set[str] = field(default_factory=set, repr=False)
    _trained_at_count: int = field(default=0, repr=False)
    _training_report: dict[str, str] = field(default_factory=dict, repr=False)
    _scrapped: set[str] = field(default_factory=set, repr=False)

    def __post_init__(self) -> None:
        """Build every part of the twin against one line definition."""
        self.estimator = StateEstimator(self.line)
        self.drift = DriftDetector(self.line)
        self.activity = ActivePeriodTracker(self.line)
        self.observed = StallObserver(self.line, self.calendar)
        self.losses = LossLedger(self.line, self.calendar)
        self.forecaster = Forecaster(self.line, self.calendar)
        self.joiner = OutcomeJoiner(self.line, self.calendar, self.store)
        self.defect = DefectService(
            line=self.line,
            calendar=self.calendar,
            distributions=self.estimator.distributions,
            model_version=MODEL_VERSION,
        )

    @property
    def cycles(self) -> tuple[CycleResult, ...]:
        """Every forecast cycle this run has produced."""
        return tuple(self._cycles)

    @property
    def cadence(self) -> float:
        """How often the forecast cycle runs, in simulated seconds."""
        return self.cadence_s or float(self.line.forecast.cadence_s)

    # -- ingest -----------------------------------------------------------

    def feed(self, events: Iterable[CanonicalEvent]) -> None:
        """Run the twin over a whole stream, cycling on the cadence."""
        for event in events:
            self.observe(event)
        self.close()

    def observe(self, event: CanonicalEvent) -> None:
        """Take one canonical event, running a cycle when the cadence comes up."""
        self.estimator.apply(event)
        self.activity.observe(event)
        self.observed.observe(event)
        self.losses.observe(event)
        self._track(event)
        at = event.ts_source
        self._last_at = at
        if self._next_cycle_at is None:
            self._next_cycle_at = at + timedelta(seconds=self.cadence)
            return
        while at >= self._next_cycle_at:
            self.run_cycle(self._next_cycle_at)
            self._next_cycle_at += timedelta(seconds=self.cadence)

    def close(self) -> None:
        """Score everything whose horizon has closed by the end of the stream."""
        if self._last_at is None:
            return
        end = self._last_at + timedelta(minutes=self.line.forecast.horizon_min + 60)
        self.joiner.record_misses(self._observations(), up_to=self._last_at)
        self.joiner.join(end, self._observations())

    def _track(self, event: CanonicalEvent) -> None:
        """Feed the drift charts and remember the verdicts and the departures."""
        if (
            event.event_type == "UNIT_ARRIVE"
            and event.station_id == self.line.station_ids[0]
        ):
            # The last unit released onto the line. Everything after it is the
            # line draining, which is not a condition the twin is asked to
            # forecast and is not one it can be scored against.
            self._last_release_at = event.ts_source
        if event.event_type == "CYCLE_END" and event.station_id is not None:
            variant = str(event.payload.get("variant_id", ""))
            raw = event.payload.get("cycle_time_s")
            cycle_s = float(raw) if isinstance(raw, int | float | str) else 0.0
            self.drift.observe(event.station_id, variant, cycle_s, event.ts_source)
            self._cycle_history.setdefault(f"{event.station_id}|{variant}", []).append(
                (event.ts_source, cycle_s)
            )
        elif event.event_type == "INSPECTION_RESULT" and event.unit_id is not None:
            gate_id = str(event.payload.get("gate_id", ""))
            passed = bool(event.payload.get("passed", True))
            self._gate_results.append(
                GateOutcome(
                    unit_id=event.unit_id,
                    gate_id=gate_id,
                    at=event.ts_source,
                    passed=passed,
                )
            )
            signature = self.estimator.signature(event.unit_id)
            if signature is not None:
                if self.defect.has_scored(event.unit_id, gate_id):
                    self._labelled += 1
                self.defect.observe_gate_result(
                    signature, gate_id, event.ts_source, passed=passed
                )
            if (
                self.line.gates
                and gate_id == self.line.gates[-1].gate_id
                and passed
                and event.unit_id not in self._completed
            ):
                self._completed.add(event.unit_id)
                self._completed_at.append(event.ts_source)

    # -- the cycle --------------------------------------------------------

    def run_cycle(self, at: datetime) -> CycleResult | None:
        """One forecast cycle. ARCHITECTURE.md Section 4."""
        state = self.estimator.state(at)
        cycle_id = f"{self.line.line_id}:{at.isoformat()}"
        seed = self.build_seed(at)
        run = self.forecaster.run(
            seed,
            cycle_id,
            replications=self.replications,
            horizon_s=(
                self.horizon_min * 60.0 if self.horizon_min is not None else None
            ),
        )
        summary = aggregate(run, self.line, self._nominal_output(at, run.horizon_s))
        attribution = self.activity.attribute(state.buffers, at)
        forecasts = build_stall_forecasts(
            run,
            summary,
            self.line,
            attribution,
            observable=frozenset(self.line.station_ids)
            - frozenset(self.observed.unobservable),
        )

        self._maybe_train(at)
        risks = self._score_units(at)

        recorded: list[Prediction] = []
        recorded.extend(self._record_stalls(forecasts, at))
        recorded.extend(self._record_drift(at))
        recorded.extend(self._record_risks(risks, at))

        observations = self._observations()
        self.joiner.record_misses(observations, up_to=at)
        self.joiner.join(at, observations)
        scorecard = self.scorecard(at)
        decisions = evaluate_gates(self.store, self.line, scorecard, at)

        result = CycleResult(
            cycle_id=cycle_id,
            at=at,
            summary=summary,
            attribution=attribution,
            forecasts=forecasts,
            drift=self.drift.drifting(),
            risks=risks,
            recorded=tuple(recorded),
            published=tuple(item for item in recorded if item.published),
            decisions=decisions,
        )
        self._cycles.append(result)
        return result

    # -- the defect models ------------------------------------------------

    def _maybe_train(self, at: datetime) -> None:
        """Fit the defect models once the line has produced enough to fit on.

        Counted in labelled units rather than in wall clock, because a model is
        ready when it has seen enough outcomes and not when enough time has
        passed. Retraining on a schedule keeps the model current as the line
        changes (US-044), and the report is kept so the interface can say which
        gates have a model and which are still learning.
        """
        if self._labelled < TRAIN_AFTER_UNITS:
            return
        if (
            self._trained_at_count
            and self._labelled - self._trained_at_count < RETRAIN_EVERY_UNITS
        ):
            return
        self._trained_at_count = self._labelled
        self._training_report = self.defect.train(at)

    @property
    def completed_units(self) -> int:
        """How many units have cleared the last gate since the run began."""
        return len(self._completed)

    def completed_since(self, since: datetime) -> int:
        """How many units have cleared the last gate since an instant.

        The shift's output is what a supervisor is judged on, and the run's
        output is not it. Counting the whole run against a shift target made
        the line look hundreds of units ahead of a pace it was in fact
        behind.
        """
        return sum(1 for at in self._completed_at if at >= since)

    @property
    def gate_results(self) -> tuple[GateOutcome, ...]:
        """Every gate verdict seen, in the order they arrived."""
        return tuple(self._gate_results)

    def cycle_series(
        self, station_id: str, variant_id: str | None = None
    ) -> tuple[tuple[datetime, float], ...]:
        """One station's recorded cycles, for the drawer and the evidence panel.

        With no variant this pools every variant in time order, which is what a
        chart of "what has this station been doing" wants. The drift charts
        never pool, because a long-wheelbase body genuinely takes longer at the
        same station and pooling would hide it; a chart a person reads is a
        different question from a chart a detector reads.
        """
        if variant_id is not None:
            return tuple(self._cycle_history.get(f"{station_id}|{variant_id}", ()))
        found: list[tuple[datetime, float]] = []
        for key, values in self._cycle_history.items():
            if key.split("|", 1)[0] == station_id:
                found.extend(values)
        return tuple(sorted(found, key=lambda item: item[0]))

    @property
    def training_report(self) -> dict[str, str]:
        """What happened at the last training pass, per gate."""
        return dict(self._training_report)

    def _score_units(self, at: datetime) -> tuple[UnitRisk, ...]:
        """Score every in-process unit for each gate it has not yet reached."""
        found: list[UnitRisk] = []
        for signature in self.estimator.signatures():
            if signature.status != "IN_PROCESS" or signature.unit_id in self._completed:
                continue
            found.extend(self.defect.score(signature, at))
        return tuple(found)

    def _record_risks(
        self, risks: tuple[UnitRisk, ...], at: datetime
    ) -> list[Prediction]:
        """One prediction per unit per gate, recorded before it may be shown."""
        written: list[Prediction] = []
        for risk in risks:
            predictor = defect_predictor(risk.gate_id)
            published = (
                self.store.state_of(
                    predictor, self.line.line_id, risk.current_station_id, at
                )
                == "ACTIVE"
            )
            claim: dict[str, object] = {
                "kind": "DEFECT_RISK",
                "gate_id": risk.gate_id,
                "unit_id": risk.unit_id,
                "probability": round(risk.risk.point, 5),
                "interval_lo": round(risk.risk.lo, 5),
                "interval_hi": round(risk.risk.hi, 5),
                "covers_both": risk.risk.covers_both,
                "flagged": risk.flagged,
                "attempt": risk.attempt,
                "stations_remaining": risk.stations_remaining,
                "minutes_remaining": round(risk.minutes_remaining, 1),
                "dark_visits": risk.dark_visits,
            }
            evidence: dict[str, object] = {
                "basis": risk.basis,
                "factors": [
                    {
                        "label": factor.label,
                        "detail": factor.detail,
                        "contribution": round(factor.contribution, 5),
                    }
                    for factor in risk.factors
                ],
                "current_station_id": risk.current_station_id,
                "conformal_alpha": risk.risk.alpha,
                "conformal_calibration_n": risk.risk.calibration_n,
            }
            written.append(
                self.store.record(
                    Prediction(
                        prediction_id=make_prediction_id(
                            predictor,
                            self.line.line_id,
                            risk.unit_id,
                            risk.gate_id,
                            risk.attempt,
                        ),
                        predictor=predictor,
                        model_version=risk.model_version,
                        line_id=self.line.line_id,
                        station_id=risk.current_station_id,
                        unit_id=risk.unit_id,
                        made_at=at,
                        horizon_end=at
                        + timedelta(minutes=max(1.0, risk.minutes_remaining * 3.0)),
                        claim=claim,
                        confidence=risk.risk.point,
                        interval=None,
                        evidence=evidence,
                        inputs_hash=inputs_hash({"claim": claim}),
                        published=published,
                    )
                )
            )
        return written

    def scorecard(self, at: datetime | None = None) -> Scorecard:
        """The predictor record as of an instant."""
        moment = at or self._last_at
        if moment is None:
            message = "no events have been seen, so there is no scorecard"
            raise ValueError(message)
        return build_scorecard(self.store, self.line, self.calendar, moment)

    # -- seeding ----------------------------------------------------------

    def build_seed(self, at: datetime) -> ForecastSeed:
        """Turn the live state into something the replications can start from."""
        epoch = self.calendar.epoch
        at_s = (at - epoch).total_seconds()
        holding = self.estimator.holding()
        slopes = self.drift.slopes()
        order = self.line.station_ids

        plans: list[StationPlan] = []
        for station in self.line.stations:
            plans.append(self._plan(station.station_id, slopes.get(station.station_id)))

        warm: list[WarmUnit] = []
        for index, station_id in enumerate(order):
            record = holding.get(station_id)
            if record is None:
                continue
            unit_id, arrived_at = record
            warm.append(
                WarmUnit(
                    unit_id=unit_id,
                    variant_id=self.estimator.variant_of(unit_id),
                    at_station_index=index,
                    remaining_s=self._remaining(station_id, unit_id, arrived_at, at),
                    in_station=True,
                )
            )
        occupancy = self.estimator.link_occupancy()
        for index, level in enumerate(occupancy):
            for position in range(level):
                warm.append(
                    WarmUnit(
                        unit_id=f"{order[index]}-link-{position}",
                        variant_id="",
                        at_station_index=index,
                        remaining_s=0.0,
                        in_station=False,
                    )
                )
        return ForecastSeed(
            line_id=self.line.line_id,
            at_s=at_s,
            plans=tuple(plans),
            warm_units=tuple(warm),
            link_occupancy=occupancy,
            upcoming_variants=self.estimator.recent_variants(20) or self.line.variants,
        )

    def _plan(self, station_id: str, slope: float | None) -> StationPlan:
        """One station's sampling plan, from whatever the twin has about it."""
        definition = self.line.station(station_id)
        if definition.tier == "C":
            bounds = self._dark_bounds(station_id)
            return StationPlan(
                station_id=station_id,
                bounds=bounds,
                drift_slope_s_per_s=slope or 0.0,
                fallback_reason=(
                    "" if bounds else self._dark_fallback_reason(station_id)
                ),
            )
        pools: dict[str, tuple[float, ...]] = {}
        pooled: list[float] = []
        rare: tuple[float, ...] = ()
        rare_rate = 0.0
        for variant_id in self.line.variants:
            distribution = self.estimator.distributions.get(station_id, variant_id)
            if distribution is None:
                continue
            pooled.extend(distribution.core)
            rare, rare_rate = distribution.rare, distribution.rare_rate
            if distribution.is_usable:
                pools[variant_id] = distribution.core
        if pooled:
            pools[""] = tuple(pooled)
        return StationPlan(
            station_id=station_id,
            pools=pools,
            rare=rare,
            rare_rate=rare_rate,
            drift_slope_s_per_s=slope or 0.0,
            fallback_reason="" if pools else "LEARNING",
        )

    def _dark_fallback_reason(self, station_id: str) -> str:
        """Whether a dark station without a bound will ever get one.

        A station inside a span the twin can bound is still learning and will
        have one shortly. A station in a span with no scan point at one end, or
        one longer than this line models, never will, and the forecast carries
        takt for it permanently and says so (STA-07, EC-18).
        """
        span = next(
            (
                item
                for item in self.estimator.sensors.spans
                if station_id in item.dark_station_ids
            ),
            None,
        )
        if span is None or not (span.is_resolvable and span.is_modelled):
            return "UNRESOLVABLE"
        return "LEARNING"

    def _dark_bounds(
        self, station_id: str
    ) -> dict[str, tuple[tuple[float, float], ...]]:
        """A dark station's sampling bounds for the forecast, per variant.

        Every entry is an interval and the sampler draws a point inside one
        rather than collapsing it, so the forecast's spread widens where the twin
        cannot see. A dark station with no bound at all, which on Line 2 is S42,
        returns nothing and the plan falls back to takt and says so (STA-07).

        **The span's bound divided, not each station's own bound.** What the
        virtual sensors bound on a run of several dark stations is their total;
        each station's own bound is that total widened by what the others could
        plausibly have taken, which is correct to show and wrong to sample from.
        Drawing five independent times from a bound that is wide enough to hold
        the whole span would have the forecast believe the span takes five times
        as long as it does, and the line would appear to be running at a quarter
        of takt. The forecast therefore divides the span's total evenly, because
        it has no evidence for any other split, and says so here. The interface
        still shows each station's own bound and still marks it `UNRESOLVED`: the
        two answer different questions, and only one of them is shown to a
        supervisor as a cycle time.
        """
        span = next(
            (
                item
                for item in self.estimator.sensors.spans
                if station_id in item.dark_station_ids
            ),
            None,
        )
        share = float(span.size) if span is not None else 1.0
        by_variant: dict[str, list[tuple[float, float]]] = {}
        for estimate in self.estimator.sensors.estimates():
            if station_id not in estimate.span.dark_station_ids:
                continue
            bound = (estimate.total.lo / share, estimate.total.hi / share)
            by_variant.setdefault(estimate.variant_id, []).append(bound)
            by_variant.setdefault("", []).append(bound)
        return {
            variant_id: tuple(values[-DARK_POOL:])
            for variant_id, values in by_variant.items()
            if values
        }

    def _remaining(
        self, station_id: str, unit_id: str, arrived_at: datetime, at: datetime
    ) -> float:
        """How much of a running cycle is left, from the station's own baseline."""
        variant_id = self.estimator.variant_of(unit_id)
        distribution = self.estimator.distributions.get(station_id, variant_id)
        typical = (
            distribution.median_s if distribution is not None else self.line.takt_s
        )
        elapsed = max(0.0, (at - arrived_at).total_seconds())
        return max(0.0, typical - elapsed)

    def _nominal_output(self, at: datetime, horizon_s: float) -> float:
        """How many units takt allows over the horizon.

        The expected unit loss is measured against this, so it comes from the
        production calendar rather than from the elapsed clock. A horizon holding
        a shift break allows fewer units, and saying otherwise would report a
        break as a loss (EC-11).
        """
        start_s = (at - self.calendar.epoch).total_seconds()
        producing = self.calendar.production_between(start_s, start_s + horizon_s)
        return producing / self.line.takt_s

    # -- recording --------------------------------------------------------

    def _record_stalls(
        self, forecasts: tuple[StallForecast, ...], at: datetime
    ) -> list[Prediction]:
        """One prediction per stall episode, not one per cycle.

        A station that stays above its probability threshold across six
        consecutive cycles has one thing wrong with it, not six. Recording a
        prediction on every cycle would multiply the ledger by the cadence, make
        precision a function of how often the worker happens to wake, and put six
        rows in front of a supervisor for one problem. The claim is made when the
        probability first crosses, and it stands until the probability falls back
        below, which is also how the action card behaves on the screen.
        """
        epoch = self.calendar.epoch
        written: list[Prediction] = []
        rising = {item.station_id for item in forecasts} - self._open_stalls
        self._open_stalls = {item.station_id for item in forecasts}
        for forecast in forecasts:
            if forecast.station_id not in rising:
                continue
            window_from = epoch + timedelta(seconds=forecast.window_from_s)
            window_to = epoch + timedelta(seconds=forecast.window_to_s)
            published = (
                self.store.state_of(
                    STALL_FORECASTER, self.line.line_id, forecast.station_id, at
                )
                == "ACTIVE"
            )
            claim: dict[str, object] = {
                "kind": "STALL_FORECAST",
                "station_id": forecast.station_id,
                "window_from": window_from.isoformat(),
                "window_to": window_to.isoformat(),
                "probability": round(forecast.probability, 4),
                "lead_time_min": round(forecast.lead_time_min, 1),
                "cause_station_id": forecast.cause.station_id,
                "cause": forecast.cause.description,
                "attribution": list(forecast.cause.methods),
                "attribution_agreement": forecast.cause.agreement,
                "expected_unit_loss_lo": round(forecast.expected_unit_loss.lo, 2),
                "expected_unit_loss_hi": round(forecast.expected_unit_loss.hi, 2),
            }
            written.append(
                self.store.record(
                    Prediction(
                        prediction_id=make_prediction_id(
                            STALL_FORECASTER,
                            self.line.line_id,
                            forecast.station_id,
                            at.isoformat(),
                        ),
                        predictor=STALL_FORECASTER,
                        model_version=MODEL_VERSION,
                        line_id=self.line.line_id,
                        station_id=forecast.station_id,
                        unit_id=None,
                        made_at=at,
                        horizon_end=window_to
                        + timedelta(minutes=self.joiner.tolerance_min),
                        claim=claim,
                        confidence=forecast.probability,
                        interval=forecast.expected_unit_loss.interval,
                        evidence=forecast.evidence,
                        inputs_hash=inputs_hash(
                            {"claim": claim, "evidence": forecast.evidence}
                        ),
                        published=published,
                        degraded=forecast.degraded,
                    )
                )
            )
        return written

    def _record_drift(self, at: datetime) -> list[Prediction]:
        """One prediction per drift episode, at the cycle that first sees it."""
        written: list[Prediction] = []
        for estimate in self.drift.drifting():
            prediction_id = make_prediction_id(
                DRIFT_DETECTOR,
                self.line.line_id,
                estimate.station_id,
                estimate.variant_id,
                estimate.onset_at.isoformat(),
            )
            try:
                self.store.prediction(prediction_id)
            except KeyError:
                pass
            else:
                continue
            published = (
                self.store.state_of(
                    DRIFT_DETECTOR, self.line.line_id, estimate.station_id, at
                )
                == "ACTIVE"
            )
            claim: dict[str, object] = {
                "kind": "DRIFT",
                "station_id": estimate.station_id,
                "variant_id": estimate.variant_id,
                "onset": estimate.onset_at.isoformat(),
                "direction": estimate.direction,
                "magnitude_s": round(estimate.magnitude_s, 3),
                "slope_s_per_s": round(estimate.slope_s_per_s, 6),
                "cycles_since_onset": estimate.cycles_since_onset,
            }
            evidence: dict[str, object] = {
                "basis": estimate.basis,
                "reference_median_s": round(estimate.reference_median_s, 3),
                "reference_scale_s": round(estimate.reference_scale_s, 3),
                "ewma_deviation_sigma": round(estimate.ewma_deviation_sigma, 3),
                "cusum_sigma": round(estimate.cusum_sigma, 3),
                "onset_lag_min": round(estimate.onset_lag_s / 60.0, 1),
                "both_charts_signalled": self.line.drift.require_both,
            }
            written.append(
                self.store.record(
                    Prediction(
                        prediction_id=prediction_id,
                        predictor=DRIFT_DETECTOR,
                        model_version=MODEL_VERSION,
                        line_id=self.line.line_id,
                        station_id=estimate.station_id,
                        unit_id=None,
                        made_at=at,
                        horizon_end=at
                        + timedelta(minutes=self.line.forecast.horizon_min),
                        claim=claim,
                        confidence=min(1.0, estimate.cusum_sigma / 10.0),
                        evidence=evidence,
                        inputs_hash=inputs_hash({"claim": claim}),
                        published=published,
                    )
                )
            )
        return written

    # -- observations -----------------------------------------------------

    def _observations(self) -> Observations:
        return Observations(
            episodes=self.observed.episodes(),
            gate_results=tuple(self._gate_results),
            gaps=(),
            units_without_outcome=frozenset(self._scrapped),
            acted_on=frozenset(),
            baseline=self._baseline,
            observed_until=self._last_at,
            fed_until=self._last_release_at,
        )

    def _baseline(
        self, station_id: str, variant_id: str, start: datetime, end: datetime
    ) -> float | None:
        """The median cycle time at a station over a span, or None if too few.

        Used only to score a drift claim after the fact. It reads the twin's own
        observed cycles, so a drift the twin never saw cannot be scored as one it
        did.
        """
        history = self._cycle_history.get(f"{station_id}|{variant_id}", [])
        inside = [value for moment, value in history if start <= moment <= end]
        if len(inside) < self.line.state.min_cycles:
            return None
        ordered = sorted(inside)
        middle = len(ordered) // 2
        if len(ordered) % 2:
            return ordered[middle]
        return (ordered[middle - 1] + ordered[middle]) / 2.0
