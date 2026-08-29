"""Defect features, assembled from the process signature. T-063.

TECHNICAL_SPEC.md Section 6.1. One row per unit per candidate gate, built from
what the twin observed of that unit's route and from nothing else.

**Missingness is a feature, and no value is ever imputed.** A missing cycle time
at S34 does not mean an average cycle time at S34; it means no sensor watched
S34, and that is information about the unit rather than a hole to be filled. The
row therefore carries `NaN` where the twin has nothing, LightGBM handles the
absence natively (Section 6.2), and the observability group counts the absences
explicitly: how many dark stations this unit passed through, how wide the
inferred intervals on its route were, and how many stations of each tier it saw.
A unit that spent a third of its route where nothing is measured is a different
unit from one that did not, and the model is told so rather than left to work it
out (DEF-03).

**Nothing here can see the future.** The lot failure rate counts only units that
reached the gate before this one, and it is updated by `observe_gate_result` as
verdicts arrive in time order. A lot rate computed over the whole run would leak
the answer through every unit that shares a lot, and the model would score
beautifully in evaluation and uselessly in a plant.

**Every feature that can reach a screen has a plant-language template.** The
registry is in `explain.py`, and a feature without an entry cannot be surfaced
(AC-022). The rule lives there rather than here so that adding a feature is a
decision about the model and surfacing one is a decision about the interface.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from twin.config.line import LineDefinition
from twin.domain.shifts import ProductionCalendar
from twin.domain.signature import ProcessSignature, StationVisit
from twin.state.distributions import DistributionStore

# A station running this far from its baseline is worth counting separately, not
# merely averaging in. Two sigma is the conventional line and it is the one the
# interface's own language uses.
OUTLIER_SIGMA = 2.0

# The process signals a tier A station reports. Named here rather than in code
# elsewhere so that the feature set and the template registry cannot drift apart.
PROCESS_SIGNALS = (
    "torque_peak",
    "torque_angle",
    "motor_current",
    "vibration_rms",
    "dimensional",
)

CATEGORICAL = ("variant_id", "shift_id", "operator_group", "first_lot")


@dataclass(frozen=True)
class FeatureRow:
    """One unit's features for one gate, with the label where one exists."""

    unit_id: str
    gate_id: str
    at: datetime
    values: dict[str, float]
    categories: dict[str, str]
    # None while the unit has not reached the gate. The training set uses only
    # rows whose label exists, and the temporal split runs on `at`.
    failed: bool | None = None

    def as_dict(self) -> dict[str, object]:
        """Everything in one mapping, for building a frame."""
        return {**self.values, **self.categories}


@dataclass
class FeatureBuilder:
    """Builds one gate's feature rows from process signatures. T-063."""

    line: LineDefinition
    calendar: ProductionCalendar
    distributions: DistributionStore
    gate_id: str
    _lot_seen: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    _lot_failed: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    _variant_seen: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    _variant_total: int = 0

    @property
    def span(self) -> tuple[str, ...]:
        """The stations this gate is the first opportunity to catch.

        Everything since the previous gate. A gate cannot be informed by work
        that another gate has already inspected and passed.
        """
        order = self.line.station_ids
        start = 0
        for gate in self.line.gates:
            end = order.index(gate.after)
            if gate.gate_id == self.gate_id:
                return order[start : end + 1]
            start = end + 1
        message = f"no gate {self.gate_id} on line {self.line.line_id}"
        raise KeyError(message)

    def observe_gate_result(
        self, signature: ProcessSignature, gate_id: str, *, passed: bool
    ) -> None:
        """Take one verdict into the rolling lot rate, in time order.

        Called only after a row has been built for that unit, so a unit never
        contributes to the feature that scores it.
        """
        if gate_id != self.gate_id:
            return
        for lot_id in _lots(signature):
            self._lot_seen[lot_id] += 1
            if not passed:
                self._lot_failed[lot_id] += 1

    def observe_release(self, signature: ProcessSignature) -> None:
        """Take one unit into the recent variant mix."""
        self._variant_seen[signature.variant_id] += 1
        self._variant_total += 1

    def build(self, signature: ProcessSignature, at: datetime) -> FeatureRow:
        """One row for one unit, from what the twin knows about it now."""
        span = self.span
        visits = [visit for visit in signature.visits if visit.station_id in span]
        values: dict[str, float] = {}
        values.update(self._timing(signature, visits))
        values.update(self._process_values(visits))
        values.update(self._environment(visits))
        values.update(self._materials(signature))
        values.update(self._schedule(signature, at))
        values.update(self._rework(signature))
        values.update(self._observability(signature, visits))
        values.update(self._variant(signature))
        lots = _lots(signature)
        return FeatureRow(
            unit_id=signature.unit_id,
            gate_id=self.gate_id,
            at=at,
            values=values,
            categories={
                "variant_id": signature.variant_id or "",
                "shift_id": _first(visit.shift_id for visit in visits) or "",
                "operator_group": _first(visit.operator_group for visit in visits)
                or "",
                "first_lot": lots[0] if lots else "",
            },
        )

    # -- the groups -------------------------------------------------------

    def _timing(
        self, signature: ProcessSignature, visits: list[StationVisit]
    ) -> dict[str, float]:
        """Per station, and aggregated. TECHNICAL_SPEC.md Section 6.1."""
        values: dict[str, float] = {}
        scores: list[float] = []
        for station_id in self.span:
            visit = next(
                (item for item in reversed(visits) if item.station_id == station_id),
                None,
            )
            score = self._z(station_id, signature.variant_id, visit)
            values[f"cycle_z_{station_id}"] = score
            values[f"dwell_s_{station_id}"] = (
                visit.dwell_s
                if visit is not None and visit.dwell_s is not None
                else math.nan
            )
            if not math.isnan(score):
                scores.append(score)
        positive = [score for score in scores if score > 0]
        values["cycle_z_max"] = max(scores) if scores else math.nan
        values["cycle_z_sum_positive"] = sum(positive) if positive else 0.0
        values["cycle_z_above_2sigma"] = float(
            sum(1 for score in scores if score > OUTLIER_SIGMA)
        )
        values["blocked_s_total"] = sum(
            visit.blocked_s.hi for visit in visits if visit.blocked_s is not None
        )
        values["starved_s_total"] = sum(
            visit.starved_s.hi for visit in visits if visit.starved_s is not None
        )
        return values

    def _z(self, station_id: str, variant_id: str, visit: StationVisit | None) -> float:
        """How far a visit's cycle sat from the station's own baseline.

        `NaN` where the station is dark, where the unit did not visit it, or
        where the baseline has too few cycles to mean anything. All three are the
        absence of evidence and none of them is a zero.
        """
        if visit is None or visit.cycle_time is None:
            return math.nan
        if visit.cycle_time.provenance != "MEASURED":
            return math.nan
        distribution = self.distributions.get(station_id, variant_id)
        if distribution is None or not distribution.is_usable:
            return math.nan
        return distribution.z(visit.cycle_time.point)

    def _process_values(self, visits: list[StationVisit]) -> dict[str, float]:
        """Residuals against each signal's own recent behaviour."""
        values: dict[str, float] = {}
        for signal in PROCESS_SIGNALS:
            observed = [
                visit.process_values[signal]
                for visit in visits
                if signal in visit.process_values
            ]
            if not observed:
                values[f"{signal}_max"] = math.nan
                values[f"{signal}_mean"] = math.nan
                values[f"{signal}_count"] = 0.0
                continue
            values[f"{signal}_max"] = max(observed)
            values[f"{signal}_mean"] = sum(observed) / len(observed)
            values[f"{signal}_count"] = float(len(observed))
        return values

    def _environment(self, visits: list[StationVisit]) -> dict[str, float]:
        """What the air was doing while this unit was in the zone."""
        humidity = [
            visit.environment["humidity_pct"]
            for visit in visits
            if "humidity_pct" in visit.environment
        ]
        temperature = [
            visit.environment["temperature_c"]
            for visit in visits
            if "temperature_c" in visit.environment
        ]
        return {
            "humidity_max": max(humidity) if humidity else math.nan,
            "humidity_mean": (sum(humidity) / len(humidity) if humidity else math.nan),
            "temperature_max": max(temperature) if temperature else math.nan,
            "temperature_mean": (
                sum(temperature) / len(temperature) if temperature else math.nan
            ),
        }

    def _materials(self, signature: ProcessSignature) -> dict[str, float]:
        """The lots this unit consumed, and how those lots have been doing.

        The rate counts only units that reached this gate before this one. A rate
        computed over the whole run would leak the answer through every unit that
        shares a lot.
        """
        lots = _lots(signature)
        rates = [
            self._lot_failed[lot_id] / self._lot_seen[lot_id]
            for lot_id in lots
            if self._lot_seen[lot_id] > 0
        ]
        return {
            "lot_count": float(len(lots)),
            "lot_failure_rate_max": max(rates) if rates else math.nan,
            "lot_failure_rate_mean": (sum(rates) / len(rates) if rates else math.nan),
            "lot_units_seen": float(
                max((self._lot_seen[lot_id] for lot_id in lots), default=0)
            ),
        }

    def _schedule(self, signature: ProcessSignature, at: datetime) -> dict[str, float]:
        """Where in the shift this unit was built."""
        epoch = self.calendar.epoch
        at_s = (at - epoch).total_seconds()
        window = self.calendar.window_at(at_s)
        return {
            "minutes_into_shift": (
                (at_s - window.start_s) / 60.0 if window is not None else math.nan
            ),
            "minutes_left_in_shift": (
                (window.end_s - at_s) / 60.0 if window is not None else math.nan
            ),
            "route_minutes": ((at - signature.entered_at).total_seconds() / 60.0),
        }

    def _rework(self, signature: ProcessSignature) -> dict[str, float]:
        """How many times this unit has been round already, and from where."""
        counts: dict[str, int] = defaultdict(int)
        for visit in signature.visits:
            counts[visit.station_id] += 1
        repeats = sum(count - 1 for count in counts.values() if count > 1)
        return {
            "rework_visits": float(repeats),
            "distinct_stations": float(len(counts)),
            "total_visits": float(len(signature.visits)),
        }

    def _observability(
        self, signature: ProcessSignature, visits: list[StationVisit]
    ) -> dict[str, float]:
        """How much of this unit's route nothing watched. DEF-03, AC-025."""
        tiers = {station.station_id: station.tier for station in self.line.stations}
        per_tier: dict[str, int] = defaultdict(int)
        widths: list[float] = []
        for visit in visits:
            per_tier[tiers.get(visit.station_id, "C")] += 1
            if (
                visit.cycle_time is not None
                and visit.cycle_time.provenance == "INFERRED"
            ):
                widths.append(visit.cycle_time.interval.width)
        dark = signature.dark_visits()
        return {
            "dark_visits": float(len(dark)),
            "dark_share": (
                len(dark) / len(signature.visits) if signature.visits else math.nan
            ),
            "inferred_dwell_s": signature.inferred_dwell_s(),
            "interval_width_mean": (sum(widths) / len(widths) if widths else math.nan),
            "interval_width_max": max(widths) if widths else math.nan,
            "tier_a_visits": float(per_tier["A"]),
            "tier_b_visits": float(per_tier["B"]),
            "tier_c_visits": float(per_tier["C"]),
            "measured_share": (
                sum(1 for visit in visits if visit.is_measured) / len(visits)
                if visits
                else math.nan
            ),
        }

    def _variant(self, signature: ProcessSignature) -> dict[str, float]:
        """This variant's share of what the line has been building lately."""
        seen = self._variant_seen.get(signature.variant_id, 0)
        return {
            "variant_recent_share": (
                seen / self._variant_total if self._variant_total else math.nan
            )
        }


def feature_names(builder: FeatureBuilder) -> tuple[str, ...]:
    """Every numeric feature one builder produces, in a stable order.

    Derived from the line rather than listed, because the per-station features
    depend on how many stations the gate covers, and a hard-coded list would be a
    plant-specific value in code (CLAUDE.md rule 5).
    """
    names: list[str] = []
    for station_id in builder.span:
        names.extend((f"cycle_z_{station_id}", f"dwell_s_{station_id}"))
    names.extend(
        (
            "cycle_z_max",
            "cycle_z_sum_positive",
            "cycle_z_above_2sigma",
            "blocked_s_total",
            "starved_s_total",
        )
    )
    for signal in PROCESS_SIGNALS:
        names.extend((f"{signal}_max", f"{signal}_mean", f"{signal}_count"))
    names.extend(
        (
            "humidity_max",
            "humidity_mean",
            "temperature_max",
            "temperature_mean",
            "lot_count",
            "lot_failure_rate_max",
            "lot_failure_rate_mean",
            "lot_units_seen",
            "minutes_into_shift",
            "minutes_left_in_shift",
            "route_minutes",
            "rework_visits",
            "distinct_stations",
            "total_visits",
            "dark_visits",
            "dark_share",
            "inferred_dwell_s",
            "interval_width_mean",
            "interval_width_max",
            "tier_a_visits",
            "tier_b_visits",
            "tier_c_visits",
            "measured_share",
            "variant_recent_share",
        )
    )
    return tuple(names)


def _lots(signature: ProcessSignature) -> tuple[str, ...]:
    """Every part lot this unit consumed, in the order it consumed them."""
    found: list[str] = []
    for visit in signature.visits:
        for lot_id in visit.part_lots:
            if lot_id not in found:
                found.append(lot_id)
    return tuple(found)


def _first(values: object) -> str | None:
    """The first value that is not empty, or None."""
    for value in values:  # type: ignore[attr-defined]
        if value:
            return str(value)
    return None
