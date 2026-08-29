"""What the routes read, assembled once per process.

The routes hold no state of their own. Everything they need is here: the live
twin, the sensor catalogue, the retro-tracer, the counterfactual engine, and the
handful of derived views that more than one route wants.

`Context.reading()` is the only way a route touches the twin, and it holds the
replay's lock for the duration. A response assembled from three separate reads
of a twin that is moving at 60x would be a response describing three different
moments, which is exactly the kind of quiet inconsistency this product exists to
argue against.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from twin.api.schemas import RangeOut
from twin.config.catalogue import SensorCatalogue
from twin.config.line import LineDefinition
from twin.config.loader import load_sensor_catalogue
from twin.counterfactual.engine import CounterfactualEngine
from twin.live import LiveTwin, get_twin
from twin.retro.trace import RetroTrace, RetroTracer
from twin.sensors.value import SensorValueService

REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOGUE_PATH = REPO_ROOT / "config" / "catalogue" / "sensors.yaml"

# The configuration version the API reports. It moves when a line file changes,
# and a prediction made under an older one is interpreted against that one, so
# it is part of the ledger's meaning rather than a build number.
CONFIG_VERSION = "3"


@dataclass
class Decision:
    """A counterfactual option somebody chose. It changes nothing on the line."""

    run_id: str
    label: str
    recorded_at: datetime
    note: str


@dataclass
class Context:
    """Everything the routes read, built once and shared."""

    twin: LiveTwin
    catalogue: SensorCatalogue
    sensors: SensorValueService = field(init=False)
    tracer: RetroTracer = field(init=False)
    sandbox: CounterfactualEngine = field(init=False)
    decisions: list[Decision] = field(default_factory=list)
    interventions: list[dict[str, object]] = field(default_factory=list)
    traces: dict[str, RetroTrace] = field(default_factory=dict)
    _guard: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def __post_init__(self) -> None:
        """Build the services that hang off one line definition."""
        self.sensors = SensorValueService(self.twin.line, self.catalogue)
        self.tracer = RetroTracer(self.twin.line)
        self.sandbox = CounterfactualEngine(self.twin.line, self.twin.calendar)

    @property
    def line(self) -> LineDefinition:
        """The line as configured."""
        return self.twin.line

    @contextmanager
    def reading(self) -> Iterator[LiveTwin]:
        """Hold the replay still for the length of one response."""
        with self.twin.lock:
            yield self.twin

    def record_decision(self, decision: Decision) -> None:
        """Keep a chosen option, so its effect can join the ledger later."""
        with self._guard:
            self.decisions.append(decision)

    def record_intervention(self, entry: dict[str, object]) -> None:
        """Keep an intervention a supervisor says they carried out."""
        with self._guard:
            self.interventions.append(entry)

    def normal_ranges(self) -> dict[str, RangeOut | None]:
        """Each station's normal band, pooled across variants for the strip.

        The strip has one bar per station and the unit on it right now is one
        variant, so a per-variant band would move under the mark every time the
        mix changed. The band shown is the widest of the variants the station
        has a usable distribution for, which is the honest one to judge a single
        reading against.
        """
        store = self.twin.pipeline.estimator.distributions
        found: dict[str, RangeOut | None] = {}
        for station in self.line.stations:
            usable = [
                item for item in store.usable() if item.station_id == station.station_id
            ]
            if not usable:
                found[station.station_id] = None
                continue
            lo = min(item.median_s - 2.0 * item.scale_s for item in usable)
            hi = max(item.median_s + 2.0 * item.scale_s for item in usable)
            found[station.station_id] = RangeOut(
                lo=round(lo, 1), hi=round(hi, 1), unit="s"
            )
        return found


_HELD: dict[str, Context] = {}
_HELD_LOCK = threading.Lock()


def get_context() -> Context:
    """The process's context, built on first use."""
    with _HELD_LOCK:
        found = _HELD.get("context")
        if found is None:
            found = Context(
                twin=get_twin(), catalogue=load_sensor_catalogue(CATALOGUE_PATH)
            )
            _HELD["context"] = found
        return found


def reset_context() -> None:
    """Drop the process's context. For tests, which build their own."""
    with _HELD_LOCK:
        _HELD.pop("context", None)
