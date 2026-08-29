"""The live twin the API reads from.

The prototype has no plant to connect to, so the source of events is the
simulator behind the `SimAdapter`, and the path from an event to the screen is
the real one: simulator, adapter, normaliser, state estimator, forecaster,
ledger, gates, API. Nothing here reaches into the simulator's ground truth, and
nothing here writes anywhere.

**Why the stream is precomputed and then replayed.** Running SimPy and the twin
in the same process on the same clock would couple the forecast cycle's runtime
to the line's pace, and a slow cycle would then slow the line it is forecasting,
which is the one thing a digital twin must never do. The line is simulated once
at start-up, and the replay then feeds the twin at the configured speed. The
events are identical either way and the twin cannot tell the difference.

**Why there is a warm-up.** A real twin is attached to a line that has been
running for months. Started cold it has no baseline, no distribution to detect
drift against and no labelled units to fit a defect model on, and it would spend
the first hour of any demonstration saying so correctly and uselessly. The
warm-up feeds the first part of the stream as fast as the machine allows,
running full forecast cycles on a coarser cadence, and the twin then goes live
with the history a twin would have. The ledger records every warm-up prediction
and scores it, which is what lets a predictor arrive on screen already promoted
or already in shadow.

Everything the replay does to the clock is reported: `LiveStatus` carries the
speed, whether the warm-up is still running and how far behind the twin is, and
the interface shows the data age it produces rather than a fabricated one.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from connector.normalise import Normaliser
from connector.protocol import CanonicalEvent, SourceHealth
from evaluation.harness import load, simulate
from plantsim.parameters import PlantModel
from plantsim.scenarios import ScenarioCatalogue
from twin.config.line import LineDefinition
from twin.domain.shifts import ProductionCalendar
from twin.pipeline import CycleResult, TwinPipeline

REPO_ROOT = Path(__file__).resolve().parents[1]

# How often the replay thread wakes. Short enough that the data age the
# interface shows is honest at 60x, long enough that the thread is not the
# process's main cost.
TICK_S = 0.25


def _env_float(name: str, fallback: float) -> float:
    """One float from the environment, with the default this module ships."""
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return fallback
    try:
        return float(raw)
    except ValueError:
        return fallback


def _env_int(name: str, fallback: int) -> int:
    """One integer from the environment."""
    return int(_env_float(name, float(fallback)))


def _env_str(name: str, fallback: str) -> str:
    """One string from the environment."""
    raw = os.environ.get(name)
    return raw.strip() if raw and raw.strip() else fallback


@dataclass(frozen=True)
class LiveSettings:
    """How the replay runs. Every field is a runtime choice, not a plant value.

    The line, the scenario and the seed name files in `config/`; nothing about
    the plant itself is written here. `TWIN_*` environment variables override
    each one so that a compose file can run the same image against a different
    line without a code change (AC-080).
    """

    line_name: str = "line2"
    scenario_id: str = "SC-01"
    seed: int = 20260302
    units: int = 900
    speed: float = 60.0
    replications: int = 48
    horizon_min: int = 120
    cadence_s: float = 300.0
    # The warm-up runs full replications on a coarser cadence, because its job
    # is to build history rather than to be watched.
    warm_cadence_s: float = 1800.0
    warm_fraction: float = 0.5

    @classmethod
    def from_environment(cls) -> LiveSettings:
        """Settings with every field overridable from the environment."""
        base = cls()
        return cls(
            line_name=_env_str("TWIN_LINE", base.line_name),
            scenario_id=_env_str("TWIN_SCENARIO", base.scenario_id),
            seed=_env_int("TWIN_SEED", base.seed),
            units=_env_int("TWIN_UNITS", base.units),
            speed=_env_float("TWIN_SPEED", base.speed),
            replications=_env_int("TWIN_REPLICATIONS", base.replications),
            horizon_min=_env_int("TWIN_HORIZON_MIN", base.horizon_min),
            cadence_s=_env_float("TWIN_CADENCE_S", base.cadence_s),
            warm_cadence_s=_env_float("TWIN_WARM_CADENCE_S", base.warm_cadence_s),
            warm_fraction=_env_float("TWIN_WARM_FRACTION", base.warm_fraction),
        )


@dataclass(frozen=True)
class LiveStatus:
    """What the replay is doing, so that no part of it is hidden.

    `behind_s` is the gap between where the replay clock has reached and where
    the twin has actually processed to. It grows while a forecast cycle runs and
    the interface shows it as data age, which is the same thing a real twin
    would show when its worker fell behind.
    """

    ready: bool
    warming: bool
    speed: float
    scenario_id: str
    seed: int
    events_total: int
    events_fed: int
    cycles: int
    at: datetime | None
    behind_s: float
    finished: bool
    note: str


@dataclass
class LiveTwin:
    """One line's twin, fed by a replayed event stream.

    The pipeline, the estimator and the ledger inside this object are the same
    ones the evaluation harness drives. The only thing this class adds is a
    clock and a lock.
    """

    settings: LiveSettings = field(default_factory=LiveSettings.from_environment)

    line: LineDefinition = field(init=False)
    calendar: ProductionCalendar = field(init=False)
    pipeline: TwinPipeline = field(init=False)
    normaliser: Normaliser = field(init=False)
    plant: PlantModel = field(init=False)
    catalogue: ScenarioCatalogue = field(init=False)

    _events: tuple[CanonicalEvent, ...] = field(default=(), repr=False)
    _cursor: int = field(default=0, repr=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    _thread: threading.Thread | None = field(default=None, repr=False)
    _stop: threading.Event = field(default_factory=threading.Event, repr=False)
    _warming: bool = field(default=True, repr=False)
    _ready: bool = field(default=False, repr=False)
    _epoch: datetime | None = field(default=None, repr=False)
    _wall_zero: float = field(default=0.0, repr=False)
    _note: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        """Load the configuration and build the twin, without running anything."""
        line, plant, catalogue = load(self.settings.line_name)
        self.line = line
        self.calendar = ProductionCalendar(line, plant.epoch)
        self.pipeline = TwinPipeline(
            line=line,
            calendar=self.calendar,
            replications=self.settings.replications,
            cadence_s=self.settings.warm_cadence_s,
            horizon_min=self.settings.horizon_min,
        )
        self.normaliser = Normaliser(line)
        self.plant = plant
        self.catalogue = catalogue

    # -- lifecycle --------------------------------------------------------

    def start(self) -> None:
        """Simulate the line, warm the twin, and begin the replay."""
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="twin-live", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Ask the replay to finish at its next tick."""
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=5.0)

    def _run(self) -> None:
        """Build the stream, warm up, then feed at the configured speed."""
        result = simulate(
            self.line,
            self.plant,
            self.catalogue,
            self.settings.scenario_id,
            self.settings.seed,
            self.settings.units,
        )
        with self._lock:
            self._events = tuple(result.events)
            self._note = (
                f"Replaying scenario {self.settings.scenario_id} at "
                f"{self.settings.speed:.0f}x from a {self.settings.units} unit run."
            )
        self._warm_up()
        self._replay()

    def _warm_up(self) -> None:
        """Feed the first part of the stream as fast as the machine allows."""
        cut = int(len(self._events) * max(0.0, min(1.0, self.settings.warm_fraction)))
        for index in range(cut):
            if self._stop.is_set():
                return
            with self._lock:
                self._feed_one(self._events[index])
                self._cursor = index + 1
        with self._lock:
            self.pipeline.cadence_s = self.settings.cadence_s
            self._warming = False
            self._ready = True
            at = self.pipeline.estimator.state().at
            self._epoch = at
            self._wall_zero = time.monotonic()

    def _replay(self) -> None:
        """Feed the rest of the stream against the wall clock."""
        while not self._stop.is_set():
            target = self._replay_clock()
            fed = 0
            while True:
                with self._lock:
                    if self._cursor >= len(self._events):
                        self._finish()
                        return
                    event = self._events[self._cursor]
                    if event.ts_source > target:
                        break
                    self._feed_one(event)
                    self._cursor += 1
                fed += 1
                if fed >= _BATCH:
                    break
            if fed < _BATCH:
                time.sleep(TICK_S)

    def _finish(self) -> None:
        """The stream ran out. Close the ledger and say so."""
        self.pipeline.close()
        self._note = (
            f"The {self.settings.units} unit run has finished. The line state "
            f"and the ledger are held at the last event."
        )
        self._stop.set()

    def _replay_clock(self) -> datetime:
        """Where the replay has reached in the line's own time.

        Raises:
            RuntimeError: before the warm-up has set the replay epoch. The
                replay has no clock until it has one, and returning a
                sentinel here would feed the whole stream in one pass.
        """
        with self._lock:
            epoch = self._epoch
        if epoch is None:
            message = "the replay clock is not set until the warm-up finishes"
            raise RuntimeError(message)
        elapsed = (time.monotonic() - self._wall_zero) * self.settings.speed
        return epoch + timedelta(seconds=elapsed)

    def _feed_one(self, event: CanonicalEvent) -> None:
        """One event through the normaliser and into the twin."""
        for released in self.normaliser.push(event):
            self.pipeline.observe(released.event)

    # -- reading ----------------------------------------------------------

    @property
    def lock(self) -> threading.RLock:
        """The lock every reader holds while it walks the twin's state."""
        return self._lock

    @property
    def ready(self) -> bool:
        """Whether the warm-up has finished and the state is worth reading."""
        return self._ready

    def status(self) -> LiveStatus:
        """What the replay is doing right now."""
        with self._lock:
            at = self.pipeline.estimator.state().at if self._ready else None
            behind = 0.0
            if at is not None and self._epoch is not None:
                behind = max(0.0, (self._replay_clock() - at).total_seconds())
            return LiveStatus(
                ready=self._ready,
                warming=self._warming,
                speed=self.settings.speed,
                scenario_id=self.settings.scenario_id,
                seed=self.settings.seed,
                events_total=len(self._events),
                events_fed=self._cursor,
                cycles=len(self.pipeline.cycles),
                at=at,
                behind_s=behind,
                finished=self._stop.is_set(),
                note=self._note,
            )

    def last_cycle(self) -> CycleResult | None:
        """The most recent forecast cycle, or None before the first one."""
        with self._lock:
            cycles = self.pipeline.cycles
            return cycles[-1] if cycles else None

    def now(self) -> datetime:
        """The line time the twin has processed to."""
        with self._lock:
            return self.pipeline.estimator.state().at

    def events_seen(self, limit: int) -> tuple[CanonicalEvent, ...]:
        """The events fed so far, up to a limit.

        Topology discovery reads a stream rather than a live state, so it needs
        the events themselves. The limit exists because reading a whole day of
        production on every request would make that endpoint the slowest in the
        API for no gain: the draft stops improving long before the stream ends.
        """
        with self._lock:
            return self._events[: min(self._cursor, limit)]

    def source_health(self) -> tuple[SourceHealth, ...]:
        """Every source the normaliser has seen, and its state."""
        with self._lock:
            return self.normaliser.sources.health(self.now(), self.normaliser.skew)


# How many events one replay pass feeds before it yields. Large enough that the
# lock is not taken once per event at 60x, small enough that a reader is never
# waiting long for it.
_BATCH = 400

# The process holds one twin. It lives in a mutable box rather than in a name
# rebound by `global`, because the box is what the lock protects and a rebound
# name is not.
_HELD: dict[str, LiveTwin] = {}
_HELD_LOCK = threading.Lock()


def get_twin() -> LiveTwin:
    """The process's live twin, started on first use."""
    with _HELD_LOCK:
        twin = _HELD.get("twin")
        if twin is None:
            twin = LiveTwin()
            _HELD["twin"] = twin
            twin.start()
        return twin


def reset_twin() -> None:
    """Drop the process's twin. For tests, which build their own."""
    with _HELD_LOCK:
        twin = _HELD.pop("twin", None)
        if twin is not None:
            twin.stop()
