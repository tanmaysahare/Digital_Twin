"""The `Estimate` and its provenance.

Every value the twin produces about the line arrives wrapped in one of these.
The provenance field has no default, so an estimate cannot be constructed
without saying where the number came from, and the interface refuses to render
one without a provenance mark (ARCHITECTURE.md Section 5.2).

Two shapes here are load-bearing:

- An estimate is always an interval. A `MEASURED` estimate is an interval whose
  bounds are equal, which is why `point` exists and why it raises on anything
  else. Collapsing an inferred interval to its midpoint is the one operation
  this module deliberately does not offer.
- `sort_key` exists because a ranked list needs a scalar. It is documented as
  lossy and the interface layer has no path from it to a rendered number.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

Provenance = Literal["MEASURED", "DERIVED", "INFERRED"]

# Whether a quantity could be separated from its neighbours at all. An
# `UNRESOLVED` estimate still carries bounds where bounds exist; what it says is
# that the twin cannot attribute the span to this station rather than to the one
# beside it (STA-07).
Resolution = Literal["RESOLVED", "UNRESOLVED"]


@dataclass(frozen=True)
class Interval:
    """A closed interval of a physical quantity, in the unit of that quantity."""

    lo: float
    hi: float

    def __post_init__(self) -> None:
        """Reject an interval whose bounds are the wrong way round or not finite."""
        if not (math.isfinite(self.lo) and math.isfinite(self.hi)):
            message = f"interval bounds must be finite, got [{self.lo}, {self.hi}]"
            raise ValueError(message)
        if self.lo > self.hi:
            message = f"interval lower bound {self.lo} exceeds upper bound {self.hi}"
            raise ValueError(message)

    @property
    def width(self) -> float:
        """How wide the interval is, in the unit of the quantity."""
        return self.hi - self.lo

    @property
    def is_point(self) -> bool:
        """Whether both bounds are the same value."""
        return self.lo == self.hi

    def contains(self, value: float) -> bool:
        """Whether a value lies inside the closed interval."""
        return self.lo <= value <= self.hi

    def shifted(self, delta: float) -> Interval:
        """The same interval moved by a constant."""
        return Interval(self.lo + delta, self.hi + delta)

    def clamped_at_zero(self) -> Interval:
        """The interval with a negative lower bound raised to zero.

        A derived cycle time whose lower bound is negative means an assumption
        was wrong, usually the transport time or the station order (EC-09). The
        caller clamps and then lowers the confidence and raises a health event;
        this method only does the clamping.
        """
        return Interval(max(0.0, self.lo), max(0.0, self.hi))


@dataclass(frozen=True)
class Estimate:
    """A quantity, where it came from, and how sure the twin is of it.

    Args:
        interval: the bounds. Equal bounds for a measurement.
        provenance: `MEASURED`, `DERIVED` or `INFERRED`. No default, deliberately.
        confidence: in [0, 1]. For an inference this comes from the interval
            width relative to the station's plausible range.
        basis: one line a supervisor can read, shown beside the value.
        resolution: whether the quantity could be separated from its neighbours.
    """

    interval: Interval
    provenance: Provenance
    confidence: float
    basis: str
    resolution: Resolution = "RESOLVED"

    def __post_init__(self) -> None:
        """Reject a confidence outside [0, 1] and a measurement with a width."""
        if not 0.0 <= self.confidence <= 1.0:
            message = f"confidence must be in [0, 1], got {self.confidence}"
            raise ValueError(message)
        if self.provenance == "MEASURED" and not self.interval.is_point:
            message = (
                "a MEASURED estimate has equal bounds. An interval means the value "
                "was derived or inferred, and saying otherwise presents an "
                "inference as a reading"
            )
            raise ValueError(message)
        if not self.basis.strip():
            message = "an estimate carries a basis, because the interface shows it"
            raise ValueError(message)

    @classmethod
    def measured(cls, value: float, basis: str, confidence: float = 1.0) -> Estimate:
        """An estimate read directly from a source."""
        return cls(Interval(value, value), "MEASURED", confidence, basis)

    @classmethod
    def derived(
        cls,
        interval: Interval,
        basis: str,
        confidence: float,
        resolution: Resolution = "RESOLVED",
    ) -> Estimate:
        """An estimate computed from measurements by a known relation."""
        return cls(interval, "DERIVED", confidence, basis, resolution)

    @classmethod
    def inferred(
        cls,
        interval: Interval,
        basis: str,
        confidence: float,
        resolution: Resolution = "RESOLVED",
    ) -> Estimate:
        """An estimate the twin reasoned to, with no direct observation of it."""
        return cls(interval, "INFERRED", confidence, basis, resolution)

    @property
    def lo(self) -> float:
        """The lower bound."""
        return self.interval.lo

    @property
    def hi(self) -> float:
        """The upper bound."""
        return self.interval.hi

    @property
    def point(self) -> float:
        """The value, for a measurement only.

        Raises:
            ValueError: if the estimate was derived or inferred. There is no
                point value for those and asking for one is the mistake this
                property exists to catch.
        """
        if self.provenance != "MEASURED":
            message = (
                f"{self.provenance} estimates have no point value. Carry the "
                f"interval [{self.lo:.1f}, {self.hi:.1f}] or render it as one"
            )
            raise ValueError(message)
        return self.interval.lo

    def sort_key(self) -> float:
        """A scalar for ordering only. Lossy, and never rendered.

        Ranking a list of intervals needs a total order and there is no
        information-preserving one. This is the midpoint, and it exists here so
        that a sort does not become an excuse to compute a midpoint somewhere a
        renderer can reach.
        """
        return (self.interval.lo + self.interval.hi) / 2.0
