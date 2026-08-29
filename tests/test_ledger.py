"""The trust ledger, its outcome rules and its gates. T-057 to T-062.

The test that carries the phase is the one on recall.
A product that reports precision as if it were accuracy is exactly the product
this one argues against, and the whole reason `missed_event` exists is so that
the arithmetic cannot be done without the events nothing predicted.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from twin.config import LineDefinition, load_line_definition
from twin.domain.shifts import ProductionCalendar
from twin.forecast.stops import StallEpisode
from twin.ledger.gates import evaluate_gates
from twin.ledger.outcomes import DataGap, GateOutcome, Observations, OutcomeJoiner
from twin.ledger.scorecard import build_scorecard
from twin.ledger.store import (
    DRIFT_DETECTOR,
    STALL_FORECASTER,
    LedgerStore,
    MissedEvent,
    Outcome,
    Prediction,
    StateChange,
    defect_predictor,
    inputs_hash,
    make_prediction_id,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
EPOCH = datetime(2026, 3, 2, 6, 0, tzinfo=None).astimezone()


@pytest.fixture
def line() -> LineDefinition:
    return load_line_definition(REPO_ROOT / "config" / "lines" / "line2.yaml")


@pytest.fixture
def calendar(line: LineDefinition) -> ProductionCalendar:
    return ProductionCalendar(line, EPOCH)


@pytest.fixture
def store() -> LedgerStore:
    return LedgerStore()


def _at(minutes: float) -> datetime:
    return EPOCH + timedelta(minutes=minutes)


def _stall(
    store: LedgerStore,
    station_id: str,
    made_min: float,
    window_from_min: float,
    window_to_min: float,
    *,
    published: bool = False,
) -> Prediction:
    claim: dict[str, object] = {
        "kind": "STALL_FORECAST",
        "station_id": station_id,
        "window_from": _at(window_from_min).isoformat(),
        "window_to": _at(window_to_min).isoformat(),
        "probability": 0.8,
    }
    return store.record(
        Prediction(
            prediction_id=make_prediction_id(
                STALL_FORECASTER, "line2", station_id, made_min, window_from_min
            ),
            predictor=STALL_FORECASTER,
            model_version="test",
            line_id="line2",
            station_id=station_id,
            unit_id=None,
            made_at=_at(made_min),
            horizon_end=_at(window_to_min + 10),
            claim=claim,
            confidence=0.8,
            evidence={},
            inputs_hash=inputs_hash({"claim": claim}),
            published=published,
        )
    )


def _episode(station_id: str, at_min: float, lost_s: float = 200.0) -> StallEpisode:
    return StallEpisode(
        line_id="line2",
        station_id=station_id,
        started_at=_at(at_min),
        ended_at=_at(at_min + 5),
        lost_s=lost_s,
        blocked_s=lost_s,
        starved_s=0.0,
    )


# -- the store -------------------------------------------------------------


def test_the_ledger_is_append_only(store: LedgerStore) -> None:
    """T-057. Evidence that can be edited after the fact is not evidence."""
    prediction = _stall(store, "S20", 60, 90, 100)
    with pytest.raises(ValueError, match="append-only"):
        store.record(prediction)


def test_an_outcome_is_written_once(store: LedgerStore) -> None:
    """One outcome per prediction, never revised."""
    prediction = _stall(store, "S20", 60, 90, 100)
    outcome = Outcome(
        prediction_id=prediction.prediction_id,
        resolved_at=_at(110),
        result="TRUE_POSITIVE",
        actual={},
    )
    store.resolve(outcome)
    with pytest.raises(ValueError, match="already has an outcome"):
        store.resolve(outcome)


def test_a_prediction_is_recorded_before_it_may_be_published(
    store: LedgerStore,
) -> None:
    """AC-011, AC-041. Shadow mode is the only path to the screen."""
    prediction = _stall(store, "S20", 60, 90, 100, published=False)
    assert prediction in store.predictions
    assert not prediction.published
    assert store.state_of(STALL_FORECASTER, "line2", "S20") == "SHADOW"


def test_the_inputs_hash_is_stable_across_processes() -> None:
    """NFR-07. A prediction in the evidence pack reproduces on another machine."""
    payload = {"station_id": "S20", "probability": 0.71, "window": "09:52"}
    assert inputs_hash(payload) == inputs_hash(dict(reversed(list(payload.items()))))
    assert inputs_hash(payload) != inputs_hash({**payload, "probability": 0.72})


def test_a_prediction_identifier_is_derived_from_what_it_is_about() -> None:
    """AC-103. Two runs of the same scenario produce the same identifiers."""
    first = make_prediction_id(STALL_FORECASTER, "line2", "S20", "09:00")
    second = make_prediction_id(STALL_FORECASTER, "line2", "S20", "09:00")
    assert first == second
    assert first != make_prediction_id(STALL_FORECASTER, "line2", "S21", "09:00")


def test_a_horizon_cannot_run_backwards(store: LedgerStore) -> None:
    """A prediction nothing could ever score is a bug, not a record."""
    with pytest.raises(ValueError, match="before"):
        Prediction(
            prediction_id=make_prediction_id("x"),
            predictor=STALL_FORECASTER,
            model_version="test",
            line_id="line2",
            station_id="S20",
            unit_id=None,
            made_at=_at(100),
            horizon_end=_at(50),
            claim={},
            confidence=0.5,
            evidence={},
            inputs_hash="",
            published=False,
        )


# -- outcome joining -------------------------------------------------------


def test_a_stall_at_or_downstream_of_the_target_is_a_hit(
    line: LineDefinition, calendar: ProductionCalendar, store: LedgerStore
) -> None:
    """T-058, TECHNICAL_SPEC 9.2."""
    joiner = OutcomeJoiner(line, calendar, store)
    prediction = _stall(store, "S20", 60, 90, 100)
    joiner.join(
        _at(200),
        Observations(
            episodes=(_episode("S22", 95),),
            observed_until=_at(300),
            fed_until=_at(300),
        ),
    )
    outcome = store.outcome_of(prediction.prediction_id)
    assert outcome is not None
    assert outcome.result == "TRUE_POSITIVE"
    assert outcome.lead_time_s == pytest.approx(35 * 60.0)


def test_a_stall_upstream_of_the_target_is_not_a_hit(
    line: LineDefinition, calendar: ProductionCalendar, store: LedgerStore
) -> None:
    """The scope is at or downstream, because that is what the forecast claimed."""
    joiner = OutcomeJoiner(line, calendar, store)
    prediction = _stall(store, "S20", 60, 90, 100)
    joiner.join(
        _at(200),
        Observations(
            episodes=(_episode("S05", 95),),
            observed_until=_at(300),
            fed_until=_at(300),
        ),
    )
    outcome = store.outcome_of(prediction.prediction_id)
    assert outcome is not None
    assert outcome.result == "FALSE_POSITIVE"


def test_the_tolerance_extends_the_window_but_not_indefinitely(
    line: LineDefinition, calendar: ProductionCalendar, store: LedgerStore
) -> None:
    """A stall nine minutes late is the one that was forecast. Eleven is not."""
    joiner = OutcomeJoiner(line, calendar, store)
    inside = _stall(store, "S20", 60, 90, 100)
    joiner.join(
        _at(200),
        Observations(
            episodes=(_episode("S22", 109),),
            observed_until=_at(300),
            fed_until=_at(300),
        ),
    )
    assert store.outcome_of(inside.prediction_id).result == "TRUE_POSITIVE"
    store_two = LedgerStore()
    later = OutcomeJoiner(line, calendar, store_two)
    late = _stall(store_two, "S20", 60, 90, 100)
    later.join(
        _at(200),
        Observations(
            episodes=(_episode("S22", 115),),
            observed_until=_at(300),
            fed_until=_at(300),
        ),
    )
    assert store_two.outcome_of(late.prediction_id).result == "FALSE_POSITIVE"


def test_a_window_inside_a_data_gap_is_unscoreable(
    line: LineDefinition, calendar: ProductionCalendar, store: LedgerStore
) -> None:
    """EC-46. The twin was not watching, so it cannot be scored either way."""
    joiner = OutcomeJoiner(line, calendar, store)
    prediction = _stall(store, "S20", 60, 90, 100)
    joiner.join(
        _at(200),
        Observations(
            episodes=(),
            gaps=(DataGap(started_at=_at(88), ended_at=_at(102)),),
            observed_until=_at(300),
            fed_until=_at(300),
        ),
    )
    outcome = store.outcome_of(prediction.prediction_id)
    assert outcome is not None
    assert outcome.result == "UNSCOREABLE"
    assert "silent" in (outcome.note or "")


def test_a_window_inside_a_shift_break_is_unscoreable(
    line: LineDefinition, calendar: ProductionCalendar, store: LedgerStore
) -> None:
    """EC-11. A planned stop is not a stall."""
    joiner = OutcomeJoiner(line, calendar, store)
    # Shift A opens at 06:20 and closes at 14:30, so a window in the small hours
    # of the next morning is entirely outside production.
    prediction = _stall(store, "S20", 60, 20 * 60, 20 * 60 + 20)
    joiner.join(
        _at(24 * 60),
        Observations(episodes=(), observed_until=_at(30 * 60), fed_until=_at(30 * 60)),
    )
    outcome = store.outcome_of(prediction.prediction_id)
    assert outcome is not None
    assert outcome.result == "UNSCOREABLE"
    assert "planned stop" in (outcome.note or "")


def test_a_prediction_the_supervisor_acted_on_is_unscoreable(
    line: LineDefinition, calendar: ProductionCalendar, store: LedgerStore
) -> None:
    """EC-25. The hardest scoring problem in the product."""
    joiner = OutcomeJoiner(line, calendar, store)
    prediction = _stall(store, "S20", 60, 90, 100)
    joiner.join(
        _at(200),
        Observations(
            episodes=(),
            acted_on=frozenset({str(prediction.prediction_id)}),
            observed_until=_at(300),
            fed_until=_at(300),
        ),
    )
    outcome = store.outcome_of(prediction.prediction_id)
    assert outcome is not None
    assert outcome.result == "UNSCOREABLE"
    assert "prevented" in (outcome.note or "")


def test_a_window_past_the_end_of_the_evidence_is_unscoreable(
    line: LineDefinition, calendar: ProductionCalendar, store: LedgerStore
) -> None:
    """No evidence either way is not the same as being wrong."""
    joiner = OutcomeJoiner(line, calendar, store)
    prediction = _stall(store, "S20", 60, 90, 100)
    joiner.join(
        _at(200),
        Observations(episodes=(), observed_until=_at(95), fed_until=_at(95)),
    )
    outcome = store.outcome_of(prediction.prediction_id)
    assert outcome is not None
    assert outcome.result == "UNSCOREABLE"


def test_a_unit_that_never_reached_its_gate_is_unscoreable(
    line: LineDefinition, calendar: ProductionCalendar, store: LedgerStore
) -> None:
    """EC-33. The prediction was about a verdict that will never exist."""
    joiner = OutcomeJoiner(line, calendar, store)
    claim: dict[str, object] = {
        "kind": "DEFECT_RISK",
        "gate_id": "G3",
        "flagged": True,
    }
    prediction = store.record(
        Prediction(
            prediction_id=make_prediction_id("defect", "3C4PDCBG7JT100001"),
            predictor=defect_predictor("G3"),
            model_version="test",
            line_id="line2",
            station_id="S28",
            unit_id="3C4PDCBG7JT100001",
            made_at=_at(60),
            horizon_end=_at(90),
            claim=claim,
            confidence=0.6,
            evidence={},
            inputs_hash="",
            published=False,
        )
    )
    joiner.join(
        _at(200),
        Observations(
            units_without_outcome=frozenset({"3C4PDCBG7JT100001"}),
            observed_until=_at(300),
            fed_until=_at(300),
        ),
    )
    outcome = store.outcome_of(prediction.prediction_id)
    assert outcome is not None
    assert outcome.result == "UNSCOREABLE"


def test_a_defect_prediction_is_scored_against_the_gate_result(
    line: LineDefinition, calendar: ProductionCalendar, store: LedgerStore
) -> None:
    """T-058. The outcome is the verdict, and nothing else."""
    joiner = OutcomeJoiner(line, calendar, store)
    for unit_id, flagged, passed, expected in (
        ("3C4PDCBG7JT100001", True, False, "TRUE_POSITIVE"),
        ("3C4PDCBG7JT100002", True, True, "FALSE_POSITIVE"),
        ("3C4PDCBG7JT100003", False, False, "FALSE_NEGATIVE"),
        ("3C4PDCBG7JT100004", False, True, "TRUE_NEGATIVE"),
    ):
        claim: dict[str, object] = {
            "kind": "DEFECT_RISK",
            "gate_id": "G3",
            "flagged": flagged,
        }
        prediction = store.record(
            Prediction(
                prediction_id=make_prediction_id("defect", unit_id),
                predictor=defect_predictor("G3"),
                model_version="test",
                line_id="line2",
                station_id="S28",
                unit_id=unit_id,
                made_at=_at(60),
                horizon_end=_at(90),
                claim=claim,
                confidence=0.6,
                evidence={},
                inputs_hash="",
                published=False,
            )
        )
        joiner.join(
            _at(200),
            Observations(
                gate_results=(GateOutcome(unit_id, "G3", _at(95), passed=passed),),
                observed_until=_at(300),
                fed_until=_at(300),
            ),
        )
        assert store.outcome_of(prediction.prediction_id).result == expected


# -- missed events and recall ----------------------------------------------


def test_a_stall_with_nothing_in_scope_is_recorded_as_missed(
    line: LineDefinition, calendar: ProductionCalendar, store: LedgerStore
) -> None:
    """T-059, EC-26. Recall that is never measured is recall that is claimed."""
    joiner = OutcomeJoiner(line, calendar, store)
    written = joiner.record_misses(
        Observations(
            episodes=(_episode("S22", 95),),
            observed_until=_at(300),
            fed_until=_at(300),
        ),
        up_to=_at(200),
    )
    assert len(written) == 1
    assert written[0].event_type == "STALL"
    assert written[0].predictor == STALL_FORECASTER


def test_a_stall_a_forecast_covered_is_not_missed(
    line: LineDefinition, calendar: ProductionCalendar, store: LedgerStore
) -> None:
    """Recall and precision have to use the same scope, or they measure two things."""
    joiner = OutcomeJoiner(line, calendar, store)
    _stall(store, "S20", 60, 90, 100)
    written = joiner.record_misses(
        Observations(
            episodes=(_episode("S22", 95),),
            observed_until=_at(300),
            fed_until=_at(300),
        ),
        up_to=_at(200),
    )
    assert written == ()


def test_recall_is_not_computable_from_predictions_alone(
    line: LineDefinition, calendar: ProductionCalendar, store: LedgerStore
) -> None:
    """T-062. The test the whole ledger exists for.

    Two ledgers with identical predictions and identical outcomes, differing only
    in whether the events nothing predicted were recorded. Precision is the same
    in both. Recall is not, and a scorecard that could not tell them apart would
    be reporting precision as accuracy.
    """
    joiner = OutcomeJoiner(line, calendar, store)
    hit = _stall(store, "S20", 60, 90, 100)
    joiner.join(
        _at(200),
        Observations(
            episodes=(_episode("S22", 95),),
            observed_until=_at(300),
            fed_until=_at(300),
        ),
    )
    assert store.outcome_of(hit.prediction_id).result == "TRUE_POSITIVE"

    without = build_scorecard(store, line, calendar, _at(300))
    row_without = without.row(STALL_FORECASTER, "S20")
    assert row_without is not None
    assert row_without.precision == 1.0
    assert row_without.recall == 1.0

    for index in range(9):
        store.miss(
            MissedEvent(
                line_id="line2",
                station_id="S20",
                event_type="STALL",
                occurred_at=_at(120 + index),
                predictor=STALL_FORECASTER,
            )
        )
    with_misses = build_scorecard(store, line, calendar, _at(300))
    row = with_misses.row(STALL_FORECASTER, "S20")
    assert row is not None
    assert row.precision == 1.0, "precision must not move: the predictions are the same"
    assert row.recall == pytest.approx(0.1), (
        "recall has to fall, and a view over predictions alone could not see it"
    )


def test_a_shadow_row_never_returns_a_precision(
    line: LineDefinition, calendar: ProductionCalendar, store: LedgerStore
) -> None:
    """API_SPEC Section 6. An unpromoted hit rate invites misplaced trust."""
    joiner = OutcomeJoiner(line, calendar, store)
    _stall(store, "S20", 60, 90, 100)
    joiner.join(
        _at(200),
        Observations(
            episodes=(_episode("S22", 95),),
            observed_until=_at(300),
            fed_until=_at(300),
        ),
    )
    row = build_scorecard(store, line, calendar, _at(300)).row(STALL_FORECASTER, "S20")
    assert row is not None
    assert row.state == "SHADOW"
    assert row.published_precision is None
    assert row.precision is not None, "the gate still needs to see it"


# -- the gates -------------------------------------------------------------


def _record_run(
    store: LedgerStore,
    line: LineDefinition,
    calendar: ProductionCalendar,
    hits: int,
    misses: int,
    station_id: str = "S20",
) -> None:
    joiner = OutcomeJoiner(line, calendar, store)
    for index in range(hits + misses):
        made = 60 + index * 30
        _stall(store, station_id, made, made + 30, made + 40)
        episodes = (_episode(station_id, made + 32),) if index < hits else ()
        joiner.join(
            _at(made + 100),
            Observations(
                episodes=episodes,
                observed_until=_at(made + 200),
                fed_until=_at(made + 200),
            ),
        )


def test_a_predictor_starts_in_shadow_and_stays_there_until_it_earns_the_floor(
    line: LineDefinition, calendar: ProductionCalendar, store: LedgerStore
) -> None:
    """AC-041. A predictor that has never been assessed has not earned the floor."""
    _record_run(store, line, calendar, hits=5, misses=0)
    scorecard = build_scorecard(store, line, calendar, _at(2000))
    decisions = evaluate_gates(store, line, scorecard, _at(2000))
    decision = next(item for item in decisions if item.station_id == "S20")
    assert decision.now == "SHADOW"
    assert not decision.changed
    assert "Learning" in decision.reason


def test_a_predictor_that_clears_its_gate_is_promoted(
    line: LineDefinition, calendar: ProductionCalendar, store: LedgerStore
) -> None:
    """T-061. Per station, on that station's own evidence."""
    _record_run(store, line, calendar, hits=24, misses=1)
    scorecard = build_scorecard(store, line, calendar, _at(3000))
    decisions = evaluate_gates(store, line, scorecard, _at(3000))
    decision = next(item for item in decisions if item.station_id == "S20")
    assert decision.now == "ACTIVE", decision.reason
    assert decision.changed
    assert "Promoted" in decision.reason
    assert store.state_of(STALL_FORECASTER, "line2", "S20", _at(3000)) == "ACTIVE"


def test_a_predictor_whose_precision_falls_is_withdrawn(
    line: LineDefinition, calendar: ProductionCalendar, store: LedgerStore
) -> None:
    """AC-042. With the numbers that caused it, which the interface reads."""
    store.change_state(
        StateChange(
            predictor=STALL_FORECASTER,
            line_id="line2",
            station_id="S20",
            state="ACTIVE",
            changed_at=_at(0),
            reason="Promoted: set up by the test",
            metrics={},
        )
    )
    _record_run(store, line, calendar, hits=4, misses=8)
    scorecard = build_scorecard(store, line, calendar, _at(3000))
    decisions = evaluate_gates(store, line, scorecard, _at(3000))
    decision = next(item for item in decisions if item.station_id == "S20")
    assert decision.now == "SHADOW"
    assert decision.changed
    assert "Withdrawn" in decision.reason
    assert decision.metrics["precision"] is not None
    change = store.last_change(STALL_FORECASTER, "line2", "S20")
    assert change is not None
    assert change.metrics["false_positive"] == 8


def test_a_withdrawn_predictor_cannot_return_during_its_cooling_period(
    line: LineDefinition, calendar: ProductionCalendar, store: LedgerStore
) -> None:
    """EC-44. A predictor that flickers is worse for trust than one that is off."""
    store.change_state(
        StateChange(
            predictor=STALL_FORECASTER,
            line_id="line2",
            station_id="S20",
            state="SHADOW",
            changed_at=_at(0),
            reason="Withdrawn: precision fell to 0.42 over 12 scored predictions",
            metrics={},
        )
    )
    _record_run(store, line, calendar, hits=24, misses=1)
    at = _at(60)
    scorecard = build_scorecard(store, line, calendar, at)
    decisions = evaluate_gates(store, line, scorecard, at)
    decision = next(item for item in decisions if item.station_id == "S20")
    assert not decision.changed
    assert "Cannot return to the floor" in decision.reason


def test_promotion_and_demotion_cannot_both_apply(line: LineDefinition) -> None:
    """The hysteresis is enforced by the configuration model itself."""
    assert (
        line.gates_policy.demotion.max_precision
        < line.gates_policy.promotion.min_precision
    )


def test_the_scorecard_reports_false_alerts_per_shift(
    line: LineDefinition, calendar: ProductionCalendar, store: LedgerStore
) -> None:
    """AC-043. A column, not a drill-down."""
    _record_run(store, line, calendar, hits=2, misses=6)
    row = build_scorecard(store, line, calendar, _at(3000)).row(STALL_FORECASTER, "S20")
    assert row is not None
    assert row.false_per_shift is not None
    assert row.false_per_shift > 0


def test_the_unscoreable_share_is_reported(
    line: LineDefinition, calendar: ProductionCalendar, store: LedgerStore
) -> None:
    """DATABASE_SCHEMA Section 5. The share is itself a number worth seeing."""
    joiner = OutcomeJoiner(line, calendar, store)
    _stall(store, "S20", 60, 90, 100)
    joiner.join(
        _at(200), Observations(episodes=(), observed_until=_at(95), fed_until=_at(95))
    )
    row = build_scorecard(store, line, calendar, _at(300)).row(STALL_FORECASTER, "S20")
    assert row is not None
    assert row.unscoreable == 1
    assert row.unscoreable_share == 1.0
    assert row.precision is None


def test_a_drift_claim_is_scored_against_the_baseline_that_followed(
    line: LineDefinition, calendar: ProductionCalendar, store: LedgerStore
) -> None:
    """T-058. The station's baseline has to have moved the way it was claimed."""
    joiner = OutcomeJoiner(line, calendar, store)
    claim: dict[str, object] = {
        "kind": "DRIFT",
        "station_id": "S20",
        "variant_id": "V-STD",
        "onset": _at(60).isoformat(),
        "direction": "UP",
        "magnitude_s": 4.0,
    }
    drift = store.record(
        Prediction(
            prediction_id=make_prediction_id(DRIFT_DETECTOR, "S20", "1"),
            predictor=DRIFT_DETECTOR,
            model_version="test",
            line_id="line2",
            station_id="S20",
            unit_id=None,
            made_at=_at(80),
            horizon_end=_at(200),
            claim=claim,
            confidence=0.7,
            evidence={},
            inputs_hash="",
            published=False,
        )
    )

    def baseline(
        station_id: str, variant_id: str, start: datetime, end: datetime
    ) -> float | None:
        del station_id, variant_id
        return 58.0 if end <= _at(60) else 62.0

    joiner.join(
        _at(300),
        Observations(baseline=baseline, observed_until=_at(400), fed_until=_at(400)),
    )
    outcome = store.outcome_of(drift.prediction_id)
    assert outcome is not None
    assert outcome.result == "TRUE_POSITIVE"
    assert outcome.lead_time_s is None, "a detection lag is not a lead time"
    assert outcome.actual["onset_lag_s"] == pytest.approx(20 * 60.0)
