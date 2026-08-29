"""Source adapters and normalisation. T-031 to T-036.

The first test in this file is the one a controls engineer would run. AC-082
says no adapter defines a write method, and it is asserted by reflecting over
every implementation in the repository rather than by reading the protocol and
trusting it.
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import pkgutil
from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path

import pytest

import connector
from connector.csv_replay_adapter import CsvReplayAdapter, read_events, write_events
from connector.normalise import (
    Normaliser,
    ReorderWindow,
    SkewEstimator,
    SourceMonitor,
)
from connector.protocol import (
    ADAPTER_METHODS,
    CanonicalEvent,
    SourceAdapter,
    write_methods,
)
from connector.sim_adapter import SimAdapter
from plantsim.emit import conforms
from plantsim.model import SimulationDetail, SimulationRequest, run_simulation
from plantsim.parameters import load_plant_model
from twin.config import load_line_definition

REPO_ROOT = Path(__file__).resolve().parent.parent
LINE2 = load_line_definition(REPO_ROOT / "config" / "lines" / "line2.yaml")
PLANT2 = load_plant_model(REPO_ROOT / "config" / "plantsim" / "line2.yaml")


def _run(units: int = 60, detail: SimulationDetail | None = None) -> object:
    return run_simulation(
        SimulationRequest(
            line=LINE2,
            plant=PLANT2,
            seed=17,
            units=units,
            detail=detail or SimulationDetail(),
        )
    )


def _adapter_classes() -> list[type]:
    """Every class in the connector package that implements the protocol."""
    found: list[type] = []
    for module in pkgutil.iter_modules(connector.__path__):
        loaded = importlib.import_module(f"connector.{module.name}")
        for _, candidate in inspect.getmembers(loaded, inspect.isclass):
            if candidate.__module__ != loaded.__name__:
                continue
            if getattr(candidate, "_is_protocol", False):
                continue
            if set(dir(candidate)) >= ADAPTER_METHODS:
                found.append(candidate)
    return found


# ---------------------------------------------------------------------------
# T-031: read-only by construction. AC-082.


def test_no_adapter_defines_a_write_method() -> None:
    """AC-082. Reflected over every implementation, not read off the protocol."""
    classes = _adapter_classes()
    assert {candidate.__name__ for candidate in classes} == {
        "SimAdapter",
        "CsvReplayAdapter",
    }
    for candidate in classes:
        assert write_methods(candidate) == (), (
            f"{candidate.__name__} defines a method that reads as a write. "
            f"The connector has no path back into the plant"
        )


def test_the_protocol_has_exactly_three_methods() -> None:
    """A controls engineer can check the read-only claim in eight lines."""
    declared = {
        name
        for name in dir(SourceAdapter)
        if not name.startswith("_") and callable(getattr(SourceAdapter, name, None))
    }
    assert declared == set(ADAPTER_METHODS)


def test_both_adapters_satisfy_the_protocol(tmp_path: Path) -> None:
    """Structural conformance, checked at runtime rather than by convention."""
    result = _run(20)
    recording = tmp_path / "line2-events.csv"
    write_events(recording, result.events)  # type: ignore[attr-defined]
    assert isinstance(SimAdapter(result), SourceAdapter)  # type: ignore[arg-type]
    assert isinstance(CsvReplayAdapter(recording, line_id="line2"), SourceAdapter)


# ---------------------------------------------------------------------------
# T-032: the simulator adapter


def test_the_sim_adapter_emits_conforming_events() -> None:
    """Every payload validates against the model for its event type."""
    adapter = SimAdapter(_run(40))  # type: ignore[arg-type]

    async def drain() -> list[CanonicalEvent]:
        return [event async for event in adapter.stream()]

    events = asyncio.run(drain())
    assert events
    bad = [event for event in events if not conforms(event)]
    assert bad == [], f"{len(bad)} events did not conform, first {bad[:1]}"


def test_the_sim_adapter_describes_what_it_can_produce() -> None:
    """The data health panel reads this, so it says what is actually there."""
    info = SimAdapter(_run(40)).describe()  # type: ignore[arg-type]
    assert info.adapter == "sim"
    assert info.line_id == "line2"
    assert "MANUAL_CHECK" in info.event_types
    assert "SHIFT_MARKER" in info.event_types


# ---------------------------------------------------------------------------
# T-033: the replay adapter


def test_a_recording_round_trips_without_loss(tmp_path: Path) -> None:
    """T-033. The canonical model survives a file written by something else."""
    result = _run(40)
    recording = tmp_path / "line2-events.csv"
    written = write_events(recording, result.events)  # type: ignore[attr-defined]
    read_back = list(read_events(recording))
    assert written == len(read_back)
    for before, after in zip(result.events, read_back, strict=True):  # type: ignore[attr-defined]
        assert before.event_id == after.event_id
        assert before.event_type == after.event_type
        assert before.ts_source == after.ts_source
        assert before.payload == after.payload


def test_a_replay_is_deterministic(tmp_path: Path) -> None:
    """Two replays of one file produce the same source clock, in the same order."""
    result = _run(30)
    recording = tmp_path / "line2-events.csv"
    write_events(recording, result.events)  # type: ignore[attr-defined]
    adapter = CsvReplayAdapter(recording, line_id="line2")

    async def drain() -> list[CanonicalEvent]:
        return [event async for event in adapter.stream()]

    first = asyncio.run(drain())
    second = asyncio.run(drain())
    assert [event.ts_source for event in first] == [event.ts_source for event in second]


# ---------------------------------------------------------------------------
# T-034: reordering and late events. EC-01.


def test_out_of_order_events_release_in_source_order() -> None:
    """ING-05. Buffered for the window, then released by the source clock."""
    events = list(_run(30).events)[:400]  # type: ignore[attr-defined]
    shuffled = events[::-1]
    window = ReorderWindow(LINE2.ingest.reorder_window_s)
    released: list[CanonicalEvent] = []
    for event in shuffled:
        released.extend(item.event for item in window.push(event))
    released.extend(item.event for item in window.flush())

    on_time = [event for event in released if event.quality_flag == "OK"]
    assert [event.ts_source for event in on_time] == sorted(
        event.ts_source for event in on_time
    )


def test_a_late_event_is_flagged_and_names_the_station_to_recompute() -> None:
    """EC-01. Accepted, never discarded, and the state is redone."""
    events = list(_run(30).events)  # type: ignore[attr-defined]
    stale = next(event for event in events if event.station_id is not None)
    window = ReorderWindow(1.0)
    for event in events[:200]:
        window.push(event)
    outcome = window.push(stale)
    assert len(outcome) == 1
    assert outcome[0].is_late
    assert outcome[0].event.quality_flag == "LATE"
    assert outcome[0].recompute_station_id == stale.station_id
    assert window.late_count == 1


def test_nothing_is_ever_discarded() -> None:
    """Every event in equals every event out, late ones included."""
    events = list(_run(30).events)[:600]  # type: ignore[attr-defined]
    normaliser = Normaliser(LINE2)
    released = list(normaliser.normalise(reversed(events)))
    assert len(released) == len(events)
    assert {item.event.event_id for item in released} == {
        event.event_id for event in events
    }


# ---------------------------------------------------------------------------
# T-035: clock skew. ING-06.


def _two_clocks(offset_s: float) -> list[CanonicalEvent]:
    """Relabel one run as two sources, with the arrival clock running fast."""
    events = list(_run(120).events)  # type: ignore[attr-defined]
    relabelled: list[CanonicalEvent] = []
    for event in events:
        if event.event_type == "UNIT_DEPART":
            relabelled.append(
                CanonicalEvent(**{**event.__dict__, "source_adapter": "plc-line"})
            )
        elif event.event_type == "UNIT_ARRIVE":
            relabelled.append(
                CanonicalEvent(
                    **{
                        **event.__dict__,
                        "source_adapter": "mes-scan",
                        "ts_source": event.ts_source + timedelta(seconds=offset_s),
                    }
                )
            )
        else:
            relabelled.append(event)
    return relabelled


def test_a_known_skew_is_recovered_within_two_tenths_of_a_second() -> None:
    """T-035. The estimate is a rolling median, so one slow handoff cannot move it."""
    injected = 1.4
    estimator = SkewEstimator(LINE2)
    for event in _two_clocks(injected):
        estimator.observe(event)
    recovered = estimator.between("plc-line", "mes-scan")
    assert recovered is not None
    assert abs(recovered - injected) < 0.2


def test_skew_is_reported_and_never_corrected() -> None:
    """ING-06. A correction applied to a slow station would hide the slow station."""
    estimator = SkewEstimator(LINE2)
    for event in _two_clocks(4.0):
        estimator.observe(event)
    assert estimator.exceeds_warning()
    # The estimator has no method that rewrites a timestamp, which is the point.
    assert not [
        name
        for name in dir(estimator)
        if not name.startswith("_") and name.startswith(("correct", "apply", "adjust"))
    ]


def test_two_clocks_that_agree_report_no_skew() -> None:
    """The null case, because a skew warning on a healthy site is a false alarm."""
    estimator = SkewEstimator(LINE2)
    for event in _two_clocks(0.0):
        estimator.observe(event)
    assert not estimator.exceeds_warning()


# ---------------------------------------------------------------------------
# T-036: source health. ING-07, EC-01.


def test_a_silent_source_is_reported_after_three_takt_periods_and_not_before() -> None:
    """T-036. Reporting sooner would fire on every gap between units."""
    events = list(_run(30).events)  # type: ignore[attr-defined]
    monitor = SourceMonitor(LINE2)
    for event in events[:200]:
        monitor.observe(event)
    last = max(event.ts_source for event in events[:200])

    threshold = LINE2.ingest.source_gap_takts * LINE2.takt_s
    assert monitor.state_of("sim", last) == "LIVE"
    assert monitor.state_of("sim", last + timedelta(seconds=threshold - 1)) != "SILENT"
    assert monitor.state_of("sim", last + timedelta(seconds=threshold + 1)) == "SILENT"


def test_a_source_never_seen_is_silent_rather_than_healthy() -> None:
    """A source that has said nothing at all has not said it is fine."""
    monitor = SourceMonitor(LINE2)
    events = list(_run(20).events)  # type: ignore[attr-defined]
    monitor.observe(events[0])
    assert monitor.state_of("historian", events[0].ts_source) == "SILENT"


def test_health_reports_the_worst_skew_across_sources() -> None:
    """AC-008. The panel shows the maximum estimated skew, not an average."""
    normaliser = Normaliser(LINE2)
    released = list(normaliser.normalise(_two_clocks(2.5)))
    assert released
    at = max(item.event.ts_source for item in released)
    health = normaliser.sources.health(at, normaliser.skew)
    assert {item.adapter for item in health} >= {"plc-line", "mes-scan"}
    assert all(item.estimated_skew_s is not None for item in health)
    assert max(item.estimated_skew_s or 0.0 for item in health) > 2.0


@pytest.mark.parametrize("adapter_type", [SimAdapter, CsvReplayAdapter])
def test_health_is_awaitable_on_every_adapter(
    adapter_type: type, tmp_path: Path
) -> None:
    """The three protocol methods work, which is what the health panel calls."""
    result = _run(20)
    if adapter_type is SimAdapter:
        adapter: object = SimAdapter(result)  # type: ignore[arg-type]
    else:
        recording = tmp_path / "line2-events.csv"
        write_events(recording, result.events)  # type: ignore[attr-defined]
        adapter = CsvReplayAdapter(recording, line_id="line2")

    async def check() -> None:
        stream = adapter.stream()  # type: ignore[attr-defined]
        assert isinstance(stream, AsyncIterator)
        await stream.aclose()
        health = await adapter.health()  # type: ignore[attr-defined]
        assert health.line_id == "line2"

    asyncio.run(check())


def test_a_gap_is_recorded_with_what_it_affected_and_what_it_cost() -> None:
    """ING-07, SC-07. A gap is a record, not a colour on a panel."""
    events = list(_run(60).events)  # type: ignore[attr-defined]
    monitor = SourceMonitor(LINE2)
    for event in events[:2000]:
        monitor.observe(event)
    last = max(event.ts_source for event in events[:2000])

    assert monitor.tick(last) == ()
    quiet = last + timedelta(seconds=monitor.gap_threshold_s + 30)
    opened = monitor.tick(quiet)
    assert len(opened) == 1
    assert opened[0].is_open
    assert opened[0].affected_stations
    # Ticking again does not open a second gap for the same silence.
    assert monitor.tick(quiet + timedelta(seconds=60)) == ()

    resumed = (
        next(event for event in events[2000:] if event.ts_source > quiet)
        if any(event.ts_source > quiet for event in events[2000:])
        else None
    )
    if resumed is None:
        return
    monitor.observe(resumed)
    closed = monitor.gaps()[0]
    assert not closed.is_open
    assert closed.events_lost_estimate > 0


def test_a_gap_closes_when_the_source_speaks_again() -> None:
    """The twin continues on the remaining sources rather than stopping."""
    events = list(_run(60).events)  # type: ignore[attr-defined]
    monitor = SourceMonitor(LINE2)
    for event in events[:500]:
        monitor.observe(event)
    last = max(event.ts_source for event in events[:500])
    monitor.tick(last + timedelta(seconds=monitor.gap_threshold_s + 1))
    assert monitor.gaps()[0].is_open

    later = CanonicalEvent(
        **{
            **events[600].__dict__,
            "ts_source": last + timedelta(seconds=600),
        }
    )
    monitor.observe(later)
    assert not monitor.gaps()[0].is_open
    assert monitor.gaps()[0].duration_s(later.ts_source) > 0
