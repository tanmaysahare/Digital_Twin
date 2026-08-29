"""Split conformal intervals on the failure probability. T-066.

TECHNICAL_SPEC.md Section 6.4. A calibrated probability says how often a unit
like this one fails. It does not say how much to trust that number for this
particular unit, and the difference matters when a third of the unit's route ran
through stations nothing watched.

```
Calibration scores  s_i = 1 - p_hat(y_i | x_i)   for the true class
q  = the ceil((n + 1)(1 - alpha)) / n quantile of s,   alpha = 0.10
The interval covers every class y with 1 - p_hat(y | x) <= q
```

**Why conformal rather than a posterior.** Distribution-free coverage under
severe class imbalance is exactly what is wanted here, and it is cheap. A
Bayesian posterior's calibration would depend on a prior and a likelihood the
twin cannot check against a two percent base rate, and the product's argument
does not survive an uncertainty estimate that rests on unverifiable assumptions
(S-20 to S-23).

**What the interval means, and what it does not.** It is a coverage guarantee
over the population of units the calibration fold was drawn from: at alpha 0.10,
the true class falls inside the reported set in at least 90 percent of cases. It
is not a statement about this unit in isolation, and the evidence pack says so
rather than letting the width read as a per-unit confidence.

Coverage is verified on a fold the calibration never saw, and the measured figure
goes in the evidence pack beside the target (AC-024).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

# The miscoverage rate. At 0.10 the interval covers the true class in at least 90
# percent of cases, which is the figure PRD Section 5 asks for.
ALPHA = 0.10

# Below this many calibration points the quantile is the sample rather than the
# distribution, and an interval derived from it would be a guess with a
# guarantee attached.
MINIMUM_CALIBRATION = 40

# A label is stored as a float so that it can go straight into an array. Half
# is the only sensible place to split two classes recorded as zero and one.
_POSITIVE = 0.5


@dataclass(frozen=True)
class ConformalInterval:
    """One unit's failure probability, with its conformal bounds."""

    point: float
    lo: float
    hi: float
    # Whether the prediction set holds both classes, which is the honest way of
    # saying the model cannot separate this unit.
    covers_both: bool
    alpha: float
    calibration_n: int

    @property
    def width(self) -> float:
        """How wide the interval is."""
        return self.hi - self.lo


@dataclass(frozen=True)
class ConformalCalibration:
    """The quantile a fold produced, and everything needed to report it."""

    quantile: float
    n: int
    alpha: float
    is_usable: bool
    reason: str | None = None

    def interval(self, probability: float) -> ConformalInterval:
        """The interval around one calibrated probability.

        The score for the failure class is `1 - p`, and for the pass class `p`.
        A class is in the prediction set when its score is at or below the
        quantile, so a unit whose probability sits in the middle admits both and
        the interval spans them.
        """
        probability = min(1.0, max(0.0, probability))
        if not self.is_usable:
            return ConformalInterval(
                point=probability,
                lo=0.0,
                hi=1.0,
                covers_both=True,
                alpha=self.alpha,
                calibration_n=self.n,
            )
        failure_in = (1.0 - probability) <= self.quantile
        pass_in = probability <= self.quantile
        if failure_in and pass_in:
            # Both classes are admissible. The interval is the widest band the
            # quantile allows, which is the honest rendering of "cannot separate".
            return ConformalInterval(
                point=probability,
                lo=max(0.0, probability - self.quantile),
                hi=min(1.0, probability + self.quantile),
                covers_both=True,
                alpha=self.alpha,
                calibration_n=self.n,
            )
        if failure_in:
            return ConformalInterval(
                point=probability,
                lo=max(0.0, 1.0 - self.quantile),
                hi=1.0,
                covers_both=False,
                alpha=self.alpha,
                calibration_n=self.n,
            )
        if pass_in:
            return ConformalInterval(
                point=probability,
                lo=0.0,
                hi=min(1.0, self.quantile),
                covers_both=False,
                alpha=self.alpha,
                calibration_n=self.n,
            )
        # Neither class is admissible. A conformal prediction set is allowed to
        # be empty, and what an empty one says is that this unit's score is
        # unlike anything in the calibration fold: the model is being asked about
        # a unit it has no comparable experience of. The honest rendering is the
        # widest interval rather than a narrow one on the wrong side of the
        # point, and the flag says the two classes could not be separated.
        return ConformalInterval(
            point=probability,
            lo=0.0,
            hi=1.0,
            covers_both=True,
            alpha=self.alpha,
            calibration_n=self.n,
        )


def calibrate(
    probabilities: np.ndarray, labels: np.ndarray, alpha: float = ALPHA
) -> ConformalCalibration:
    """Fit the conformal quantile on a fold the model did not train on."""
    n = int(probabilities.size)
    if n < MINIMUM_CALIBRATION:
        return ConformalCalibration(
            quantile=1.0,
            n=n,
            alpha=alpha,
            is_usable=False,
            reason=(
                f"{n} calibration points, below the {MINIMUM_CALIBRATION} a "
                f"distribution-free guarantee needs. Every interval is reported "
                f"as the full range until there are more"
            ),
        )
    # The score of the true class, which is what the guarantee is about.
    scores = np.where(labels > _POSITIVE, 1.0 - probabilities, probabilities)
    ordered = np.sort(scores)
    rank = math.ceil((n + 1) * (1.0 - alpha))
    index = min(n - 1, max(0, rank - 1))
    return ConformalCalibration(
        quantile=float(ordered[index]), n=n, alpha=alpha, is_usable=True
    )


def empirical_coverage(
    calibration: ConformalCalibration,
    probabilities: np.ndarray,
    labels: np.ndarray,
) -> float:
    """How often the prediction set held the true class, on a held-out fold.

    This is the number the evidence pack reports against the 0.90 target. It is
    measured on a fold the quantile never saw, because a coverage figure computed
    on the calibration fold is arithmetic rather than evidence.
    """
    if probabilities.size == 0 or not calibration.is_usable:
        return math.nan
    scores = np.where(labels > _POSITIVE, 1.0 - probabilities, probabilities)
    return float((scores <= calibration.quantile).mean())
