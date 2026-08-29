"""Replay a recorded event file. T-033.

The second adapter exists for two reasons. It proves the canonical event model
survives a round trip through a file written by something that is not this
codebase, which is what a site export will be. And it is the path a plant can
use to try the twin against a historian extract without connecting anything,
which USER_RESEARCH.md Section 4 names as the highest-value next step.

Read-only by construction, like every adapter. `write_events` exists so that a
run can be recorded, and it writes a file rather than a source.
"""

from __future__ import annotations

import asyncio
import csv
import json
from collections.abc import AsyncIterator, Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from connector.protocol import (
    AdapterInfo,
    CanonicalEvent,
    QualityFlag,
    SourceHealth,
)
from twin.config.sources import AdapterName, EventType

ADAPTER_NAME: AdapterName = "csv_replay"

# The demo replays an hour of line time in a minute. Faster than this and the
# interface cannot follow it: the forecast cadence is two minutes of line time,
# so above about 120x a viewer sees fewer than one update a second and the strip
# reads as a flicker rather than as a line (EC-55).
DEMO_SPEED_MULTIPLIER = 60.0
MAX_SPEED_MULTIPLIER = 120.0

COLUMNS = (
    "event_id",
    "event_type",
    "line_id",
    "station_id",
    "unit_id",
    "ts_source",
    "ts_ingest",
    "payload",
    "source_adapter",
    "quality_flag",
)


def write_events(path: Path | str, events: Iterable[CanonicalEvent]) -> int:
    """Record a stream to a file, one event per row. Returns the row count."""
    written = 0
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        for event in events:
            writer.writerow(
                (
                    str(event.event_id),
                    event.event_type,
                    event.line_id,
                    event.station_id or "",
                    event.unit_id or "",
                    event.ts_source.isoformat(),
                    event.ts_ingest.isoformat(),
                    json.dumps(event.payload, sort_keys=True, separators=(",", ":")),
                    event.source_adapter,
                    event.quality_flag,
                )
            )
            written += 1
    return written


def read_events(path: Path | str) -> Iterator[CanonicalEvent]:
    """Read a recorded file back into canonical events."""
    with Path(path).open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            yield _from_row(row)


def _from_row(row: dict[str, str]) -> CanonicalEvent:
    event_type: EventType = row["event_type"]  # type: ignore[assignment]
    quality: QualityFlag = row["quality_flag"]  # type: ignore[assignment]
    return CanonicalEvent(
        event_id=UUID(row["event_id"]),
        event_type=event_type,
        line_id=row["line_id"],
        station_id=row["station_id"] or None,
        unit_id=row["unit_id"] or None,
        ts_source=datetime.fromisoformat(row["ts_source"]),
        ts_ingest=datetime.fromisoformat(row["ts_ingest"]),
        payload=json.loads(row["payload"]),
        source_adapter=row["source_adapter"],
        quality_flag=quality,
    )


class CsvReplayAdapter:
    """Replays a recorded event file, optionally at a multiple of real time."""

    def __init__(
        self,
        path: Path | str,
        line_id: str,
        speed_multiplier: float = 0.0,
        description: str = "A recorded canonical event file",
    ) -> None:
        """Open a recorded file for replay.

        Args:
            path: the recorded file.
            line_id: which line the file describes.
            speed_multiplier: simulated seconds per real second. Zero replays as
                fast as the consumer reads, which is what a test wants; 60
                replays an hour of line time in a minute, which is the demo
                default (EC-55).
            description: shown in the data health panel.
        """
        self._path = Path(path)
        self._line_id = line_id
        self._speed = min(MAX_SPEED_MULTIPLIER, max(0.0, speed_multiplier))
        self._capped = speed_multiplier > MAX_SPEED_MULTIPLIER
        self._description = description
        self._delivered = 0
        self._last_event_at: datetime | None = None

    @property
    def speed_multiplier(self) -> float:
        """Simulated seconds per real second, after the cap."""
        return self._speed

    @property
    def is_capped(self) -> bool:
        """Whether the requested speed was reduced to what the view can follow."""
        return self._capped

    def describe(self) -> AdapterInfo:
        """What this adapter is and what the file it replays contains."""
        types: set[EventType] = {event.event_type for event in read_events(self._path)}
        return AdapterInfo(
            adapter=ADAPTER_NAME,
            line_id=self._line_id,
            description=f"{self._description}: {self._path.name}",
            event_types=frozenset(types),
            # A recording is one step further from the plant than a live source,
            # and where two sources disagree the live one wins for state.
            fidelity=0.9,
        )

    async def stream(self) -> AsyncIterator[CanonicalEvent]:
        """Yield the recorded events, re-stamping the ingest clock."""
        previous: datetime | None = None
        for event in read_events(self._path):
            if self._speed > 0 and previous is not None:
                gap = (event.ts_source - previous).total_seconds()
                if gap > 0:
                    await asyncio.sleep(gap / self._speed)
            previous = event.ts_source
            self._delivered += 1
            self._last_event_at = event.ts_source
            # The ingest clock is ours and is stamped when the event is read,
            # so a replay records honestly that the twin saw it now and not
            # when the plant produced it.
            yield CanonicalEvent(
                event_id=event.event_id,
                event_type=event.event_type,
                line_id=event.line_id,
                station_id=event.station_id,
                unit_id=event.unit_id,
                ts_source=event.ts_source,
                ts_ingest=datetime.now(tz=UTC),
                payload=event.payload,
                source_adapter=ADAPTER_NAME,
                quality_flag=event.quality_flag,
            )

    async def health(self) -> SourceHealth:
        """Report how much of the file has been replayed so far."""
        return SourceHealth(
            adapter=ADAPTER_NAME,
            line_id=self._line_id,
            state="LIVE" if self._delivered else "SILENT",
            last_event_at=self._last_event_at,
            events_last_min=self._delivered,
            estimated_skew_s=None,
            checked_at=datetime.now(tz=UTC),
        )
