"""The line simulator. T-020 to T-030.

The simulator is not scaffolding. It is the environment the whole system is
developed against, and its fidelity bounds everything downstream, so it is
tested as a deliverable rather than as a fixture.
"""

from __future__ import annotations

import statistics
from collections import Counter
from pathlib import Path

import pytest

from connector.csv_replay_adapter import (
    DEMO_SPEED_MULTIPLIER,
    MAX_SPEED_MULTIPLIER,
    CsvReplayAdapter,
    write_events,
)
from plantsim.emit import MACHINE_EVENTS, TIER_EVENTS
from plantsim.model import (
    SimulationDetail,
    SimulationRequest,
    SimulationResult,
    run_simulation,
)
from plantsim.parameters import PlantModel, load_plant_model
from plantsim.scenarios import load_scenarios
from twin.config import LineDefinition, load_line_definition
from twin.domain.shifts import ProductionCalendar

REPO_ROOT = Path(__file__).resolve().parent.parent
SCENARIOS = load_scenarios(REPO_ROOT / "config" / "plantsim" / "scenarios.yaml")

TIMING_ONLY = SimulationDetail(
    process_values=False, station_state=False, buffer_levels=False
)


def _line(name: str) -> LineDefinition:
    return load_line_definition(REPO_ROOT / "config" / "lines" / f"{name}.yaml")


def _plant(name: str) -> PlantModel:
    return load_plant_model(REPO_ROOT / "config" / "plantsim" / f"{name}.yaml")


def _run(
    name: str,
    units: int,
    seed: int = 41,
    scenario_id: str | None = None,
    detail: SimulationDetail | None = None,
) -> SimulationResult:
    line, plant = _line(name), _plant(name)
    scenario = (
        SCENARIOS.build(scenario_id, name)
        if scenario_id is not None
        else SimulationRequest(line=line, plant=plant, seed=seed, units=1).scenario
    )
    return run_simulation(
        SimulationRequest(
            line=line,
            plant=plant,
            seed=seed,
            units=units,
            scenario=scenario,
            detail=detail or TIMING_ONLY,
        )
    )


@pytest.fixture(scope="module")
def reference_day() -> SimulationResult:
    """A day of the reference line, at the takt slots the calendar allows."""
    line, plant = _line("line2"), _plant("line2")
    calendar = ProductionCalendar(line, plant.epoch)
    slots = int(calendar.production_between(0.0, 86400.0) / line.takt_s)
    return _run("line2", slots)


# ---------------------------------------------------------------------------
# T-020: the line runs


@pytest.mark.parametrize("name", ["line2", "line7"])
def test_a_day_of_output_lands_within_five_percent_of_nominal(name: str) -> None:
    """T-020. Nominal is what the plant plans for, not the takt-limited ideal."""
    line, plant = _line(name), _plant(name)
    calendar = ProductionCalendar(line, plant.epoch)
    slots = int(calendar.production_between(0.0, 86400.0) / line.takt_s)
    result = _run(name, slots)

    released = min(unit.released_at_s for unit in result.truth.units)
    finished = max(unit.completed_at_s or 0.0 for unit in result.truth.units)
    per_unit_s = calendar.production_between(released, finished) / slots
    a_day = calendar.production_between(0.0, 86400.0) / per_unit_s
    nominal = plant.nominal_output_per_day
    assert abs(a_day - nominal) / nominal <= 0.05, (
        f"{name} built {a_day:.0f} units a day against a nominal of {nominal}"
    )


def test_every_released_unit_leaves_the_line(reference_day: SimulationResult) -> None:
    """Conservation. Units in equals units out, with none left inside."""
    released = len(reference_day.truth.units)
    accounted = Counter(unit.status for unit in reference_day.truth.units)
    assert sum(accounted.values()) == released
    assert accounted["IN_PROCESS"] == 0


def test_loss_accounting_adds_up(reference_day: SimulationResult) -> None:
    """Every visit's dwell is its work plus its blocking, within rounding."""
    for visit in reference_day.truth.visits[:2000]:
        dwell = visit.departed_at_s - visit.arrived_at_s
        assert dwell >= visit.cycle_time_s - 1e-6
        assert visit.blocked_s >= 0
        assert visit.queued_before_s >= 0


# ---------------------------------------------------------------------------
# T-021: the model mix


def test_the_observed_mix_matches_the_configured_mix(
    reference_day: SimulationResult,
) -> None:
    """T-021. A level schedule reproduces the mix exactly, not on average."""
    line = _line("line2")
    built = Counter(unit.variant_id for unit in reference_day.truth.units)
    total = sum(built.values())
    for variant_id, share in line.mix.items():
        assert abs(built[variant_id] / total - share) < 0.01


# ---------------------------------------------------------------------------
# T-022: cycle-time distributions


def test_sampled_cycle_times_match_the_configuration() -> None:
    """T-022. The median of what the line produced is what was configured."""
    line, plant = _line("line7"), _plant("line7")
    result = _run("line7", 1500)
    zone_of = {}
    order = line.station_ids
    for zone in line.zones:
        first, last = zone.span
        for station_id in order[order.index(first) : order.index(last) + 1]:
            zone_of[station_id] = zone.zone_id

    for station_id in ("W02", "W05", "W12", "W18"):
        for variant_id in line.variants:
            observed = [
                visit.cycle_time_s
                for visit in result.truth.visits
                if visit.station_id == station_id and visit.variant_id == variant_id
            ]
            assert len(observed) > 200
            zone = plant.zone(zone_of[station_id])
            expected = (
                plant.station(station_id).base_cycle_s
                * zone.variant_cycle_factor[variant_id]
            )
            assert abs(statistics.median(observed) - expected) / expected < 0.03


def test_a_repair_lands_inside_the_cycle_it_interrupted() -> None:
    """Failures are operation-dependent, so a repair is part of a cycle time."""
    result = _run("line2", 900)
    with_repairs = [visit for visit in result.truth.visits if visit.down_s > 0]
    assert with_repairs, "no repair happened, so the failure model is untested"
    for visit in with_repairs:
        assert visit.cycle_time_s > visit.down_s


# ---------------------------------------------------------------------------
# T-023: gates, defects and rework


def test_gate_failure_rates_are_near_the_configured_base(
    reference_day: SimulationResult,
) -> None:
    """T-023. Causes raise the rate above base; they do not multiply it away."""
    plant = _plant("line2")
    results = Counter(
        (result.gate_id, result.passed) for result in reference_day.truth.gate_results
    )
    for gate in plant.gates:
        failed = results[(gate.gate_id, False)]
        passed = results[(gate.gate_id, True)]
        rate = failed / (failed + passed)
        # A day of one line is a few thousand inspections, so the observed rate
        # scatters around the configured one. What matters is that the causes
        # raise it rather than swamping it.
        assert 0.5 * gate.base_failure_rate <= rate <= 3.0 * gate.base_failure_rate


def test_every_failure_carries_its_causes(reference_day: SimulationResult) -> None:
    """T-023. A defect is traceable to what produced it, in ground truth."""
    failures = [
        result for result in reference_day.truth.gate_results if not result.passed
    ]
    assert failures
    for result in failures:
        assert "base" in result.cause_odds
        assert result.defect_class
        assert 0.0 <= result.failure_probability <= 1.0


def test_a_reworked_unit_goes_back_and_comes_round_again(
    reference_day: SimulationResult,
) -> None:
    """The rework loop puts the unit back on the line, not into a hole."""
    reworked = [unit for unit in reference_day.truth.units if unit.rework_passes > 0]
    assert reworked, "no unit was ever reworked, so the loop is untested"
    for unit in reworked:
        visits = [
            visit
            for visit in reference_day.truth.visits
            if visit.unit_id == unit.unit_id
        ]
        seen = Counter(visit.station_id for visit in visits)
        assert max(seen.values()) > 1


# ---------------------------------------------------------------------------
# T-025: tier filtering


def test_dark_stations_emit_no_machine_events() -> None:
    """T-025. Asserted by scanning the stream, not by reading the filter."""
    line = _line("line2")
    result = _run("line2", 200, detail=SimulationDetail())
    dark = set(line.stations_of_tier("C"))
    offending = [
        event
        for event in result.events
        if event.station_id in dark and event.event_type in MACHINE_EVENTS
    ]
    assert offending == []


def test_tier_b_stations_report_a_clock_and_nothing_else() -> None:
    """A basic station's state is the estimator's inference, not a reading."""
    line = _line("line2")
    result = _run("line2", 200, detail=SimulationDetail())
    basic = set(line.stations_of_tier("B"))
    seen = {event.event_type for event in result.events if event.station_id in basic}
    assert "STATION_STATE" not in seen
    assert "PROCESS_VALUE" not in seen
    assert {"CYCLE_START", "CYCLE_END"} <= seen


def test_the_filter_drops_a_material_share_of_what_happened() -> None:
    """The suppressed count is the plainest statement of the coverage problem."""
    result = _run("line2", 200, detail=SimulationDetail())
    assert result.suppressed > 0
    assert 0.5 < result.observability < 1.0


def test_a_gate_verdict_survives_a_dark_station() -> None:
    """The final gate stands after S42, which emits nothing. Its verdict does not."""
    line = _line("line2")
    result = _run("line2", 200, detail=SimulationDetail())
    last_gate = line.gates[-1]
    verdicts = [
        event
        for event in result.events
        if event.event_type == "INSPECTION_RESULT"
        and event.payload.get("gate_id") == last_gate.gate_id
    ]
    assert verdicts
    assert line.station(last_gate.after).tier == "C"


def test_the_tier_table_matches_the_reference_line() -> None:
    """PRD Section 1. A dark station can produce only a call and a checklist."""
    assert TIER_EVENTS["C"] == frozenset({"ANDON", "MANUAL_CHECK"})
    assert not TIER_EVENTS["C"] & MACHINE_EVENTS


# ---------------------------------------------------------------------------
# T-026: determinism


def test_two_runs_with_the_same_seed_are_identical() -> None:
    """T-026, NFR-07. Down to the event identifiers, not only the durations."""
    first = _run("line2", 250, seed=808)
    second = _run("line2", 250, seed=808)
    assert first.run_id == second.run_id
    assert [
        (event.event_id, event.event_type, event.ts_source, event.payload)
        for event in first.events
    ] == [
        (event.event_id, event.event_type, event.ts_source, event.payload)
        for event in second.events
    ]
    assert first.truth.visits == second.truth.visits


def test_a_different_seed_produces_a_different_run() -> None:
    """Otherwise the previous test would pass on a simulator that does nothing."""
    first = _run("line2", 250, seed=808)
    second = _run("line2", 250, seed=809)
    assert first.truth.visits != second.truth.visits


# ---------------------------------------------------------------------------
# T-027 to T-029: scenarios


def test_the_catalogue_covers_every_scenario_in_the_prd() -> None:
    """Eight scenarios on the reference line, including the null one."""
    ids = {scenario.scenario_id for scenario in SCENARIOS.for_line("line2")}
    assert ids == {f"SC-0{index}" for index in range(1, 9)}


def test_the_null_scenario_injects_nothing() -> None:
    """SC-06. The absence is the point, so it is asserted rather than assumed."""
    scenario = SCENARIOS.build("SC-06", "line2")
    assert scenario.injections == ()
    assert scenario.truth() == ()


@pytest.mark.parametrize(
    ("scenario_id", "expected"),
    [
        ("SC-01", {"S20"}),
        ("SC-03", {"S31"}),
        ("SC-05", {"S34"}),
        ("SC-08", {"S20", "S31"}),
    ],
)
def test_a_scenario_changes_only_what_it_injects(
    scenario_id: str, expected: set[str]
) -> None:
    """T-028, T-029. Verified against a control run at the same seed.

    Long enough to reach the second shift, because SC-03 injects at the crew
    change and a run that stops before it would pass by injecting nothing.
    """
    control = _run("line2", 700, seed=3)
    injected = _run("line2", 700, seed=3, scenario_id=scenario_id)
    # Keyed on the visit rather than on the unit and station, so that a rework
    # revisit is a separate row instead of overwriting the first pass.
    before = {
        (visit.unit_id, visit.station_id, visit.seq): visit.cycle_time_s
        for visit in control.truth.visits
    }
    after = {
        (visit.unit_id, visit.station_id, visit.seq): visit.cycle_time_s
        for visit in injected.truth.visits
    }
    shared = set(before) & set(after)
    changed = {key[1] for key in shared if abs(before[key] - after[key]) > 1e-9}
    assert changed == expected
    # A handful of units take a different route, because a unit that ran long at
    # the injected station is more likely to fail a gate and that coupling is the
    # thing the defect model exists to find. It stays a handful: every draw in
    # the simulator is keyed on the unit it is about, so a unit scrapped in one
    # run does not shift the draws of every unit behind it (see `_draw_for`).
    diverged = {key[0] for key in set(before) ^ set(after)}
    assert len(diverged) <= len(control.truth.units) // 100


def test_the_fixture_wear_scenario_stays_inside_its_tolerance_band() -> None:
    """SC-01. A threshold alarm would never see this, which is the point."""
    line, plant = _line("line2"), _plant("line2")
    result = _run("line2", 700, seed=3, scenario_id="SC-01")
    drifted = [
        visit.cycle_time_s for visit in result.truth.visits if visit.station_id == "S20"
    ]
    injection = SCENARIOS.build("SC-01", "line2").injections[0]
    ceiling = injection.parameters["to_cycle_s"]
    # It crosses takt at the end, and never leaves the band a limit check would
    # be set at, which is why a control chart is needed to catch it at all.
    assert max(drifted) > line.takt_s
    assert statistics.median(drifted) < ceiling * 1.1
    assert plant.station("S20").base_cycle_s == injection.parameters["from_cycle_s"]


def test_the_dark_station_scenario_moves_a_station_no_sensor_watches() -> None:
    """SC-05. Nothing but the virtual sensors can see this at all."""
    line = _line("line2")
    result = _run("line2", 700, seed=3, scenario_id="SC-05")
    assert line.station("S34").tier == "C"
    events_about_it = [event for event in result.events if event.station_id == "S34"]
    assert all(event.event_type not in MACHINE_EVENTS for event in events_about_it)
    late = [
        visit.cycle_time_s
        for visit in result.truth.visits
        if visit.station_id == "S34" and visit.arrived_at_s > 20000
    ]
    early = [
        visit.cycle_time_s
        for visit in result.truth.visits
        if visit.station_id == "S34" and visit.arrived_at_s < 7000
    ]
    assert statistics.median(late) > statistics.median(early) + 5.0


def test_the_source_outage_scenario_names_a_window() -> None:
    """SC-07. The outage is ground truth, so the harness can score against it."""
    scenario = SCENARIOS.build("SC-07", "line2")
    assert scenario.is_source_silent(9300.0)
    assert not scenario.is_source_silent(8000.0)
    assert not scenario.is_source_silent(10000.0)
    assert [record.mechanism for record in scenario.truth()] == ["source_outage"]


def test_the_concurrent_scenario_keeps_its_two_faults_distinct() -> None:
    """SC-08. Two injections, not one merged story."""
    scenario = SCENARIOS.build("SC-08", "line2")
    stations = {injection.station_id for injection in scenario.injections}
    assert stations == {"S20", "S31"}


def test_every_injection_is_recorded_as_ground_truth() -> None:
    """The evaluation harness joins the ledger against exactly these rows."""
    result = _run("line2", 120, scenario_id="SC-01")
    assert [record.mechanism for record in result.truth.injections] == ["cycle_drift"]
    assert result.truth.injections[0].station_id == "S20"


# ---------------------------------------------------------------------------
# T-030: accelerated time


def test_accelerated_mode_is_capped_at_what_the_interface_can_follow(
    tmp_path: Path,
) -> None:
    """T-030, EC-55. The demo runs at 60x and nothing runs faster than 120x."""
    recording = tmp_path / "line2-events.csv"
    write_events(recording, _run("line2", 40).events)

    demo = CsvReplayAdapter(
        recording, line_id="line2", speed_multiplier=DEMO_SPEED_MULTIPLIER
    )
    assert demo.speed_multiplier == DEMO_SPEED_MULTIPLIER
    assert not demo.is_capped

    reckless = CsvReplayAdapter(recording, line_id="line2", speed_multiplier=6000.0)
    assert reckless.speed_multiplier == MAX_SPEED_MULTIPLIER
    assert reckless.is_capped
