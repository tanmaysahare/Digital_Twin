"""Turning replications into probabilities. T-053.

TECHNICAL_SPEC.md Section 5.1 and BTL-02. The forecaster produces R runs of the
line; this reduces them to the quantities the interface reads.

**A stall is a bucket, not an instant.** TECHNICAL_SPEC.md Section 5.1 defines a
stop as a station blocked or starved for longer than `stall_threshold_s`, and
reports it per five-minute bucket. On a paced line the two readings of that
sentence are not the same, and only one of them is measurable: a station on a
line running to takt waits a few seconds on every cycle by construction, so a
*continuous* wait past the threshold happens only during a long repair, while
the accumulated wait inside a bucket is what a supervisor sees as the line
falling behind. The accumulated reading is the one implemented, here and in the
evaluation harness, and TECHNICAL_SPEC.md Section 5.1 records the finding that
forced the choice. The two must agree, because the ledger scores the forecast
against ground truth computed the same way.

**Everything leaves here as an interval.** An output figure is a quantile pair
over the replications, never a mean, and the expected unit loss is a range. The
one place a point appears is a probability, which is what a probability is.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from twin.config.line import LineDefinition
from twin.domain.estimate import Estimate, Interval
from twin.forecast.des import BUCKET_S, ForecastRun

# The quantiles every interval in the forecast is reported at. The 10th and 90th
# rather than the 5th and 95th, because at 200 replications the tails of the
# tails are the replication count talking rather than the line.
LOW_QUANTILE = 0.10
HIGH_QUANTILE = 0.90

# How many learning stations the note names before it says how many more.
_NAMED_IN_NOTE = 4


@dataclass(frozen=True)
class BucketWindow:
    """One five-minute bucket, as seconds from the calendar's epoch."""

    index: int
    start_s: float
    end_s: float

    @property
    def midpoint_s(self) -> float:
        """The middle of the bucket, used when a single instant is needed."""
        return (self.start_s + self.end_s) / 2.0


@dataclass(frozen=True)
class StationForecast:
    """One station's forecast across the horizon."""

    station_id: str
    # Probability that the station loses more than the threshold in each bucket.
    stall_probability: tuple[float, ...]
    blocked_probability: tuple[float, ...]
    starved_probability: tuple[float, ...]
    # Mean production seconds lost per bucket, for the strip's shading.
    mean_lost_s: tuple[float, ...]

    @property
    def peak(self) -> tuple[int, float]:
        """The bucket with the highest stall probability, and that probability."""
        index = int(np.argmax(self.stall_probability))
        return index, self.stall_probability[index]


@dataclass(frozen=True)
class BufferForecast:
    """One buffer's occupancy trajectory, as an interval per bucket."""

    buffer_id: str
    after_station_id: str
    capacity: int
    low: tuple[float, ...]
    high: tuple[float, ...]
    mean: tuple[float, ...]


@dataclass(frozen=True)
class ForecastSummary:
    """The whole forecast, aggregated. What the API returns and the ledger cites."""

    line_id: str
    at_s: float
    horizon_s: float
    replications: int
    degraded: bool
    fallback_stations: tuple[str, ...]
    learning_stations: tuple[str, ...]
    drifting_stations: tuple[str, ...]
    buckets: tuple[BucketWindow, ...]
    stations: tuple[StationForecast, ...]
    buffers: tuple[BufferForecast, ...]
    # Probability that any station stalls, per bucket.
    line_stall_probability: tuple[float, ...]
    # Units completed over the whole horizon, as an interval over replications.
    output: Estimate
    # Units the line will not build against what takt allows, as an interval.
    expected_unit_loss: Estimate
    runtime_s: float

    @property
    def is_forecastable(self) -> bool:
        """Whether every station has a baseline the flow model can run on."""
        return not self.learning_stations

    def learning_note(self) -> str:
        """What the interface says instead of a forecast, while one is learning."""
        if self.is_forecastable:
            return ""
        named = ", ".join(self.learning_stations[:_NAMED_IN_NOTE])
        remainder = len(self.learning_stations) - _NAMED_IN_NOTE
        more = f" and {remainder} others" if remainder > 0 else ""
        return (
            f"No forecast yet. {named}{more} have not produced enough cycles for "
            f"a baseline, and blocking and starving propagate the length of the "
            f"line, so one station without one leaves every station's forecast "
            f"resting on an assumption"
        )

    def station(self, station_id: str) -> StationForecast:
        """One station's forecast by identifier."""
        for item in self.stations:
            if item.station_id == station_id:
                return item
        message = f"no forecast for station {station_id}"
        raise KeyError(message)

    def window_of(self, index: int) -> BucketWindow:
        """One bucket by index."""
        return self.buckets[index]


def aggregate(
    run: ForecastRun, line: LineDefinition, nominal_output: float
) -> ForecastSummary:
    """Reduce every replication to the quantities the interface reads.

    Args:
        run: the replications, as the forecaster produced them.
        line: the line, for its stall threshold and its buffer definitions.
        nominal_output: how many units takt allows over the horizon, which is
            what the expected loss is measured against.
    """
    threshold = line.forecast.stall_threshold_s
    lost = np.stack([item.lost_s for item in run.replications])
    blocked = np.stack([item.blocked_s for item in run.replications])
    starved = np.stack([item.starved_s for item in run.replications])
    occupancy = np.stack([item.link_occupancy for item in run.replications])
    completed = np.stack([item.completed for item in run.replications])

    stall = (lost > threshold).mean(axis=0)
    stations = tuple(
        StationForecast(
            station_id=station_id,
            stall_probability=tuple(float(value) for value in stall[index]),
            blocked_probability=tuple(
                float(value) for value in (blocked[:, index] > threshold).mean(axis=0)
            ),
            starved_probability=tuple(
                float(value) for value in (starved[:, index] > threshold).mean(axis=0)
            ),
            mean_lost_s=tuple(float(value) for value in lost[:, index].mean(axis=0)),
        )
        for index, station_id in enumerate(line.station_ids)
    )

    order = line.station_ids
    buffers = tuple(
        BufferForecast(
            buffer_id=definition.buffer_id,
            after_station_id=definition.after,
            capacity=definition.capacity,
            low=tuple(
                float(value)
                for value in np.quantile(
                    occupancy[:, order.index(definition.after) + 1],
                    LOW_QUANTILE,
                    axis=0,
                )
            ),
            high=tuple(
                float(value)
                for value in np.quantile(
                    occupancy[:, order.index(definition.after) + 1],
                    HIGH_QUANTILE,
                    axis=0,
                )
            ),
            mean=tuple(
                float(value)
                for value in occupancy[:, order.index(definition.after) + 1].mean(
                    axis=0
                )
            ),
        )
        for definition in line.buffers
        if order.index(definition.after) + 1 < len(order)
    )

    total = completed.sum(axis=1)
    output_lo = float(np.quantile(total, LOW_QUANTILE))
    output_hi = float(np.quantile(total, HIGH_QUANTILE))
    loss = np.maximum(0.0, nominal_output - total)
    return ForecastSummary(
        line_id=line.line_id,
        at_s=run.seed.at_s,
        horizon_s=run.horizon_s,
        replications=run.count,
        degraded=run.degraded or not run.is_forecastable,
        fallback_stations=run.fallback_stations,
        learning_stations=run.learning_stations,
        drifting_stations=run.seed.drifting,
        buckets=tuple(
            BucketWindow(
                index=index,
                start_s=run.seed.at_s + index * BUCKET_S,
                end_s=run.seed.at_s + (index + 1) * BUCKET_S,
            )
            for index in range(run.buckets)
        ),
        stations=stations,
        buffers=buffers,
        line_stall_probability=tuple(
            float(value) for value in (lost > threshold).any(axis=1).mean(axis=0)
        ),
        output=Estimate.derived(
            Interval(output_lo, output_hi),
            basis=(
                f"{run.count} replications of the next "
                f"{run.horizon_s / 60:.0f} minutes from the state at this cycle"
            ),
            confidence=_confidence(run),
        ),
        expected_unit_loss=Estimate.derived(
            Interval(
                float(np.quantile(loss, LOW_QUANTILE)),
                float(np.quantile(loss, HIGH_QUANTILE)),
            ),
            basis=(
                f"takt allows {nominal_output:.0f} units over the horizon and the "
                f"forecast builds {output_lo:.0f} to {output_hi:.0f}"
            ),
            confidence=_confidence(run),
        ),
        runtime_s=run.runtime_s,
    )


def _confidence(run: ForecastRun) -> float:
    """How much weight the forecast's own intervals carry.

    Falls with a reduced replication count and with every station the forecast
    had to fall back to takt for, because both widen what the intervals do not
    say rather than what they do.
    """
    base = 0.9 if not run.degraded else 0.7
    penalty = 0.05 * len(run.fallback_stations)
    return max(0.0, min(1.0, base - penalty))
