"""Sensor value scoring and card generation. T-099, AC-050, AC-051.

TECHNICAL_SPEC.md Section 10. A blind spot on this line is not a fact to be
apologised for; it is a costed decision waiting to be taken, and this module is
what turns one into the other.

The reasoning, in order.

**Observability.** How well the twin can see one station today, in [0, 1]. Three
terms, weighted from the line's own `sensors` policy rather than from constants
here:

```
measured_share   what fraction of that station's reported values are MEASURED
interval_width   1 - (bound width / a plausible cycle range), clamped
signal_coverage  how many of the signals a prediction wants are present
```

A Tier A station scores near 1 and never generates a card. A Tier C station in a
resolvable span scores by how tight its bound is. A Tier C station in a span the
twin cannot separate at all scores zero on the middle term, because a bound that
does not exist is not a narrow one.

**Criticality.** How much that blindness costs, also in [0, 1]. Two terms, both
measured from what the line has actually done rather than assumed: the share of
forecast cycles in which this station was named the constraint, and the share of
units whose defect risk was scored with a gap in their signature at this
station.

**The gate.** A card is generated only where observability is below the line's
threshold and criticality is above it (AC-050). A station nobody can see and
nothing depends on does not need a sensor, and saying so is part of the
argument.

**The value.** Modelled annual value is an interval, never a point, and it is
`criticality x expected unit loss avoided x unit value`. `unit_value_usd`
defaults to zero in `config/lines/*.yaml`, so a plant that has not supplied its
own contribution margin sees a modelled value of zero rather than a number the
twin invented. That is deliberate and the card says so.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from datetime import datetime

from twin.config.catalogue import SensorCatalogue, SensorOption
from twin.config.line import LineDefinition
from twin.domain.estimate import Estimate, Interval
from twin.domain.signature import ProcessSignature
from twin.domain.state import LineState
from twin.state.virtual_sensors import DarkSpan, VirtualSensors

# How many working days a year the modelled annual value is spread over, and
# how many shifts a day. Both come from the line's own shift definitions where
# they can, and these are the fallbacks for a line that defines no shifts.
DAYS_PER_YEAR = 240

# The signals a prediction wants from a station. A station missing all of them
# scores zero on signal coverage. Present as a list here rather than in
# configuration because it describes what the twin's own models read, not
# anything about a plant.
WANTED_SIGNALS = ("cycle_time", "arrival", "departure", "process_value")


@dataclass(frozen=True)
class Observability:
    """How well the twin sees one station today, and why."""

    station_id: str
    score: float
    measured_share: float
    interval_score: float
    signal_coverage: float
    unknown: str
    basis: str


@dataclass(frozen=True)
class Criticality:
    """How much this station's blindness costs, measured rather than assumed."""

    station_id: str
    score: float
    critical_path_share: float
    defect_confidence_impact: float
    basis: str


@dataclass(frozen=True)
class SensorRecommendation:
    """One Sensor Value Card. AC-051.

    Every field the card renders is here, including the cost's own source
    string, because an indicative cost presented without saying it is indicative
    is the kind of number that ends up in a capital request unchallenged.
    """

    rec_id: str
    line_id: str
    station_id: str
    unknown: str
    option: SensorOption
    confidence_now: float
    confidence_projected: float
    confidence_projected_lo: float
    confidence_projected_hi: float
    observability: Observability
    criticality: Criticality
    modelled_annual_value: Estimate
    next_window: str
    status: str
    resolves: str
    cost_source: str

    @property
    def rank_key(self) -> float:
        """What the queue sorts on. Lossy, and never rendered as a number."""
        return self.modelled_annual_value.sort_key()


@dataclass
class SensorValueService:
    """Scores every station and generates the cards the gate lets through."""

    line: LineDefinition
    catalogue: SensorCatalogue

    def observability(
        self, state: LineState, sensors: VirtualSensors
    ) -> tuple[Observability, ...]:
        """Score every station's observability from what the twin has seen."""
        found: list[Observability] = []
        spans = {
            station_id: span
            for span in sensors.spans
            for station_id in span.dark_station_ids
        }
        for station in self.line.stations:
            snapshot = state.station(station.station_id)
            span = spans.get(station.station_id)
            found.append(self._observability(station.station_id, snapshot, span))
        return tuple(found)

    def _observability(
        self,
        station_id: str,
        snapshot: object,
        span: DarkSpan | None,
    ) -> Observability:
        """One station's observability, from its own snapshot and its span."""
        estimate = getattr(snapshot, "last_cycle", None)
        tier = getattr(snapshot, "tier", "A")
        provenance = estimate.provenance if estimate is not None else "INFERRED"
        measured_share = 1.0 if provenance == "MEASURED" else 0.0
        interval_score, unknown = self._interval_term(station_id, estimate, span)
        coverage = self._signal_coverage(tier)
        policy = self.line.sensors
        score = (
            policy.weight_measured_share * measured_share
            + policy.weight_interval_width * interval_score
            + policy.weight_signal_coverage * coverage
        )
        return Observability(
            station_id=station_id,
            score=_clamp(score),
            measured_share=measured_share,
            interval_score=interval_score,
            signal_coverage=coverage,
            unknown=unknown,
            basis=(
                f"{measured_share:.2f} measured, {interval_score:.2f} on bound "
                f"width, {coverage:.2f} on signal coverage"
            ),
        )

    def _interval_term(
        self, station_id: str, estimate: Estimate | None, span: DarkSpan | None
    ) -> tuple[float, str]:
        """How tight the station's bound is, and what remains unknown."""
        plausible = self.line.takt_s * self.line.state.max_plausible_cycle_takts
        if estimate is None:
            return 0.0, f"{station_id} has produced no cycle value yet."
        if estimate.provenance == "MEASURED":
            return 1.0, ""
        width = estimate.interval.width
        term = _clamp(1.0 - width / plausible) if plausible > 0 else 0.0
        if span is not None and not span.is_separable:
            # A bound that covers several stations at once is not a narrow bound
            # about one of them, whatever its width.
            term = 0.0
            return term, (
                f"{station_id} shares a bound with "
                f"{', '.join(s for s in span.dark_station_ids if s != station_id)}. "
                f"Its own cycle time cannot be separated: {span.unresolvable_reason()}."
            )
        return term, (
            f"{station_id} has no machine data. Cycle time is bounded to "
            f"{estimate.lo:.0f} to {estimate.hi:.0f} s from the stations either "
            f"side. Blocked, starved and slow work cannot be separated."
        )

    def _signal_coverage(self, tier: str) -> float:
        """What share of the signals a prediction wants this tier supplies."""
        if tier == "A":
            return 1.0
        if tier == "B":
            return 2.0 / len(WANTED_SIGNALS)
        return 0.0

    def criticality(
        self,
        constraint_counts: Counter[str],
        cycles: int,
        dark_visit_share: dict[str, float],
    ) -> tuple[Criticality, ...]:
        """Score how much each station's blindness costs the twin's answers."""
        found: list[Criticality] = []
        for station in self.line.stations:
            station_id = station.station_id
            named = constraint_counts.get(station_id, 0)
            share = named / cycles if cycles else 0.0
            impact = dark_visit_share.get(station_id, 0.0)
            score = _clamp(max(share, impact))
            found.append(
                Criticality(
                    station_id=station_id,
                    score=score,
                    critical_path_share=share,
                    defect_confidence_impact=impact,
                    basis=(
                        f"named the constraint in {named} of {cycles} forecast "
                        f"cycles; {impact:.2f} of scored units carry a gap here"
                    ),
                )
            )
        return tuple(found)

    def recommend(
        self,
        observability: tuple[Observability, ...],
        criticality: tuple[Criticality, ...],
        *,
        expected_unit_loss: float,
        at: datetime,
    ) -> tuple[SensorRecommendation, ...]:
        """Generate a card for every station the gate lets through. AC-050."""
        policy = self.line.sensors
        by_station = {item.station_id: item for item in criticality}
        tiers = {s.station_id: s.tier for s in self.line.stations}
        manual = {s.station_id: s.is_manual for s in self.line.stations}
        found: list[SensorRecommendation] = []
        for seen in observability:
            crit = by_station.get(seen.station_id)
            if crit is None:
                continue
            if seen.score >= policy.observability_threshold:
                continue
            if crit.score <= policy.criticality_threshold:
                continue
            option = self._best_option(
                tiers.get(seen.station_id, "A"),
                is_manual=manual.get(seen.station_id, False),
            )
            if option is None:
                continue
            found.append(self._card(seen, crit, option, expected_unit_loss, at))
        return tuple(sorted(found, key=lambda item: -item.rank_key))

    def _best_option(self, tier: str, *, is_manual: bool) -> SensorOption | None:
        """The catalogue entry that resolves the most for the least money."""
        applicable = [
            option
            for option in self.catalogue.options
            if tier in option.applicable_to
            and (option.applies_to_manual if is_manual else option.applies_to_automated)
        ]
        if not applicable:
            return None
        return max(
            applicable,
            key=lambda option: (
                option.confidence_model.projected_confidence
                / max(1.0, option.indicative_cost_usd)
            ),
        )

    def _card(
        self,
        seen: Observability,
        crit: Criticality,
        option: SensorOption,
        expected_unit_loss: float,
        at: datetime,
    ) -> SensorRecommendation:
        """One card, with its modelled value as an interval."""
        model = option.confidence_model
        margin = model.projected_confidence_margin
        unit_value = self.line.sensors.unit_value_usd
        gain = max(0.0, model.projected_confidence - seen.score)
        annual_units = expected_unit_loss * DAYS_PER_YEAR
        centre = crit.score * gain * annual_units * unit_value
        interval = Interval(max(0.0, centre * 0.4), centre * 1.8)
        basis = (
            f"criticality {crit.score:.2f} times a confidence gain of {gain:.2f} "
            f"times {annual_units:.0f} units a year at "
            f"{unit_value:.0f} {self.catalogue.currency} a unit"
        )
        if unit_value <= 0.0:
            basis = (
                f"{basis}. The unit value is zero until the plant supplies its "
                f"own contribution margin, so this is a modelled shape rather "
                f"than a modelled amount"
            )
        return SensorRecommendation(
            rec_id=f"{self.line.line_id}:{seen.station_id}:{option.option_id}",
            line_id=self.line.line_id,
            station_id=seen.station_id,
            unknown=seen.unknown,
            option=option,
            confidence_now=seen.score,
            confidence_projected=model.projected_confidence,
            confidence_projected_lo=_clamp(model.projected_confidence - margin),
            confidence_projected_hi=_clamp(model.projected_confidence + margin),
            observability=seen,
            criticality=crit,
            modelled_annual_value=Estimate.derived(
                interval, basis, confidence=0.5 if unit_value > 0 else 0.2
            ),
            next_window=_next_window(at, requires_window=option.requires_window),
            status="OPEN",
            resolves=model.resolves,
            cost_source=option.source,
        )


def dark_visit_share(signatures: tuple[ProcessSignature, ...]) -> dict[str, float]:
    """What share of scored units carry an inferred visit at each station.

    This is the defect side of criticality: a unit whose signature has a gap at
    a station was scored with a feature the model could not read, and the more
    units that describes, the more a sensor there is worth.
    """
    total = len(signatures)
    if total == 0:
        return {}
    counts: Counter[str] = Counter()
    for signature in signatures:
        for visit in signature.visits:
            estimate = visit.cycle_time
            if estimate is not None and estimate.provenance != "MEASURED":
                counts[visit.station_id] += 1
    return {station: count / total for station, count in counts.items()}


def _next_window(at: datetime, *, requires_window: bool) -> str:
    """When this could be fitted, in the plant's own words."""
    if not requires_window:
        return "no window needed, fitted while running"
    return f"next planned maintenance window after {at:%d %b}"


def _clamp(value: float) -> float:
    """A score held inside [0, 1], with a non-finite value read as zero."""
    if not math.isfinite(value):
        return 0.0
    return max(0.0, min(1.0, value))
