"""Cycle-time distributions per station per variant. T-043.

TECHNICAL_SPEC.md Section 4.2. Two decisions here carry the weight.

**Robust location and scale.** The median and the median absolute deviation,
scaled by 1.4826 so it is comparable with a standard deviation under normality.
A single six-minute andon stop would move a mean baseline enough to make the
station look drifted for the rest of the window, and the drift detector reading
that baseline would then signal on an event that has already been dealt with.

**An empirical pool, not a fitted curve.** The forecast resamples from the
observed cycles rather than from a fitted lognormal. Two operators with two
habits produce a bimodal cycle time, and a parametric fit to that produces a
confident wrong forecast, which is the worst output this system can make.

Below the line's minimum cycle count a station has no usable distribution. It is
excluded from forecasting and the interface says how many cycles remain, because
this happens on every cold start and after every new variant and has to look
deliberate rather than broken (EC-20).
"""

from __future__ import annotations

import statistics
from collections import defaultdict, deque
from dataclasses import dataclass

from twin.config.line import LineDefinition

# The constant that makes a median absolute deviation comparable with a standard
# deviation when the underlying data is normal.
MAD_TO_SIGMA = 1.4826

# A scale of zero would divide by zero in every z-score. It happens when a
# window holds one repeated value, which is a stuck sensor rather than a
# perfectly consistent station, and the floor keeps the arithmetic finite while
# the model-health view reports the flat window.
MINIMUM_SCALE_S = 1e-6

# A cycle this far above the station's own median is not the station working
# slowly, it is the station having stopped: a repair, a fumble recovered, a
# fastener refetched. Four robust standard deviations is well outside anything
# the paced work produces and comfortably inside anything an interruption does.
RARE_SIGMA = 4.0

# How many of a station's rare cycles are kept. Enough to sample a magnitude
# from, few enough that a station which had a bad month is not represented by it
# for ever.
RARE_MEMORY = 200


@dataclass(frozen=True)
class CycleDistribution:
    """One station's cycle time for one variant, over a rolling window."""

    station_id: str
    variant_id: str
    n: int
    median_s: float
    # Median absolute deviation scaled to be read as a standard deviation.
    scale_s: float
    p05_s: float
    p95_s: float
    # The pool the discrete-event forecast resamples from.
    sample: tuple[float, ...]
    is_usable: bool
    # The window with its rare interruptions removed, and the rate and magnitudes
    # of those interruptions estimated over the station's whole history rather
    # than over the window.
    #
    # This split exists because resampling a rolling window misrepresents a rare
    # heavy tail badly, and the forecast is exactly where that matters. A station
    # that fails once in five thousand cycles has a four percent chance that any
    # given 200-cycle window holds one of those failures. Where it does, the
    # forecast resamples that failure at one draw in two hundred, twenty-five
    # times its real rate, and predicts a stall at that station with confidence.
    # Where it does not, the forecast believes the station never fails at all.
    # Averaged over the line the two errors cancel, which is why the forecast's
    # mean lost time looked well calibrated while its alarms were noise.
    core: tuple[float, ...] = ()
    rare: tuple[float, ...] = ()
    rare_rate: float = 0.0

    def z(self, cycle_s: float) -> float:
        """How many robust standard deviations a cycle sits from the median."""
        return (cycle_s - self.median_s) / max(self.scale_s, MINIMUM_SCALE_S)


class DistributionStore:
    """Rolling cycle-time windows for every station and variant on a line."""

    def __init__(self, line: LineDefinition) -> None:
        """Build a store sized by the line's own window policy."""
        self._line = line
        self._windows: dict[tuple[str, str], deque[float]] = defaultdict(
            lambda: deque(maxlen=line.state.window_cycles)
        )
        self._counts: dict[tuple[str, str], int] = defaultdict(int)
        # Rare cycles and how many cycles they were rare out of, kept over the
        # station's whole history rather than over the rolling window.
        self._rare: dict[str, deque[float]] = defaultdict(
            lambda: deque(maxlen=RARE_MEMORY)
        )
        self._seen: dict[str, int] = defaultdict(int)
        self._line_rare: deque[float] = deque(maxlen=RARE_MEMORY)
        self._line_seen: int = 0
        self._line_rare_count: int = 0
        self._rare_count: dict[str, int] = defaultdict(int)

    def record(self, station_id: str, variant_id: str, cycle_s: float) -> None:
        """Take one completed cycle into the window."""
        if cycle_s < 0:
            message = f"{station_id}: a cycle time cannot be negative, got {cycle_s}"
            raise ValueError(message)
        key = (station_id, variant_id)
        current = self.get(station_id, variant_id)
        if current is not None and current.is_usable:
            limit = current.median_s + RARE_SIGMA * max(
                current.scale_s, MINIMUM_SCALE_S
            )
            if cycle_s > limit:
                self._rare[station_id].append(cycle_s)
                self._rare_count[station_id] += 1
                self._line_rare.append(cycle_s)
                self._line_rare_count += 1
        self._seen[station_id] += 1
        self._line_seen += 1
        self._windows[key].append(cycle_s)
        self._counts[key] += 1

    def observed(self, station_id: str, variant_id: str) -> int:
        """How many cycles this station has produced for this variant."""
        return self._counts[(station_id, variant_id)]

    def cycles_remaining(self, station_id: str, variant_id: str) -> int:
        """How many more cycles before this station can be forecast from."""
        return max(
            0,
            self._line.state.min_cycles - len(self._windows[(station_id, variant_id)]),
        )

    def get(self, station_id: str, variant_id: str) -> CycleDistribution | None:
        """The current distribution, or None if nothing has been seen yet."""
        window = self._windows.get((station_id, variant_id))
        if not window:
            return None
        values = sorted(window)
        median = statistics.median(values)
        deviations = sorted(abs(value - median) for value in values)
        scale = statistics.median(deviations) * MAD_TO_SIGMA
        limit = median + RARE_SIGMA * max(scale, MINIMUM_SCALE_S)
        core = tuple(value for value in window if value <= limit)
        rare, rate = self._rare_component(station_id)
        return CycleDistribution(
            station_id=station_id,
            variant_id=variant_id,
            n=len(values),
            median_s=median,
            scale_s=scale,
            p05_s=_quantile(values, 0.05),
            p95_s=_quantile(values, 0.95),
            sample=tuple(window),
            is_usable=len(values) >= self._line.state.min_cycles,
            core=core or tuple(window),
            rare=rare,
            rare_rate=rate,
        )

    def _rare_component(self, station_id: str) -> tuple[tuple[float, ...], float]:
        """How often this station is interrupted, and by how much.

        Estimated over the station's whole history, and pooled with the line's
        where the station has not been watched long enough to say. A station is a
        station: they fail at similar rates on the same line, and a pooled
        estimate of a rare rate is very much better than a rate of zero or a rate
        twenty-five times too high.
        """
        seen = self._seen[station_id]
        count = self._rare_count[station_id]
        if seen >= _RARE_CONFIDENT and count > 0:
            return tuple(self._rare[station_id]), count / seen
        if self._line_seen <= 0 or not self._line_rare:
            return (), 0.0
        return tuple(self._line_rare), self._line_rare_count / self._line_seen

    def usable(self) -> tuple[CycleDistribution, ...]:
        """Every distribution the forecast is allowed to draw from."""
        found = []
        for station_id, variant_id in sorted(self._windows):
            distribution = self.get(station_id, variant_id)
            if distribution is not None and distribution.is_usable:
                found.append(distribution)
        return tuple(found)


# Below this many observed cycles a station's own rare rate is a count of one
# or zero, so the line's pooled rate is used instead.
_RARE_CONFIDENT = 2000


def _quantile(ordered: list[float], share: float) -> float:
    """A quantile of an already sorted list, by nearest rank."""
    if not ordered:
        message = "a quantile of an empty window is not defined"
        raise ValueError(message)
    position = round(share * (len(ordered) - 1))
    return ordered[position]
