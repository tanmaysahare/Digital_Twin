"""Canonical event emission, filtered by observability tier. T-025.

This module is where the product's central problem is created rather than
solved. The simulator knows everything; this filter throws most of it away
before the twin sees any of it, according to the tier each station carries in
the line definition.

| Tier | What leaves this module |
|---|---|
| A | Cycle start and end, unit movement, station state, process values,
      part lot scans, andon |
| B | Cycle start and end, unit movement, part lot scans, andon |
| C | Andon and a manual checklist result. Nothing else at all |

A tier B station emits no state word, so `BLOCKED` and `STARVED` there are the
state estimator's inference rather than a reading. A tier C station emits no
machine data of any kind: the only trace a unit leaves of its time there is the
scan when it reaches the next instrumented station, which is what the virtual
sensors work from.

A manual check is recorded by a person some time after the work, so its
timestamp says when a form was filled in. It never anchors a cycle-time
interval, and the filter keeps it well away from the events that do.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from uuid import UUID, uuid5

from connector.payloads import validate_payload
from connector.protocol import CanonicalEvent
from twin.config.line import LineDefinition, Tier
from twin.config.sources import EventType

# A fixed namespace, so that two runs of the same seeded scenario produce the
# same event identifiers and not merely the same event contents (NFR-07,
# T-026). A random UUID here would make byte-identical replay impossible.
EVENT_NAMESPACE = UUID("6f2a1c94-8b3d-5f47-9a21-0c7e4d6b8f10")

# What each tier is physically able to produce. PRD.md Section 1.
TIER_EVENTS: dict[Tier, frozenset[EventType]] = {
    "A": frozenset(
        {
            "CYCLE_START",
            "CYCLE_END",
            "UNIT_ARRIVE",
            "UNIT_DEPART",
            "STATION_STATE",
            "PROCESS_VALUE",
            "PART_LOT_SCAN",
            "ANDON",
        }
    ),
    # Cycle start and stop only, plus the scans and calls that come from
    # outside the machine. No state word: what a tier B station is doing when
    # it is not cycling is the estimator's problem, not the source's.
    "B": frozenset(
        {
            "CYCLE_START",
            "CYCLE_END",
            "UNIT_ARRIVE",
            "UNIT_DEPART",
            "PART_LOT_SCAN",
            "ANDON",
        }
    ),
    # No machine data. This is the case the product exists to handle.
    "C": frozenset({"ANDON", "MANUAL_CHECK"}),
}

# Events that carry no station, so no tier applies to them.
LINE_LEVEL_EVENTS: frozenset[EventType] = frozenset({"ENV_READING", "SHIFT_MARKER"})

# An inspection gate is not the station it stands after. Its verdict comes from
# the quality system, so it survives the filter even where the station it
# follows emits nothing at all. Line 2's final gate sits after S42, which is
# dark, and suppressing its results would lose every label the defect model
# trains on.
GATE_EVENTS: frozenset[EventType] = frozenset({"INSPECTION_RESULT"})

# The events a machine produces. A tier C station emits none of these, and a
# test asserts it by scanning the emitted stream rather than by reading the
# filter (TEST_PLAN.md Section 2).
MACHINE_EVENTS: frozenset[EventType] = frozenset(
    {
        "CYCLE_START",
        "CYCLE_END",
        "UNIT_ARRIVE",
        "UNIT_DEPART",
        "STATION_STATE",
        "PROCESS_VALUE",
    }
)

# Where two events share a timestamp, this is the order a plant would produce
# them in. A unit is scanned in before its parts are, its parts before its cycle
# starts, and its state word is written after whatever caused it. Without a
# stated order the tie would be broken by an identifier, which is to say
# arbitrarily, and a part lot scan would land against the wrong visit.
EVENT_ORDER: dict[EventType, int] = {
    "SHIFT_MARKER": 0,
    "ENV_READING": 1,
    "UNIT_ARRIVE": 2,
    "PART_LOT_SCAN": 3,
    "CYCLE_START": 4,
    "PROCESS_VALUE": 5,
    "CYCLE_END": 6,
    "MANUAL_CHECK": 7,
    "ANDON": 8,
    "UNIT_DEPART": 9,
    "INSPECTION_RESULT": 10,
    "STATION_STATE": 11,
}

EventSink = Callable[[CanonicalEvent], None]


class EventEmitter:
    """Builds canonical events, drops what a station's tier cannot produce."""

    def __init__(
        self,
        line: LineDefinition,
        run_id: UUID,
        epoch: datetime,
        sink: EventSink,
        adapter_name: str = "sim",
    ) -> None:
        """Build an emitter for one run of one line.

        Args:
            line: the line, which is where each station's tier comes from.
            run_id: identifies the run, and seeds the event identifiers.
            epoch: the wall clock at second zero.
            sink: where an event goes once it survives the filter.
            adapter_name: recorded on every event as its source.
        """
        self._line = line
        self._run_id = run_id
        self._epoch = epoch
        self._sink = sink
        self._adapter = adapter_name
        self._tier: dict[str, Tier] = {
            station.station_id: station.tier for station in line.stations
        }
        self._seq = 0
        self._suppressed = 0

    @property
    def emitted(self) -> int:
        """How many events reached the sink."""
        return self._seq

    @property
    def suppressed(self) -> int:
        """How many events the tier filter dropped.

        Reported at the end of a run, because the size of this number against
        the emitted count is the plainest statement of how much of this line the
        twin cannot see.
        """
        return self._suppressed

    def can_emit(self, event_type: EventType, station_id: str | None) -> bool:
        """Whether a station's tier permits this event type."""
        if station_id is None:
            return event_type in LINE_LEVEL_EVENTS
        if event_type in GATE_EVENTS:
            return True
        return event_type in TIER_EVENTS[self._tier[station_id]]

    def emit(
        self,
        event_type: EventType,
        at_s: float,
        payload: dict[str, object],
        station_id: str | None = None,
        unit_id: str | None = None,
    ) -> None:
        """Emit one event if the station's tier can produce it, otherwise drop it."""
        if not self.can_emit(event_type, station_id):
            self._suppressed += 1
            return
        ts = self._epoch + timedelta(seconds=at_s)
        self._seq += 1
        self._sink(
            CanonicalEvent(
                event_id=uuid5(EVENT_NAMESPACE, f"{self._run_id}:{self._seq}"),
                event_type=event_type,
                line_id=self._line.line_id,
                station_id=station_id,
                unit_id=unit_id,
                ts_source=ts,
                # The simulator's ingest clock is its own clock. Stamping a real
                # wall clock here would make a seeded replay differ from run to
                # run, which NFR-07 does not allow. A replay adapter stamps its
                # own ingest time when it reads a recorded file.
                ts_ingest=ts,
                payload=payload,
                source_adapter=self._adapter,
                quality_flag="OK",
            )
        )


def conforms(event: CanonicalEvent) -> bool:
    """Whether an event's payload validates against the model for its type.

    Used by the tests that assert the stream conforms (T-032). Validation is not
    done at emission: inside our own simulator it would cost a pydantic parse
    per event for no benefit, and the place conformance actually matters is the
    adapter boundary, where a test checks every event rather than a sample.
    """
    try:
        validate_payload(event.event_type, event.payload)
    except ValueError:
        return False
    return True
