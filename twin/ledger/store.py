"""The trust ledger. T-057.

TECHNICAL_SPEC.md Section 9 and ARCHITECTURE.md Section 5.3. The ledger sits
between every predictor and the interface. A predictor cannot publish; it emits a
prediction, the ledger records it, and the ledger decides whether that predictor
is `ACTIVE` for that station. Shadow mode is therefore not a flag a developer can
forget to check, it is the only route to the screen.

**Append-only, and enforced twice.** This store raises on a second write to the
same prediction and on a second outcome for one prediction; the database raises
on UPDATE and DELETE through a trigger and a role without those grants
(DATABASE_SCHEMA.md Section 8). Two enforcements rather than one because the
ledger is the product's evidence, and evidence that can be edited after the fact
is not evidence.

**Recorded at emission, before any publication decision.** AC-011. A prediction
made while a predictor is in shadow exists in full, carries `published = false`,
and never reaches an interface response. That is what makes the promotion gate
measurable: the shadow predictions are the evidence the gate is decided on.

**The inputs hash.** Every prediction carries a digest of what it was made from,
so it can be reproduced. Blake2b over a canonical rendering rather than Python's
`hash`, which is salted per process and would differ between two runs of the same
scenario (NFR-07).

This store is in memory. The evaluation harness runs the whole pipeline without a
database, which is what lets `make evaluate` work on a clean checkout, and
`twin/ledger/persist.py` writes the same records to the tables in
DATABASE_SCHEMA.md Section 5 when there is one.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid5

from twin.domain.estimate import Interval

# A fixed namespace, so that a prediction identifier is a function of what the
# prediction is about rather than of when the process happened to start.
PREDICTION_NAMESPACE = UUID("6f1a4b0e-2f7d-4d5a-9a1b-0c7e5d3f2a10")

Predictor = str
PredictorState = Literal["SHADOW", "ACTIVE", "UNAVAILABLE"]
OutcomeResult = Literal[
    "TRUE_POSITIVE",
    "FALSE_POSITIVE",
    "TRUE_NEGATIVE",
    "FALSE_NEGATIVE",
    "UNSCOREABLE",
]
MissedKind = Literal["STALL", "GATE_FAILURE"]

STALL_FORECASTER = "stall_forecaster"
DRIFT_DETECTOR = "drift_detector"


def defect_predictor(gate_id: str) -> str:
    """The predictor name for one gate's defect model.

    The gate identifier comes from the line definition, so the predictor names on
    a line are a function of its configuration rather than of anything in code
    (CODING_STANDARDS.md 1.3).
    """
    return f"defect_risk_{gate_id.lower()}"


def inputs_hash(payload: dict[str, object]) -> str:
    """A stable digest of what a prediction was made from.

    Stable across processes, platforms and Python versions, which is what makes a
    prediction in the evidence pack reproducible on someone else's laptop.
    """
    rendered = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.blake2b(rendered.encode("utf-8"), digest_size=16).hexdigest()


@dataclass(frozen=True)
class Prediction:
    """One claim, with everything needed to score and reproduce it."""

    prediction_id: UUID
    predictor: Predictor
    model_version: str
    line_id: str
    station_id: str | None
    unit_id: str | None
    made_at: datetime
    horizon_end: datetime
    claim: dict[str, object]
    confidence: float
    evidence: dict[str, object]
    inputs_hash: str
    published: bool
    interval: Interval | None = None
    degraded: bool = False

    def __post_init__(self) -> None:
        """Reject a prediction whose horizon runs backwards or that is unbounded."""
        if self.horizon_end < self.made_at:
            message = (
                f"{self.predictor}: horizon_end {self.horizon_end} is before "
                f"made_at {self.made_at}, so nothing could ever score it"
            )
            raise ValueError(message)
        if not 0.0 <= self.confidence <= 1.0:
            message = f"confidence must be in [0, 1], got {self.confidence}"
            raise ValueError(message)


@dataclass(frozen=True)
class Outcome:
    """What happened, joined to the prediction that claimed it."""

    prediction_id: UUID
    resolved_at: datetime
    result: OutcomeResult
    actual: dict[str, object]
    lead_time_s: float | None = None
    note: str | None = None

    @property
    def is_scored(self) -> bool:
        """Whether this outcome counts towards precision."""
        return self.result in {"TRUE_POSITIVE", "FALSE_POSITIVE"}


@dataclass(frozen=True)
class MissedEvent:
    """Something happened and nothing predicted it. T-059, EC-26.

    Without these rows recall is not computable, and a product that reports
    precision as if it were accuracy is exactly the product this one argues
    against. A scorecard built only from predictions can only ever say how often
    the twin was right when it spoke, never how often it should have spoken.
    """

    line_id: str
    station_id: str | None
    event_type: MissedKind
    occurred_at: datetime
    predictor: Predictor


@dataclass(frozen=True)
class StateChange:
    """A predictor moving between shadow and the floor, and why."""

    predictor: Predictor
    line_id: str
    station_id: str | None
    state: PredictorState
    changed_at: datetime
    reason: str
    metrics: dict[str, object]


@dataclass
class LedgerStore:
    """Append-only predictions, their outcomes, and the gate state history."""

    predictions: list[Prediction] = field(default_factory=list)
    outcomes: dict[UUID, Outcome] = field(default_factory=dict)
    missed: list[MissedEvent] = field(default_factory=list)
    state_changes: list[StateChange] = field(default_factory=list)
    _by_id: dict[UUID, Prediction] = field(default_factory=dict, repr=False)

    # -- writing ----------------------------------------------------------

    def record(self, prediction: Prediction) -> Prediction:
        """Append one prediction. Raises if it has been recorded already."""
        if prediction.prediction_id in self._by_id:
            message = (
                f"prediction {prediction.prediction_id} is already in the ledger. "
                f"The ledger is append-only and a prediction is never rewritten"
            )
            raise ValueError(message)
        self.predictions.append(prediction)
        self._by_id[prediction.prediction_id] = prediction
        return prediction

    def resolve(self, outcome: Outcome) -> Outcome:
        """Attach the one outcome a prediction gets."""
        if outcome.prediction_id not in self._by_id:
            message = f"no prediction {outcome.prediction_id} to attach an outcome to"
            raise KeyError(message)
        if outcome.prediction_id in self.outcomes:
            message = (
                f"prediction {outcome.prediction_id} already has an outcome. "
                f"An outcome is written once and never revised"
            )
            raise ValueError(message)
        self.outcomes[outcome.prediction_id] = outcome
        return outcome

    def miss(self, event: MissedEvent) -> MissedEvent:
        """Record something that happened with no prediction in scope."""
        self.missed.append(event)
        return event

    def change_state(self, change: StateChange) -> StateChange:
        """Record a promotion, a demotion or a predictor becoming unavailable."""
        self.state_changes.append(change)
        return change

    # -- reading ----------------------------------------------------------

    def prediction(self, prediction_id: UUID) -> Prediction:
        """One prediction by identifier."""
        return self._by_id[prediction_id]

    def outcome_of(self, prediction_id: UUID) -> Outcome | None:
        """One prediction's outcome, or None while its horizon is still open."""
        return self.outcomes.get(prediction_id)

    def unresolved(self, before: datetime) -> tuple[Prediction, ...]:
        """Every prediction whose horizon has passed and that has no outcome."""
        return tuple(
            item
            for item in self.predictions
            if item.horizon_end <= before and item.prediction_id not in self.outcomes
        )

    def by_predictor(
        self, predictor: Predictor, station_id: str | None = None
    ) -> tuple[Prediction, ...]:
        """Every prediction from one predictor, optionally at one station."""
        return tuple(
            item
            for item in self.predictions
            if item.predictor == predictor
            and (station_id is None or item.station_id == station_id)
        )

    def state_of(
        self,
        predictor: Predictor,
        line_id: str,
        station_id: str | None,
        at: datetime | None = None,
    ) -> PredictorState:
        """The gate state in force for one predictor at one station.

        Defaults to `SHADOW`. A predictor that has never been assessed has not
        earned the floor, and defaulting the other way would put an unproven
        predictor in front of a supervisor on its first cycle.
        """
        state: PredictorState = "SHADOW"
        for change in self.state_changes:
            if change.predictor != predictor or change.line_id != line_id:
                continue
            if change.station_id != station_id:
                continue
            if at is not None and change.changed_at > at:
                continue
            state = change.state
        return state

    def last_change(
        self, predictor: Predictor, line_id: str, station_id: str | None
    ) -> StateChange | None:
        """The most recent state change for one predictor at one station."""
        found = [
            change
            for change in self.state_changes
            if change.predictor == predictor
            and change.line_id == line_id
            and change.station_id == station_id
        ]
        return found[-1] if found else None

    def missed_for(
        self, predictor: Predictor, station_id: str | None = None
    ) -> tuple[MissedEvent, ...]:
        """Every missed event attributed to one predictor."""
        return tuple(
            item
            for item in self.missed
            if item.predictor == predictor
            and (station_id is None or item.station_id == station_id)
        )

    def counts(self) -> dict[str, int]:
        """How much is in the ledger, for the evidence pack's own accounting."""
        by_predictor: dict[str, int] = defaultdict(int)
        for item in self.predictions:
            by_predictor[item.predictor] += 1
        return dict(by_predictor)


def make_prediction_id(*parts: object) -> UUID:
    """A prediction identifier derived from what the prediction is about.

    Deterministic, so that two runs of the same scenario at the same seed produce
    the same ledger down to the identifiers (AC-103).
    """
    return uuid5(PREDICTION_NAMESPACE, "".join(str(part) for part in parts))
