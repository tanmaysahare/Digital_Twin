"""Plant-language factors from SHAP contributions. T-067.

TECHNICAL_SPEC.md Section 6.5, AC-022. The top three features by absolute
contribution, translated through a template registry.

**A feature without a template cannot be surfaced.** That is the whole point of
the registry and it is enforced here rather than in the interface: `factors`
returns only features it has a template for, so an untemplated feature cannot
reach a screen even if a later change forgets to check. It forces every
explainable factor to have been thought about in plant terms before anyone can
see it, and it is why no raw feature name appears anywhere in the interface.

**Three factors, not all of them.** A supervisor reading an at-risk unit between
two other jobs has time for three. A list of twenty ranked contributions is a
model diagnostic rather than an explanation, and it belongs in the evidence pack.

**A contribution is not a cause.** SHAP says how much a feature moved this
prediction relative to the model's base value. The templates are written to say
what was observed rather than what it did, which is why they read "torque at S12
ran 2.1 sigma low" and never "torque at S12 caused this".
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from twin.defect.features import PROCESS_SIGNALS, FeatureRow

# How many factors reach a screen. AC-022 asserts exactly three.
TOP_FACTORS = 3

# A per-station timing feature is named `cycle_z_<station>`, which is the
# prefix plus exactly two underscores. The aggregate that stands for them all
# is `cycle_z_max`, which has the same shape, so the template picks the
# station out by looking for the largest of the per-station scores.
_STATION_PREFIX = "cycle_z_"
_STATION_PARTS = 2

# Some SHAP versions return one array per class stacked on a third axis.
_THREE_DIMENSIONS = 3


@dataclass(frozen=True)
class Factor:
    """One thing about this unit, in the language of the plant."""

    feature: str
    label: str
    detail: str
    contribution: float


Template = Callable[[FeatureRow, float], tuple[str, str] | None]


def _cycle_z_max(row: FeatureRow, _: float) -> tuple[str, str] | None:
    value = row.values.get("cycle_z_max")
    if value is None or math.isnan(value) or abs(value) < 1.0:
        return None
    station = max(
        (
            (name, score)
            for name, score in row.values.items()
            if name.startswith(_STATION_PREFIX)
            and not math.isnan(score)
            and name.count("_") == _STATION_PARTS
        ),
        key=lambda item: abs(item[1]),
        default=None,
    )
    where = station[0].removeprefix("cycle_z_") if station else "a station"
    direction = "above" if value > 0 else "below"
    return (
        f"cycle time at {where} ran {abs(value):.1f} sigma {direction} normal",
        f"Measured against {where}'s own recent cycles for this variant.",
    )


def _dwell_total(row: FeatureRow, _: float) -> tuple[str, str] | None:
    value = row.values.get("blocked_s_total")
    if not value:
        return None
    return (
        f"this unit sat {value:.0f} s longer than the work took",
        "Time between a station finishing and the unit leaving it, added up "
        "across the stations this gate covers.",
    )


def _lot_rate(row: FeatureRow, _: float) -> tuple[str, str] | None:
    rate = row.values.get("lot_failure_rate_max")
    if rate is None or math.isnan(rate):
        return None
    lot_id = row.categories.get("first_lot") or "an unrecorded lot"
    seen = row.values.get("lot_units_seen", 0.0)
    return (
        f"part lot {lot_id}",
        f"{rate * 100:.1f} percent of the {seen:.0f} units from this lot that "
        f"have already reached {row.gate_id} failed it.",
    )


def _dark_visits(row: FeatureRow, _: float) -> tuple[str, str] | None:
    count = row.values.get("dark_visits")
    if not count:
        return None
    share = row.values.get("dark_share")
    portion = (
        f", which is {share * 100:.0f} percent of its route"
        if share is not None and not math.isnan(share)
        else ""
    )
    return (
        f"{count:.0f} stations on this unit's route have no machine data",
        f"Their cycle times are bounds rather than readings{portion}. The "
        f"prediction carries that uncertainty rather than assuming they were "
        f"normal.",
    )


def _interval_width(row: FeatureRow, _: float) -> tuple[str, str] | None:
    width = row.values.get("interval_width_mean")
    if width is None or math.isnan(width) or width <= 0:
        return None
    return (
        f"the inferred parts of this unit's route span {width:.0f} s of "
        f"uncertainty on average",
        "Wider bounds mean less was established about what happened to this "
        "unit, not that anything went wrong.",
    )


def _humidity(row: FeatureRow, _: float) -> tuple[str, str] | None:
    value = row.values.get("humidity_max")
    if value is None or math.isnan(value):
        return None
    return (
        f"zone humidity reached {value:.0f} percent while this unit was in it",
        "Recorded by the zone's own ambient logger during this unit's passage.",
    )


def _temperature(row: FeatureRow, _: float) -> tuple[str, str] | None:
    value = row.values.get("temperature_max")
    if value is None or math.isnan(value):
        return None
    return (
        f"zone temperature reached {value:.1f} C while this unit was in it",
        "Recorded by the zone's own ambient logger during this unit's passage.",
    )


def _rework(row: FeatureRow, _: float) -> tuple[str, str] | None:
    count = row.values.get("rework_visits")
    if not count:
        return None
    return (
        f"this unit has been through {count:.0f} station revisits already",
        "A unit that has already been reworked is more likely to be reworked again.",
    )


def _shift(row: FeatureRow, _: float) -> tuple[str, str] | None:
    shift_id = row.categories.get("shift_id")
    if not shift_id:
        return None
    minutes = row.values.get("minutes_into_shift")
    when = (
        f" {minutes:.0f} minutes into the shift"
        if minutes is not None and not math.isnan(minutes)
        else ""
    )
    return (
        f"built on shift {shift_id}",
        f"This unit was worked on{when}, by operator group "
        f"{row.categories.get('operator_group') or 'unrecorded'}.",
    )


def _variant(row: FeatureRow, _: float) -> tuple[str, str] | None:
    variant_id = row.categories.get("variant_id")
    if not variant_id:
        return None
    return (
        f"model variant {variant_id}",
        "Variants carry different work content, so the same station takes "
        "different times on each.",
    )


def _signal(name: str) -> Template:
    def template(row: FeatureRow, _: float) -> tuple[str, str] | None:
        value = row.values.get(f"{name}_max")
        if value is None or math.isnan(value):
            return None
        readable = name.replace("_", " ")
        return (
            f"{readable} peaked at {value:.2f} on this unit",
            "Measured at every tier A station this unit passed, against that "
            "station's own recent distribution.",
        )

    return template


# Every feature that may reach a screen, and how it reads in plant language. A
# feature absent from this registry cannot be surfaced, whatever its
# contribution (AC-022).
FACTOR_TEMPLATES: dict[str, Template] = {
    "cycle_z_max": _cycle_z_max,
    "cycle_z_sum_positive": _cycle_z_max,
    "cycle_z_above_2sigma": _cycle_z_max,
    "blocked_s_total": _dwell_total,
    "starved_s_total": _dwell_total,
    "lot_failure_rate_max": _lot_rate,
    "lot_failure_rate_mean": _lot_rate,
    "dark_visits": _dark_visits,
    "dark_share": _dark_visits,
    "tier_c_visits": _dark_visits,
    "interval_width_mean": _interval_width,
    "interval_width_max": _interval_width,
    "measured_share": _interval_width,
    "humidity_max": _humidity,
    "humidity_mean": _humidity,
    "temperature_max": _temperature,
    "temperature_mean": _temperature,
    "rework_visits": _rework,
    "shift_id": _shift,
    "operator_group": _shift,
    "minutes_into_shift": _shift,
    "variant_id": _variant,
    "variant_recent_share": _variant,
    **{f"{signal}_max": _signal(signal) for signal in PROCESS_SIGNALS},
    **{f"{signal}_mean": _signal(signal) for signal in PROCESS_SIGNALS},
}


class Explainer:
    """Turns one prediction into three things a supervisor can act on."""

    def __init__(self, model: object, feature_names: tuple[str, ...]) -> None:
        """Build a tree explainer over a fitted model, or none if SHAP is absent."""
        self._names = feature_names
        self._explainer: object | None = None
        source = getattr(model, "shap_source", None)
        if source is None:
            return
        try:
            import shap
        except ImportError:  # pragma: no cover - the dependency is declared
            return
        try:
            self._explainer = shap.TreeExplainer(source())
        except Exception:  # noqa: BLE001 - any SHAP failure degrades to no factors
            self._explainer = None

    @property
    def is_available(self) -> bool:
        """Whether contributions can be computed at all."""
        return self._explainer is not None

    def contributions(self, frame: object) -> np.ndarray:
        """SHAP values, one row per unit, one column per feature."""
        if self._explainer is None:
            return np.zeros((0, 0))
        values = self._explainer.shap_values(frame)  # type: ignore[attr-defined]
        if isinstance(values, list):
            # Two-class output. The positive class is the one being explained.
            values = values[-1]
        array = np.asarray(values)
        if array.ndim == _THREE_DIMENSIONS:
            array = array[:, :, -1]
        return array

    def factors(
        self, row: FeatureRow, contributions: np.ndarray, columns: tuple[str, ...]
    ) -> tuple[Factor, ...]:
        """The top three templated factors for one unit. AC-022.

        Features without a template are skipped rather than rendered, so the
        registry decides what can be seen and no raw feature name can escape.
        """
        ranked = sorted(
            zip(columns, contributions, strict=False),
            key=lambda item: -abs(float(item[1])),
        )
        found: list[Factor] = []
        used: set[str] = set()
        for name, value in ranked:
            if len(found) >= TOP_FACTORS:
                break
            template = FACTOR_TEMPLATES.get(name)
            if template is None:
                continue
            rendered = template(row, float(value))
            if rendered is None:
                continue
            label, detail = rendered
            if label in used:
                continue
            used.add(label)
            found.append(
                Factor(
                    feature=name,
                    label=label,
                    detail=detail,
                    contribution=float(value),
                )
            )
        return tuple(found)


def untemplated(feature_names: tuple[str, ...]) -> tuple[str, ...]:
    """Every feature that has no plant-language rendering.

    Not an error. Most of the per-station features are model inputs that are
    never shown on their own, and the aggregate that stands for them is. This
    exists so a test can assert that the features which *are* shown all have a
    template, and so that a reviewer can see the list rather than guess at it.
    """
    return tuple(name for name in feature_names if name not in FACTOR_TEMPLATES)
