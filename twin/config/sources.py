"""The SourceMapping.

A site's native tags, topics or tables translated into canonical events
(ONB-02). The mapping is read-only by construction: it says where an event comes
from and never where one goes.
"""

from __future__ import annotations

from typing import Literal, Self

from pydantic import Field, model_validator

from twin.config.line import Strict

AdapterName = Literal[
    "sim", "csv_replay", "opcua", "mtconnect", "sparkplug", "historian"
]

EventType = Literal[
    "CYCLE_START",
    "CYCLE_END",
    "UNIT_ARRIVE",
    "UNIT_DEPART",
    "STATION_STATE",
    "PROCESS_VALUE",
    "ANDON",
    "INSPECTION_RESULT",
    "MANUAL_CHECK",
    "PART_LOT_SCAN",
    "ENV_READING",
    "SHIFT_MARKER",
]


class MappingEntry(Strict):
    """One native reference and the canonical event it becomes."""

    # A tag path, an MQTT topic, a table and column, or a simulator channel.
    native_ref: str = Field(min_length=1)
    event_type: EventType
    # Null where the reference covers every station, for example a simulator
    # channel or a line-level shift marker.
    station_id: str | None = None
    # Unit conversion, scaling, enum mapping. Applied on ingest.
    transform: dict[str, object] = Field(default_factory=dict)
    note: str | None = None


class SourceMapping(Strict):
    """Every native reference one adapter offers for one line."""

    line_id: str = Field(min_length=1)
    adapter: AdapterName
    description: str = Field(min_length=1)
    mappings: tuple[MappingEntry, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def native_references_are_unique(self) -> Self:
        """Two entries cannot claim the same native reference."""
        seen: set[tuple[str, str | None]] = set()
        for entry in self.mappings:
            key = (entry.native_ref, entry.station_id)
            if key in seen:
                message = (
                    f"mappings: {entry.native_ref} is mapped more than once for "
                    f"station {entry.station_id}"
                )
                raise ValueError(message)
            seen.add(key)
        return self

    def event_types(self) -> frozenset[str]:
        """Which canonical event types this source can produce."""
        return frozenset(entry.event_type for entry in self.mappings)
