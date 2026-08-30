"""Virtual sensors for dark stations. T-040, T-041, T-042.

The most important tests in the project. Six of Line 2's 42 stations emit
nothing at all, and this module is the whole of the twin's answer to that. If
the coverage test below fails, the central claim fails with it and no amount of
work downstream recovers it.

The gate for Phase 1 is the first test in this file: the derived interval has to
contain the simulator's ground truth in at least 90 percent of cycles over 5,000
cycles (AC-005, PRD Section 5).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import pytest

from plantsim.model import (
    SimulationDetail,
    SimulationRequest,
    SimulationResult,
    run_simulation,
)
from plantsim.parameters import load_plant_model
from plantsim.truth import VisitTruth
from twin.config import LineDefinition, load_line_definition
from twin.state.virtual_sensors import DarkSpan, VirtualSensors, dark_spans

REPO_ROOT = Path(__file__).resolve().parent.parent
COVERAGE_CYCLES = 5000
COVERAGE_TARGET = 0.90

# Timing only. Process values, state words and buffer traces multiply the work
# a run does by roughly nine and answer no question this file asks.
TIMING_ONLY = SimulationDetail(
    process_values=False, station_state=False, buffer_levels=False
)


@dataclass(frozen=True)
class Derived:
    """One run, its ground truth, and every span estimate the twin made."""

    line: LineDefinition
    result: SimulationResult
    sensors: VirtualSensors
    # The truth indexed by unit and station. A run is a quarter of a million
    # visits and the coverage check asks about five thousand of them, so a scan
    # per question would make this file take ten minutes rather than two.
    by_unit: dict[str, dict[str, VisitTruth]]

    def true_sum(self, unit_id: str, station_ids: tuple[str, ...]) -> float | None:
        """The true total cycle time of a set of stations for one unit."""
        visits = self.by_unit.get(unit_id, {})
        if not set(station_ids) <= set(visits):
            return None
        return sum(visits[station_id].cycle_time_s for station_id in station_ids)

    def true_non_work(self, unit_id: str, span: DarkSpan) -> float | None:
        """The true time one unit spent not working inside a span.

        Blocking is a station waiting to hand its unit on. Queueing is the unit
        waiting to be picked up. Both happen inside the span and neither is
        work, so the twin's non-work bound has to cover their sum. The queueing
        before the station at the far end counts too: the unit is still inside
        the span until that station takes it.
        """
        dark = span.dark_station_ids
        downstream = span.downstream_id
        if downstream is None:
            return None
        by_station = self.by_unit.get(unit_id, {})
        if not set(dark) <= set(by_station) or downstream not in by_station:
            return None
        total = sum(
            by_station[station_id].blocked_s + by_station[station_id].queued_before_s
            for station_id in dark
        )
        return total + by_station[downstream].queued_before_s


def _derive(line_name: str, units: int, seed: int = 20260301) -> Derived:
    line = load_line_definition(REPO_ROOT / "config" / "lines" / f"{line_name}.yaml")
    plant = load_plant_model(REPO_ROOT / "config" / "plantsim" / f"{line_name}.yaml")
    result = run_simulation(
        SimulationRequest(
            line=line, plant=plant, seed=seed, units=units, detail=TIMING_ONLY
        )
    )
    sensors = VirtualSensors(line)
    for event in result.events:
        sensors.observe(event)
    by_unit: dict[str, dict[str, VisitTruth]] = {}
    for visit in result.truth.visits:
        by_unit.setdefault(visit.unit_id, {})[visit.station_id] = visit
    return Derived(line=line, result=result, sensors=sensors, by_unit=by_unit)


@pytest.fixture(scope="module")
def line7_run() -> Derived:
    """Line 7 over 5,000 cycles. It carries both dark-station cases."""
    return _derive("line7", COVERAGE_CYCLES)


@pytest.fixture(scope="module")
def line2_run() -> Derived:
    """The reference line over 5,000 cycles."""
    return _derive("line2", COVERAGE_CYCLES)


def _coverage(run: Derived) -> dict[str, tuple[int, int]]:
    """Covered and total counts per span, over every estimate the twin made."""
    tally: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for estimate in run.sensors.estimates():
        truth = run.true_sum(estimate.unit_id, estimate.span.dark_station_ids)
        if truth is None:
            continue
        counts = tally[estimate.span.span_id]
        counts[1] += 1
        if estimate.total.interval.contains(truth):
            counts[0] += 1
    return {span_id: (hit, total) for span_id, (hit, total) in tally.items()}


# ---------------------------------------------------------------------------
# The gate. T-040, AC-005.


def test_the_derived_interval_contains_ground_truth(line7_run: Derived) -> None:
    """At least 90 percent of cycles, over 5,000 cycles, on both dark cases."""
    coverage = _coverage(line7_run)
    assert coverage, "no dark span produced an estimate"
    for span_id, (hit, total) in sorted(coverage.items()):
        assert total >= 1000, f"{span_id}: only {total} estimates, too few to judge"
        assert hit / total >= COVERAGE_TARGET, (
            f"{span_id}: interval contained ground truth in {hit / total:.3f} of "
            f"{total} cycles, below the {COVERAGE_TARGET} gate in PRD Section 5"
        )


def test_the_derived_interval_contains_ground_truth_on_the_reference_line(
    line2_run: Derived,
) -> None:
    """The same gate on Line 2, whose dark span is five stations long."""
    coverage = _coverage(line2_run)
    assert coverage, "no dark span produced an estimate"
    for span_id, (hit, total) in sorted(coverage.items()):
        assert hit / total >= COVERAGE_TARGET, (
            f"{span_id}: interval contained ground truth in {hit / total:.3f} of "
            f"{total} cycles, below the {COVERAGE_TARGET} gate"
        )


# ---------------------------------------------------------------------------
# What the module may never do. CODING_STANDARDS.md 1.1 and 1.2.


def test_no_dark_station_ever_gets_a_point_value(line2_run: Derived) -> None:
    """Rule 3. A bound is not a midpoint, anywhere, for any station."""
    seen = 0
    for estimate in line2_run.sensors.estimates():
        for station_id, value in estimate.per_station.items():
            seen += 1
            assert value.interval.width > 0, (
                f"{station_id} received a point value from a virtual sensor"
            )
            with pytest.raises(ValueError, match="no point value"):
                _ = value.point
    assert seen > 0


def test_every_derived_value_is_marked_inferred(line2_run: Derived) -> None:
    """Rule 2. An inference is never presented as a measurement."""
    for estimate in line2_run.sensors.estimates():
        assert estimate.total.provenance == "INFERRED"
        for value in estimate.per_station.values():
            assert value.provenance == "INFERRED"


def test_confidence_is_reported_and_bounded(line2_run: Derived) -> None:
    """Every estimate carries a confidence in [0, 1] derived from its width."""
    for estimate in line2_run.sensors.estimates():
        assert 0.0 <= estimate.total.confidence <= 1.0
        assert estimate.total.basis.strip()


# ---------------------------------------------------------------------------
# Separability. T-042, STA-07, EC-17.


def test_a_lone_dark_station_is_resolved(line7_run: Derived) -> None:
    """W05 and W17 each sit alone between two instrumented stations."""
    resolved = [span for span in dark_spans(line7_run.line) if span.is_separable]
    assert {span.dark_station_ids for span in resolved} == {("W05",), ("W17",)}
    for span in resolved:
        estimates = [
            estimate
            for estimate in line7_run.sensors.estimates()
            if estimate.span.span_id == span.span_id
        ]
        assert estimates, f"{span.span_id} produced no estimate"
        for estimate in estimates:
            assert estimate.total.resolution == "RESOLVED"


def test_adjacent_dark_stations_are_unresolved(line2_run: Derived) -> None:
    """STA-07. The sum is bounded; neither station individually is."""
    span = next(
        item for item in dark_spans(line2_run.line) if len(item.dark_station_ids) > 1
    )
    assert span.dark_station_ids == ("S33", "S34", "S35", "S36", "S37")
    estimates = [
        estimate
        for estimate in line2_run.sensors.estimates()
        if estimate.span.span_id == span.span_id
    ]
    assert estimates
    for estimate in estimates:
        assert estimate.total.resolution == "RESOLVED"
        for station_id in span.dark_station_ids:
            assert estimate.per_station[station_id].resolution == "UNRESOLVED"


def test_the_individual_bound_is_wider_than_the_shared_one(
    line2_run: Derived,
) -> None:
    """Adding a dark station to a span never narrows any bound in it."""
    for estimate in line2_run.sensors.estimates():
        if len(estimate.span.dark_station_ids) == 1:
            continue
        for value in estimate.per_station.values():
            assert value.interval.width >= estimate.total.interval.width


def test_a_dark_station_with_no_downstream_scan_is_unresolved(
    line2_run: Derived,
) -> None:
    """S42 is dark and last. Nothing downstream ever scans the unit again."""
    unresolved = {item.station_id: item for item in line2_run.sensors.unresolved()}
    assert "S42" in unresolved
    assert unresolved["S42"].resolved_by
    assert line2_run.sensors.latest("S42") is None


def test_a_span_longer_than_the_line_allows_is_not_modelled() -> None:
    """EC-18. A dark run past the configured length is excluded, not widened."""
    line = load_line_definition(REPO_ROOT / "config" / "lines" / "line2.yaml")
    tightened = line.model_copy(
        update={"state": line.state.model_copy(update={"max_dark_span": 2})}
    )
    spans = dark_spans(tightened)
    long_span = next(span for span in spans if len(span.dark_station_ids) > 2)
    assert not long_span.is_modelled


# ---------------------------------------------------------------------------
# Blocking and starving attribution. T-041.


def test_the_non_work_bound_contains_the_real_waiting(line2_run: Derived) -> None:
    """Whatever the label, the bound on the unaccounted time has to hold."""
    contained = total = 0
    for estimate in line2_run.sensors.estimates():
        truth = line2_run.true_non_work(estimate.unit_id, estimate.span)
        if truth is None:
            continue
        total += 1
        if estimate.attribution.non_work.contains(truth):
            contained += 1
    assert total > 1000
    assert contained / total >= COVERAGE_TARGET


def _labelled(run: Derived, span_id: str) -> dict[str, tuple[int, int]]:
    """How often each label went with a unit that really did wait."""
    tally: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for estimate in run.sensors.estimates():
        if estimate.span.span_id != span_id:
            continue
        truth = run.true_non_work(estimate.unit_id, estimate.span)
        if truth is None:
            continue
        counts = tally[estimate.attribution.label]
        counts[1] += 1
        if truth > 0:
            counts[0] += 1
    return {label: (hit, total) for label, (hit, total) in tally.items()}


def test_blocking_is_claimed_only_where_the_unit_really_waited(
    line7_run: Derived,
) -> None:
    """T-041. On a separable span the label separates, and here is the margin.

    W05 sits alone between two instrumented stations, so the station beyond the
    span is the only thing that could have held this unit up, and its occupancy
    is a reading rather than a guess.
    """
    labelled = _labelled(line7_run, "W04:W06")
    blocked_hit, blocked_total = labelled["BLOCKED"]
    assert blocked_total > 200
    # Measured at 0.99 against a base rate of 0.73. The margin comes from asking
    # when the station beyond the span was occupied rather than whether it ever
    # was: on a line running to takt it always was, so the second question
    # separates nothing (see `_BLOCKED_TAIL_SHARE`).
    assert blocked_hit / blocked_total >= 0.90

    working_hit, working_total = labelled["WORK"]
    assert working_total > 0
    assert working_hit / working_total < blocked_hit / blocked_total - 0.2, (
        "the labels do not separate, so they are describing nothing"
    )
    # The majority answer is still UNKNOWN, which is the honest one. A labeller
    # that claimed to know on nearly every passage would be the failure this
    # module exists to avoid, whatever its precision looked like.
    unknown_total = _labelled(line7_run, "W04:W06").get("UNKNOWN", (0, 0))[1]
    assert unknown_total > blocked_total


def test_a_span_that_cannot_be_separated_claims_nothing(line2_run: Derived) -> None:
    """T-041, STA-07. Five dark stations in a row, so the answer is UNKNOWN.

    The station beyond the span is occupied for most of a takt on any line
    running to takt, so its occupancy carries no information about which of the
    five held a unit up, or whether any of them did. A blocked label here would
    agree with the truth at the base rate, which is another way of saying it
    would be describing nothing.
    """
    labels = {
        estimate.attribution.label
        for estimate in line2_run.sensors.estimates()
        if len(estimate.span.dark_station_ids) > 1
    }
    assert labels == {"UNKNOWN"}


def test_attribution_says_unknown_rather_than_guessing(line2_run: Derived) -> None:
    """Every estimate carries a label from the closed set, and a reason."""
    for estimate in line2_run.sensors.estimates():
        assert estimate.attribution.label in {
            "WORK",
            "BLOCKED",
            "STARVED",
            "UNKNOWN",
        }
        assert estimate.attribution.basis.strip()


# ---------------------------------------------------------------------------
# Topology


def test_dark_spans_are_found_from_the_line_definition_alone() -> None:
    """Which stations are dark, and what flanks them, is configuration."""
    line = load_line_definition(REPO_ROOT / "config" / "lines" / "line2.yaml")
    spans = dark_spans(line)
    covered = tuple(
        station_id for span in spans for station_id in span.dark_station_ids
    )
    assert covered == line.stations_of_tier("C")
    by_id = {span.dark_station_ids: span for span in spans}
    inner = by_id[("S33", "S34", "S35", "S36", "S37")]
    assert inner.upstream_id == "S32"
    assert inner.downstream_id == "S38"
    # S32 to S33, then four hops inside the span, then S37 to S38.
    assert inner.transport_s == pytest.approx(4.2 * 6)
    tail = by_id[("S42",)]
    assert tail.downstream_id is None
    assert not tail.is_resolvable
