"""The simulator adapter. T-032.

Reads the built-in line model and yields canonical events. It is read-only for
the same reason every other adapter is: the protocol it implements has no method
that writes, and there is nothing here that could be pointed at a control
system even by mistake.

The adapter takes a finished `SimulationResult` rather than driving the model
itself. A run is deterministic, so a recorded run and a live one are the same
stream, and separating them means the ingest path can be tested without a
simulation in the loop.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime

from connector.protocol import AdapterInfo, CanonicalEvent, SourceHealth
from plantsim.model import SimulationResult
from twin.config.sources import AdapterName, EventType

ADAPTER_NAME: AdapterName = "sim"


class SimAdapter:
    """Streams the events one simulation run emitted."""

    def __init__(
        self,
        result: SimulationResult,
        description: str = "The built-in SimPy line model, filtered by tier",
        speed: float = 0.0,
    ) -> None:
        """Wrap a finished run.

        Args:
            result: the run to stream.
            description: shown in the data health panel.
            speed: real seconds per simulated second. Zero streams as fast as
                the consumer can read, which is what the tests and the
                evaluation harness want. The demo runs accelerated (EC-55) and
                sets a small positive value.
        """
        self._result = result
        self._description = description
        self._speed = max(0.0, speed)
        self._delivered = 0
        self._last_event_at: datetime | None = None

    def describe(self) -> AdapterInfo:
        """What this adapter is and what it can produce."""
        types: set[EventType] = {event.event_type for event in self._result.events}
        return AdapterInfo(
            adapter=ADAPTER_NAME,
            line_id=self._result.line_id,
            description=self._description,
            event_types=frozenset(types),
        )

    async def stream(self) -> AsyncIterator[CanonicalEvent]:
        """Yield the run's events in source-clock order."""
        previous: datetime | None = None
        for event in self._result.events:
            if self._speed > 0 and previous is not None:
                gap = (event.ts_source - previous).total_seconds()
                if gap > 0:
                    await asyncio.sleep(gap * self._speed)
            previous = event.ts_source
            self._delivered += 1
            self._last_event_at = event.ts_source
            yield event

    async def health(self) -> SourceHealth:
        """Report how much of the run has been delivered so far."""
        remaining = len(self._result.events) - self._delivered
        return SourceHealth(
            adapter=ADAPTER_NAME,
            line_id=self._result.line_id,
            state="LIVE" if remaining else "SILENT",
            last_event_at=self._last_event_at,
            events_last_min=self._delivered,
            # One source has nothing to be skewed against. Skew is estimated
            # across adapters, in `connector.normalise`.
            estimated_skew_s=None,
            checked_at=self._last_event_at or self._result.truth.epoch,
        )
