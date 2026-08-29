"""Sensor value scoring, the retro-trace and the loss ledger.

T-097 to T-099, AC-026 to AC-029, AC-050, AC-051.

The tests that matter here are the ones about refusing to answer: a station the
gate should not let through, a walk that finds nothing worth reporting, a
containment list that has to recall most of an affected lot, and a
reconciliation that is allowed to disagree with itself.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from twin.config.loader import load_line_definition, load_sensor_catalogue
from twin.domain.estimate import Estimate, Interval
from twin.domain.signature import ProcessSignature, StationVisit
from twin.retro.trace import DISCLAIMER, RetroTracer, to_csv
from twin.sensors.value import (
    SensorValueService,
    dark_visit_share,
)
from twin.state.virtual_sensors import VirtualSensors

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO_ROOT / "config"

EPOCH = datetime(2026, 3, 2, 6, 0, tzinfo=UTC)


@pytest.fixture(name="line")
def fixture_line():
    return load_line_definition(CONFIG_DIR / "lines" / "line2.yaml")


@pytest.fixture(name="catalogue")
def fixture_catalogue():
    return load_sensor_catalogue(CONFIG_DIR / "catalogue" / "sensors.yaml")


def _visit(station_id: str, seq: int, at: datetime, cycle_s: float, lot: str = ""):
    return StationVisit(
        station_id=station_id,
        seq=seq,
        arrived_at=at,
        departed_at=at + timedelta(seconds=cycle_s),
        dwell_s=cycle_s,
        cycle_time=Estimate.measured(cycle_s, f"{station_id} reported its cycle"),
        state_during="RUNNING",
        blocked_s=None,
        starved_s=None,
        part_lots=(lot,) if lot else (),
    )


def _signature(unit_id: str, at: datetime, cycles: dict[str, float], lot: str = ""):
    visits = tuple(
        _visit(station_id, index, at + timedelta(seconds=60 * index), cycle_s, lot)
        for index, (station_id, cycle_s) in enumerate(cycles.items(), start=1)
    )
    return ProcessSignature(
        unit_id=unit_id,
        line_id="line2",
        variant_id="V-STD",
        entered_at=at,
        exited_at=None,
        status="IN_PROCESS",
        visits=visits,
    )


class TestSensorValue:
    def test_a_measured_station_never_generates_a_card(self, line, catalogue):
        """AC-050. A station the twin sees clearly does not need a sensor."""
        service = SensorValueService(line, catalogue)
        seen = service._observability(
            "S20",
            _Snapshot(
                tier="A",
                last_cycle=Estimate.measured(58.4, "S20 reported its own cycle"),
                observed_cycles=200,
            ),
            None,
        )
        assert seen.score >= line.sensors.observability_threshold
        assert seen.unknown == ""

    def test_an_unseen_but_unimportant_station_generates_nothing(self, line, catalogue):
        """AC-050. Both halves of the gate have to open, not just one."""
        service = SensorValueService(line, catalogue)
        blind = service._observability(
            "S33",
            _Snapshot(
                tier="C",
                last_cycle=Estimate.inferred(
                    Interval(0.0, 260.0), "bounded from the flanking scans", 0.1
                ),
                observed_cycles=0,
            ),
            None,
        )
        assert blind.score < line.sensors.observability_threshold
        cards = service.recommend(
            (blind,),
            (_Criticality("S33", 0.0),),
            expected_unit_loss=1.0,
            at=EPOCH,
        )
        assert cards == ()

    def test_a_card_states_everything_the_interface_renders(self, line, catalogue):
        """AC-051."""
        service = SensorValueService(line, catalogue)
        blind = service._observability(
            "S33",
            _Snapshot(
                tier="C",
                last_cycle=Estimate.inferred(
                    Interval(0.0, 260.0), "bounded from the flanking scans", 0.1
                ),
                observed_cycles=0,
            ),
            None,
        )
        cards = service.recommend(
            (blind,),
            (_Criticality("S33", 0.6),),
            expected_unit_loss=2.0,
            at=EPOCH,
        )
        assert len(cards) == 1
        card = cards[0]
        assert card.unknown
        assert card.option.name
        assert card.option.indicative_cost_usd > 0
        assert card.cost_source.lower().startswith("assumption")
        assert card.confidence_projected > card.confidence_now
        assert card.modelled_annual_value.provenance == "DERIVED"
        assert card.next_window

    def test_the_modelled_value_is_zero_where_the_unit_value_is(self, line, catalogue):
        """A plant that has supplied no contribution margin sees zero, not a guess."""
        assert line.sensors.unit_value_usd == 0.0
        service = SensorValueService(line, catalogue)
        blind = service._observability(
            "S33",
            _Snapshot(
                tier="C",
                last_cycle=Estimate.inferred(Interval(0.0, 260.0), "bounded", 0.1),
                observed_cycles=0,
            ),
            None,
        )
        cards = service.recommend(
            (blind,),
            (_Criticality("S33", 0.6),),
            expected_unit_loss=2.0,
            at=EPOCH,
        )
        assert cards[0].modelled_annual_value.hi == 0.0
        assert "unit value is zero" in cards[0].modelled_annual_value.basis

    def test_dark_visits_are_counted_per_unit(self):
        """Criticality's defect half is measured, not assumed."""
        inferred = Estimate.inferred(Interval(0.0, 200.0), "bounded", 0.2)
        signature = ProcessSignature(
            unit_id="3C4PDCBG7JT100001",
            line_id="line2",
            variant_id="V-STD",
            entered_at=EPOCH,
            exited_at=None,
            status="IN_PROCESS",
            visits=(
                StationVisit(
                    station_id="S33",
                    seq=1,
                    arrived_at=EPOCH,
                    departed_at=EPOCH,
                    dwell_s=0.0,
                    cycle_time=inferred,
                    state_during="IDLE_UNKNOWN",
                    blocked_s=None,
                    starved_s=None,
                ),
            ),
        )
        assert dark_visit_share((signature,)) == {"S33": 1.0}


class TestRetroTrace:
    def test_a_unit_with_no_signature_yields_nothing(self, line):
        """EC-34. A verdict for a unit the twin never saw is not a trace."""
        tracer = RetroTracer(line)
        assert tracer.trace("3C4PDCBG7JT999999", "G3", EPOCH, ()) is None

    def test_the_disclaimer_is_part_of_the_response(self, line):
        """AC-029. It is a contract field, not a decoration a client may drop."""
        tracer = RetroTracer(line)
        subject = _signature("3C4PDCBG7JT100001", EPOCH, {"S12": 58.0}, "B-4471")
        trace = tracer.trace(
            "3C4PDCBG7JT100001", "G3", EPOCH + timedelta(minutes=30), (subject,)
        )
        assert trace is not None
        assert trace.disclaimer == DISCLAIMER
        assert "root cause" not in trace.disclaimer.replace(
            "not a confirmed root cause", ""
        )

    def test_a_diverging_station_is_found_against_its_own_population(self, line):
        """AC-026. The comparison is contemporaneous, not against a baseline."""
        tracer = RetroTracer(line)
        at = EPOCH + timedelta(hours=1)
        peers = [
            _signature(
                f"3C4PDCBG7JT10001{index}",
                at,
                {"S12": 56.0 + (index % 5) * 0.9},
                "B-4470",
            )
            for index in range(10)
        ]
        subject = _signature("3C4PDCBG7JT100099", at, {"S12": 92.0}, "B-4471")
        trace = tracer.trace(
            "3C4PDCBG7JT100099",
            "G3",
            at + timedelta(minutes=30),
            (*peers, subject),
        )
        assert trace is not None
        assert trace.hypotheses
        assert trace.hypotheses[0].station_id == "S12"
        assert trace.hypotheses[0].divergence > 1.5
        assert trace.runtime_s < 10.0

    def test_containment_recalls_the_lot(self, line):
        """AC-027. The list is built on shared evidence a person can check."""
        tracer = RetroTracer(line)
        at = EPOCH + timedelta(hours=1)
        affected = [
            _signature(
                f"3C4PDCBG7JT10002{index}",
                at,
                {"S12": 56.0 + (index % 5) * 0.9},
                "B-4471",
            )
            for index in range(10)
        ]
        clean = [
            _signature(
                f"3C4PDCBG7JT10003{index}",
                at,
                {"S12": 56.0 + (index % 5) * 0.9},
                "B-4470",
            )
            for index in range(10)
        ]
        subject = _signature("3C4PDCBG7JT100099", at, {"S12": 92.0}, "B-4471")
        trace = tracer.trace(
            "3C4PDCBG7JT100099",
            "G3",
            at + timedelta(minutes=30),
            (*affected, *clean, subject),
        )
        assert trace is not None
        found = {row.unit_id for row in trace.on_line} | {
            row.unit_id for row in trace.in_yard
        }
        carried = {item.unit_id for item in affected}
        assert len(found & carried) / len(carried) >= 0.80
        assert not (found & {item.unit_id for item in clean})

    def test_the_export_carries_the_evidence_per_row(self, line):
        """AC-028."""
        tracer = RetroTracer(line)
        at = EPOCH + timedelta(hours=1)
        others = [
            _signature(
                f"3C4PDCBG7JT10004{index}",
                at,
                {"S12": 56.0 + index * 0.9},
                "B-4471",
            )
            for index in range(8)
        ]
        subject = _signature("3C4PDCBG7JT100099", at, {"S12": 92.0}, "B-4471")
        trace = tracer.trace(
            "3C4PDCBG7JT100099",
            "G3",
            at + timedelta(minutes=30),
            (*others, subject),
        )
        assert trace is not None
        text = to_csv(trace)
        header, *rows = text.strip().splitlines()
        assert "evidence" in header
        assert rows
        assert "lot B-4471" in text
        assert DISCLAIMER in text


class TestVirtualSensorsStillHold:
    def test_every_dark_station_is_named_and_none_is_given_a_point(self, line):
        """Rule 3 in CLAUDE.md, expressed over the whole line at once."""
        sensors = VirtualSensors(line)
        dark = {station.station_id for station in line.stations if station.tier == "C"}
        covered = {
            station_id for span in sensors.spans for station_id in span.dark_station_ids
        }
        assert covered == dark


class _Snapshot:
    """The two fields observability reads off a station snapshot."""

    def __init__(self, tier: str, last_cycle, observed_cycles: int) -> None:
        self.tier = tier
        self.last_cycle = last_cycle
        self.observed_cycles = observed_cycles


class _Criticality:
    """A criticality score with the fields the recommender reads."""

    def __init__(self, station_id: str, score: float) -> None:
        self.station_id = station_id
        self.score = score
        self.critical_path_share = score
        self.defect_confidence_impact = 0.0
        self.basis = f"{station_id} named the constraint"
