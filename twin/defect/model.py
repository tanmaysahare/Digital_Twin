"""The defect risk model. T-064, T-065.

TECHNICAL_SPEC.md Sections 6.2 and 6.3. One LightGBM binary classifier per gate,
calibrated by isotonic regression on a held-out temporal fold.

**Separate models per gate, not one multi-label model.** The causal paths differ.
A body-in-white weld failure at G1 and a paint contamination at G2 share almost
no mechanism, and a single model would blur them into an average that explains
neither. Separate models also mean a gate whose model fails calibration can be
withheld while the others keep running (ARCHITECTURE.md Section 8).

**The split is temporal and it is never random.** A random split leaks the future
through shared part lots and shared drift episodes: the same lot appears on both
sides, the model learns the lot rather than the mechanism, and the evaluation
reports a number that cannot be reproduced in a plant. The split here is by time,
and `Split.leaks` exists so a test can assert that no unit and no lot spans the
boundary (T-064).

**Class imbalance is handled with a weight, not by resampling.** The base failure
rate is around two percent. Resampling would distort the probabilities that then
have to be calibrated, and the calibration is the part the product's argument
rests on: a probability shown as a probability has to be one.

**A model that does not calibrate is not promoted.** Expected calibration error
above the line's target leaves the model `UNAVAILABLE` rather than published, and
the interface says which capability is missing. An uncalibrated probability
rendered as a probability is a lie in a product whose whole argument is honesty
(Section 6.3, AC-024).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd  # type: ignore[import-untyped]

try:  # pragma: no cover - the dependency is declared, this is the degraded path
    import lightgbm
except ImportError:  # pragma: no cover
    # ARCHITECTURE.md Section 8: a model that fails to load moves that predictor
    # to UNAVAILABLE and the interface says which capability is missing. Every
    # other predictor keeps running.
    lightgbm = None  # type: ignore[assignment]

from twin.defect.features import CATEGORICAL, FeatureRow
from twin.domain.seeds import seed_for

# Typed loosely on purpose: the degraded path in ARCHITECTURE.md Section 8 needs
# `lgb is None` to remain a live question at runtime, which a module type would
# answer statically.
lgb: Any = lightgbm

# The share of the labelled rows that trains the model. The rest splits evenly
# between the calibration fold and the held-out fold, so that calibration and the
# number reported for it never come from the same rows.
TRAIN_SHARE = 0.6
CALIBRATION_SHARE = 0.2

# Bins for the reliability diagram and the expected calibration error. Ten is the
# convention and it is what the evidence pack plots (AC-093).
RELIABILITY_BINS = 10

# Expected calibration error above this and the model is not promoted.
# PRD Section 5.
ECE_TARGET = 0.05

# Below this many failures in the training fold there is nothing to learn, and a
# model fitted anyway would produce confident noise.
MINIMUM_FAILURES = 12


@dataclass(frozen=True)
class Split:
    """A temporal split of the labelled rows into three folds."""

    train: tuple[FeatureRow, ...]
    calibrate: tuple[FeatureRow, ...]
    holdout: tuple[FeatureRow, ...]
    train_end: datetime
    calibrate_end: datetime

    @property
    def sizes(self) -> tuple[int, int, int]:
        """How many rows each fold holds."""
        return len(self.train), len(self.calibrate), len(self.holdout)

    def leaks(self) -> tuple[str, ...]:
        """Any unit that appears in more than one fold.

        Empty by construction, because a row is one unit at one gate and the
        split is by time. The check exists because "by construction" is what
        everyone says about the leak they later find (T-064).
        """
        seen: dict[str, str] = {}
        found: list[str] = []
        for name, fold in (
            ("train", self.train),
            ("calibrate", self.calibrate),
            ("holdout", self.holdout),
        ):
            for row in fold:
                previous = seen.get(row.unit_id)
                if previous is not None and previous != name:
                    found.append(row.unit_id)
                seen[row.unit_id] = name
        return tuple(sorted(set(found)))


def temporal_split(rows: tuple[FeatureRow, ...]) -> Split:
    """Split labelled rows by time, never at random."""
    labelled = sorted(
        (row for row in rows if row.failed is not None), key=lambda row: row.at
    )
    if not labelled:
        now = datetime.now(tz=None)  # noqa: DTZ005
        return Split((), (), (), now, now)
    train_end = int(len(labelled) * TRAIN_SHARE)
    calibrate_end = int(len(labelled) * (TRAIN_SHARE + CALIBRATION_SHARE))
    return Split(
        train=tuple(labelled[:train_end]),
        calibrate=tuple(labelled[train_end:calibrate_end]),
        holdout=tuple(labelled[calibrate_end:]),
        train_end=labelled[max(0, train_end - 1)].at,
        calibrate_end=labelled[max(0, calibrate_end - 1)].at,
    )


@dataclass(frozen=True)
class Reliability:
    """A reliability diagram and the error it summarises. AC-093."""

    bin_lower: tuple[float, ...]
    bin_upper: tuple[float, ...]
    predicted: tuple[float, ...]
    observed: tuple[float, ...]
    counts: tuple[int, ...]
    expected_calibration_error: float

    @property
    def is_calibrated(self) -> bool:
        """Whether the model may be promoted on its calibration. AC-024."""
        return self.expected_calibration_error <= ECE_TARGET


def reliability(
    probabilities: np.ndarray, labels: np.ndarray, bins: int = RELIABILITY_BINS
) -> Reliability:
    """Bin the predictions and compare each bin's claim against what happened."""
    edges = np.linspace(0.0, 1.0, bins + 1)
    lower: list[float] = []
    upper: list[float] = []
    predicted: list[float] = []
    observed: list[float] = []
    counts: list[int] = []
    error = 0.0
    total = max(1, len(probabilities))
    for index in range(bins):
        low, high = float(edges[index]), float(edges[index + 1])
        inside = (probabilities >= low) & (
            probabilities < high if index < bins - 1 else probabilities <= high
        )
        count = int(inside.sum())
        lower.append(low)
        upper.append(high)
        counts.append(count)
        if count == 0:
            predicted.append(math.nan)
            observed.append(math.nan)
            continue
        claimed = float(probabilities[inside].mean())
        happened = float(labels[inside].mean())
        predicted.append(claimed)
        observed.append(happened)
        error += (count / total) * abs(claimed - happened)
    return Reliability(
        bin_lower=tuple(lower),
        bin_upper=tuple(upper),
        predicted=tuple(predicted),
        observed=tuple(observed),
        counts=tuple(counts),
        expected_calibration_error=error,
    )


@dataclass
class _Isotonic:
    """Isotonic regression, fitted on the calibration fold. Section 6.3.

    scikit-learn's implementation where it is available, and the pool adjacent
    violators algorithm in a dozen lines where it is not. The fallback exists
    because the evidence pack has to regenerate on a clean checkout, and a
    calibration that silently became the identity would be the worst possible
    failure in the one place this product claims to be honest.
    """

    thresholds: np.ndarray = field(default_factory=lambda: np.zeros(0))
    values: np.ndarray = field(default_factory=lambda: np.zeros(0))
    fitted: bool = False

    def fit(self, scores: np.ndarray, labels: np.ndarray) -> _Isotonic:
        """Fit the mapping from raw score to observed frequency."""
        if scores.size == 0:
            return self
        order = np.argsort(scores, kind="stable")
        x = scores[order].astype(float)
        y = labels[order].astype(float)
        weights = np.ones_like(y)
        # Pool adjacent violators. Repeatedly merge any pair that runs downhill,
        # because a calibrated map cannot say a higher score means a lower rate.
        values = list(y)
        counts = list(weights)
        index = 0
        while index < len(values) - 1:
            if values[index] <= values[index + 1]:
                index += 1
                continue
            total = counts[index] + counts[index + 1]
            merged = (
                values[index] * counts[index] + values[index + 1] * counts[index + 1]
            ) / total
            values[index : index + 2] = [merged]
            counts[index : index + 2] = [total]
            index = max(0, index - 1)
        expanded: list[float] = []
        for value, count in zip(values, counts, strict=True):
            expanded.extend([value] * int(count))
        self.thresholds = x
        self.values = np.asarray(expanded[: x.size], dtype=float)
        self.fitted = True
        return self

    def apply(self, scores: np.ndarray) -> np.ndarray:
        """Map raw scores through the fitted calibration."""
        if not self.fitted or self.thresholds.size == 0:
            return scores
        positions = np.searchsorted(self.thresholds, scores, side="left")
        positions = np.clip(positions, 0, self.values.size - 1)
        return self.values[positions]


@dataclass
class GateModel:
    """One gate's calibrated classifier and the evidence for it."""

    gate_id: str
    model_version: str
    feature_names: tuple[str, ...]
    booster: object | None = None
    calibration: _Isotonic = field(default_factory=_Isotonic)
    reliability_holdout: Reliability | None = None
    base_rate: float = 0.0
    split_sizes: tuple[int, int, int] = (0, 0, 0)
    unavailable_reason: str | None = None
    # The fallback rate a model that could not be fitted reports for every unit.
    # It is the training fold's base rate, which is the only honest answer when
    # nothing has been learned.
    _fallback: float = 0.0

    @property
    def is_available(self) -> bool:
        """Whether this model may score anything at all."""
        return self.unavailable_reason is None

    @property
    def is_promotable(self) -> bool:
        """Whether its calibration lets it reach a screen. AC-024."""
        return (
            self.is_available
            and self.reliability_holdout is not None
            and self.reliability_holdout.is_calibrated
        )

    def predict(self, rows: tuple[FeatureRow, ...]) -> np.ndarray:
        """Calibrated failure probabilities, one per row."""
        if not rows:
            return np.zeros(0)
        if self.booster is None:
            return np.full(len(rows), self._fallback)
        frame = self.frame(rows)
        raw = np.asarray(self.booster.predict(frame))  # type: ignore[attr-defined]
        # Bound to the unit interval and named, because np.clip is untyped here
        # and returning it directly loses the array type at the boundary.
        clipped: np.ndarray = np.clip(self.calibration.apply(raw), 0.0, 1.0)
        return clipped

    def frame(self, rows: tuple[FeatureRow, ...]) -> object:
        """The rows as the booster wants them."""
        data: dict[str, list[object]] = {
            name: [row.values.get(name, math.nan) for row in rows]
            for name in self.feature_names
        }
        for name in CATEGORICAL:
            data[name] = [row.categories.get(name, "") for row in rows]
        frame = pd.DataFrame(data)
        for name in CATEGORICAL:
            frame[name] = frame[name].astype("category")
        return frame


def train_gate_model(
    gate_id: str,
    rows: tuple[FeatureRow, ...],
    feature_names: tuple[str, ...],
    model_version: str,
) -> GateModel:
    """Fit, calibrate and assess one gate's model. T-064, T-065.

    Returns a model that is `UNAVAILABLE` rather than one that is wrong, whenever
    the data cannot support one. A gate with eleven failures in its training fold
    has nothing to learn from and saying so is the correct output.
    """
    split = temporal_split(rows)
    model = GateModel(
        gate_id=gate_id,
        model_version=model_version,
        feature_names=feature_names,
        split_sizes=split.sizes,
    )
    if not split.train or not split.holdout:
        model.unavailable_reason = (
            f"{gate_id} has no labelled units on both sides of a temporal split "
            f"yet, so there is nothing to train on and nothing to test against"
        )
        return model

    labels = np.asarray(
        [1.0 if row.failed else 0.0 for row in split.train], dtype=float
    )
    model.base_rate = float(labels.mean())
    model._fallback = model.base_rate
    failures = int(labels.sum())
    if failures < MINIMUM_FAILURES:
        model.unavailable_reason = (
            f"{gate_id} has {failures} failures in its training fold, below the "
            f"{MINIMUM_FAILURES} a model needs. Every unit is scored at the "
            f"gate's base rate until there are more"
        )
        return model

    if lgb is None:
        model.unavailable_reason = (
            f"{gate_id}: LightGBM is not installed, so no defect model can be "
            f"fitted. Every other predictor continues"
        )
        return model

    positive = max(1.0, float(len(labels) - failures)) / max(1.0, float(failures))
    booster = lgb.LGBMClassifier(
        n_estimators=250,
        learning_rate=0.05,
        num_leaves=15,
        min_child_samples=20,
        # Class imbalance by weight rather than by resampling. Resampling
        # distorts the probabilities the calibration then has to correct.
        scale_pos_weight=positive,
        # Native handling of both. A missing value means a station was dark, and
        # imputing one would erase the fact (Section 6.2).
        verbose=-1,
        random_state=_stable_seed(gate_id),
        deterministic=True,
        force_col_wise=True,
    )
    frame = model.frame(split.train)
    booster.fit(frame, labels, categorical_feature=list(CATEGORICAL))
    model.booster = booster

    calibration_scores = np.asarray(
        booster.predict_proba(model.frame(split.calibrate))
    )[:, 1]
    calibration_labels = np.asarray(
        [1.0 if row.failed else 0.0 for row in split.calibrate], dtype=float
    )
    model.calibration = _Isotonic().fit(calibration_scores, calibration_labels)

    holdout_raw = np.asarray(booster.predict_proba(model.frame(split.holdout)))[:, 1]
    holdout_labels = np.asarray(
        [1.0 if row.failed else 0.0 for row in split.holdout], dtype=float
    )
    model.reliability_holdout = reliability(
        np.clip(model.calibration.apply(holdout_raw), 0.0, 1.0), holdout_labels
    )
    # `booster.predict` on a plain frame returns a class, so the model keeps the
    # probability path explicitly.
    model.booster = _Probability(booster)
    return model


@dataclass(frozen=True)
class _Probability:
    """Wraps a classifier so `predict` returns the failure probability."""

    inner: object

    def predict(self, frame: object) -> np.ndarray:
        """The probability of the positive class, one per row."""
        return np.asarray(self.inner.predict_proba(frame))[:, 1]  # type: ignore[attr-defined]

    def shap_source(self) -> object:
        """The underlying booster, which is what a tree explainer needs."""
        return self.inner


def _stable_seed(gate_id: str) -> int:
    """A seed for the booster derived from the gate rather than from the clock.

    Two runs of the same evaluation have to produce the same model (AC-103), and
    a library default that reads the system entropy would make that impossible.
    """
    return int(seed_for("defect", gate_id) % (2**31 - 1))
