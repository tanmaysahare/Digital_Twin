"""Estimates, the state machine, signatures and distributions.

T-037, T-038, T-039, T-043.
"""

from __future__ import annotations

import statistics
from collections import Counter
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from connector.normalise import Released
from connector.protocol import CanonicalEvent
from plantsim.model import (
    SimulationDetail,
    SimulationRequest,
    SimulationResult,
    run_simulation,
)
from plantsim.parameters import load_plant_model
from twin.config import load_line_definition
from twin.domain.estimate import Estimate, Interval
from twin.domain.shifts import ProductionCalendar
from twin.state.distributions import MAD_TO_SIGMA, DistributionStore
from twin.state.estimator import StateEstimator

REPO_ROOT = Path(__file__).resolve().parent.parent
LINE2 = load_line_definition(REPO_ROOT / "config" / "lines" / "line2.yaml")
PLANT2 = load_plant_model(REPO_ROOT / "config" / "plantsim" / "line2.yaml")


@pytest.fixture(scope="module")
def run() -> SimulationResult:
    """A few hundred units of the reference line, with every signal on."""
    return run_simulation(
        SimulationRequest(
            line=LINE2, plant=PLANT2, seed=91, units=300, detail=SimulationDetail()
        )
    )


@pytest.fixture(scope="module")
def estimator(run: SimulationResult) -> StateEstimator:
    """The twin's picture of that run, built from the filtered stream alone."""
    built = StateEstimator(LINE2)
    built.apply_all(run.events)
    return built


# ---------------------------------------------------------------------------
# T-037: the Estimate type. STA-05.


def test_an_estimate_cannot_be_built_without_a_provenance() -> None:
    """T-037. The field has no default, so there is no way to omit it."""
    with pytest.raises(TypeError):
        Estimate(Interval(1.0, 2.0))  # type: ignore[call-arg]


def test_a_measured_estimate_cannot_carry_an_interval() -> None:
    """Rule 2. An inference in the shape of a reading is refused."""
    with pytest.raises(ValueError, match="MEASURED estimate has equal bounds"):
        Estimate(Interval(48.0, 53.0), "MEASURED", 1.0, "a torque gun said so")


def test_an_inferred_estimate_has_no_point_value() -> None:
    """Rule 3. Asking for one raises rather than returning a midpoint."""
    inferred = Estimate.inferred(
        Interval(210.0, 260.0), "bounded by the flanking scans", 0.6
    )
    with pytest.raises(ValueError, match="no point value"):
        _ = inferred.point
    assert inferred.sort_key() == pytest.approx(235.0)


def test_an_estimate_is_immutable() -> None:
    """A value that can be edited after it is shown is not evidence."""
    measured = Estimate.measured(51.0, "S20 reported its own cycle time")
    with pytest.raises(FrozenInstanceError):
        measured.confidence = 0.5  # type: ignore[misc]


def test_an_interval_refuses_bounds_the_wrong_way_round() -> None:
    with pytest.raises(ValueError, match="exceeds upper bound"):
        Interval(90.0, 40.0)


def test_a_confidence_outside_the_unit_interval_is_refused() -> None:
    with pytest.raises(ValueError, match=r"confidence must be in \[0, 1\]"):
        Estimate.measured(51.0, "S20 said so", confidence=1.4)


def test_an_estimate_carries_a_basis_a_person_can_read() -> None:
    """The interface prints this beside the number, so it cannot be blank."""
    with pytest.raises(ValueError, match="carries a basis"):
        Estimate.measured(51.0, "   ")


# ---------------------------------------------------------------------------
# T-038: the state machine


def test_every_station_has_a_state_and_a_basis(estimator: StateEstimator) -> None:
    state = estimator.state()
    assert len(state.stations) == len(LINE2.stations)
    for snapshot in state.stations:
        assert snapshot.basis.strip()
        assert snapshot.since is not None


def test_a_rich_station_reports_its_own_state(run: SimulationResult) -> None:
    """The only place a station state is MEASURED rather than reasoned to."""
    reported = {
        event.station_id for event in run.events if event.event_type == "STATION_STATE"
    }
    assert reported == set(LINE2.stations_of_tier("A"))


def test_a_basic_station_has_its_state_inferred(estimator: StateEstimator) -> None:
    """A tier B station reports a clock. Blocked and starved are worked out."""
    basic = LINE2.stations_of_tier("B")
    states = {estimator.state().station(station_id).state for station_id in basic}
    assert states <= {"RUNNING", "BLOCKED", "STARVED", "IDLE", "IDLE_UNKNOWN"}
    assert states & {"BLOCKED", "STARVED"}


def test_idle_unknown_is_produced_and_never_collapsed(
    estimator: StateEstimator,
) -> None:
    """A station downstream of a dark run cannot know whether it is starved."""
    state = estimator.state()
    downstream_of_dark = state.station("S38")
    assert downstream_of_dark.state in {"RUNNING", "BLOCKED", "IDLE_UNKNOWN"}
    tail = state.station("S42")
    assert tail.state == "IDLE_UNKNOWN"
    assert "no scan point on both sides" in tail.basis


def test_a_blocked_station_finished_its_work_and_still_holds_the_unit(
    run: SimulationResult,
) -> None:
    """The transition a forecast is built on, checked against the stream."""
    fresh = StateEstimator(LINE2)
    seen_blocked = False
    for event in run.events:
        fresh.apply(event)
        if event.event_type == "CYCLE_END" and event.station_id == "S20":
            assert fresh.state().station("S20").state == "BLOCKED"
            seen_blocked = True
    assert seen_blocked


def test_a_station_between_units_is_starved_or_idle(run: SimulationResult) -> None:
    """After a departure the station has nothing, and the twin says which."""
    fresh = StateEstimator(LINE2)
    checked = 0
    for event in run.events:
        fresh.apply(event)
        if event.event_type == "UNIT_DEPART" and event.station_id == "S18":
            assert fresh.state().station("S18").state in {"STARVED", "IDLE"}
            checked += 1
    assert checked > 10


def test_dark_stations_are_never_shown_as_running_when_the_span_is_empty(
    run: SimulationResult,
) -> None:
    """Conservation says the run is empty, so its stations have no work."""
    fresh = StateEstimator(LINE2)
    fresh.apply(run.events[0])
    state = fresh.state()
    assert state.station("S34").state in {"STARVED", "IDLE_UNKNOWN"}


# ---------------------------------------------------------------------------
# Buffers. STA-02.


def test_buffer_levels_are_derived_by_conservation(estimator: StateEstimator) -> None:
    """Between two instrumented stations the count in less the count out is exact."""
    state = estimator.state()
    between_instrumented = state.buffers[0]
    assert between_instrumented.occupancy.provenance == "DERIVED"
    assert between_instrumented.occupancy.interval.is_point
    assert 0 <= between_instrumented.occupancy.lo <= between_instrumented.capacity


def test_a_buffer_fed_by_a_dark_station_is_an_interval(
    estimator: StateEstimator,
) -> None:
    """B9 sits after S37, which emits nothing. Its level cannot be a number."""
    buffer = next(item for item in estimator.state().buffers if item.buffer_id == "B9")
    assert buffer.occupancy.provenance == "INFERRED"
    assert "emit nothing" in buffer.occupancy.basis


def test_every_buffer_reports_a_trend(estimator: StateEstimator) -> None:
    for buffer in estimator.state().buffers:
        assert buffer.trend in {"RISING", "FALLING", "FLAT"}


# ---------------------------------------------------------------------------
# T-039: process signatures. STA-03.


def test_a_completed_signature_matches_the_simulated_route(
    run: SimulationResult, estimator: StateEstimator
) -> None:
    """T-039. Exactly, including the six stations that emitted nothing."""
    completed = [
        signature
        for signature in estimator.signatures()
        if signature.status == "COMPLETED"
    ]
    assert len(completed) > 100
    truth_routes: dict[str, list[str]] = {}
    for visit in run.truth.visits:
        truth_routes.setdefault(visit.unit_id, []).append(visit.station_id)
    for signature in completed[:50]:
        assert [visit.station_id for visit in signature.visits] == truth_routes[
            signature.unit_id
        ]


def test_a_signature_marks_which_of_its_numbers_were_read(
    estimator: StateEstimator,
) -> None:
    """DEF-03. Missingness is a feature, so it has to be visible per visit."""
    signature = next(
        item for item in estimator.signatures() if item.status == "COMPLETED"
    )
    dark = {visit.station_id for visit in signature.dark_visits()}
    assert dark == set(LINE2.stations_of_tier("C"))
    measured = [visit for visit in signature.visits if visit.is_measured]
    assert len(measured) == len(LINE2.stations) - len(dark)


def test_a_signature_carries_the_process_values_and_lots_it_saw(
    estimator: StateEstimator,
) -> None:
    signature = next(
        item for item in estimator.signatures() if item.status == "COMPLETED"
    )
    at_rich = signature.visit("S20")
    assert at_rich is not None
    assert set(at_rich.process_values) >= {"torque", "motor_current"}
    with_lot = signature.visit("S07")
    assert with_lot is not None
    assert with_lot.part_lots


# ---------------------------------------------------------------------------
# T-043: robust distributions


def _store() -> DistributionStore:
    return DistributionStore(LINE2)


def test_a_single_long_stop_does_not_move_the_baseline() -> None:
    """T-043. A six-minute andon stop is one cycle, not a new normal."""
    store = _store()
    for _ in range(60):
        store.record("S20", "V-STD", 58.0)
    clean = store.get("S20", "V-STD")
    store.record("S20", "V-STD", 58.0 + 6 * 60)
    after = store.get("S20", "V-STD")
    assert clean is not None
    assert after is not None
    assert abs(after.median_s - clean.median_s) < 0.5
    assert after.n == clean.n + 1


def test_the_scale_is_a_median_absolute_deviation() -> None:
    """Comparable with a standard deviation under normality, and robust."""
    store = _store()
    values = [56.0, 57.0, 58.0, 59.0, 60.0] * 12
    for value in values:
        store.record("S20", "V-STD", value)
    distribution = store.get("S20", "V-STD")
    assert distribution is not None
    assert distribution.median_s == pytest.approx(58.0)
    assert distribution.scale_s == pytest.approx(1.0 * MAD_TO_SIGMA)


def test_a_station_below_the_minimum_is_excluded_from_forecasting() -> None:
    """EC-20. It says how many cycles remain rather than looking broken."""
    store = _store()
    for _ in range(LINE2.state.min_cycles - 1):
        store.record("S34", "V-STD", 49.0)
    distribution = store.get("S34", "V-STD")
    assert distribution is not None
    assert not distribution.is_usable
    assert store.cycles_remaining("S34", "V-STD") == 1
    store.record("S34", "V-STD", 49.0)
    usable = store.get("S34", "V-STD")
    assert usable is not None
    assert usable.is_usable
    assert store.cycles_remaining("S34", "V-STD") == 0


def test_the_window_keeps_only_the_configured_number_of_cycles() -> None:
    store = _store()
    for index in range(LINE2.state.window_cycles + 40):
        store.record("S20", "V-STD", 50.0 + index)
    distribution = store.get("S20", "V-STD")
    assert distribution is not None
    assert distribution.n == LINE2.state.window_cycles
    assert store.observed("S20", "V-STD") == LINE2.state.window_cycles + 40


def test_the_pool_is_empirical_rather_than_fitted() -> None:
    """A bimodal cycle time survives, because a fit to it would not."""
    store = _store()
    for _ in range(50):
        store.record("S31", "V-STD", 44.0)
        store.record("S31", "V-STD", 56.0)
    distribution = store.get("S31", "V-STD")
    assert distribution is not None
    assert set(distribution.sample) == {44.0, 56.0}


def test_the_estimator_fits_a_distribution_per_station_per_variant(
    estimator: StateEstimator,
) -> None:
    """Conditioned on variant, because a variant changes the work content."""
    for variant_id in LINE2.variants:
        distribution = estimator.distributions.get("S20", variant_id)
        assert distribution is not None
        assert distribution.n > 0
    dark = estimator.distributions.get("S34", "V-STD")
    assert dark is None, "a dark station has no measured cycles to fit"


def test_the_fitted_median_matches_what_the_line_did(
    run: SimulationResult, estimator: StateEstimator
) -> None:
    """The twin's baseline for an instrumented station is the truth for it."""
    for station_id in ("S20", "S22", "S38"):
        observed = [
            visit.cycle_time_s
            for visit in run.truth.visits
            if visit.station_id == station_id
        ]
        fitted = [
            estimator.distributions.get(station_id, variant_id)
            for variant_id in LINE2.variants
        ]
        medians = [item.median_s for item in fitted if item is not None]
        assert medians
        assert abs(statistics.median(medians) - statistics.median(observed)) < 3.0


# ---------------------------------------------------------------------------
# Late events. EC-01.


def test_a_late_event_names_the_station_to_recompute() -> None:
    """The estimator is told which station a late arrival invalidated."""
    estimator = StateEstimator(LINE2)
    calendar = ProductionCalendar(LINE2, datetime(2026, 3, 2, tzinfo=UTC))
    event = CanonicalEvent(
        event_id=uuid4(),
        event_type="CYCLE_END",
        line_id="line2",
        station_id="S20",
        unit_id="3C4PDCBG7JT100001",
        ts_source=calendar.at(3600.0),
        ts_ingest=calendar.at(3600.0) + timedelta(seconds=40),
        payload={"variant_id": "V-STD", "shift_id": "A", "cycle_time_s": 58.4},
        source_adapter="sim",
        quality_flag="LATE",
    )
    estimator.apply_released(Released(event, recompute_station_id="S20"))
    assert estimator.pending_recomputes == ("S20",)


def test_the_line_state_reports_what_it_cannot_resolve(
    estimator: StateEstimator,
) -> None:
    """STA-07. Every unresolved station names the sensor that would fix it."""
    unresolved = estimator.state().unresolved
    assert {item.station_id for item in unresolved} == set(LINE2.stations_of_tier("C"))
    for item in unresolved:
        assert item.reason.strip()
        assert item.resolved_by.strip()


def test_the_dark_station_count_is_visible_in_the_state(
    estimator: StateEstimator,
) -> None:
    """AC-008. The panel states the dark count separately, so the state carries it."""
    state = estimator.state()
    assert len(state.dark_stations()) == 6
    assert Counter(snapshot.tier for snapshot in state.stations) == Counter(
        {"A": 24, "B": 12, "C": 6}
    )
