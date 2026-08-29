"""EWMA and CUSUM drift detection. T-055.

TECHNICAL_SPEC.md Section 5.3. Two control charts run in parallel on each
station's cycle time, per variant, and a `DRIFT` event is emitted only where both
of them signal.

**Why two charts.** An EWMA reacts to a sustained small shift sooner than a
Shewhart limit and is what catches a fixture wearing inside its tolerance band. A
CUSUM does the same and, more usefully, carries the arithmetic that says when the
shift began. Requiring both to agree roughly halves the false positive rate at a
small cost in detection delay, and given what a false alarm costs on a floor
(USER_RESEARCH.md Section 3) that is the right trade. `require_both` is
configurable per line, and turning it off is a decision a plant makes with its
eyes open rather than a default.

**Why the onset matters more than the detection.** A supervisor reading "drift
detected at 09:26" has to work out what changed at 09:26, and nothing did. The
answer is that the fixture started wearing at 09:14, and CUSUM gives that
directly: the last instant at which the relevant cumulative sum was zero is the
last instant at which the process was still centred. The interface says "drifted
since 09:14" because of this, and the difference is the difference between a
supervisor finding the cause and not.

**Why the reference window excludes the drift.** `mu` and `sigma` are the robust
estimates from Section 4.2, computed over the cycles *before* the current CUSUM
run began. A reference window that included the drift would chase it: the
baseline would climb with the station, the z-score would fall back towards zero,
and the chart would fall silent exactly when the station had moved furthest. This
is the failure mode that makes a naive rolling baseline useless for slow wear.
"""

from __future__ import annotations

import statistics
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from twin.config.line import LineDefinition
from twin.state.distributions import MAD_TO_SIGMA, MINIMUM_SCALE_S

Direction = Literal["UP", "DOWN"]

# How many cycles a chart needs before it will judge anything, and where they
# come from.
#
# The two estimates a control chart rests on need very different amounts of data,
# and treating them as one number is what makes a chart either blind or noisy.
#
# The centre line is a median, which is cheap: twenty-five cycles put its own
# standard error near a fifth of a sigma. It has to be per variant, because a
# long-wheelbase body genuinely takes longer at the same station and pooling the
# variants would centre the chart between them.
#
# The scale is a median absolute deviation, which is expensive: from twenty
# points its standard error is about twenty percent of itself, and the whole of
# the chart's arithmetic is in units of it. An underestimated sigma shrinks both
# the cumulative sum's slack and its limit together, and the chart then signals
# on ordinary noise. Measured on a stable simulated station, a reference of
# twenty cycles produced a first signal at cycle fifty on a process that never
# moved.
#
# So the scale is pooled across the variants at a station, on the relative
# deviation from each variant's own median. The spread of a station's cycle time
# is a property of the station, of its fixture and its operator, and not of the
# body on it; the simulator builds it that way and so does a real line. Pooling
# reaches a hundred cycles about three times sooner, which on this line is the
# difference between having a baseline before the fault arrives and not.
MINIMUM_CENTRE = 25
MINIMUM_REFERENCE = 100


@dataclass(frozen=True)
class DriftEstimate:
    """What the twin currently believes about one station's drift.

    `slope_s_per_s` is what the forecaster extrapolates with (T-052) and
    `onset_at` is what the interface prints. Both are estimates from the cycles
    since the onset and both are shown with the count they rest on.
    """

    station_id: str
    variant_id: str
    detected_at: datetime
    onset_at: datetime
    direction: Direction
    # How far the station has moved since its reference baseline, in seconds.
    magnitude_s: float
    # Seconds of cycle time added per second of elapsed time. Zero where too few
    # cycles have accumulated since the onset to fit a line through them.
    slope_s_per_s: float
    reference_median_s: float
    reference_scale_s: float
    cycles_since_onset: int
    ewma_deviation_sigma: float
    cusum_sigma: float
    basis: str

    @property
    def onset_lag_s(self) -> float:
        """How long the drift had been running before it was detected."""
        return (self.detected_at - self.onset_at).total_seconds()

    @property
    def is_material(self) -> bool:
        """Whether this drift is large enough to forecast from.

        Both charts signalling says the station has moved. Whether the move is
        worth extrapolating is a second question, and the answer here is that it
        has to be at least as large as the station's own noise. A control chart
        tuned to catch a one sigma shift raises a signal every few hundred
        in-control cycles by
        construction, and on a 42 station line that is several a shift. Those
        signals belong in the ledger, where they are scored and where a station
        that produces them stays in shadow. They do not belong in the forecast's
        extrapolation, where a spurious slope on eleven stations at once turns a
        useful forecast into a wall of alarm.
        """
        return abs(self.magnitude_s) >= self.reference_scale_s


@dataclass
class _Chart:
    """One station, one variant: the two charts and the history behind them."""

    station_id: str
    variant_id: str
    line: LineDefinition
    history: deque[tuple[datetime, float]]
    ewma: float | None = None
    ewma_count: int = 0
    cusum_high: float = 0.0
    cusum_low: float = 0.0
    # Where in the history the current CUSUM run began. Everything before it is
    # the reference the charts are judged against.
    run_start: int = 0
    # How many cycles have entered the history in total, so that `run_start`
    # survives the deque dropping its oldest entries.
    seen: int = 0
    signalled: bool = False

    def centre(self) -> tuple[float, int] | None:
        """This variant's median at this station, from before the current run.

        Returns None until enough cycles have accumulated to say anything, which
        is the cold-start case the interface reports as a count of cycles
        remaining rather than as a broken station (EC-20).
        """
        values = self.reference_values()
        if len(values) < MINIMUM_CENTRE:
            return None
        return statistics.median(values), len(values)

    def reference_values(self) -> list[float]:
        """Every cycle that is reference rather than evidence of a shift."""
        dropped = self.seen - len(self.history)
        cutoff = max(0, self.run_start - dropped)
        return [value for _, value in list(self.history)[:cutoff]]

    def reset_run(self) -> None:
        """Start a new run here. The cycles so far become the reference.

        Both charts reset, not only the cumulative sums. An exponentially
        weighted average carries its history for about a dozen cycles at lambda
        0.2, so an episode that closed while the average was still elevated would
        re-signal the moment the cumulative sum next crossed, and one drift would
        be reported as four. Measured on a stable station, leaving the average in
        place turned an in-control run length of several hundred cycles into one
        of about a hundred and fifty.
        """
        self.run_start = self.seen
        self.cusum_high = 0.0
        self.cusum_low = 0.0
        self.ewma = None
        self.ewma_count = 0
        self.signalled = False

    def since_run(self) -> list[tuple[datetime, float]]:
        """Every cycle observed since the current run began."""
        dropped = self.seen - len(self.history)
        cutoff = max(0, self.run_start - dropped)
        return list(self.history)[cutoff:]


class DriftDetector:
    """Watches every station's cycle time for a sustained shift. T-055."""

    def __init__(self, line: LineDefinition) -> None:
        """Build a detector for one line, from that line's own drift policy."""
        self.line = line
        self._charts: dict[tuple[str, str], _Chart] = {}
        self._active: dict[str, DriftEstimate] = {}
        self._episodes: dict[tuple[str, str], DriftEstimate] = {}
        self._counts: dict[str, int] = defaultdict(int)
        # Relative deviations from each variant's own median, pooled per station.
        # This is where the scale comes from. See MINIMUM_REFERENCE.
        self._spread: dict[str, deque[float]] = defaultdict(
            lambda: deque(maxlen=line.state.window_cycles * 3)
        )

    # -- state ------------------------------------------------------------

    def active(self, station_id: str) -> DriftEstimate | None:
        """The station's current drift, or None if it is not drifting."""
        return self._active.get(station_id)

    def drifting(self) -> tuple[DriftEstimate, ...]:
        """Every station currently believed to be drifting."""
        return tuple(self._active[station_id] for station_id in sorted(self._active))

    def slopes(self) -> dict[str, float]:
        """The slope per station, which is what the forecast extrapolates with.

        Material drifts only. See `DriftEstimate.is_material` for why the two
        questions are separated.
        """
        return {
            station_id: estimate.slope_s_per_s
            for station_id, estimate in self._active.items()
            if estimate.is_material
        }

    # -- ingest -----------------------------------------------------------

    def observe(
        self, station_id: str, variant_id: str, cycle_s: float, at: datetime
    ) -> DriftEstimate | None:
        """Take one completed cycle. Returns an estimate when an episode opens.

        A single episode emits once. The estimate stays queryable through
        `active` for as long as the charts hold, because the forecaster needs the
        current slope on every cycle while the ledger needs one prediction per
        episode.
        """
        chart = self._charts.get((station_id, variant_id))
        if chart is None:
            chart = _Chart(
                station_id=station_id,
                variant_id=variant_id,
                line=self.line,
                history=deque(maxlen=self.line.state.window_cycles),
            )
            self._charts[(station_id, variant_id)] = chart
        chart.history.append((at, cycle_s))
        chart.seen += 1

        centre = chart.centre()
        if centre is None:
            chart.run_start = chart.seen
            return None
        median, _ = centre
        if not chart.signalled:
            # While no shift is claimed, this cycle contributes to the station's
            # pooled spread. Once one is claimed the pool stops taking cycles,
            # because a shift that inflated the scale it is measured against
            # would talk the chart out of the signal it had just raised.
            self._spread[station_id].append((cycle_s - median) / max(median, 1e-9))
        pooled = self._spread[station_id]
        if len(pooled) < MINIMUM_REFERENCE:
            chart.run_start = chart.seen
            return None
        relative = sorted(abs(value) for value in pooled)
        scale = max(
            statistics.median(relative) * MAD_TO_SIGMA * median, MINIMUM_SCALE_S
        )

        policy = self.line.drift
        deviation = cycle_s - median
        chart.ewma_count += 1
        # The average starts at the target, not at the first observation. Seeding
        # it with the observation makes the statistic equal to that observation
        # while its own standard deviation is still only a fifth of the process
        # sigma, so the chart signals whenever the first cycle after a reset sits
        # more than six tenths of a sigma from the median, which is more than half
        # the time. Measured on a stable station, that alone accounted for most of
        # the detector's in-control signals.
        chart.ewma = policy.ewma_lambda * deviation + (1.0 - policy.ewma_lambda) * (
            chart.ewma or 0.0
        )
        limit = _ewma_limit(scale, policy.ewma_lambda, chart.ewma_count)
        ewma_signal = abs(chart.ewma) > policy.ewma_l * limit

        step = policy.cusum_k_sigma * scale
        threshold = policy.cusum_h_sigma * scale
        high_was_zero = chart.cusum_high <= 0.0
        low_was_zero = chart.cusum_low <= 0.0
        chart.cusum_high = max(0.0, chart.cusum_high + deviation - step)
        chart.cusum_low = max(0.0, chart.cusum_low - deviation - step)
        if chart.cusum_high <= 0.0 and chart.cusum_low <= 0.0 and not chart.signalled:
            # Both sums are back at zero and nothing has been claimed, so the
            # cycles so far are all reference.
            chart.run_start = chart.seen
        elif high_was_zero and low_was_zero and not chart.signalled:
            # A run has just started. Its first cycle is the onset candidate.
            chart.run_start = chart.seen - 1
        cusum_signal = chart.cusum_high > threshold or chart.cusum_low > threshold

        signalled = (
            (ewma_signal and cusum_signal)
            if policy.require_both
            else (ewma_signal or cusum_signal)
        )
        if not signalled:
            if chart.signalled and not ewma_signal and not cusum_signal:
                self._close(chart)
            return None

        estimate = self._estimate(
            chart, at, median, scale, ewma=chart.ewma or 0.0, threshold=threshold
        )
        self._active[station_id] = estimate
        if chart.signalled:
            # The episode is already open. The estimate is refreshed so that the
            # forecaster extrapolates from the current slope, but the ledger
            # holds one prediction per episode rather than one per cycle.
            self._episodes[(station_id, variant_id)] = estimate
            return None
        chart.signalled = True
        self._episodes[(station_id, variant_id)] = estimate
        self._counts[station_id] += 1
        return estimate

    def _close(self, chart: _Chart) -> None:
        """A drift that came back on its own. The episode ends (EC-27)."""
        self._active.pop(chart.station_id, None)
        self._episodes.pop((chart.station_id, chart.variant_id), None)
        chart.reset_run()

    def _estimate(
        self,
        chart: _Chart,
        at: datetime,
        median: float,
        scale: float,
        *,
        ewma: float,
        threshold: float,
    ) -> DriftEstimate:
        window = chart.since_run()
        onset_at = window[0][0] if window else at
        values = [value for _, value in window]
        moved = (statistics.median(values) - median) if values else 0.0
        direction: Direction = "UP" if chart.cusum_high >= chart.cusum_low else "DOWN"
        slope = _slope(window)
        return DriftEstimate(
            station_id=chart.station_id,
            variant_id=chart.variant_id,
            detected_at=at,
            onset_at=onset_at,
            direction=direction,
            magnitude_s=moved,
            slope_s_per_s=slope,
            reference_median_s=median,
            reference_scale_s=scale,
            cycles_since_onset=len(window),
            ewma_deviation_sigma=ewma / scale,
            cusum_sigma=max(chart.cusum_high, chart.cusum_low) / scale,
            basis=(
                f"{chart.station_id} has run {abs(moved):.1f} s "
                f"{'above' if moved >= 0 else 'below'} its baseline of "
                f"{median:.1f} s since {onset_at:%H:%M}, over {len(window)} cycles. "
                f"Both the exponentially weighted chart and the cumulative sum "
                f"chart signalled, the cumulative sum at "
                f"{max(chart.cusum_high, chart.cusum_low) / max(threshold, 1e-9):.1f} "
                f"times its limit"
            ),
        )


def _ewma_limit(scale: float, lam: float, count: int) -> float:
    """The exponentially weighted moving average's own standard deviation.

    TECHNICAL_SPEC.md Section 5.3. The variance of the statistic grows towards
    its asymptote over the first cycles, and using the asymptote from the start
    would make the chart insensitive exactly when a new station or a new variant
    is most worth watching.
    """
    growth = 1.0 - (1.0 - lam) ** (2 * count)
    return float(scale * (lam / (2.0 - lam) * growth) ** 0.5)


# Below this many cycles since the onset there is nothing to fit a line through,
# and a slope from two points is the two points rather than the trend.
_MINIMUM_SLOPE_CYCLES = 8


def _slope(window: list[tuple[datetime, float]]) -> float:
    """Seconds of cycle time added per second of elapsed time.

    An ordinary least squares fit over the cycles since the onset. Least squares
    rather than the difference of the two ends, because a single long cycle at
    either end would otherwise set the whole extrapolation, and the extrapolation
    is what the forecast rests on.
    """
    if len(window) < _MINIMUM_SLOPE_CYCLES:
        return 0.0
    origin = window[0][0]
    times = [(moment - origin).total_seconds() for moment, _ in window]
    values = [value for _, value in window]
    mean_t = sum(times) / len(times)
    mean_v = sum(values) / len(values)
    variance = sum((time - mean_t) ** 2 for time in times)
    if variance <= 0.0:
        return 0.0
    covariance = sum(
        (time - mean_t) * (value - mean_v)
        for time, value in zip(times, values, strict=True)
    )
    return covariance / variance
