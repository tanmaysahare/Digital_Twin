"""The sandbox, the loss ledger, the readiness model and the business case.

T-094 to T-095, T-110, T-117, T-118, T-122. AC-030 to AC-033, AC-070, AC-071.

Every test here is about a refusal or a disclosure: the sandbox refusing a
fourth option, the loss reconciliation refusing to tie by construction, the
readiness model refusing to score a site it has not seen, the business case
refusing an assumption with no source, and topology discovery refusing to
invent a buffer capacity.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from connector.protocol import CanonicalEvent
from twin.config.loader import load_line_definition
from twin.counterfactual.engine import (
    MAX_OPTIONS,
    CounterfactualEngine,
    Intervention,
    Option,
    RunRequest,
)
from twin.domain.shifts import ProductionCalendar
from twin.forecast.des import ForecastSeed, StationPlan
from twin.program import business_case
from twin.program.readiness import StreamReading, measure, score
from twin.state.losses import LossLedger
from twin.topology.discover import TopologyDiscoverer

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "config"
EPOCH = datetime(2026, 3, 2, 6, 0, tzinfo=UTC)


@pytest.fixture(name="line")
def fixture_line():
    return load_line_definition(CONFIG_DIR / "lines" / "line2.yaml")


@pytest.fixture(name="calendar")
def fixture_calendar(line):
    return ProductionCalendar(line, EPOCH)


def _seed(line) -> ForecastSeed:
    """A seed with a usable pool at every station and nothing warm on the line."""
    pool = tuple(54.0 + (index % 7) * 1.1 for index in range(60))
    return ForecastSeed(
        line_id=line.line_id,
        at_s=3600.0,
        plans=tuple(
            StationPlan(station_id=station.station_id, pools={"": pool})
            for station in line.stations
        ),
        warm_units=(),
        link_occupancy=tuple(0 for _ in line.stations),
        upcoming_variants=("V-STD",) * 120,
    )


class TestSandbox:
    def test_a_fourth_option_is_refused(self, line, calendar):
        """AC-033. Three plus doing nothing is a decision; more is a table."""
        engine = CounterfactualEngine(line, calendar)
        options = tuple(
            Option(
                label=f"Add an operator at S2{index}",
                interventions=(
                    Intervention(type="ADD_OPERATOR", station_id=f"S2{index}"),
                ),
            )
            for index in range(MAX_OPTIONS + 1)
        )
        with pytest.raises(ValueError, match="at most"):
            engine.run(_seed(line), options, RunRequest(run_id="cf-too-many"))

    def test_baseline_and_options_share_their_seeds(self, line, calendar):
        """AC-031. The comparison is paired, which is why the difference reads."""
        engine = CounterfactualEngine(line, calendar)
        seed = _seed(line)
        request = RunRequest(run_id="cf-shared", replications=8, horizon_s=1800.0)
        first = engine.run(seed, (), request)
        again = engine.run(seed, (), request)
        assert first.baseline_units.lo == again.baseline_units.lo
        assert first.baseline_units.hi == again.baseline_units.hi

    def test_an_operator_at_the_slowest_station_is_modelled_as_a_change(
        self, line, calendar
    ):
        """AC-030. The option has to differ from doing nothing, or it says nothing."""
        engine = CounterfactualEngine(line, calendar)
        result = engine.run(
            _seed(line),
            (
                Option(
                    label="Add an operator at S20",
                    interventions=(
                        Intervention(type="ADD_OPERATOR", station_id="S20"),
                    ),
                ),
            ),
            RunRequest(run_id="cf-operator", replications=12, horizon_s=1800.0),
        )
        assert len(result.options) == 1
        option = result.options[0]
        assert option.assumptions
        assert "0.88" in option.assumptions[0] or "factor" in option.assumptions[0]
        assert option.units.provenance == "DERIVED"
        assert option.delta.provenance == "DERIVED"

    def test_a_reduced_run_states_the_reduction(self, line, calendar):
        """AC-032. A degraded answer says so where the answer is."""
        engine = CounterfactualEngine(line, calendar)
        options = tuple(
            Option(
                label=f"Add an operator at S1{index}",
                interventions=(
                    Intervention(type="ADD_OPERATOR", station_id=f"S1{index}"),
                ),
            )
            for index in range(3)
        )
        result = engine.run(
            _seed(line),
            options,
            RunRequest(
                run_id="cf-budget",
                replications=200,
                budget_s=0.01,
                horizon_s=1800.0,
            ),
        )
        assert result.degraded
        assert result.degraded_note
        assert str(result.replications_used) in result.degraded_note

    def test_nothing_the_sandbox_does_touches_the_line(self, line, calendar):
        """The architectural boundary, asserted rather than assumed."""
        engine = CounterfactualEngine(line, calendar)
        for name in dir(engine):
            assert not name.startswith(
                ("write", "send", "apply_to", "command", "actuate")
            )


class TestLossLedger:
    def test_the_two_sides_are_computed_from_different_evidence(self, line, calendar):
        """AC-061. A reconciliation that ties by construction says nothing."""
        ledger = LossLedger(line, calendar)
        at = EPOCH + timedelta(hours=1)
        # One station works for 50 s and is then blocked for 10 s, once.
        ledger.observe(_event("CYCLE_END", "S20", at, {"cycle_time_s": 50.0}))
        ledger.observe(_event("UNIT_DEPART", "S20", at + timedelta(seconds=10), {}))
        split = ledger.split(at - timedelta(minutes=5), at + timedelta(minutes=5))
        assert split.minutes["blocked"] == pytest.approx(10.0 / 60.0, rel=1e-3)
        # The implied total comes from production time against work recorded and
        # is far larger, because 41 other stations reported nothing at all.
        assert split.implied_total_min > split.accounted_min
        assert split.available_min > split.implied_total_min

    def test_a_period_is_clipped_to_the_window_by_production_time(self, line, calendar):
        """A stoppage that began before the window is not credited to it in full."""
        ledger = LossLedger(line, calendar)
        began = EPOCH + timedelta(hours=1)
        ended = began + timedelta(minutes=20)
        ledger.observe(_event("CYCLE_END", "S20", began, {"cycle_time_s": 50.0}))
        ledger.observe(_event("UNIT_DEPART", "S20", ended, {}))
        whole = ledger.split(began - timedelta(minutes=1), ended + timedelta(minutes=1))
        part = ledger.split(ended - timedelta(minutes=5), ended + timedelta(minutes=1))
        assert whole.minutes["blocked"] > part.minutes["blocked"]
        assert part.minutes["blocked"] == pytest.approx(5.0, rel=0.05)

    def test_the_reconciliation_says_which_way_it_disagrees(self, line, calendar):
        """The sentence has to work for a negative gap as well as a positive one."""
        ledger = LossLedger(line, calendar)
        at = EPOCH + timedelta(hours=1)
        ledger.observe(_event("CYCLE_END", "S20", at, {"cycle_time_s": 50.0}))
        ledger.observe(_event("UNIT_DEPART", "S20", at + timedelta(seconds=10), {}))
        text = ledger.split(
            at - timedelta(minutes=5), at + timedelta(minutes=5)
        ).reconciliation()
        assert "Sum of causes" in text
        assert "available" in text
        assert "Difference" in text


class TestReadiness:
    def test_a_site_with_no_stream_is_not_scored_as_a_bad_site(self, line):
        """AC-070. A component that could not be measured is not one that failed."""
        result = score(line, measure(line, StreamReading()), 0.0)
        assert result.band == "NOT READY"
        assert "no event stream" in result.note.lower()
        assert any(item.value == "not measured" for item in result.components)

    def test_a_connected_site_scores_from_what_it_emitted(self, line):
        """AC-070. Every component is present and banded in words."""
        reading = StreamReading(
            stations_emitting=36,
            units_with_full_signature=480,
            units_seen=500,
            inspection_results=1400,
            max_skew_s=0.4,
            events_seen=190000,
        )
        result = score(line, measure(line, reading), 325.0)
        assert result.band in {"READY", "READY WITH INSTRUMENTATION"}
        assert len(result.components) == 6
        assert all(0.0 <= item.score <= 1.0 for item in result.components)
        assert sum(item.weight for item in result.components) == pytest.approx(1.0)


class TestBusinessCase:
    def test_an_assumption_without_a_source_is_refused(self):
        """AC-071. A number nobody can trace is a number nobody can defend."""
        with pytest.raises(ValueError, match="no source"):
            business_case.Assumption(
                key="baseline_stop_min_per_month",
                label="Unplanned stop minutes",
                value=1200.0,
                unit="min",
                source="   ",
                uncertainty="unknown",
            )

    def test_precision_comes_from_the_ledger_and_is_not_editable(self):
        """The case rests on what the twin has been measured at, not on a target."""
        assumptions = business_case.defaults(
            measured_precision=None,
            precision_basis="No prediction has been scored yet.",
            instrumentation_cost_usd=325.0,
            unit_value_usd=0.0,
        )
        precision = next(
            item for item in assumptions if item.key == "forecast_precision"
        )
        assert precision.value == 0.0
        assert not precision.editable
        edited = business_case.apply(assumptions, {"forecast_precision": 0.9})
        assert (
            next(item for item in edited if item.key == "forecast_precision").value
            == 0.0
        )

    def test_the_sensitivity_table_is_always_produced(self):
        """AC-071. A case that cannot be interrogated is not a case."""
        assumptions = business_case.defaults(
            measured_precision=0.62,
            precision_basis="Measured from the ledger.",
            instrumentation_cost_usd=325.0,
            unit_value_usd=180.0,
        )
        edited = business_case.apply(
            assumptions, {"baseline_stop_min_per_month": 1400.0}
        )
        result = business_case.evaluate(edited)
        assert result.sensitivity
        swings = [row.swing for row in result.sensitivity]
        assert swings == sorted(swings, reverse=True)
        assert result.annual_benefit.hi > result.annual_benefit.lo
        assert result.payback_months is not None

    def test_a_zero_unit_value_produces_zero_and_says_so(self):
        """The plant has supplied no margin, so the case is zero rather than a guess."""
        result = business_case.evaluate(
            business_case.defaults(
                measured_precision=0.62,
                precision_basis="Measured from the ledger.",
                instrumentation_cost_usd=325.0,
                unit_value_usd=0.0,
            )
        )
        assert result.annual_benefit.hi == 0.0
        assert any("margin per unit is zero" in note for note in result.notes)


class TestTopology:
    def test_a_buffer_capacity_is_left_blank_rather_than_guessed(self):
        """AC-081."""
        draft = TopologyDiscoverer().draft()
        buffers = next(item for item in draft.fields if item.field == "buffers")
        assert buffers.value is None
        assert "lower bound" in buffers.note
        assert "buffers" in draft.not_inferable

    def test_station_order_comes_from_the_routes_units_took(self):
        """The order is observed rather than assumed from an identifier's digits."""
        discoverer = TopologyDiscoverer()
        at = EPOCH
        for unit in range(8):
            moment = at + timedelta(seconds=60 * unit)
            for index, station_id in enumerate(("S01", "S02", "S03")):
                arrive = moment + timedelta(seconds=10 * index)
                discoverer.observe(
                    _event(
                        "UNIT_ARRIVE",
                        station_id,
                        arrive,
                        {},
                        unit_id=f"3C4PDCBG7JT10000{unit}",
                    )
                )
                discoverer.observe(
                    _event(
                        "CYCLE_END",
                        station_id,
                        arrive + timedelta(seconds=5),
                        {"cycle_time_s": 50.0, "variant_id": "V-STD"},
                    )
                )
                discoverer.observe(
                    _event(
                        "UNIT_DEPART",
                        station_id,
                        arrive + timedelta(seconds=8),
                        {},
                        unit_id=f"3C4PDCBG7JT10000{unit}",
                    )
                )
        draft = discoverer.draft()
        assert [item.field for item in draft.stations] == ["S01", "S02", "S03"]
        variants = next(item for item in draft.fields if item.field == "variants")
        assert variants.value == "V-STD"


def _event(
    event_type: str,
    station_id: str | None,
    at: datetime,
    payload: dict[str, object],
    unit_id: str | None = None,
) -> CanonicalEvent:
    """One canonical event, built for a test rather than for a wire."""
    from uuid import uuid4

    return CanonicalEvent(
        event_id=uuid4(),
        event_type=event_type,  # type: ignore[arg-type]
        line_id="line2",
        station_id=station_id,
        unit_id=unit_id,
        ts_source=at,
        ts_ingest=at,
        payload=payload,
        source_adapter="sim",
    )
