"""Defect risk, as it leaves the model. T-068.

AC-020, AC-021, AC-023, AC-025. One risk per in-process unit per gate it has not
yet reached, with the lead time expressed in the two units a supervisor works in:
how many stations are left, and how many minutes that is.

**Stations first, minutes second.** A supervisor decides whether there is time to
act by counting stations, because that is what they can see from where they
stand. Minutes are the derived figure and they come from takt, so they move when
the line does.

**The risk is an interval and it is never shown as a point alone.** The point is
the calibrated probability; the bounds are the conformal set (Section 6.4). A
unit whose route ran through five dark stations gets a wider interval than one
that did not, and that width is the product's whole argument made visible on a
single row.

**Training is temporal and it happens once the line has produced enough.** The
service accumulates labelled rows as units clear their gates and fits when there
are enough to fit on. Before that it scores every unit at the gate's own base
rate and says so, which is honest and is what a plant sees on its first week.
Nothing is scored from a model that has seen that unit's own outcome.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from twin.config.line import LineDefinition
from twin.defect.conformal import ConformalCalibration, ConformalInterval, calibrate
from twin.defect.conformal import empirical_coverage as measure_coverage
from twin.defect.explain import Explainer, Factor
from twin.defect.features import FeatureBuilder, FeatureRow, feature_names
from twin.defect.model import GateModel, temporal_split, train_gate_model
from twin.domain.shifts import ProductionCalendar
from twin.domain.signature import ProcessSignature

# The risk above which a unit is worth putting on a supervisor's screen. A share
# of the gate's own base rate rather than an absolute number, because a gate that
# fails one unit in seventy and one that fails one in seven cannot share a
# threshold.
FLAG_MULTIPLE = 4.0

# Below this many labelled rows there is nothing to fit, and the service says so
# rather than fitting anyway.
MINIMUM_ROWS = 200


@dataclass(frozen=True)
class UnitRisk:
    """One unit's risk at one gate, with everything the row needs."""

    unit_id: str
    gate_id: str
    at: datetime
    current_station_id: str | None
    risk: ConformalInterval
    factors: tuple[Factor, ...]
    stations_remaining: int
    minutes_remaining: float
    dark_visits: int
    # Which pass through this gate the claim is about. A unit that failed G1 and
    # came back through the rework loop is scored again, and the second claim is
    # a different claim about a different unit state.
    attempt: int
    flagged: bool
    model_version: str
    basis: str


@dataclass
class GateService:
    """One gate's model, its conformal calibration, and its explainer."""

    gate_id: str
    builder: FeatureBuilder
    names: tuple[str, ...]
    model: GateModel | None = None
    conformal: ConformalCalibration | None = None
    explainer: Explainer | None = None
    coverage: float = math.nan
    rows: list[FeatureRow] = field(default_factory=list)
    trained_at: datetime | None = None
    # The row as it stood when the unit was scored, kept until its verdict
    # arrives. Training on this rather than on a row rebuilt at gate time is what
    # keeps the model honest: a model fitted on a complete route and applied to
    # half of one is relying on features that will not be there when it matters.
    scored: dict[str, FeatureRow] = field(default_factory=dict)
    # How many verdicts each unit has had at this gate, and which passes have
    # already been scored. Both are needed because a rework loop brings a unit
    # back through the same span, and the second pass is a new claim rather than
    # a repeat of the first.
    attempts: dict[str, int] = field(default_factory=dict)
    emitted: set[tuple[str, int]] = field(default_factory=set)

    @property
    def is_trained(self) -> bool:
        """Whether this gate has a model that can score anything."""
        return self.model is not None and self.model.booster is not None

    @property
    def base_rate(self) -> float:
        """The share of units this gate has failed so far."""
        labelled = [row for row in self.rows if row.failed is not None]
        if not labelled:
            return 0.0
        return sum(1 for row in labelled if row.failed) / len(labelled)


@dataclass
class DefectService:
    """Every gate's defect model, trained and scored in time order. T-063 to T-068."""

    line: LineDefinition
    calendar: ProductionCalendar
    distributions: object
    model_version: str
    gates: dict[str, GateService] = field(default_factory=dict)
    minimum_rows: int = MINIMUM_ROWS

    def __post_init__(self) -> None:
        """One service per gate on the line."""
        for gate in self.line.gates:
            builder = FeatureBuilder(
                line=self.line,
                calendar=self.calendar,
                distributions=self.distributions,  # type: ignore[arg-type]
                gate_id=gate.gate_id,
            )
            self.gates[gate.gate_id] = GateService(
                gate_id=gate.gate_id,
                builder=builder,
                names=feature_names(builder),
            )

    # -- accumulating -----------------------------------------------------

    def observe_gate_result(
        self,
        signature: ProcessSignature,
        gate_id: str,
        at: datetime,  # noqa: ARG002 - part of the call the pipeline makes
        *,
        passed: bool,
    ) -> None:
        """Take one verdict and label the row this unit was actually scored on.

        A unit the twin never scored produces no training row. That is correct:
        the model has to be fitted on rows of the shape it will be asked to
        predict from, and a row rebuilt now would carry the whole route rather
        than the part that was visible when the prediction was due.

        The lot rate is updated afterwards, so a unit never contributes to the
        feature that scored it.
        """
        service = self.gates.get(gate_id)
        if service is None:
            return
        row = service.scored.pop(signature.unit_id, None)
        if row is not None:
            service.rows.append(
                FeatureRow(
                    unit_id=row.unit_id,
                    gate_id=row.gate_id,
                    at=row.at,
                    values=row.values,
                    categories=row.categories,
                    failed=not passed,
                )
            )
        service.attempts[signature.unit_id] = (
            service.attempts.get(signature.unit_id, 0) + 1
        )
        service.builder.observe_gate_result(signature, gate_id, passed=passed)
        service.builder.observe_release(signature)

    def adopt(self, other: DefectService) -> None:
        """Take another service's fitted models as this one's.

        Models are fitted ahead on a long run and shipped, which is what a plant
        does (NFR-05) and what a gate failing one unit in seventy requires: a few
        hundred units carry three or four failures, and a model fitted on those
        would be confident noise. Only the fitted parts are taken. The feature
        builder stays this run's own, because the rolling lot rate and the recent
        variant mix are properties of the line now rather than of the run the
        model was fitted on.
        """
        for gate_id, source in other.gates.items():
            target = self.gates.get(gate_id)
            if target is None or source.model is None:
                continue
            target.model = source.model
            target.conformal = source.conformal
            target.coverage = source.coverage
            target.rows = list(source.rows)
            target.trained_at = source.trained_at
            # Rebuilt rather than carried across, because a tree explainer holds
            # a handle into the library and does not survive a process boundary.
            target.explainer = Explainer(source.model.booster, target.names)

    def has_scored(self, unit_id: str, gate_id: str) -> bool:
        """Whether this unit has an open prediction awaiting a verdict here."""
        service = self.gates.get(gate_id)
        return service is not None and unit_id in service.scored

    # -- training ---------------------------------------------------------

    def train(self, at: datetime) -> dict[str, str]:
        """Fit every gate that has enough history. Returns what happened to each."""
        report: dict[str, str] = {}
        for gate_id, service in self.gates.items():
            labelled = [row for row in service.rows if row.failed is not None]
            if len(labelled) < self.minimum_rows:
                report[gate_id] = (
                    f"{len(labelled)} of the {self.minimum_rows} labelled units a "
                    f"model needs. Every unit is scored at the gate's base rate "
                    f"until there are more"
                )
                continue
            model = train_gate_model(
                gate_id, tuple(labelled), service.names, self.model_version
            )
            service.model = model
            service.trained_at = at
            if not model.is_available:
                report[gate_id] = model.unavailable_reason or "unavailable"
                continue
            split = temporal_split(tuple(labelled))
            calibration_probabilities = model.predict(split.calibrate)
            calibration_labels = np.asarray(
                [1.0 if row.failed else 0.0 for row in split.calibrate], dtype=float
            )
            service.conformal = calibrate(calibration_probabilities, calibration_labels)
            holdout_probabilities = model.predict(split.holdout)
            holdout_labels = np.asarray(
                [1.0 if row.failed else 0.0 for row in split.holdout], dtype=float
            )
            service.coverage = measure_coverage(
                service.conformal, holdout_probabilities, holdout_labels
            )
            service.explainer = Explainer(model.booster, service.names)
            error = (
                model.reliability_holdout.expected_calibration_error
                if model.reliability_holdout is not None
                else math.nan
            )
            report[gate_id] = (
                f"fitted on {len(split.train)} units, calibrated on "
                f"{len(split.calibrate)}, tested on {len(split.holdout)}. "
                f"Calibration error {error:.3f}, conformal coverage "
                f"{service.coverage:.3f}"
            )
        return report

    # -- scoring ----------------------------------------------------------

    def score(self, signature: ProcessSignature, at: datetime) -> tuple[UnitRisk, ...]:
        """Every downstream gate's risk for one in-process unit.

        One risk per unit per gate, at the first cycle after the unit enters the
        stretch of line that gate inspects. Emitting again on every subsequent
        cycle would multiply the ledger by the number of cycles a unit spends on
        the line without adding a claim, and scoring earlier than the span would
        be scoring a unit whose route has not started.
        """
        found: list[UnitRisk] = []
        for gate in self.line.gates:
            service = self.gates.get(gate.gate_id)
            if service is None:
                continue
            attempt = service.attempts.get(signature.unit_id, 0)
            if (signature.unit_id, attempt) in service.emitted:
                continue
            remaining = self._stations_remaining(signature, gate.after)
            if remaining is None or not self._in_span(signature, gate.gate_id):
                continue
            risk = self._score_one(signature, gate.gate_id, at, remaining, attempt)
            if risk is not None:
                found.append(risk)
        return tuple(found)

    def _in_span(self, signature: ProcessSignature, gate_id: str) -> bool:
        """Whether the unit has reached the stretch of line this gate inspects."""
        service = self.gates[gate_id]
        span = set(service.builder.span)
        return any(visit.station_id in span for visit in signature.visits)

    def _score_one(
        self,
        signature: ProcessSignature,
        gate_id: str,
        at: datetime,
        remaining: int,
        attempt: int,
    ) -> UnitRisk | None:
        service = self.gates.get(gate_id)
        if service is None:
            return None
        row = service.builder.build(signature, at)
        service.scored[signature.unit_id] = row
        service.emitted.add((signature.unit_id, attempt))
        base = service.base_rate
        if not service.is_trained or service.model is None:
            probability = base
            interval = ConformalInterval(
                point=probability,
                lo=0.0,
                hi=1.0,
                covers_both=True,
                alpha=0.10,
                calibration_n=0,
            )
            factors: tuple[Factor, ...] = ()
            basis = (
                f"no model for {gate_id} yet, so this is the gate's own base rate "
                f"over {len(service.rows)} units and not a prediction about this "
                f"one"
            )
        else:
            probability = float(service.model.predict((row,))[0])
            interval = (
                service.conformal.interval(probability)
                if service.conformal is not None
                else ConformalInterval(probability, 0.0, 1.0, True, 0.10, 0)
            )
            # Contributions only for the units that will be shown. A tree
            # explainer costs more than the prediction it explains, and the
            # interface renders three factors on an at-risk row and nothing at
            # all on the ninety-eight percent of units that are fine (AC-022).
            factors = (
                self._factors(service, row)
                if probability >= max(base * FLAG_MULTIPLE, 1e-9)
                else ()
            )
            basis = (
                f"{gate_id} model {self.model_version}, calibrated on "
                f"{service.model.split_sizes[1]} units, conformal interval at "
                f"alpha {interval.alpha:.2f}"
            )
        dark = int(row.values.get("dark_visits", 0.0) or 0.0)
        return UnitRisk(
            unit_id=signature.unit_id,
            gate_id=gate_id,
            at=at,
            current_station_id=(
                signature.visits[-1].station_id if signature.visits else None
            ),
            risk=interval,
            factors=factors,
            stations_remaining=remaining,
            minutes_remaining=remaining * self.line.takt_s / 60.0,
            dark_visits=dark,
            attempt=attempt,
            flagged=probability >= max(base * FLAG_MULTIPLE, 1e-9),
            model_version=self.model_version,
            basis=basis,
        )

    def _factors(self, service: GateService, row: FeatureRow) -> tuple[Factor, ...]:
        if (
            service.explainer is None
            or not service.explainer.is_available
            or service.model is None
        ):
            return ()
        frame = service.model.frame((row,))
        contributions = service.explainer.contributions(frame)
        if contributions.size == 0:
            return ()
        columns = tuple(frame.columns)  # type: ignore[attr-defined]
        return service.explainer.factors(row, contributions[0], columns)

    def _stations_remaining(
        self, signature: ProcessSignature, gate_after: str
    ) -> int | None:
        """How many stations this unit still has before the gate, or None.

        None where the unit has already passed the gate, which is the case that
        stops the twin scoring a unit for a verdict it has already had.
        """
        order = self.line.station_ids
        if gate_after not in order:
            return None
        target = order.index(gate_after)
        if not signature.visits:
            return target + 1
        current = order.index(signature.visits[-1].station_id)
        if current > target:
            return None
        return target - current
