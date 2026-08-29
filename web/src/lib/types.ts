// The wire shapes, mirroring twin/api/schemas.py.
//
// Written by hand rather than generated, because the generator would produce a
// bare `number` wherever the API returns an Estimate and the whole point of the
// Estimate shape is that a value cannot be rendered without its provenance. The
// types here keep that: a `Estimate` has no `value` field, only bounds, and
// `point` is null unless the value was measured.

export type Provenance = 'MEASURED' | 'DERIVED' | 'INFERRED';
export type Resolution = 'RESOLVED' | 'UNRESOLVED';
export type Tier = 'A' | 'B' | 'C';

export interface Estimate {
  lo: number;
  hi: number;
  point: number | null;
  unit: string | null;
  provenance: Provenance;
  resolution: Resolution;
  confidence: number;
  basis: string;
}

export interface Range {
  lo: number;
  hi: number;
  unit: string | null;
}

export interface Window {
  from: string;
  to: string;
}

export interface Zone {
  zone_id: string;
  name: string;
  from_station_id: string;
  to_station_id: string;
}

export interface Gate {
  gate_id: string;
  name: string;
  after_station_id: string;
}

export interface LineSummary {
  line_id: string;
  name: string;
  takt_s: number;
  stations: number;
  tiers: Record<string, number>;
  config_version: string;
  zones: Zone[];
  gates: Gate[];
}

export interface Station {
  station_id: string;
  seq: number;
  zone_id: string;
  tier: Tier;
  state: string;
  since: string;
  current_unit_id: string | null;
  cycle_time: Estimate | null;
  normal_range: Range | null;
  observed_cycles: number;
  lost_s: number;
  losing: boolean;
  flags: string[];
  basis: string;
}

export interface Buffer {
  buffer_id: string;
  after_station_id: string;
  occupancy: Estimate;
  capacity: number;
  trend: string;
}

export interface Unresolved {
  station_id: string;
  reason: string;
  resolved_by: string;
}

export interface Shift {
  shift_id: string | null;
  started_at: string | null;
  target_units: number;
  completed: number;
  pace_delta_units: number;
  pace_note: string;
}

export interface DataHealth {
  sources_live: number;
  sources_total: number;
  last_event_at: string | null;
  max_skew_s: number;
  stations_reporting: number;
  stations_dark_by_design: number;
  open_gaps: string[];
  notes: string[];
}

export interface Replay {
  ready: boolean;
  warming: boolean;
  speed: number;
  scenario_id: string;
  seed: number;
  events_total: number;
  events_fed: number;
  cycles: number;
  behind_s: number;
  finished: boolean;
  note: string;
}

export interface Loss {
  minutes: Record<string, number>;
  accounted_min: number;
  implied_total_min: number;
  available_min: number;
  unexplained_min: number;
  unexplained_share: number;
  reconciliation: string;
}

export interface LineState {
  line_id: string;
  as_of: string;
  age_s: number;
  shift: Shift;
  stations: Station[];
  buffers: Buffer[];
  unresolved: Unresolved[];
  loss_this_shift: Loss;
  data_health: DataHealth;
  replay: Replay;
}

export interface PredictorRecord {
  state: string;
  made: number;
  hits: number | null;
  precision: number | null;
  median_lead_min: number | null;
  required: number | null;
  note: string;
}

export interface Cause {
  station_id: string | null;
  description: string;
  attribution: string[];
  agreement: boolean;
}

export interface Action {
  prediction_id: string;
  predictor: string;
  kind: string;
  station_id: string;
  window: Window;
  probability: number;
  lead_time_min: number;
  cause: Cause;
  expected_unit_loss: Estimate;
  evidence_url: string;
  predictor_record: PredictorRecord;
  degraded: boolean;
}

export interface Actions {
  as_of: string;
  actions: Action[];
  shadow_count: number;
  stations_running: number;
  calm_note: string;
  learning_note: string;
}

export interface Factor {
  label: string;
  detail: string;
  contribution: number;
}

export interface UnitAtRisk {
  unit_id: string;
  current_station_id: string | null;
  gate_id: string;
  risk: Estimate;
  stations_remaining: number;
  minutes_remaining: number;
  dark_visits: number;
  factors: Factor[];
  published: boolean;
}

export interface UnitsAtRisk {
  as_of: string;
  units: UnitAtRisk[];
  threshold: number;
  total: number;
  highest_below_threshold: {
    unit_id: string;
    current_station_id: string | null;
    gate_id: string;
    risk_point: number;
  } | null;
  note: string;
}

export interface Bucket {
  index: number;
  start_at: string;
  end_at: string;
}

export interface StationForecast {
  station_id: string;
  stall_probability: number[];
  blocked_probability: number[];
  starved_probability: number[];
  mean_lost_s: number[];
}

export interface BufferForecast {
  buffer_id: string;
  after_station_id: string;
  capacity: number;
  low: number[];
  high: number[];
  mean: number[];
}

export interface Forecast {
  line_id: string;
  as_of: string;
  horizon_min: number;
  replications: number;
  degraded: boolean;
  buckets: Bucket[];
  stations: StationForecast[];
  buffers: BufferForecast[];
  line_stall_probability: number[];
  output: Estimate;
  expected_unit_loss: Estimate;
  fallback_stations: string[];
  learning_stations: string[];
  drifting_stations: string[];
  learning_note: string;
  runtime_s: number;
}

export interface SeriesPoint {
  at: string;
  value: number;
}

export interface Marker {
  at: string;
  label: string;
}

export interface AttributionRow {
  station_id: string;
  average_active_s: number;
  is_constraint: boolean;
}

export interface Evidence {
  prediction_id: string;
  predictor: string;
  model_version: string;
  made_at: string;
  horizon_end: string;
  published: boolean;
  inputs_hash: string;
  claim: Record<string, unknown>;
  cause_station_id: string | null;
  cycle_series: SeriesPoint[];
  normal_range: Range | null;
  markers: Marker[];
  buffer_series: SeriesPoint[];
  buffer_id: string | null;
  attribution: AttributionRow[];
  predictor_record: PredictorRecord;
  notes: string[];
}

export interface SensorCard {
  rec_id: string;
  station_id: string;
  unknown: string;
  option_id: string;
  option_name: string;
  signal_provided: string;
  indicative_cost_usd: number;
  cost_source: string;
  install_hours: number;
  requires_window: boolean;
  next_window: string;
  confidence_now: number;
  confidence_projected: number;
  confidence_projected_lo: number;
  confidence_projected_hi: number;
  resolves: string;
  criticality: number;
  criticality_basis: string;
  modelled_annual_value: Estimate;
  status: string;
}

export interface SensorRecommendations {
  line_id: string;
  as_of: string;
  recommendations: SensorCard[];
  currency: string;
  note: string;
}

export interface ScorecardRow {
  predictor: string;
  station_id: string | null;
  state: string;
  made: number;
  true_positive: number;
  false_positive: number;
  unscoreable: number;
  missed: number;
  precision: number | null;
  recall: number | null;
  median_lead_min: number | null;
  false_per_shift: number | null;
  required: number | null;
  state_changed_at: string | null;
  state_reason: string | null;
}

export interface Scorecard {
  line_id: string;
  as_of: string;
  window_days: number;
  rows: ScorecardRow[];
  totals: ScorecardRow[];
}

export interface RecentEvent {
  at: string;
  kind: string;
  detail: string;
}

export interface StationDetail {
  station: Station;
  zone_name: string;
  time_in_state_s: number;
  cycle_series: SeriesPoint[];
  normal_range: Range | null;
  markers: Marker[];
  knows: string[];
  does_not_know: string[];
  buffer_upstream: Buffer | null;
  buffer_downstream: Buffer | null;
  predictor_record: ScorecardRow[];
  sensor_card: SensorCard | null;
  recent_events: RecentEvent[];
  cycles_recorded: number;
  cycles_required: number;
}

export interface StationVisit {
  station_id: string;
  seq: number;
  arrived_at: string | null;
  departed_at: string | null;
  dwell_s: number | null;
  cycle_time: Estimate | null;
  normal_range: Range | null;
  state_during: string;
  outside_normal: boolean;
  part_lots: string[];
  process_values: Record<string, number>;
}

export interface GateResult {
  gate_id: string;
  at: string;
  passed: boolean;
}

export interface UnitDetail {
  unit_id: string;
  line_id: string;
  variant_id: string;
  entered_at: string;
  exited_at: string | null;
  status: string;
  current_station_id: string | null;
  visits: StationVisit[];
  gates: GateResult[];
  risks: UnitAtRisk[];
  part_lots: string[];
  has_retro_trace: boolean;
}

export interface Intervention {
  type: string;
  station_id?: string | null;
  buffer_id?: string | null;
  count?: number;
  percent?: number;
  minutes?: number;
  variant_order?: string[];
}

export interface SandboxOption {
  label: string;
  interventions: Intervention[];
}

export interface OptionResult {
  label: string;
  units: Estimate;
  delta: Estimate;
  stall_probability: Record<string, number>;
  assumptions: string[];
  rank: number;
}

export interface CounterfactualResult {
  run_id: string;
  line_id: string;
  seed_state_at: string;
  horizon_min: number;
  replications_used: number;
  replications_requested: number;
  runtime_ms: number;
  degraded: boolean;
  degraded_note: string;
  baseline_units: Estimate;
  baseline_stall_probability: Record<string, number>;
  options: OptionResult[];
  footer: string;
}

export interface Hypothesis {
  rank: number;
  station_id: string;
  window: Window;
  divergence: number;
  strength: string;
  description: string;
  shared_attribute: { type: string; value: string } | null;
  population: number;
}

export interface ContainedUnit {
  unit_id: string;
  similarity: number;
  at: string;
  evidence: string[];
}

export interface RetroTrace {
  unit_id: string;
  line_id: string;
  failed_at_gate: string;
  failed_at: string;
  hypotheses: Hypothesis[];
  on_line: ContainedUnit[];
  in_yard: ContainedUnit[];
  shipped: ContainedUnit[];
  counts: Record<string, number>;
  runtime_s: number;
  disclaimer: string;
}

export interface Notice {
  tone: 'neutral' | 'attention';
  text: string;
  detail: string;
}

export interface ConstraintCell {
  station_id: string;
  period: string;
  share: number;
}

export interface ConstraintMigration {
  line_id: string;
  periods: string[];
  stations: string[];
  cells: ConstraintCell[];
  current_constraint: string | null;
  note: string;
}

export interface ParetoRow {
  cause: string;
  minutes: number;
  share: number;
}

export interface LossPareto {
  line_id: string;
  from_at: string;
  to_at: string;
  rows: ParetoRow[];
  reconciliation: string;
  unexplained_min: number;
  unexplained_share: number;
}

export interface Recommendation {
  rec_id: string;
  change: string;
  station_id: string | null;
  buffer_id: string | null;
  modelled_effect: Estimate;
  assumptions: string[];
  sandbox: SandboxOption;
}

export interface Recommendations {
  line_id: string;
  as_of: string;
  rows: Recommendation[];
  note: string;
}

export interface ReadinessComponent {
  name: string;
  value: string;
  score: number;
  weight: number;
  missing: string;
}

export interface SiteReadiness {
  site_id: string;
  name: string;
  band: string;
  score: number;
  components: ReadinessComponent[];
  missing: string[];
  instrumentation_cost_usd: number;
  note: string;
}

export interface Sites {
  sites: SiteReadiness[];
  computed_from: string;
}

export interface Assumption {
  key: string;
  label: string;
  value: number;
  unit: string;
  source: string;
  uncertainty: string;
  editable: boolean;
}

export interface SensitivityRow {
  key: string;
  label: string;
  low_result: number;
  high_result: number;
  swing: number;
}

export interface BusinessCase {
  scenario_id: string;
  assumptions: Assumption[];
  annual_benefit: Estimate;
  payback_months: number | null;
  sensitivity: SensitivityRow[];
  notes: string[];
}

export interface RealisedRow {
  site_id: string;
  measure: string;
  modelled: number;
  realised: number | null;
  gap: number | null;
  unit: string;
  evidence: string;
}

export interface Realised {
  rows: RealisedRow[];
  note: string;
}

export interface TopologyField {
  field: string;
  value: string | null;
  confidence: number | null;
  inferred_from: string;
  note: string;
}

export interface TopologyDraft {
  line_id: string;
  observed_events: number;
  fields: TopologyField[];
  stations: TopologyField[];
  not_inferable: string[];
  note: string;
}

export interface Problem {
  type: string;
  title: string;
  status: number;
  detail: string;
  instance: string;
}
