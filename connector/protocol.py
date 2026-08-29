"""The canonical event and the read-only source adapter.

This module is the boundary a controls engineer reads to check the claim in
SECURITY_REQUIREMENTS.md: the twin cannot write to a control system, because the
interface it talks to sources through has no method that writes.

`SourceAdapter` has three methods. `describe` says what the adapter is,
`stream` yields events, `health` reports whether the source is still talking.
There is no fourth method, no escape hatch, and no configuration that adds one.
`write_methods` below turns that claim into something a test can assert over
every implementation in the repository (AC-082).

The canonical event lives here rather than in `twin/domain/` because it is the
wire format between a site and the twin, and the simulator produces it without
knowing anything about the twin's internals.
"""

from __future__ import annotations

import inspect
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol, runtime_checkable
from uuid import UUID

from twin.config.sources import AdapterName, EventType

QualityFlag = Literal["OK", "LATE", "SKEWED", "ESTIMATED"]
SourceState = Literal["LIVE", "DEGRADED", "SILENT"]

# The three methods of the protocol, named once so the reflection test and the
# documentation cannot drift apart.
ADAPTER_METHODS = frozenset({"describe", "stream", "health"})

# Verbs that would mean a path back into the plant. A method whose name starts
# with one of these on a class that also implements the protocol is a failure,
# not a style question.
WRITE_VERBS = (
    "write",
    "send",
    "publish",
    "put",
    "post",
    "set",
    "command",
    "control",
    "actuate",
    "acknowledge",
    "reset",
    "start",
    "stop",
)


@dataclass(frozen=True)
class CanonicalEvent:
    """One observation of the line, in the twin's own vocabulary. ING-01, ING-02."""

    event_id: UUID
    event_type: EventType
    line_id: str
    station_id: str | None
    unit_id: str | None
    # The source's clock. Never corrected, because a correction applied to a
    # genuinely slow station would hide the thing we are looking for (ING-06).
    ts_source: datetime
    # Ours, stamped when the event reached the connector.
    ts_ingest: datetime
    payload: dict[str, object]
    source_adapter: str
    quality_flag: QualityFlag = "OK"

    def with_quality(self, flag: QualityFlag) -> CanonicalEvent:
        """The same event carrying a different quality flag."""
        return CanonicalEvent(
            event_id=self.event_id,
            event_type=self.event_type,
            line_id=self.line_id,
            station_id=self.station_id,
            unit_id=self.unit_id,
            ts_source=self.ts_source,
            ts_ingest=self.ts_ingest,
            payload=self.payload,
            source_adapter=self.source_adapter,
            quality_flag=flag,
        )


@dataclass(frozen=True)
class AdapterInfo:
    """What an adapter is, and what it can produce."""

    adapter: AdapterName
    line_id: str
    description: str
    event_types: frozenset[EventType]
    # Stated by the adapter and shown in the data health panel. Where two
    # sources disagree about the same event, the higher fidelity wins for state
    # and the disagreement is still reported (EC-02).
    fidelity: float = 1.0


@dataclass(frozen=True)
class SourceHealth:
    """Whether a source is still talking, and how far its clock has drifted."""

    adapter: str
    line_id: str
    state: SourceState
    last_event_at: datetime | None
    events_last_min: int
    estimated_skew_s: float | None
    checked_at: datetime
    affected_stations: tuple[str, ...] = field(default=())


@runtime_checkable
class SourceAdapter(Protocol):
    """A source of canonical events. There is no write method, deliberately."""

    def describe(self) -> AdapterInfo:
        """What this adapter is and what it can produce."""
        ...

    def stream(self) -> AsyncIterator[CanonicalEvent]:
        """Yield canonical events until the source ends or the caller stops."""
        ...

    async def health(self) -> SourceHealth:
        """Report whether the source is still talking."""
        ...


def write_methods(candidate: type) -> tuple[str, ...]:
    """Every public method on a class whose name reads as a write.

    This is AC-082 in mechanical form. A controls engineer can run it against
    any adapter, including one written for their own site, and get a list that
    has to be empty.
    """
    found: list[str] = []
    for name, member in inspect.getmembers(candidate):
        if name.startswith("_") or not callable(member):
            continue
        if name in ADAPTER_METHODS:
            continue
        if any(name.startswith(verb) for verb in WRITE_VERBS):
            found.append(name)
    return tuple(sorted(found))
