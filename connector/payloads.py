"""Event payloads, one pydantic model per canonical event type.

TECHNICAL_SPEC.md Section 3 says the payload is typed per event type and
validated by pydantic. This is that typing. It matters more than it looks: an
adapter for a site's own protocol is written by somebody who has never read this
repository, and a payload that validates is the only definition of "conforming"
they get.

Field names carry their unit where the unit is not obvious, per
CODING_STANDARDS.md Section 2. A units mismatch in a cycle time is a wrong
forecast that looks entirely plausible.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from twin.config.sources import EventType

StationStateName = Literal[
    "RUNNING", "BLOCKED", "STARVED", "DOWN", "CHANGEOVER", "IDLE"
]
CheckResult = Literal["PASS", "FAIL", "NOT_DONE"]


class Payload(BaseModel):
    """Base for every payload. Unknown keys are an error, not a shrug."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class CycleStart(Payload):
    """A station began work on a unit."""

    variant_id: str = Field(min_length=1)
    shift_id: str = Field(min_length=1)
    operator_group: str | None = None


class CycleEnd(Payload):
    """A station finished work on a unit, and how long that took."""

    variant_id: str = Field(min_length=1)
    shift_id: str = Field(min_length=1)
    cycle_time_s: float = Field(ge=0.0)
    operator_group: str | None = None


class UnitMovement(Payload):
    """A unit arrived at or departed from a station.

    On a real line this is a scan, and it is the only observation a dark station
    contributes to its own cycle time: the scan at the next instrumented
    station. That asymmetry is the whole reason the virtual sensors exist.
    """

    variant_id: str = Field(min_length=1)


class StationStateChange(Payload):
    """A station changed state, as reported by its own controller."""

    state: StationStateName


class ProcessValue(Payload):
    """One process signal sampled during a cycle. Tier A only."""

    signal: str = Field(min_length=1)
    value: float
    unit: str = Field(min_length=1)


class Andon(Payload):
    """An operator raised or cleared an andon call."""

    reason: str = Field(min_length=1)
    raised: bool


class InspectionResult(Payload):
    """A gate passed or failed a unit."""

    gate_id: str = Field(min_length=1)
    passed: bool
    defect_class: str | None = None


class ManualCheck(Payload):
    """A checklist result recorded by an operator.

    The timestamp is when it was recorded, not when the work happened, which is
    why this event never anchors a cycle-time interval.
    """

    check_id: str = Field(min_length=1)
    result: CheckResult


class PartLotScan(Payload):
    """A part lot consumed at a station."""

    lot_id: str = Field(min_length=1)
    part: str = Field(min_length=1)


class EnvReading(Payload):
    """Zone temperature and humidity. Zone level, so the station is null."""

    zone_id: str = Field(min_length=1)
    temperature_c: float
    humidity_pct: float = Field(ge=0.0, le=100.0)


class ShiftMarker(Payload):
    """A shift, break or changeover boundary."""

    shift_id: str = Field(min_length=1)
    marker: Literal["START", "END", "BREAK_START", "BREAK_END", "CHANGEOVER"]


PAYLOAD_MODELS: dict[EventType, type[Payload]] = {
    "CYCLE_START": CycleStart,
    "CYCLE_END": CycleEnd,
    "UNIT_ARRIVE": UnitMovement,
    "UNIT_DEPART": UnitMovement,
    "STATION_STATE": StationStateChange,
    "PROCESS_VALUE": ProcessValue,
    "ANDON": Andon,
    "INSPECTION_RESULT": InspectionResult,
    "MANUAL_CHECK": ManualCheck,
    "PART_LOT_SCAN": PartLotScan,
    "ENV_READING": EnvReading,
    "SHIFT_MARKER": ShiftMarker,
}


def validate_payload(event_type: EventType, payload: dict[str, object]) -> Payload:
    """Parse a payload against the model for its event type.

    Raises:
        pydantic.ValidationError: if the payload does not conform. The caller
            records it as a malformed event rather than dropping it silently.
    """
    return PAYLOAD_MODELS[event_type].model_validate(payload)
