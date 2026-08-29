"""Joining predictions to what happened. T-058, T-059, T-060.

TECHNICAL_SPEC.md Section 9.2. A job runs each cycle over the predictions whose
horizon has passed and writes exactly one outcome for each. No human labels
anything in this loop, and that is what makes the scorecard credible: there is
nobody in the path who could decide that a near miss was really a hit.

**The three things that are not a hit or a miss.**

`UNSCOREABLE` is the honest category and it carries three cases. A prediction
whose window fell inside a data gap cannot be scored either way, because the twin
was not watching (EC-46). A prediction whose window fell inside a shift break did
not have a line to be right about (EC-11). A prediction the supervisor acted on
cannot be scored at all: counting a prevented stall as a false positive punishes
the system for working, counting it as a true positive lets it claim credit for
an event that did not occur, and both are wrong, so it is excluded and counted
separately (EC-25). The share of unscoreable predictions is itself reported.

`missed_event` is the other half of the arithmetic. A stall that happened with no
prediction in scope produces a row, and without those rows recall is not
computable (EC-26, T-059). A view over predictions alone can only say how often
the twin was right when it spoke.

A unit scrapped before it reached the gate its risk was scored against is
`UNSCOREABLE` too (EC-33). The prediction was about a gate result that will never
exist.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from twin.config.line import LineDefinition
from twin.domain.shifts import ProductionCalendar
from twin.forecast.stops import StallEpisode
from twin.ledger.store import (
    DRIFT_DETECTOR,
    STALL_FORECASTER,
    LedgerStore,
    MissedEvent,
    Outcome,
    OutcomeResult,
    Prediction,
)

# How far past its window a stall still counts as the one that was forecast.
# TECHNICAL_SPEC.md Section 9.2 default.
TOLERANCE_MIN = 10.0

# A window with less than this share of it producing is not a window the line
# could have stalled in, so a prediction over it is unscoreable rather than
# wrong (EC-11).
_MINIMUM_PRODUCING_SHARE = 0.5


@dataclass(frozen=True)
class GateOutcome:
    """One inspection verdict as the twin observed it, not as truth recorded it."""

    unit_id: str
    gate_id: str
    at: datetime
    passed: bool


@dataclass(frozen=True)
class DataGap:
    """A span during which a source was silent. EC-46."""

    started_at: datetime
    ended_at: datetime
    affected_stations: tuple[str, ...] = ()

    def covers(self, start: datetime, end: datetime) -> bool:
        """Whether this gap overlaps a window at all."""
        return self.started_at < end and self.ended_at > start


@dataclass
class Observations:
    """Everything the joiner needs to say what happened.

    All of it is what the twin itself observed. Ground truth never enters this
    path: the evaluation harness compares the two afterwards, which is a
    different question and is reported as one.
    """

    episodes: tuple[StallEpisode, ...] = ()
    gate_results: tuple[GateOutcome, ...] = ()
    gaps: tuple[DataGap, ...] = ()
    # Units that left the line without reaching the gate they were scored for.
    units_without_outcome: frozenset[str] = frozenset()
    # Predictions the supervisor marked as acted on. EC-25.
    acted_on: frozenset[str] = frozenset()
    # The station baseline over a span, for scoring a drift claim. Returns None
    # where the span holds too few cycles to say anything.
    baseline: Callable[[str, str, datetime, datetime], float | None] | None = None
    # The last instant the twin was watching. A forecast whose window runs past
    # it cannot be scored: there is no evidence either way, and calling it wrong
    # would punish the forecaster for the recording having stopped.
    observed_until: datetime | None = None
    # The last instant the line was still being fed. Everything after it is the
    # line draining, and a draining line starves at every station by
    # construction. Scoring a forecast against a drain would flatter it and
    # scoring the drain as a stall the forecast missed would damn it, so the
    # drain is excluded from both sides of the arithmetic.
    fed_until: datetime | None = None


@dataclass
class OutcomeJoiner:
    """Writes one outcome per elapsed prediction, and the misses beside them."""

    line: LineDefinition
    calendar: ProductionCalendar
    store: LedgerStore
    tolerance_min: float = TOLERANCE_MIN
    _missed_seen: set[tuple[str, str]] = field(default_factory=set, repr=False)

    def join(self, now: datetime, observations: Observations) -> tuple[Outcome, ...]:
        """Score every prediction whose horizon has closed."""
        written: list[Outcome] = []
        for prediction in self.store.unresolved(before=now):
            outcome = self._score(prediction, observations)
            if outcome is not None:
                written.append(self.store.resolve(outcome))
        return tuple(written)

    def record_misses(
        self, observations: Observations, up_to: datetime
    ) -> tuple[MissedEvent, ...]:
        """Write a row for every stall nothing had in scope. T-059, EC-26."""
        written: list[MissedEvent] = []
        limit = min(
            [up_to]
            + [
                value
                for value in (observations.observed_until, observations.fed_until)
                if value is not None
            ]
        )
        for episode in observations.episodes:
            if episode.started_at > limit:
                continue
            key = (episode.station_id, episode.started_at.isoformat())
            if key in self._missed_seen:
                continue
            self._missed_seen.add(key)
            if self._in_scope(episode):
                continue
            written.append(
                self.store.miss(
                    MissedEvent(
                        line_id=episode.line_id,
                        station_id=episode.station_id,
                        event_type="STALL",
                        occurred_at=episode.started_at,
                        predictor=STALL_FORECASTER,
                    )
                )
            )
        return tuple(written)

    # -- the rules --------------------------------------------------------

    def _score(
        self, prediction: Prediction, observations: Observations
    ) -> Outcome | None:
        if prediction.predictor == STALL_FORECASTER:
            return self._score_stall(prediction, observations)
        if prediction.predictor == DRIFT_DETECTOR:
            return self._score_drift(prediction, observations)
        if prediction.predictor.startswith("defect_risk_"):
            return self._score_defect(prediction, observations)
        return None

    def _score_stall(
        self, prediction: Prediction, observations: Observations
    ) -> Outcome:
        window_from = _moment(prediction.claim["window_from"])
        window_to = _moment(prediction.claim["window_to"])
        extended = window_to + timedelta(minutes=self.tolerance_min)

        unscoreable = self._unscoreable_window(
            prediction, observations, window_from, extended
        )
        if unscoreable is not None:
            return unscoreable

        order = self.line.station_ids
        target = prediction.station_id
        at_or_downstream = (
            set(order[order.index(target) :]) if target in order else set(order)
        )
        hits = [
            episode
            for episode in observations.episodes
            if episode.station_id in at_or_downstream
            and window_from <= episode.started_at <= extended
        ]
        if not hits:
            return Outcome(
                prediction_id=prediction.prediction_id,
                resolved_at=extended,
                result="FALSE_POSITIVE",
                actual={
                    "stalls_in_window": 0,
                    "window_from": window_from.isoformat(),
                    "window_to": extended.isoformat(),
                    "scope": "at or downstream of the forecast station",
                },
                note=(
                    f"no station at or downstream of {target} lost more than "
                    f"{self.line.forecast.stall_threshold_s:.0f} s in a bucket "
                    f"inside the window"
                ),
            )
        first = min(hits, key=lambda episode: episode.started_at)
        return Outcome(
            prediction_id=prediction.prediction_id,
            resolved_at=extended,
            result="TRUE_POSITIVE",
            actual={
                "stalls_in_window": len(hits),
                "station_id": first.station_id,
                "started_at": first.started_at.isoformat(),
                "lost_s": round(first.lost_s, 1),
                "dominant": first.dominant,
            },
            lead_time_s=(first.started_at - prediction.made_at).total_seconds(),
        )

    def _unscoreable_window(
        self,
        prediction: Prediction,
        observations: Observations,
        window_from: datetime,
        window_to: datetime,
    ) -> Outcome | None:
        if (
            observations.observed_until is not None
            and window_to > observations.observed_until
        ):
            return Outcome(
                prediction_id=prediction.prediction_id,
                resolved_at=window_to,
                result="UNSCOREABLE",
                actual={
                    "observed_until": observations.observed_until.isoformat(),
                    "window_to": window_to.isoformat(),
                },
                note=(
                    "the window runs past the end of the recorded run, so there "
                    "is no evidence either way"
                ),
            )
        if observations.fed_until is not None and window_from > observations.fed_until:
            return Outcome(
                prediction_id=prediction.prediction_id,
                resolved_at=window_to,
                result="UNSCOREABLE",
                actual={
                    "fed_until": observations.fed_until.isoformat(),
                    "window_from": window_from.isoformat(),
                },
                note=(
                    "the last unit was released before this window opened, so "
                    "the line was draining rather than running and every station "
                    "starves in a drain whatever the forecast said"
                ),
            )
        if str(prediction.prediction_id) in observations.acted_on:
            return Outcome(
                prediction_id=prediction.prediction_id,
                resolved_at=window_to,
                result="UNSCOREABLE",
                actual={"acted_on": True},
                note=(
                    "the supervisor recorded acting on this forecast, so whether "
                    "the stall would have happened cannot be established. Counted "
                    "separately as a probable prevented stall (EC-25)"
                ),
            )
        for gap in observations.gaps:
            if gap.covers(window_from, window_to):
                return Outcome(
                    prediction_id=prediction.prediction_id,
                    resolved_at=window_to,
                    result="UNSCOREABLE",
                    actual={
                        "gap_from": gap.started_at.isoformat(),
                        "gap_to": gap.ended_at.isoformat(),
                    },
                    note=(
                        "a source was silent for part of this window, so the twin "
                        "was not watching and the forecast cannot be scored "
                        "either way (EC-46)"
                    ),
                )
        epoch = self.calendar.epoch
        span = (window_to - window_from).total_seconds()
        producing = self.calendar.production_between(
            (window_from - epoch).total_seconds(), (window_to - epoch).total_seconds()
        )
        if span > 0 and producing / span < _MINIMUM_PRODUCING_SHARE:
            return Outcome(
                prediction_id=prediction.prediction_id,
                resolved_at=window_to,
                result="UNSCOREABLE",
                actual={"producing_share": round(producing / span, 3)},
                note=(
                    "the line was stopped for most of this window, and a planned "
                    "stop is not a stall (EC-11)"
                ),
            )
        return None

    def _score_drift(
        self, prediction: Prediction, observations: Observations
    ) -> Outcome | None:
        if observations.baseline is None:
            return None
        station_id = prediction.station_id or ""
        variant_id = str(prediction.claim.get("variant_id", ""))
        onset = _moment(prediction.claim["onset"])
        magnitude = _number(prediction.claim["magnitude_s"])
        direction = str(prediction.claim["direction"])
        span = prediction.horizon_end - prediction.made_at
        before = observations.baseline(station_id, variant_id, onset - span, onset)
        after = observations.baseline(
            station_id,
            variant_id,
            prediction.horizon_end - span,
            prediction.horizon_end,
        )
        if before is None or after is None:
            return Outcome(
                prediction_id=prediction.prediction_id,
                resolved_at=prediction.horizon_end,
                result="UNSCOREABLE",
                actual={"before": before, "after": after},
                note=(
                    "too few comparable cycles either side of the claimed onset "
                    "to measure whether the baseline moved"
                ),
            )
        moved = after - before
        held = (
            moved >= abs(magnitude) * _DRIFT_AGREEMENT
            if direction == "UP"
            else -moved >= abs(magnitude) * _DRIFT_AGREEMENT
        )
        return Outcome(
            prediction_id=prediction.prediction_id,
            resolved_at=prediction.horizon_end,
            result="TRUE_POSITIVE" if held else "FALSE_POSITIVE",
            actual={
                "baseline_before_s": round(before, 2),
                "baseline_after_s": round(after, 2),
                "moved_s": round(moved, 2),
                "claimed_s": round(magnitude, 2),
                "direction": direction,
                # How long the drift had been running before the charts caught
                # it. A cost rather than a lead, which is why it is recorded here
                # and not in `lead_time_s`: a detection lag averaged into a
                # forecaster's lead times would make both numbers meaningless.
                "onset_lag_s": round((prediction.made_at - onset).total_seconds(), 1),
            },
            lead_time_s=None,
        )

    def _score_defect(
        self, prediction: Prediction, observations: Observations
    ) -> Outcome | None:
        unit_id = prediction.unit_id or ""
        gate_id = str(prediction.claim.get("gate_id", ""))
        verdict = next(
            (
                item
                for item in observations.gate_results
                if item.unit_id == unit_id and item.gate_id == gate_id
            ),
            None,
        )
        if verdict is None:
            if unit_id in observations.units_without_outcome:
                return Outcome(
                    prediction_id=prediction.prediction_id,
                    resolved_at=prediction.horizon_end,
                    result="UNSCOREABLE",
                    actual={"reached_gate": False},
                    note=(
                        f"{unit_id} left the line before it reached {gate_id}, so "
                        f"there is no verdict to score this against (EC-33)"
                    ),
                )
            return None
        flagged = bool(prediction.claim.get("flagged", False))
        failed = not verdict.passed
        result: OutcomeResult
        if flagged and failed:
            result = "TRUE_POSITIVE"
        elif flagged:
            result = "FALSE_POSITIVE"
        elif failed:
            result = "FALSE_NEGATIVE"
        else:
            result = "TRUE_NEGATIVE"
        return Outcome(
            prediction_id=prediction.prediction_id,
            resolved_at=verdict.at,
            result=result,
            actual={"passed": verdict.passed, "gate_id": gate_id},
            lead_time_s=(verdict.at - prediction.made_at).total_seconds(),
        )

    # -- scope ------------------------------------------------------------

    def _in_scope(self, episode: StallEpisode) -> bool:
        """Whether any stall forecast covered this episode.

        A forecast at or upstream of the station covers it, because the outcome
        rule scores a forecast against a stall at or downstream of its target. A
        recall figure has to use the same scope as the precision figure beside
        it, or the two are not measuring the same predictor.
        """
        order = self.line.station_ids
        if episode.station_id not in order:
            return False
        limit = order.index(episode.station_id)
        for prediction in self.store.by_predictor(STALL_FORECASTER):
            target = prediction.station_id
            if target not in order or order.index(target) > limit:
                continue
            window_from = _moment(prediction.claim["window_from"])
            window_to = _moment(prediction.claim["window_to"]) + timedelta(
                minutes=self.tolerance_min
            )
            if window_from <= episode.started_at <= window_to:
                return True
        return False


# How much of the claimed movement has to be there for a drift claim to hold. A
# drift detector that claimed 5 s and delivered 4.5 s was right about the station
# and close enough about the size to be worth reading.
_DRIFT_AGREEMENT = 0.5


def _number(value: object) -> float:
    """Read a quantity out of a claim, which the ledger stores untyped."""
    if isinstance(value, int | float):
        return float(value)
    return float(str(value))


def _moment(value: object) -> datetime:
    """Read a timestamp out of a claim, which is stored as text in the ledger."""
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))
