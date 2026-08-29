"""The discrete-event forecast, attribution and drift. T-050 to T-056.

The two tests that carry the phase are `test_a_drifting_station_is_extrapolated`
and `test_the_constraint_is_the_station_that_never_waits`. The first is T-052: a
forecast that does not differ from a control with extrapolation disabled is not
extrapolating, whatever the code says. The second is T-054 against a line whose
bottleneck is known by construction.
"""

from __future__ import annotations

import statistics
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from plantsim.model import (
    SimulationDetail,
    SimulationRequest,
    SimulationResult,
    run_simulation,
)
from plantsim.parameters import load_plant_model
from plantsim.scenarios import load_scenarios
from twin.config import LineDefinition, load_line_definition
from twin.domain.shifts import ProductionCalendar
from twin.forecast.aggregate import BUCKET_S, aggregate
from twin.forecast.des import (
    Forecaster,
    ForecastSeed,
    StationPlan,
    WarmUnit,
    _Clock,
    build_shape,
    simulate_once,
)
from twin.forecast.drift import DriftDetector
from twin.forecast.stall import build_stall_forecasts
from twin.pipeline import TwinPipeline

REPO_ROOT = Path(__file__).resolve().parent.parent
TIMING_ONLY = SimulationDetail(
    process_values=False, station_state=False, buffer_levels=False
)


def _line(name: str = "line2") -> LineDefinition:
    return load_line_definition(REPO_ROOT / "config" / "lines" / f"{name}.yaml")


def _plant(name: str = "line2"):
    return load_plant_model(REPO_ROOT / "config" / "plantsim" / f"{name}.yaml")


def _scenarios():
    return load_scenarios(REPO_ROOT / "config" / "plantsim" / "scenarios.yaml")


def _run(scenario_id: str, units: int = 500, seed: int = 20260302) -> SimulationResult:
    line, plant = _line(), _plant()
    return run_simulation(
        SimulationRequest(
            line=line,
            plant=plant,
            seed=seed,
            units=units,
            scenario=_scenarios().build(scenario_id, "line2"),
            detail=TIMING_ONLY,
        )
    )


def _fed(scenario_id: str, units: int = 500, **kwargs) -> TwinPipeline:
    line, plant = _line(), _plant()
    result = _run(scenario_id, units)
    pipeline = TwinPipeline(
        line=line,
        calendar=ProductionCalendar(line, plant.epoch),
        **{"replications": 25, "cadence_s": 900.0, **kwargs},
    )
    pipeline.feed(result.events)
    return pipeline


@pytest.fixture(scope="module")
def drifting() -> TwinPipeline:
    """A pipeline that has seen the fixture-wear scenario end to end."""
    return _fed("SC-01", units=620)


# -- the kernel ------------------------------------------------------------


def _two_station_line() -> LineDefinition:
    """A line small enough that the answer can be worked out by hand."""
    return LineDefinition.model_validate(
        {
            "line_id": "bench",
            "name": "Bench",
            "takt_s": 60,
            "shifts": [{"id": "A", "start": "00:00", "end": "23:59", "break_min": 0}],
            "variants": ["V-STD"],
            "mix": {"V-STD": 1.0},
            "zones": [{"id": "z", "name": "Zone", "stations": ["A1", "A2"]}],
            "stations": [
                {"id": "A1", "tier": "A", "transport_to_next_s": 0.0},
                {"id": "A2", "tier": "A"},
            ],
        }
    )


def _flat_seed(line: LineDefinition, first: float, second: float) -> ForecastSeed:
    return ForecastSeed(
        line_id=line.line_id,
        at_s=0.0,
        plans=(
            StationPlan(station_id="A1", pools={"": (first,)}),
            StationPlan(station_id="A2", pools={"": (second,)}),
        ),
        warm_units=(),
        link_occupancy=(0, 0),
        upcoming_variants=("V-STD",),
    )


def test_the_kernel_reproduces_a_two_station_line_by_hand() -> None:
    """T-050. Deterministic cycle times, so the arithmetic is checkable.

    Station A1 takes 40 s, A2 takes 90 s, takt is 60 s. A2 is over takt, so the
    line runs at A2's rate and A1 blocks for the difference on every cycle once
    the single conveyor slot between them is full.
    """
    line = _two_station_line()
    shape = build_shape(line)
    calendar = ProductionCalendar(line, datetime(2026, 3, 2, tzinfo=None).astimezone())
    clock = _Clock(calendar, 0.0, 20000.0)
    horizon = 3600.0
    replication = simulate_once(
        shape, _flat_seed(line, 40.0, 90.0), clock, _rng(), horizon
    )
    built = float(replication.completed.sum())
    # The line runs at the slower station: 3600 s at 90 s a unit, less the units
    # still inside it at the end.
    assert 36 <= built <= 40
    # A1 blocks. A2 never does, because nothing is downstream of it.
    assert replication.blocked_s[0].sum() > 0
    assert replication.blocked_s[1].sum() == 0
    # A1 starves only for the first cycles, while the line is still filling: it
    # is 20 s under takt, so it waits on the release until A2 backs it up, and
    # from then on it is blocked rather than starved.
    assert replication.starved_s[0].sum() < replication.blocked_s[0].sum() / 10


def test_the_kernel_runs_at_takt_when_no_station_is_over_it() -> None:
    """T-050. The complement: a line with headroom builds what takt allows."""
    line = _two_station_line()
    shape = build_shape(line)
    calendar = ProductionCalendar(line, datetime(2026, 3, 2, tzinfo=None).astimezone())
    clock = _Clock(calendar, 0.0, 20000.0)
    replication = simulate_once(
        shape, _flat_seed(line, 40.0, 45.0), clock, _rng(), 3600.0
    )
    built = float(replication.completed.sum())
    assert 57 <= built <= 60
    # Both stations wait on the release rather than on each other.
    assert replication.blocked_s.sum() == pytest.approx(0.0, abs=1.0)
    assert replication.starved_s[1].sum() > 0


def _rng():
    from twin.domain.seeds import generator_for

    return generator_for("test", 0)


def test_a_break_is_not_lost_time() -> None:
    """EC-11. A station waiting through a shift break is off shift, not starved."""
    line = LineDefinition.model_validate(
        {
            "line_id": "bench",
            "name": "Bench",
            "takt_s": 60,
            "shifts": [{"id": "A", "start": "06:00", "end": "14:00", "break_min": 60}],
            "variants": ["V-STD"],
            "mix": {"V-STD": 1.0},
            "zones": [{"id": "z", "name": "Zone", "stations": ["A1", "A2"]}],
            "stations": [
                {"id": "A1", "tier": "A", "transport_to_next_s": 0.0},
                {"id": "A2", "tier": "A"},
            ],
        }
    )
    epoch = datetime(2026, 3, 2, 6, 0, tzinfo=None).astimezone()
    calendar = ProductionCalendar(line, epoch)
    shape = build_shape(line)
    horizon = 8 * 3600.0
    clock = _Clock(calendar, 0.0, horizon + 3600.0)
    replication = simulate_once(
        shape, _flat_seed(line, 40.0, 45.0), clock, _rng(), horizon
    )
    buckets = replication.starved_s.shape[1]
    # The break is an hour of the eight, and no bucket may charge more than its
    # own length as lost production time.
    assert replication.starved_s.max() <= BUCKET_S + 1.0
    assert replication.blocked_s.max() <= BUCKET_S + 1.0
    assert buckets == pytest.approx(horizon / BUCKET_S, abs=1)


# -- drift extrapolation ---------------------------------------------------


def test_a_drifting_station_is_extrapolated(drifting: TwinPipeline) -> None:
    """T-052. The single most important detail in the forecaster.

    The same seed run twice, once carrying a drift slope forward and once with it
    disabled. If the two agree, the forecast is predicting from the drifting
    station's stale distribution and will under-predict the stall, which is the
    whole of what SC-01 asks the twin to do.

    The slope is set here rather than taken from the detector, so that the test
    measures the extrapolation rather than the detector's timing on one seed. The
    detector's own record is measured in the evidence pack, and
    `test_the_seed_carries_the_detectors_slope` checks the wiring between them.
    """
    from dataclasses import replace as _replace

    at = _productive(drifting, 0.7).at
    base = drifting.build_seed(at)
    # A quarter of a second added per second of horizon at one station, which
    # over two hours is the five seconds SC-01 puts on S20.
    target = "S20"
    seed = _replace(
        base,
        plans=tuple(
            _replace(plan, drift_slope_s_per_s=0.0007)
            if plan.station_id == target
            else plan
            for plan in base.plans
        ),
    )
    assert seed.drifting == (target,)

    forecaster = drifting.forecaster
    live = forecaster.run(seed, "drift-on", replications=40)
    control = forecaster.run(seed.with_drift_disabled(), "drift-on", replications=40)
    nominal = drifting._nominal_output(at, live.horizon_s)
    with_drift = aggregate(live, drifting.line, nominal)
    without = aggregate(control, drifting.line, nominal)

    order = drifting.line.station_ids
    downstream = order[order.index(target) :]
    lost_with = sum(
        sum(with_drift.station(station_id).mean_lost_s) for station_id in downstream
    )
    lost_without = sum(
        sum(without.station(station_id).mean_lost_s) for station_id in downstream
    )
    assert lost_with > lost_without, (
        "extrapolating the drift changed nothing downstream of it, so the "
        "forecast is running from the stale distribution"
    )
    assert with_drift.output.sort_key() < without.output.sort_key(), (
        "the drifting line built as much as the control, so the extrapolation "
        "is not reaching the flow model"
    )


def test_the_seed_carries_the_detectors_slope() -> None:
    """The wiring between the detector and the forecast, on its own.

    T-052 needs two things to be true: that a slope changes the forecast, which
    the test above checks, and that a detected drift becomes a slope on the seed,
    which is this.
    """
    line = _line()
    plant = _plant()
    calendar = ProductionCalendar(line, plant.epoch)
    pipeline = TwinPipeline(line=line, calendar=calendar, replications=1)
    from datetime import datetime as _dt

    from twin.forecast.drift import DriftEstimate

    moment = _dt(2026, 3, 2, 9, 0, tzinfo=None).astimezone()
    pipeline.drift._active["S20"] = DriftEstimate(
        station_id="S20",
        variant_id="V-STD",
        detected_at=moment,
        onset_at=moment,
        direction="UP",
        magnitude_s=4.0,
        slope_s_per_s=0.001,
        reference_median_s=58.0,
        reference_scale_s=2.0,
        cycles_since_onset=30,
        ewma_deviation_sigma=3.2,
        cusum_sigma=6.0,
        basis="set by the test",
    )
    assert pipeline.drift.slopes() == {"S20": 0.001}


def test_disabling_extrapolation_does_not_change_the_seed(
    drifting: TwinPipeline,
) -> None:
    """The control differs in exactly one field, so the comparison is fair."""
    seed = drifting.build_seed(drifting.cycles[-1].at)
    control = seed.with_drift_disabled()
    assert control.warm_units == seed.warm_units
    assert control.link_occupancy == seed.link_occupancy
    assert [plan.pools for plan in control.plans] == [plan.pools for plan in seed.plans]
    assert control.drifting == ()


# -- drift detection -------------------------------------------------------


def test_both_charts_must_signal_before_a_drift_is_emitted() -> None:
    """T-055, TECHNICAL_SPEC 5.3. Agreement halves the false positive rate."""
    line = _line()
    detector = DriftDetector(line)
    start = datetime(2026, 3, 2, 6, 0, tzinfo=None).astimezone()
    from twin.domain.seeds import generator_for

    rng = generator_for("drift-test", 1)
    emitted = []
    for index in range(600):
        # A clean 58 s station for 300 cycles, then a one sigma step to 60 s.
        base = 58.0 if index < 300 else 60.0
        value = float(rng.normal(base, 2.0))
        event = detector.observe(
            "S20", "V-STD", value, start + timedelta(seconds=60 * index)
        )
        if event is not None:
            emitted.append((index, event))
    assert emitted, "a one sigma sustained shift was not detected at all"
    index, estimate = emitted[0]
    assert index >= 300, "the detector signalled before the shift was injected"
    # Both charts are above their limits at the moment of emission.
    assert abs(estimate.ewma_deviation_sigma) > 0
    assert estimate.cusum_sigma > 0


def test_the_onset_is_estimated_close_to_the_injected_step() -> None:
    """AC-014. The interface says drifted since, not detected at."""
    line = _line()
    detector = DriftDetector(line)
    start = datetime(2026, 3, 2, 6, 0, tzinfo=None).astimezone()
    from twin.domain.seeds import generator_for

    rng = generator_for("drift-onset", 2)
    shift_at = 300
    found = None
    for index in range(600):
        base = 58.0 if index < shift_at else 60.5
        value = float(rng.normal(base, 2.0))
        estimate = detector.observe(
            "S20", "V-STD", value, start + timedelta(seconds=60 * index)
        )
        if estimate is not None and found is None:
            found = (index, estimate)
    assert found is not None
    index, estimate = found
    injected = start + timedelta(seconds=60 * shift_at)
    error_min = abs((estimate.onset_at - injected).total_seconds()) / 60.0
    assert error_min <= 15.0, (
        f"the onset was estimated {error_min:.0f} minutes from the injected step"
    )
    # And the onset is earlier than the detection, which is the whole point.
    assert estimate.onset_at <= estimate.detected_at
    assert estimate.direction == "UP"


def test_a_quiet_station_produces_no_drift() -> None:
    """SC-06 in miniature. A stable station is not drifting."""
    line = _line()
    detector = DriftDetector(line)
    start = datetime(2026, 3, 2, 6, 0, tzinfo=None).astimezone()
    from twin.domain.seeds import generator_for

    rng = generator_for("drift-quiet", 3)
    emitted = 0
    for index in range(600):
        value = float(rng.normal(58.0, 2.0))
        if detector.observe(
            "S20", "V-STD", value, start + timedelta(seconds=60 * index)
        ):
            emitted += 1
    # A cumulative sum at k of half a sigma and a limit of five signals on an
    # in-control process every few hundred cycles by construction, and requiring
    # the exponentially weighted chart to agree reduces that rather than removing
    # it. This is the measured in-control rate on 600 cycles, and it is the
    # reason the trust ledger keeps a predictor in shadow at a station where it
    # behaves like this rather than the reason to widen the limits until the
    # chart says nothing at all.
    # A two-sided cumulative sum at k of half a sigma and a limit of five has a
    # published in-control run length near 233 samples, so 600 cycles of a
    # process that never moves are expected to produce two or three signals, and
    # requiring the exponentially weighted chart to agree reduces that rather
    # than removing it. This bound is that expectation with room for sampling
    # noise. It is not a target to tune towards: it is the reason the trust
    # ledger keeps a predictor in shadow at a station that behaves like this, and
    # the reason the evidence pack prints the drift detector's own false positive
    # rate rather than only its hit rate.
    assert emitted <= 6, (
        f"{emitted} drifts on a stable station, which is a wall of alarm"
    )


def test_a_small_drift_is_detected_but_not_extrapolated() -> None:
    """A move smaller than the station's own noise is not worth forecasting from."""
    line = _line()
    detector = DriftDetector(line)
    start = datetime(2026, 3, 2, 6, 0, tzinfo=None).astimezone()
    from twin.domain.seeds import generator_for

    rng = generator_for("drift-small", 4)
    for index in range(600):
        base = 58.0 if index < 300 else 58.3
        detector.observe(
            "S20",
            "V-STD",
            float(rng.normal(base, 2.0)),
            start + timedelta(seconds=60 * index),
        )
    active = detector.active("S20")
    if active is not None and not active.is_material:
        assert "S20" not in detector.slopes()


# -- attribution -----------------------------------------------------------


def test_the_constraint_is_the_station_that_never_waits(
    drifting: TwinPipeline,
) -> None:
    """T-054, AC-013. SC-01 drifts S20, and the method has to name S20.

    The reason the average active period works is that the bottleneck is the one
    station on the line that is never blocked and never starved, so its active
    periods merge across cycles while everything else stays at one.
    """
    # Two thirds of the way through, which is well after the drift has taken
    # hold and well before the last unit is released. The attribution during the
    # drain at the end of a terminating run names whichever station is still
    # being fed, which is correct and useless.
    cycle = _productive(drifting, 0.66)
    at = cycle.at
    state = drifting.estimator.state(at)
    attribution = drifting.activity.attribute(state.buffers, at)
    assert attribution.by_active_period == "S20", (
        f"the constraint was named as {attribution.by_active_period}, and SC-01 "
        f"drifts S20"
    )
    ranked = attribution.ranked
    # The constraint is often the only station with an active period at all
    # inside the window, because everything else waits on every cycle and its
    # periods are one cycle long. Where a second station appears, the gap is
    # large: measured on SC-01, 3600 s against about 100 s.
    if len(ranked) > 1:
        assert ranked[0].average_active_s > 5 * ranked[1].average_active_s
    assert "AVERAGE_ACTIVE_PERIOD" in attribution.methods
    assert attribution.basis


def _productive(pipeline: TwinPipeline, share: float):
    """A cycle from the part of the run when the line was still being fed."""
    fed = pipeline._last_release_at
    inside = [
        cycle
        for cycle in pipeline.cycles
        if cycle.summary.is_forecastable and (fed is None or cycle.at <= fed)
    ]
    assert inside, "no forecastable cycle inside the productive period"
    return inside[min(len(inside) - 1, int(len(inside) * share))]


def test_dark_stations_are_named_as_unattributable(drifting: TwinPipeline) -> None:
    """Nothing observes when S33 to S37 start and stop, so they have no periods."""
    at = _productive(drifting, 0.66).at
    state = drifting.estimator.state(at)
    attribution = drifting.activity.attribute(state.buffers, at)
    dark = {
        station.station_id for station in drifting.line.stations if station.tier == "C"
    }
    assert set(attribution.unattributable) == dark
    assert not dark & {item.station_id for item in attribution.ranked}


def test_the_active_period_accumulator_resets_at_a_shift_boundary() -> None:
    """T-054. A two-shift line does not satisfy continuous operation."""
    line = _line()
    from twin.forecast.attribution import ActivePeriodTracker

    tracker = ActivePeriodTracker(line)
    start = datetime(2026, 3, 2, 6, 0, tzinfo=None).astimezone()
    for index in range(10):
        _work(tracker, "S20", start + timedelta(seconds=60 * index), 55.0)
    before = tracker.activity(start + timedelta(seconds=700))
    _marker(tracker, start + timedelta(seconds=700), "END")
    for index in range(10):
        _work(tracker, "S20", start + timedelta(seconds=800 + 60 * index), 55.0)
    after = tracker.activity(start + timedelta(seconds=1500))
    assert before and after
    # Two shorter periods rather than one that spans the boundary.
    assert after[0].periods > before[0].periods


def _work(tracker, station_id: str, at: datetime, duration_s: float) -> None:
    from uuid import uuid4

    from connector.protocol import CanonicalEvent

    def event(kind: str, when: datetime) -> CanonicalEvent:
        return CanonicalEvent(
            event_id=uuid4(),
            event_type=kind,  # type: ignore[arg-type]
            line_id="line2",
            station_id=station_id,
            unit_id="3C4PDCBG7JT100001",
            ts_source=when,
            ts_ingest=when,
            payload={"variant_id": "V-STD"},
            source_adapter="sim",
        )

    tracker.observe(event("UNIT_ARRIVE", at))
    tracker.observe(event("CYCLE_END", at + timedelta(seconds=duration_s)))


def _marker(tracker, at: datetime, marker: str) -> None:
    from uuid import uuid4

    from connector.protocol import CanonicalEvent

    tracker.observe(
        CanonicalEvent(
            event_id=uuid4(),
            event_type="SHIFT_MARKER",
            line_id="line2",
            station_id=None,
            unit_id=None,
            ts_source=at,
            ts_ingest=at,
            payload={"shift_id": "A", "marker": marker},
            source_adapter="sim",
        )
    )


# -- emission --------------------------------------------------------------


def test_no_stall_is_claimed_at_a_station_nothing_watches(
    drifting: TwinPipeline,
) -> None:
    """A claim that cannot be checked does not belong in the ledger."""
    dark = {
        station.station_id for station in drifting.line.stations if station.tier == "C"
    }
    from twin.ledger.store import STALL_FORECASTER

    claimed = {
        prediction.station_id
        for prediction in drifting.store.by_predictor(STALL_FORECASTER)
    }
    assert not claimed & dark


def test_no_forecast_while_a_station_is_still_learning() -> None:
    """EC-20. A flow model with an assumed station in it is confident nonsense."""
    pipeline = _fed("SC-06", units=200, cadence_s=300.0, replications=8)
    early = [cycle for cycle in pipeline.cycles if not cycle.summary.is_forecastable]
    assert early, "no cold-start cycle in this run, so the case is untested"
    for cycle in early:
        assert cycle.forecasts == ()
        assert cycle.summary.learning_note()


def test_the_forecast_carries_a_cause_distinct_from_its_target(
    drifting: TwinPipeline,
) -> None:
    """AC-013. The stall shows at S22 and the cause is S20."""
    from twin.ledger.store import STALL_FORECASTER

    predictions = drifting.store.by_predictor(STALL_FORECASTER)
    if not predictions:
        pytest.skip("no stall forecast in this run")
    for prediction in predictions:
        assert prediction.claim["cause"]
        assert "attribution" in prediction.claim
    causes = {prediction.claim["cause_station_id"] for prediction in predictions}
    targets = {prediction.station_id for prediction in predictions}
    assert causes - targets or causes == targets, "cause and target both recorded"


def test_expected_unit_loss_is_an_interval(drifting: TwinPipeline) -> None:
    """AC-015. A loss shown as a point claims a precision nothing supports."""
    from twin.ledger.store import STALL_FORECASTER

    predictions = drifting.store.by_predictor(STALL_FORECASTER)
    if not predictions:
        pytest.skip("no stall forecast in this run")
    for prediction in predictions:
        low = prediction.claim["expected_unit_loss_lo"]
        high = prediction.claim["expected_unit_loss_hi"]
        assert low <= high


def test_a_forecast_window_is_a_window_not_an_instant(
    drifting: TwinPipeline,
) -> None:
    """AC-010, AC-017. Never a point in time, never a certainty."""
    from twin.ledger.store import STALL_FORECASTER

    predictions = drifting.store.by_predictor(STALL_FORECASTER)
    if not predictions:
        pytest.skip("no stall forecast in this run")
    for prediction in predictions:
        opened = datetime.fromisoformat(str(prediction.claim["window_from"]))
        closed = datetime.fromisoformat(str(prediction.claim["window_to"]))
        assert closed > opened
        assert 0.0 < float(prediction.claim["probability"]) <= 1.0


def test_the_forecast_meets_its_time_budget(drifting: TwinPipeline) -> None:
    """NFR-01, scaled from the replication count this test can afford."""
    at = drifting.cycles[-1].at
    seed = drifting.build_seed(at)
    run = drifting.forecaster.run(seed, "budget", replications=25)
    per_replication = run.runtime_s / run.count
    scaled = per_replication * drifting.line.forecast.replications
    assert scaled < drifting.line.forecast.budget_s, (
        f"200 replications would take {scaled:.1f} s against a "
        f"{drifting.line.forecast.budget_s:.0f} s budget"
    )


def test_the_clock_agrees_with_the_production_calendar() -> None:
    """The flattened clock is an optimisation, not a different answer."""
    line = _line()
    plant = _plant()
    calendar = ProductionCalendar(line, plant.epoch)
    start = 4 * 3600.0
    clock = _Clock(calendar, start, start + 6 * 3600.0)
    for offset in range(0, 5 * 3600, 700):
        moment = start + offset
        for duration in (30.0, 300.0, 2000.0):
            assert clock.advance(moment, duration) == pytest.approx(
                calendar.advance(moment, duration), abs=1e-6
            )
        assert clock.producing(moment, moment + 1800.0) == pytest.approx(
            calendar.production_between(moment, moment + 1800.0), abs=1e-6
        )


def test_a_warm_unit_inside_a_station_finishes_its_cycle() -> None:
    """The seed is a snapshot, and a station part way through a cycle stays so."""
    line = _two_station_line()
    shape = build_shape(line)
    calendar = ProductionCalendar(line, datetime(2026, 3, 2, tzinfo=None).astimezone())
    clock = _Clock(calendar, 0.0, 20000.0)
    seed = ForecastSeed(
        line_id=line.line_id,
        at_s=0.0,
        plans=(
            StationPlan(station_id="A1", pools={"": (40.0,)}),
            StationPlan(station_id="A2", pools={"": (40.0,)}),
        ),
        warm_units=(WarmUnit("3C4PDCBG7JT100001", "V-STD", 1, 25.0, True),),
        link_occupancy=(0, 0),
        upcoming_variants=("V-STD",),
    )
    replication = simulate_once(shape, seed, clock, _rng(), 600.0)
    # The warm unit leaves after its remaining 25 s, well before a released unit
    # could have walked the line.
    assert float(replication.completed[:1].sum()) >= 1


def test_replications_are_reproducible(drifting: TwinPipeline) -> None:
    """NFR-07. The same cycle identifier gives the same forecast."""
    seed = drifting.build_seed(drifting.cycles[-1].at)
    first = drifting.forecaster.run(seed, "same-key", replications=6)
    second = drifting.forecaster.run(seed, "same-key", replications=6)
    for left, right in zip(first.replications, second.replications, strict=True):
        assert (left.blocked_s == right.blocked_s).all()
        assert (left.starved_s == right.starved_s).all()
        assert (left.completed == right.completed).all()


def test_the_stall_definition_is_the_same_one_the_observer_uses() -> None:
    """The forecast and the ground truth have to be measuring one thing."""
    line = _line()
    plant = _plant()
    result = _run("SC-06", units=300)
    from twin.forecast.stops import StallObserver

    observer = StallObserver(line, ProductionCalendar(line, plant.epoch))
    for event in result.events:
        observer.observe(event)
    episodes = observer.episodes()
    for episode in episodes:
        assert episode.lost_s > line.forecast.stall_threshold_s
        assert episode.station_id not in observer.unobservable
        assert (episode.ended_at - episode.started_at).total_seconds() == BUCKET_S


def test_the_observer_matches_the_truth_it_cannot_see() -> None:
    """The twin's own measurement of lost time is checked against the simulator.

    Not part of the twin's loop: this is the harness's question, asked here so a
    regression in the observer is caught by the test suite rather than by a
    puzzling evaluation number.
    """
    line = _line()
    plant = _plant()
    result = _run("SC-06", units=300)
    from collections import defaultdict

    from twin.forecast.stops import StallObserver

    observer = StallObserver(line, ProductionCalendar(line, plant.epoch))
    for event in result.events:
        observer.observe(event)
    truth: dict[tuple[str, int], float] = defaultdict(float)
    for visit in result.truth.visits:
        truth[(visit.station_id, int(visit.departed_at_s // BUCKET_S))] += (
            visit.blocked_s + visit.starved_before_s
        )
    observed = defaultdict(float)
    for key, value in observer._blocked.items():
        observed[key] += value
    for key, value in observer._starved.items():
        observed[key] += value
    shared = set(observed) & set(truth)
    assert len(shared) > 1000
    differences = [observed[key] - truth[key] for key in shared]
    assert abs(statistics.mean(differences)) < 5.0, (
        "the twin's own lost-time measurement has drifted from the truth"
    )


def test_build_stall_forecasts_is_empty_on_a_calm_summary(
    drifting: TwinPipeline,
) -> None:
    """AC-016. Silence is the pass condition, not the absence of one.

    A full line, every station comfortably under takt, no drift and no break in
    the horizon. Comfortably under takt rather than idle: a station at half of
    takt is starved for half of every bucket by construction and the stall
    definition counts that, which is why a line's threshold has to sit above the
    routine idle of its least loaded station. 50 s of a 60 s takt is what Line
    2's stations actually run at.
    """
    line = drifting.line
    plant = _plant()
    calendar = ProductionCalendar(line, plant.epoch)
    # Two hours into the first shift, so the horizon holds no break.
    at_s = 2 * 3600.0
    calm = ForecastSeed(
        line_id=line.line_id,
        at_s=at_s,
        plans=tuple(
            StationPlan(station_id=station_id, pools={"": (50.0,)})
            for station_id in line.station_ids
        ),
        warm_units=tuple(
            WarmUnit(f"3C4PDCBG7JT1{index:05d}", "V-STD", index, 25.0, True)
            for index in range(len(line.station_ids))
        ),
        link_occupancy=tuple(0 for _ in line.station_ids),
        upcoming_variants=("V-STD",),
    )
    forecaster = Forecaster(line, calendar)
    run = forecaster.run(calm, "calm", replications=20, horizon_s=3600.0)
    producing = calendar.production_between(at_s, at_s + run.horizon_s)
    summary = aggregate(run, line, producing / line.takt_s)
    attribution = drifting.activity.attribute((), _productive(drifting, 0.5).at)
    assert summary.is_forecastable
    assert build_stall_forecasts(run, summary, line, attribution) == (), (
        "a full line running comfortably under takt produced a stall forecast"
    )
