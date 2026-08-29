"""The LineDefinition.

Everything plant-specific lives here and arrives from YAML. No station
identifier, buffer capacity, threshold or tag name appears in code, and a test
asserts it (AC-080). Onboarding a second line is two files, not a branch.

The field names match the YAML keys in TECHNICAL_SPEC.md Section 12. Where a key
would shadow a Python builtin, the YAML keeps its short key and the attribute is
named for what it holds.
"""

from __future__ import annotations

from datetime import time
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

Tier = Literal["A", "B", "C"]

# A rework loop that leaves the line, for example to a repair yard. Modelled as
# a destination rather than as a station, because the unit stops being the
# twin's business once it is off the line.
OFF_LINE = "off_line"

Probability = Annotated[float, Field(ge=0.0, le=1.0)]
PositiveSeconds = Annotated[float, Field(gt=0.0)]

# Shares are written as decimals in YAML and compared after a float sum, so an
# exact equality would fail on 0.55 + 0.30 + 0.15.
SHARE_TOLERANCE = 1e-6


class Strict(BaseModel):
    """Base for every configuration model.

    Unknown keys are an error rather than a shrug: a typo in a line definition
    that silently does nothing is a plant misconfigured without anyone knowing.
    """

    model_config = ConfigDict(
        extra="forbid", populate_by_name=True, frozen=True, str_strip_whitespace=True
    )


class ShiftDefinition(Strict):
    """One shift pattern."""

    shift_id: str = Field(alias="id", min_length=1)
    start: time
    end: time
    break_min: int = Field(ge=0, le=120)
    # Time between one shift handing over to the next. The line does not run
    # during it, and the active period accumulator resets across it.
    changeover_min: int = Field(default=0, ge=0, le=120)


class ZoneDefinition(Strict):
    """A contiguous run of stations that shares an environment and a gate."""

    zone_id: str = Field(alias="id", min_length=1)
    name: str = Field(min_length=1)
    # First and last station of the zone, inclusive.
    span: tuple[str, str] = Field(alias="stations")


class StationDefinition(Strict):
    """One station, its observability tier, and its transport to the next."""

    station_id: str = Field(alias="id", min_length=1)
    tier: Tier
    # Nominal seconds from this station to the next. Null on the last station.
    transport_to_next_s: float | None = Field(default=None, ge=0.0)
    # Whether a second pair of hands changes the cycle time here, which is what
    # the counterfactual operator model needs to know.
    is_manual: bool = False


class BufferDefinition(Strict):
    """An inter-station buffer and how many units it holds."""

    buffer_id: str = Field(alias="id", min_length=1)
    after: str = Field(min_length=1)
    capacity: int = Field(ge=1)


class GateDefinition(Strict):
    """An inspection gate and the defect classes it catches."""

    gate_id: str = Field(alias="id", min_length=1)
    after: str = Field(min_length=1)
    name: str = Field(min_length=1)
    catches: tuple[str, ...] = ()


class ReworkLoop(Strict):
    """Where a unit goes when a gate fails it."""

    origin: str = Field(alias="from", min_length=1)
    destination: str = Field(alias="to", min_length=1)


class IngestPolicy(Strict):
    """Reordering, clock skew and source health. TECHNICAL_SPEC.md Section 3."""

    reorder_window_s: float = Field(default=30.0, gt=0.0)
    # Skew is reported, never silently corrected: a correction applied to a
    # genuinely slow station would hide the thing we are looking for.
    skew_warn_s: float = Field(default=2.0, gt=0.0)
    source_gap_takts: int = Field(default=3, ge=1)


class StatePolicy(Strict):
    """Distribution fitting and the virtual sensors. Sections 4.2 and 4.3."""

    window_cycles: int = Field(default=200, ge=20)
    # Below this a station has no usable distribution and is excluded from the
    # forecast, with the interface saying how many cycles remain.
    min_cycles: int = Field(default=20, ge=2)
    # How far the real transport time may sit either side of the nominal one in
    # the line definition. This is the only reason a single dark station between
    # two instrumented ones still yields an interval rather than a point: the
    # twin does not know the transport exactly, and pretending it does would be
    # the first step towards presenting an inference as a reading.
    transport_tolerance: float = Field(default=0.15, gt=0.0, le=0.5)
    # The most a station could plausibly take, as a multiple of takt. It sets
    # how fast an individual bound widens when several dark stations share one
    # span, and it is a plant judgement rather than a constant.
    max_plausible_cycle_takts: float = Field(default=2.5, gt=1.0, le=10.0)
    # The lower bound on a dark span's work content comes from the fastest
    # comparable transit recently observed, which is the same reasoning
    # TECHNICAL_SPEC.md Section 11 uses for transport times: the quickest
    # observed passage is close to pure work. The slack is what buys the
    # coverage target, since a unit can be genuinely faster than any seen so far.
    free_flow_quantile: float = Field(default=0.01, gt=0.0, le=0.5)
    free_flow_slack: float = Field(default=0.10, ge=0.0, le=0.5)
    # A contiguous run of dark stations longer than this cannot be modelled at
    # all, and the twin says so rather than producing an interval so wide it is
    # meaningless (EC-18).
    max_dark_span: int = Field(default=6, ge=1)


class ForecastPolicy(Strict):
    """The discrete-event forecast. Section 5.1."""

    horizon_min: int = Field(default=120, ge=5)
    cadence_s: int = Field(default=120, ge=10)
    replications: int = Field(default=200, ge=1)
    # A stop is any station blocked or starved for longer than this.
    stall_threshold_s: float = Field(default=180.0, gt=0.0)
    stall_probability_threshold: Probability = 0.55
    budget_s: float = Field(default=20.0, gt=0.0)
    # The rolling window for average active period attribution. Section 5.2.
    attribution_window_min: int = Field(default=60, ge=5)


class DriftPolicy(Strict):
    """EWMA and CUSUM parameters. Section 5.3."""

    ewma_lambda: float = Field(default=0.2, gt=0.0, le=1.0)
    ewma_l: float = Field(default=3.0, alias="ewma_L", gt=0.0)
    cusum_k_sigma: float = Field(default=0.5, gt=0.0)
    cusum_h_sigma: float = Field(default=5.0, gt=0.0)
    # Requiring both charts to signal roughly halves the false positive rate at
    # a small cost in detection delay. Given what a false alarm costs on a floor,
    # that is the right trade.
    require_both: bool = True


class PromotionGate(Strict):
    """What a predictor must show before it can reach the floor."""

    min_predictions: int = Field(default=20, ge=1)
    min_precision: Probability = 0.70
    min_recall: Probability = 0.50


class DemotionGate(Strict):
    """What withdraws a predictor from the floor again."""

    min_predictions: int = Field(default=10, ge=1)
    max_precision: Probability = 0.55


class GatesPolicy(Strict):
    """Shadow mode, promotion and demotion. Section 9.3."""

    promotion: PromotionGate = PromotionGate()
    demotion: DemotionGate = DemotionGate()
    window_days: int = Field(default=14, ge=1)
    # After a demotion a predictor cannot be promoted again for this long, so a
    # borderline predictor does not oscillate on the floor.
    cooling_period_days: int = Field(default=7, ge=0)

    @model_validator(mode="after")
    def demotion_is_below_promotion(self) -> Self:
        """A predictor cannot be promotable and demotable at the same precision."""
        if self.demotion.max_precision >= self.promotion.min_precision:
            message = (
                f"demotion.max_precision ({self.demotion.max_precision}) must be "
                f"below promotion.min_precision ({self.promotion.min_precision}), "
                f"otherwise a predictor is promoted and demoted at once"
            )
            raise ValueError(message)
        return self


class CounterfactualPolicy(Strict):
    """How an intervention changes a station. Section 8."""

    # The effect of a second pair of hands is not universal, so both the default
    # and the per-station override are configuration.
    operator_add_cycle_scale: float = Field(default=0.88, gt=0.0, le=1.0)
    operator_add_variance_scale: float = Field(default=0.75, gt=0.0, le=1.0)
    station_overrides: dict[str, float] = Field(default_factory=dict)
    latency_budget_s: float = Field(default=5.0, gt=0.0)


class SensorPolicy(Strict):
    """Thresholds and weights for sensor value scoring. Section 10."""

    observability_threshold: Probability = 0.60
    criticality_threshold: Probability = 0.20
    weight_measured_share: float = Field(default=0.4, ge=0.0, le=1.0)
    weight_interval_width: float = Field(default=0.4, ge=0.0, le=1.0)
    weight_signal_coverage: float = Field(default=0.2, ge=0.0, le=1.0)
    target_confidence: Probability = 0.85
    unit_value_usd: float = Field(default=0.0, ge=0.0)

    @model_validator(mode="after")
    def weights_sum_to_one(self) -> Self:
        """The three observability weights are a mixture."""
        total = (
            self.weight_measured_share
            + self.weight_interval_width
            + self.weight_signal_coverage
        )
        if abs(total - 1.0) > SHARE_TOLERANCE:
            message = f"observability weights must sum to 1.0, they sum to {total}"
            raise ValueError(message)
        return self


class LineDefinition(Strict):
    """A complete line, described in one file. ONB-01."""

    line_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    takt_s: PositiveSeconds
    shifts: tuple[ShiftDefinition, ...] = Field(min_length=1)
    variants: tuple[str, ...] = Field(min_length=1)
    mix: dict[str, float]
    zones: tuple[ZoneDefinition, ...] = Field(min_length=1)
    stations: tuple[StationDefinition, ...] = Field(min_length=2)
    buffers: tuple[BufferDefinition, ...] = ()
    gates: tuple[GateDefinition, ...] = ()
    rework: tuple[ReworkLoop, ...] = ()
    ingest: IngestPolicy = IngestPolicy()
    state: StatePolicy = StatePolicy()
    forecast: ForecastPolicy = ForecastPolicy()
    drift: DriftPolicy = DriftPolicy()
    gates_policy: GatesPolicy = GatesPolicy()
    counterfactual: CounterfactualPolicy = CounterfactualPolicy()
    sensors: SensorPolicy = SensorPolicy()

    @property
    def station_ids(self) -> tuple[str, ...]:
        """Station identifiers in line order."""
        return tuple(station.station_id for station in self.stations)

    def station(self, station_id: str) -> StationDefinition:
        """One station by identifier."""
        for candidate in self.stations:
            if candidate.station_id == station_id:
                return candidate
        message = f"no station {station_id} on line {self.line_id}"
        raise KeyError(message)

    def sequence_of(self, station_id: str) -> int:
        """The 1-based position of a station in the line."""
        return self.station_ids.index(station_id) + 1

    def stations_of_tier(self, tier: Tier) -> tuple[str, ...]:
        """Every station at one observability tier."""
        return tuple(
            station.station_id for station in self.stations if station.tier == tier
        )

    @model_validator(mode="after")
    def stations_are_unique(self) -> Self:
        """Two stations cannot share an identifier."""
        seen: set[str] = set()
        for station in self.stations:
            if station.station_id in seen:
                message = f"stations: {station.station_id} appears more than once"
                raise ValueError(message)
            seen.add(station.station_id)
        return self

    @model_validator(mode="after")
    def last_station_has_no_transport(self) -> Self:
        """Transport to the next station is meaningless at the end of the line."""
        last = self.stations[-1]
        if last.transport_to_next_s is not None:
            message = (
                f"stations: {last.station_id} is the last station and cannot have "
                f"transport_to_next_s"
            )
            raise ValueError(message)
        for station in self.stations[:-1]:
            if station.transport_to_next_s is None:
                message = f"stations: {station.station_id} needs transport_to_next_s"
                raise ValueError(message)
        return self

    @model_validator(mode="after")
    def zones_cover_the_line_in_order(self) -> Self:
        """Every station belongs to exactly one zone, and zones do not interleave."""
        known = self.station_ids
        covered: list[str] = []
        for zone in self.zones:
            first, last = zone.span
            for end in (first, last):
                if end not in known:
                    message = f"zones.{zone.zone_id}: no station {end} on this line"
                    raise ValueError(message)
            start_index = known.index(first)
            end_index = known.index(last)
            if end_index < start_index:
                message = (
                    f"zones.{zone.zone_id}: {last} comes before {first} in the line"
                )
                raise ValueError(message)
            covered.extend(known[start_index : end_index + 1])
        if tuple(covered) != known:
            message = (
                "zones: must cover every station exactly once, in line order. "
                f"They cover {len(covered)} of {len(known)} stations"
            )
            raise ValueError(message)
        return self

    @model_validator(mode="after")
    def buffers_sit_between_stations(self) -> Self:
        """A buffer follows a station, and not the last one."""
        known = self.station_ids
        seen: set[str] = set()
        for item in self.buffers:
            if item.after not in known:
                message = f"buffers.{item.buffer_id}: no station {item.after}"
                raise ValueError(message)
            if item.after == known[-1]:
                message = (
                    f"buffers.{item.buffer_id}: {item.after} is the last station, "
                    f"so nothing accumulates after it"
                )
                raise ValueError(message)
            if item.buffer_id in seen:
                message = f"buffers: {item.buffer_id} appears more than once"
                raise ValueError(message)
            seen.add(item.buffer_id)
        return self

    @model_validator(mode="after")
    def gates_follow_a_station(self) -> Self:
        """A gate inspects what a station has just finished."""
        known = self.station_ids
        seen: set[str] = set()
        for item in self.gates:
            if item.after not in known:
                message = f"gates.{item.gate_id}: no station {item.after}"
                raise ValueError(message)
            if item.gate_id in seen:
                message = f"gates: {item.gate_id} appears more than once"
                raise ValueError(message)
            seen.add(item.gate_id)
        return self

    @model_validator(mode="after")
    def rework_loops_connect_known_points(self) -> Self:
        """A rework loop runs from a gate to a station, or off the line."""
        gate_ids = {item.gate_id for item in self.gates}
        known = set(self.station_ids)
        for loop in self.rework:
            if loop.origin not in gate_ids:
                message = f"rework: {loop.origin} is not a gate on this line"
                raise ValueError(message)
            if loop.destination not in known and loop.destination != OFF_LINE:
                message = (
                    f"rework: {loop.destination} is neither a station on this line "
                    f"nor {OFF_LINE}"
                )
                raise ValueError(message)
        return self

    @model_validator(mode="after")
    def mix_covers_the_variants(self) -> Self:
        """The scheduled mix names every variant and sums to one."""
        if set(self.mix) != set(self.variants):
            missing = sorted(set(self.variants) - set(self.mix))
            extra = sorted(set(self.mix) - set(self.variants))
            message = (
                f"mix: must name exactly the variants. Missing {missing}, "
                f"unexpected {extra}"
            )
            raise ValueError(message)
        total = sum(self.mix.values())
        if abs(total - 1.0) > SHARE_TOLERANCE:
            message = f"mix: shares must sum to 1.0, they sum to {total}"
            raise ValueError(message)
        return self
