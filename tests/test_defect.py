"""The defect risk model. T-063 to T-068.

The two that carry the phase are `test_no_unit_spans_the_split_boundary`, because
a leaked split produces a number that cannot be reproduced in a plant, and
`test_a_feature_without_a_template_cannot_be_surfaced`, because AC-022 is the
rule that keeps raw feature names off a supervisor's screen.
"""

from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest

from plantsim.model import SimulationRequest, run_simulation
from plantsim.parameters import load_plant_model
from plantsim.scenarios import load_scenarios
from twin.config import LineDefinition, load_line_definition
from twin.defect.conformal import calibrate, empirical_coverage
from twin.defect.explain import FACTOR_TEMPLATES, TOP_FACTORS, Explainer
from twin.defect.features import FeatureRow, feature_names
from twin.defect.model import ECE_TARGET, reliability, temporal_split
from twin.domain.shifts import ProductionCalendar
from twin.pipeline import TwinPipeline

REPO_ROOT = Path(__file__).resolve().parent.parent


def _line() -> LineDefinition:
    return load_line_definition(REPO_ROOT / "config" / "lines" / "line2.yaml")


def _plant():
    return load_plant_model(REPO_ROOT / "config" / "plantsim" / "line2.yaml")


@pytest.fixture(scope="module")
def trained() -> TwinPipeline:
    """A pipeline that has seen enough units for its gates to fit a model."""
    line, plant = _line(), _plant()
    catalogue = load_scenarios(REPO_ROOT / "config" / "plantsim" / "scenarios.yaml")
    result = run_simulation(
        SimulationRequest(
            line=line,
            plant=plant,
            seed=20260301,
            units=2400,
            scenario=catalogue.build("SC-02", "line2"),
        )
    )
    pipeline = TwinPipeline(
        line=line,
        calendar=ProductionCalendar(line, plant.epoch),
        replications=1,
        cadence_s=1800.0,
        horizon_min=30,
    )
    pipeline.feed(result.events)
    pipeline.defect.train(result.truth.epoch)
    return pipeline


# -- features --------------------------------------------------------------


def test_the_feature_set_is_derived_from_the_line(trained: TwinPipeline) -> None:
    """T-063. No station identifier is hard coded, so a second line needs none."""
    service = trained.defect.gates["G3"]
    names = feature_names(service.builder)
    assert names
    for station_id in service.builder.span:
        assert f"cycle_z_{station_id}" in names
    assert "dark_visits" in names
    assert "measured_share" in names


def test_missingness_survives_into_the_row(trained: TwinPipeline) -> None:
    """DEF-03. A missing value means a station was dark, and that is information."""
    service = trained.defect.gates["G3"]
    rows = [row for row in service.rows if row.failed is not None]
    assert rows
    dark = {
        station.station_id for station in trained.line.stations if station.tier == "C"
    }
    for station_id in dark & set(service.builder.span):
        column = f"cycle_z_{station_id}"
        values = [row.values.get(column, math.nan) for row in rows]
        assert all(math.isnan(value) for value in values), (
            f"{station_id} emits nothing, so its z-score cannot be a number"
        )


def test_a_unit_that_passed_dark_stations_says_so(trained: TwinPipeline) -> None:
    """AC-025. The count of dark stations visited is a feature and it is shown."""
    service = trained.defect.gates["G3"]
    rows = [row for row in service.rows if row.failed is not None]
    counts = {row.values.get("dark_visits", 0.0) for row in rows}
    assert max(counts) > 0, "no unit recorded a dark visit on a line with six"


def test_the_lot_rate_cannot_see_the_unit_it_scores(trained: TwinPipeline) -> None:
    """T-063. A rate over the whole run leaks the answer through shared lots."""
    service = trained.defect.gates["G3"]
    ordered = sorted(
        (row for row in service.rows if row.failed is not None),
        key=lambda row: row.at,
    )
    first = ordered[0]
    total = len(ordered)
    # The rate the earliest row carries rests on the handful of units that had
    # already cleared the gate when it was scored, not on the thousands that
    # eventually did. A rate computed over the whole run would leak the answer
    # through every unit that shares a lot.
    assert first.values["lot_units_seen"] < total / 20
    assert all(row.values["lot_units_seen"] <= total for row in ordered)


# -- the split -------------------------------------------------------------


def test_the_split_is_temporal(trained: TwinPipeline) -> None:
    """T-064, TECHNICAL_SPEC 6.2. Never random."""
    service = trained.defect.gates["G3"]
    rows = tuple(row for row in service.rows if row.failed is not None)
    split = temporal_split(rows)
    assert split.train and split.calibrate and split.holdout
    assert max(row.at for row in split.train) <= min(row.at for row in split.calibrate)
    assert max(row.at for row in split.calibrate) <= min(
        row.at for row in split.holdout
    )


def test_no_unit_spans_the_split_boundary(trained: TwinPipeline) -> None:
    """T-064. The check exists because everyone says it holds by construction."""
    for service in trained.defect.gates.values():
        rows = tuple(row for row in service.rows if row.failed is not None)
        if not rows:
            continue
        assert temporal_split(rows).leaks() == ()


def test_the_row_a_model_trains_on_is_the_row_it_scored(
    trained: TwinPipeline,
) -> None:
    """A model fitted on a whole route and asked to predict from half of one.

    The training row is taken at the moment the prediction was made and labelled
    when the verdict arrived, so the shape the model learns is the shape it is
    asked to predict from.
    """
    service = trained.defect.gates["G3"]
    rows = [row for row in service.rows if row.failed is not None]
    assert rows
    span = set(service.builder.span)
    # Rows are taken as the unit enters the gate's span, so most of the span's
    # per-station columns are still absent.
    missing = [
        sum(
            1
            for station_id in span
            if math.isnan(row.values.get(f"cycle_z_{station_id}", math.nan))
        )
        for row in rows
    ]
    assert min(missing) > 0, (
        "every row carries every station, so the rows were rebuilt at gate time"
    )


# -- calibration and conformal ---------------------------------------------


def test_reliability_bins_and_error() -> None:
    """AC-093. The diagram carries its bin counts, and the error is over them."""
    probabilities = np.array([0.02, 0.02, 0.02, 0.98, 0.98, 0.98])
    labels = np.array([0.0, 0.0, 0.0, 1.0, 1.0, 1.0])
    diagram = reliability(probabilities, labels)
    assert diagram.expected_calibration_error < 0.03
    assert sum(diagram.counts) == 6
    assert diagram.is_calibrated


def test_an_uncalibrated_model_is_reported_as_uncalibrated() -> None:
    """Section 6.3. A model that does not calibrate is not promoted."""
    probabilities = np.array([0.9] * 10)
    labels = np.array([0.0] * 10)
    diagram = reliability(probabilities, labels)
    assert diagram.expected_calibration_error > ECE_TARGET
    assert not diagram.is_calibrated


def test_conformal_coverage_holds_on_a_held_out_fold() -> None:
    """T-066, AC-024. Distribution-free coverage at alpha 0.10."""
    from twin.domain.seeds import generator_for

    rng = generator_for("conformal", 1)
    labels = (rng.random(4000) < 0.02).astype(float)
    # A well behaved score: high where the label is one, low where it is zero.
    probabilities = np.clip(
        labels * rng.normal(0.7, 0.15, 4000)
        + (1 - labels) * rng.normal(0.05, 0.05, 4000),
        0.0,
        1.0,
    )
    calibration = calibrate(probabilities[:2000], labels[:2000])
    assert calibration.is_usable
    coverage = empirical_coverage(calibration, probabilities[2000:], labels[2000:])
    # Split conformal guarantees coverage of at least 1 - alpha in expectation
    # over the draw of the calibration fold, so a single sample sits either side
    # of the nominal figure by a little. The tolerance here is that sampling
    # error and nothing else: the evidence pack reports the measured coverage
    # against the target rather than asserting it away.
    assert coverage >= 0.89, f"coverage {coverage:.3f} well below the 0.90 target"


def test_too_few_calibration_points_reports_the_full_range() -> None:
    """A guarantee needs a sample. Below it the interval says everything."""
    calibration = calibrate(np.array([0.1, 0.2]), np.array([0.0, 1.0]))
    assert not calibration.is_usable
    interval = calibration.interval(0.5)
    assert (interval.lo, interval.hi) == (0.0, 1.0)
    assert interval.covers_both
    assert calibration.reason


def test_a_conformal_interval_is_never_a_point() -> None:
    """The risk row shows an interval, and a point would claim more than it can."""
    from twin.domain.seeds import generator_for

    rng = generator_for("conformal", 2)
    labels = (rng.random(1000) < 0.05).astype(float)
    probabilities = np.clip(labels * 0.6 + rng.normal(0.05, 0.05, 1000), 0.0, 1.0)
    calibration = calibrate(probabilities, labels)
    for value in (0.01, 0.2, 0.5, 0.9):
        interval = calibration.interval(value)
        assert interval.lo <= interval.point <= interval.hi, (
            f"the interval for {value} does not contain it"
        )
        assert interval.hi > interval.lo


# -- explanations ----------------------------------------------------------


def test_a_feature_without_a_template_cannot_be_surfaced(
    trained: TwinPipeline,
) -> None:
    """AC-022. The registry decides what can be seen, not the model."""
    service = trained.defect.gates["G3"]
    if not service.is_trained or service.explainer is None:
        pytest.skip("G3 fitted no model in this run")
    rows = [row for row in service.rows if row.failed is not None][:1]
    if not rows:
        pytest.skip("no labelled rows")
    frame = service.model.frame(tuple(rows))
    contributions = service.explainer.contributions(frame)
    if contributions.size == 0:
        pytest.skip("no tree explainer available")
    columns = tuple(frame.columns)
    # A contribution loaded entirely on to a feature with no template must
    # produce no factor for it.
    forced = np.zeros(len(columns))
    untemplated = next(
        (index for index, name in enumerate(columns) if name not in FACTOR_TEMPLATES),
        None,
    )
    assert untemplated is not None, "every feature has a template, so nothing is tested"
    forced[untemplated] = 100.0
    factors = service.explainer.factors(rows[0], forced, columns)
    assert all(factor.feature != columns[untemplated] for factor in factors)


def test_at_most_three_factors_reach_a_row(trained: TwinPipeline) -> None:
    """AC-022. Exactly three, because a supervisor has time for three."""
    service = trained.defect.gates["G3"]
    if not service.is_trained or service.explainer is None:
        pytest.skip("G3 fitted no model in this run")
    rows = [row for row in service.rows if row.failed is not None][:20]
    frame = service.model.frame(tuple(rows))
    contributions = service.explainer.contributions(frame)
    if contributions.size == 0:
        pytest.skip("no tree explainer available")
    columns = tuple(frame.columns)
    for index, row in enumerate(rows):
        factors = service.explainer.factors(row, contributions[index], columns)
        assert len(factors) <= TOP_FACTORS


def test_no_raw_feature_name_appears_in_a_rendered_factor(
    trained: TwinPipeline,
) -> None:
    """AC-022. The interface never shows a column name."""
    service = trained.defect.gates["G3"]
    if not service.is_trained or service.explainer is None:
        pytest.skip("G3 fitted no model in this run")
    rows = [row for row in service.rows if row.failed is not None][:20]
    frame = service.model.frame(tuple(rows))
    contributions = service.explainer.contributions(frame)
    if contributions.size == 0:
        pytest.skip("no tree explainer available")
    columns = tuple(frame.columns)
    names = set(feature_names(service.builder))
    for index, row in enumerate(rows):
        for factor in service.explainer.factors(row, contributions[index], columns):
            for name in names:
                assert name not in factor.label
                assert name not in factor.detail


def test_an_explainer_without_shap_degrades_rather_than_raising() -> None:
    """ARCHITECTURE Section 8. Degrade to less information, never to wrong."""
    explainer = Explainer(object(), ("a", "b"))
    assert not explainer.is_available
    assert explainer.contributions(None).size == 0
    row = FeatureRow(
        unit_id="3C4PDCBG7JT100001",
        gate_id="G3",
        at=datetime(2026, 3, 2, tzinfo=None).astimezone(),
        values={},
        categories={},
    )
    assert explainer.factors(row, np.zeros(2), ("a", "b")) == ()


# -- emission --------------------------------------------------------------


def test_a_risk_carries_its_lead_in_stations_and_minutes(
    trained: TwinPipeline,
) -> None:
    """AC-023. A supervisor counts stations; minutes are the derived figure."""
    from twin.ledger.store import defect_predictor

    predictions = trained.store.by_predictor(defect_predictor("G3"))
    assert predictions
    for prediction in predictions[:50]:
        assert prediction.claim["stations_remaining"] >= 0
        assert prediction.claim["minutes_remaining"] >= 0
        assert prediction.claim["interval_lo"] <= prediction.claim["interval_hi"]


def test_a_unit_is_scored_once_per_gate_per_pass(trained: TwinPipeline) -> None:
    """One claim per unit per gate. A rework pass is a new claim, not a repeat."""
    from collections import Counter

    from twin.ledger.store import defect_predictor

    seen = Counter(
        (prediction.unit_id, prediction.claim.get("attempt"))
        for prediction in trained.store.by_predictor(defect_predictor("G3"))
    )
    assert seen
    assert max(seen.values()) == 1


def test_risk_is_scored_well_before_the_gate(trained: TwinPipeline) -> None:
    """AC-020, PRD Section 5. At least six stations of warning at the last gate."""
    import statistics

    from twin.ledger.store import defect_predictor

    remaining = [
        float(prediction.claim["stations_remaining"])
        for prediction in trained.store.by_predictor(defect_predictor("G3"))
    ]
    assert remaining
    assert statistics.median(remaining) >= 6.0, (
        f"median lead {statistics.median(remaining):.1f} stations before G3"
    )


def test_a_model_that_cannot_be_fitted_says_so_rather_than_guessing(
    trained: TwinPipeline,
) -> None:
    """ARCHITECTURE Section 8. The interface says which capability is missing."""
    line, plant = _line(), _plant()
    from twin.defect.risk import DefectService

    service = DefectService(
        line=line,
        calendar=ProductionCalendar(line, plant.epoch),
        distributions=trained.estimator.distributions,
        model_version="test",
    )
    report = service.train(plant.epoch)
    assert set(report) == {gate.gate_id for gate in line.gates}
    for reason in report.values():
        assert "base rate" in reason
    for gate_service in service.gates.values():
        assert not gate_service.is_trained


def test_two_trainings_on_the_same_data_produce_the_same_model(
    trained: TwinPipeline,
) -> None:
    """AC-103. A library default that read the system entropy would break this."""
    from twin.defect.model import train_gate_model

    service = trained.defect.gates["G3"]
    rows = tuple(row for row in service.rows if row.failed is not None)
    if len(rows) < 300:
        pytest.skip("not enough labelled rows to fit twice")
    names = feature_names(service.builder)
    first = train_gate_model("G3", rows, names, "test")
    second = train_gate_model("G3", rows, names, "test")
    if first.booster is None or second.booster is None:
        pytest.skip("G3 fitted no model")
    sample = rows[:200]
    assert np.allclose(first.predict(sample), second.predict(sample))


def test_the_gate_span_is_the_stretch_since_the_previous_gate(
    trained: TwinPipeline,
) -> None:
    """A gate is the first opportunity to catch the work it covers."""
    order = trained.line.station_ids
    spans = {
        gate_id: service.builder.span
        for gate_id, service in trained.defect.gates.items()
    }
    covered: list[str] = []
    for gate in trained.line.gates:
        covered.extend(spans[gate.gate_id])
    assert covered == list(order[: order.index(trained.line.gates[-1].after) + 1])


def test_no_gate_sees_another_gates_stations(trained: TwinPipeline) -> None:
    """Separate models, because the causal paths differ."""
    spans = [set(service.builder.span) for service in trained.defect.gates.values()]
    for index, first in enumerate(spans):
        for second in spans[index + 1 :]:
            assert not first & second


def test_a_prediction_is_recorded_even_while_the_predictor_is_in_shadow(
    trained: TwinPipeline,
) -> None:
    """AC-021. The shadow predictions are the evidence the gate is decided on."""
    from twin.ledger.store import defect_predictor

    predictions = trained.store.by_predictor(defect_predictor("G3"))
    assert predictions
    assert any(not prediction.published for prediction in predictions)


def test_the_defect_horizon_leaves_room_for_the_unit_to_reach_the_gate(
    trained: TwinPipeline,
) -> None:
    """A horizon that closed first would score every unit as unresolved."""
    from twin.ledger.store import defect_predictor

    for prediction in trained.store.by_predictor(defect_predictor("G3"))[:50]:
        minutes = float(prediction.claim["minutes_remaining"])
        available = (prediction.horizon_end - prediction.made_at).total_seconds() / 60
        assert available >= minutes
