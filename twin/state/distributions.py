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

    def record(self, station_id: str, variant_id: str, cycle_s: float) -> None:
        """Take one completed cycle into the window."""
        if cycle_s < 0:
            message = f"{station_id}: a cycle time cannot be negative, got {cycle_s}"
            raise ValueError(message)
        key = (station_id, variant_id)
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
        )

    def usable(self) -> tuple[CycleDistribution, ...]:
        """Every distribution the forecast is allowed to draw from."""
        found = []
        for station_id, variant_id in sorted(self._windows):
            distribution = self.get(station_id, variant_id)
            if distribution is not None and distribution.is_usable:
                found.append(distribution)
        return tuple(found)


def _quantile(ordered: list[float], share: float) -> float:
    """A quantile of an already sorted list, by nearest rank."""
    if not ordered:
        message = "a quantile of an empty window is not defined"
        raise ValueError(message)
    position = round(share * (len(ordered) - 1))
    return ordered[position]
