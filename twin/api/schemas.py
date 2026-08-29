"""The response shapes. API_SPEC.md Sections 1 to 8.

One rule generates most of this file: **there is no bare number in any
response**. Every quantity the twin produces about the line leaves as an
`EstimateOut`, carrying its bounds, its provenance and the one line of basis a
supervisor reads beside it. A client cannot render a value without knowing where
it came from, because the wire format does not offer one.

The second rule is the shadow-mode guarantee, and it is expressed here as much
as in the routes: `ActionOut` exists only for published predictions, and
`ScorecardRowOut.precision` is optional so that a shadow row can decline to
answer. A client that trusted itself to filter would be a client one bug away
from putting an unpromoted forecast on a wall.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from twin.domain.estimate import Estimate


class EstimateOut(BaseModel):
    """A quantity, its bounds, and where it came from. API_SPEC.md Section 1."""

    lo: float
    hi: float
    point: float | None
    unit: str | None
    provenance: Literal["MEASURED", "DERIVED", "INFERRED"]
    resolution: Literal["RESOLVED", "UNRESOLVED"]
    confidence: float
    basis: str

    @classmethod
    def of(cls, estimate: Estimate, unit: str | None = None) -> EstimateOut:
        """Wire form of one estimate. `point` is present only for a measurement."""
        return cls(
            lo=estimate.lo,
            hi=estimate.hi,
            point=estimate.lo if estimate.provenance == "MEASURED" else None,
            unit=unit,
            provenance=estimate.provenance,
            resolution=estimate.resolution,
            confidence=estimate.confidence,
            basis=estimate.basis,
        )


class RangeOut(BaseModel):
    """A plain range with no provenance: a normal band, not an estimate."""

    lo: float
    hi: float
    unit: str | None = None


class WindowOut(BaseModel):
    """A time window, always with both ends."""

    from_at: datetime = Field(serialization_alias="from")
    to_at: datetime = Field(serialization_alias="to")

    model_config = {"populate_by_name": True}


class LineSummaryOut(BaseModel):
    """One configured line, as `/lines` lists it."""

    line_id: str
    name: str
    takt_s: float
    stations: int
    tiers: dict[str, int]
    config_version: str
    zones: list[ZoneOut]
    gates: list[GateOut]


class ZoneOut(BaseModel):
    """One zone and the stations it covers."""

    zone_id: str
    name: str
    from_station_id: str
    to_station_id: str


class GateOut(BaseModel):
    """One inspection gate and the station it stands after."""

    gate_id: str
    name: str
    after_station_id: str


class LinesOut(BaseModel):
    """Every configured line."""

    lines: list[LineSummaryOut]


class StationOut(BaseModel):
    """One station in the live state."""

    station_id: str
    seq: int
    zone_id: str
    tier: Literal["A", "B", "C"]
    state: str
    since: datetime
    current_unit_id: str | None
    cycle_time: EstimateOut | None
    normal_range: RangeOut | None
    observed_cycles: int
    flags: list[str]
    basis: str


class BufferOut(BaseModel):
    """One buffer's occupancy against its capacity."""

    buffer_id: str
    after_station_id: str
    occupancy: EstimateOut
    capacity: int
    trend: str


class UnresolvedOut(BaseModel):
    """A station the twin cannot separate, and what would fix it."""

    station_id: str
    reason: str
    resolved_by: str


class ShiftOut(BaseModel):
    """Where the shift has got to against its target."""

    shift_id: str | None
    started_at: datetime | None
    target_units: int
    completed: int
    pace_delta_units: int
    pace_note: str


class DataHealthOut(BaseModel):
    """What the twin can and cannot see right now. UX_SPEC.md Section 2.7."""

    sources_live: int
    sources_total: int
    last_event_at: datetime | None
    max_skew_s: float
    stations_reporting: int
    stations_dark_by_design: int
    open_gaps: list[str]
    notes: list[str]


class ReplayOut(BaseModel):
    """What the replay behind the prototype is doing. Never hidden."""

    ready: bool
    warming: bool
    speed: float
    scenario_id: str
    seed: int
    events_total: int
    events_fed: int
    cycles: int
    behind_s: float
    finished: bool
    note: str


class LossOut(BaseModel):
    """The shift's lost minutes by cause, with what they do not explain."""

    minutes: dict[str, float]
    accounted_min: float
    implied_total_min: float
    unexplained_min: float
    unexplained_share: float
    reconciliation: str


class LineStateOut(BaseModel):
    """The complete live state. The single call that fills Line view."""

    line_id: str
    as_of: datetime
    age_s: float
    shift: ShiftOut
    stations: list[StationOut]
    buffers: list[BufferOut]
    unresolved: list[UnresolvedOut]
    loss_this_shift: LossOut
    data_health: DataHealthOut
    replay: ReplayOut


class CauseOut(BaseModel):
    """Which station a forecast blames, and how that was decided."""

    station_id: str | None
    description: str
    attribution: list[str]
    agreement: bool


class PredictorRecordOut(BaseModel):
    """One predictor's record, as an action card shows it."""

    state: str
    made: int
    hits: int | None
    precision: float | None
    median_lead_min: float | None
    required: int | None
    note: str


class ActionOut(BaseModel):
    """One published prediction, ranked. Shadow predictions never appear here."""

    prediction_id: str
    predictor: str
    kind: str
    station_id: str
    window: WindowOut
    probability: float
    lead_time_min: float
    cause: CauseOut
    expected_unit_loss: EstimateOut
    evidence_url: str
    predictor_record: PredictorRecordOut
    degraded: bool


class ActionsOut(BaseModel):
    """The ranked action list, and how many forecasts are held in shadow."""

    as_of: datetime
    actions: list[ActionOut]
    shadow_count: int
    stations_running: int
    calm_note: str
    learning_note: str


class FactorOut(BaseModel):
    """One reason a unit is at risk, in plant language."""

    label: str
    detail: str
    contribution: float


class UnitAtRiskOut(BaseModel):
    """One unit's risk at one gate."""

    unit_id: str
    current_station_id: str | None
    gate_id: str
    risk: EstimateOut
    stations_remaining: int
    minutes_remaining: float
    dark_visits: int
    factors: list[FactorOut]
    published: bool


class HighestBelowOut(BaseModel):
    """The highest risk under the threshold, so the calm state can measure."""

    unit_id: str
    current_station_id: str | None
    gate_id: str
    risk_point: float


class UnitsAtRiskOut(BaseModel):
    """The at-risk table, and the measurement behind an empty one."""

    as_of: datetime
    units: list[UnitAtRiskOut]
    threshold: float
    total: int
    highest_below_threshold: HighestBelowOut | None
    note: str


class BucketOut(BaseModel):
    """One five-minute bucket of the forecast."""

    index: int
    start_at: datetime
    end_at: datetime


class StationForecastOut(BaseModel):
    """One station's stall probability across the horizon."""

    station_id: str
    stall_probability: list[float]
    blocked_probability: list[float]
    starved_probability: list[float]
    mean_lost_s: list[float]


class BufferForecastOut(BaseModel):
    """One buffer's trajectory, as an interval per bucket."""

    buffer_id: str
    after_station_id: str
    capacity: int
    low: list[float]
    high: list[float]
    mean: list[float]


class ForecastOut(BaseModel):
    """The whole forecast. What the strip and the charts read."""

    line_id: str
    as_of: datetime
    horizon_min: float
    replications: int
    degraded: bool
    buckets: list[BucketOut]
    stations: list[StationForecastOut]
    buffers: list[BufferForecastOut]
    line_stall_probability: list[float]
    output: EstimateOut
    expected_unit_loss: EstimateOut
    fallback_stations: list[str]
    learning_stations: list[str]
    drifting_stations: list[str]
    learning_note: str
    runtime_s: float


class SeriesPointOut(BaseModel):
    """One point of a time series."""

    at: datetime
    value: float


class MarkerOut(BaseModel):
    """A labelled instant on a chart: a drift onset, a shift boundary."""

    at: datetime
    label: str


class EvidenceOut(BaseModel):
    """Everything behind one prediction. API_SPEC.md Section 3."""

    # `model_version` is the ledger's own field name and the one a plant
    # reads in an audit. Pydantic reserves the `model_` prefix by default;
    # renaming the field to satisfy that would rename it in the ledger too.
    model_config = ConfigDict(protected_namespaces=())

    prediction_id: str
    predictor: str
    model_version: str
    made_at: datetime
    horizon_end: datetime
    published: bool
    inputs_hash: str
    claim: dict[str, object]
    cause_station_id: str | None
    cycle_series: list[SeriesPointOut]
    normal_range: RangeOut | None
    markers: list[MarkerOut]
    buffer_series: list[SeriesPointOut]
    buffer_id: str | None
    attribution: list[AttributionRowOut]
    predictor_record: PredictorRecordOut
    notes: list[str]


class AttributionRowOut(BaseModel):
    """One station's average active period, which is the constraint evidence."""

    station_id: str
    average_active_s: float
    is_constraint: bool


class StationVisitOut(BaseModel):
    """One station a unit passed through."""

    station_id: str
    seq: int
    arrived_at: datetime | None
    departed_at: datetime | None
    dwell_s: float | None
    cycle_time: EstimateOut | None
    normal_range: RangeOut | None
    state_during: str
    outside_normal: bool
    part_lots: list[str]
    process_values: dict[str, float]


class GateResultOut(BaseModel):
    """A gate this unit has already been through."""

    gate_id: str
    at: datetime
    passed: bool


class UnitDetailOut(BaseModel):
    """The unit drawer. UX_SPEC.md Section 7."""

    unit_id: str
    line_id: str
    variant_id: str
    entered_at: datetime
    exited_at: datetime | None
    status: str
    current_station_id: str | None
    visits: list[StationVisitOut]
    gates: list[GateResultOut]
    risks: list[UnitAtRiskOut]
    part_lots: list[str]
    has_retro_trace: bool


class SensorCardOut(BaseModel):
    """One Sensor Value Card. AC-051."""

    rec_id: str
    station_id: str
    unknown: str
    option_id: str
    option_name: str
    signal_provided: str
    indicative_cost_usd: float
    cost_source: str
    install_hours: float
    requires_window: bool
    next_window: str
    confidence_now: float
    confidence_projected: float
    confidence_projected_lo: float
    confidence_projected_hi: float
    resolves: str
    criticality: float
    criticality_basis: str
    modelled_annual_value: EstimateOut
    status: str


class SensorRecommendationsOut(BaseModel):
    """The sensor investment queue, ranked."""

    line_id: str
    as_of: datetime
    recommendations: list[SensorCardOut]
    currency: str
    note: str


class RecentEventOut(BaseModel):
    """One thing that happened at a station, for the drawer's tail."""

    at: datetime
    kind: str
    detail: str


class StationDetailOut(BaseModel):
    """The station drawer. UX_SPEC.md Section 6."""

    station: StationOut
    zone_name: str
    time_in_state_s: float
    cycle_series: list[SeriesPointOut]
    normal_range: RangeOut | None
    markers: list[MarkerOut]
    knows: list[str]
    does_not_know: list[str]
    buffer_upstream: BufferOut | None
    buffer_downstream: BufferOut | None
    predictor_record: list[ScorecardRowOut]
    sensor_card: SensorCardOut | None
    recent_events: list[RecentEventOut]
    cycles_recorded: int
    cycles_required: int


class ScorecardRowOut(BaseModel):
    """One predictor at one station. A shadow row never carries a precision."""

    predictor: str
    station_id: str | None
    state: str
    made: int
    true_positive: int
    false_positive: int
    unscoreable: int
    missed: int
    precision: float | None
    recall: float | None
    median_lead_min: float | None
    false_per_shift: float | None
    required: int | None
    state_changed_at: datetime | None
    state_reason: str | None


class ScorecardOut(BaseModel):
    """Every predictor's record over the gate window."""

    line_id: str
    as_of: datetime
    window_days: int
    rows: list[ScorecardRowOut]
    totals: list[ScorecardRowOut]


class PredictionRowOut(BaseModel):
    """One ledger row, as the ledger query returns it."""

    prediction_id: str
    predictor: str
    station_id: str | None
    unit_id: str | None
    made_at: datetime
    horizon_end: datetime
    published: bool
    confidence: float
    claim: dict[str, object]
    result: str | None
    resolved_at: datetime | None


class PredictionsOut(BaseModel):
    """A page of the ledger."""

    line_id: str
    rows: list[PredictionRowOut]
    total: int
    offset: int
    limit: int


class InterventionIn(BaseModel):
    """One change to test in the sandbox."""

    type: Literal[
        "ADD_OPERATOR",
        "REMOVE_OPERATOR",
        "CHANGE_TAKT",
        "CHANGE_BUFFER_TARGET",
        "RESEQUENCE_MIX",
        "STATION_DOWN",
    ]
    station_id: str | None = None
    buffer_id: str | None = None
    count: int = 1
    percent: float = 0.0
    minutes: float = 0.0
    variant_order: list[str] = Field(default_factory=list)


class OptionIn(BaseModel):
    """One labelled option to compare against doing nothing."""

    label: str
    interventions: list[InterventionIn]


class CounterfactualIn(BaseModel):
    """A sandbox request. Nothing here is applied to anything."""

    options: list[OptionIn]
    replications: int | None = None
    budget_ms: int | None = None


class OptionResultOut(BaseModel):
    """One option's modelled outcome beside the baseline it was paired with."""

    label: str
    units: EstimateOut
    delta: EstimateOut
    stall_probability: dict[str, float]
    assumptions: list[str]
    rank: int


class CounterfactualOut(BaseModel):
    """The comparison, and everything the footer states. AC-031, AC-032."""

    run_id: str
    line_id: str
    seed_state_at: datetime
    horizon_min: float
    replications_used: int
    replications_requested: int
    runtime_ms: int
    degraded: bool
    degraded_note: str
    baseline_units: EstimateOut
    baseline_stall_probability: dict[str, float]
    options: list[OptionResultOut]
    footer: str


class DecisionIn(BaseModel):
    """A record that an option was chosen. It changes nothing on the line."""

    label: str
    note: str = ""


class DecisionOut(BaseModel):
    """What was recorded, and the plain statement that nothing was applied."""

    run_id: str
    label: str
    recorded_at: datetime
    note: str
    applied: bool = False
    statement: str = (
        "Recorded as a decision. Nothing was sent to the line: this product "
        "has no path to a control system."
    )


class HypothesisOut(BaseModel):
    """One station that looked different, and by how much."""

    rank: int
    station_id: str
    window: WindowOut
    divergence: float
    strength: str
    description: str
    shared_attribute: dict[str, str] | None
    population: int


class ContainedUnitOut(BaseModel):
    """One unit on the containment list, with its evidence."""

    unit_id: str
    similarity: float
    at: str
    evidence: list[str]


class RetroTraceOut(BaseModel):
    """The retro-trace. `disclaimer` is part of the contract, not decoration."""

    unit_id: str
    line_id: str
    failed_at_gate: str
    failed_at: datetime
    hypotheses: list[HypothesisOut]
    on_line: list[ContainedUnitOut]
    in_yard: list[ContainedUnitOut]
    shipped: list[ContainedUnitOut]
    counts: dict[str, int]
    runtime_s: float
    disclaimer: str


class ConstraintCellOut(BaseModel):
    """One station in one period of the constraint migration heatmap."""

    station_id: str
    period: str
    share: float


class ConstraintMigrationOut(BaseModel):
    """Which station has been holding the line back, over time. AC-060."""

    line_id: str
    periods: list[str]
    stations: list[str]
    cells: list[ConstraintCellOut]
    current_constraint: str | None
    note: str


class ParetoRowOut(BaseModel):
    """One cause in the loss Pareto."""

    cause: str
    minutes: float
    share: float


class LossParetoOut(BaseModel):
    """The loss Pareto with its mandatory reconciliation line. AC-061."""

    line_id: str
    from_at: datetime
    to_at: datetime
    rows: list[ParetoRowOut]
    reconciliation: str
    unexplained_min: float
    unexplained_share: float


class RecommendationOut(BaseModel):
    """One buffer or staffing change, with its modelled effect and assumptions."""

    rec_id: str
    change: str
    station_id: str | None
    buffer_id: str | None
    modelled_effect: EstimateOut
    assumptions: list[str]
    sandbox: OptionIn


class RecommendationsOut(BaseModel):
    """The Plan view recommendation table. AC-062."""

    line_id: str
    as_of: datetime
    rows: list[RecommendationOut]
    note: str


class ReadinessComponentOut(BaseModel):
    """One scored component of a site's readiness."""

    name: str
    value: str
    score: float
    weight: float
    missing: str


class SiteReadinessOut(BaseModel):
    """One site, its band, and exactly what is missing. AC-070."""

    site_id: str
    name: str
    band: str
    score: float
    components: list[ReadinessComponentOut]
    missing: list[str]
    instrumentation_cost_usd: float
    note: str


class SitesOut(BaseModel):
    """Every site the programme covers."""

    sites: list[SiteReadinessOut]
    computed_from: str


class AssumptionOut(BaseModel):
    """One business case assumption, with its source and its uncertainty."""

    key: str
    label: str
    value: float
    unit: str
    source: str
    uncertainty: str
    editable: bool


class SensitivityRowOut(BaseModel):
    """How much the result moves when one assumption moves."""

    key: str
    label: str
    low_result: float
    high_result: float
    swing: float


class BusinessCaseOut(BaseModel):
    """The modelled case, and what it is most sensitive to. AC-071."""

    scenario_id: str
    assumptions: list[AssumptionOut]
    annual_benefit: EstimateOut
    payback_months: float | None
    sensitivity: list[SensitivityRowOut]
    notes: list[str]


class BusinessCaseIn(BaseModel):
    """Edited assumptions. Not persisted globally."""

    values: dict[str, float]


class RealisedRowOut(BaseModel):
    """Modelled against realised for one measure at one site."""

    site_id: str
    measure: str
    modelled: float
    realised: float | None
    gap: float | None
    unit: str
    evidence: str


class RealisedOut(BaseModel):
    """Modelled against realised. Renders correctly with a negative gap."""

    rows: list[RealisedRowOut]
    note: str


class TopologyFieldOut(BaseModel):
    """One inferred field of a line definition draft, with its confidence."""

    field: str
    value: str | None
    confidence: float | None
    inferred_from: str
    note: str


class TopologyDraftOut(BaseModel):
    """A LineDefinition draft from a stream. Blank where nothing was inferable."""

    line_id: str
    observed_events: int
    fields: list[TopologyFieldOut]
    stations: list[TopologyFieldOut]
    not_inferable: list[str]
    note: str


class HealthOut(BaseModel):
    """Service health. API_SPEC.md Section 10."""

    status: str
    service: str
    twin: str
    worker_last_cycle_at: datetime | None
    cycle_lag_s: float | None


class NoticeOut(BaseModel):
    """One thing the interface has to say and keep saying."""

    tone: Literal["neutral", "attention"]
    text: str
    detail: str = ""


class SocketMessageOut(BaseModel):
    """The WebSocket envelope. API_SPEC.md Section 9."""

    type: Literal[
        "STATE",
        "ACTIONS",
        "UNITS_AT_RISK",
        "HEALTH",
        "SCORECARD",
        "NOTICE",
        "HEARTBEAT",
    ]
    as_of: datetime
    seq: int
    payload: dict[str, object]


LineSummaryOut.model_rebuild()
EvidenceOut.model_rebuild()
StationDetailOut.model_rebuild()
