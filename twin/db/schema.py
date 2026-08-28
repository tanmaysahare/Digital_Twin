"""The database schema, as SQLAlchemy metadata.

This is the declarative half of docs/technical/DATABASE_SCHEMA.md. The migration
under `migrations/versions/` creates the same shape plus the parts SQLAlchemy
cannot express: the TimescaleDB hypertables, the append-only trigger on the
ledger, the separate truth schema, and the role grants. A test asserts that
Alembic finds no difference between this metadata and a freshly migrated
database, so the two cannot drift.

Two shapes here are load-bearing and are not conveniences:

- Cycle time is stored as a pair of bounds, never as a single value, with a
  check constraint saying that a MEASURED value has equal bounds. That makes it
  structurally impossible to store an inference as if it were a reading.
- `prediction` has no update path. The trigger in the migration raises on UPDATE
  and DELETE, and the application role has no grant for either.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    Numeric,
    PrimaryKeyConstraint,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

# Constraint naming so that Alembic can generate reversible migrations and so
# that a failing constraint names itself in the error a developer reads.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)

TRUTH_SCHEMA = "truth"

PROVENANCE_VALUES = ("MEASURED", "DERIVED", "INFERRED")
TIER_VALUES = ("A", "B", "C")
STATION_STATES = (
    "RUNNING",
    "BLOCKED",
    "STARVED",
    "DOWN",
    "CHANGEOVER",
    "IDLE",
    "IDLE_UNKNOWN",
)
QUALITY_FLAGS = ("OK", "LATE", "SKEWED", "ESTIMATED")
OUTCOME_RESULTS = (
    "TRUE_POSITIVE",
    "FALSE_POSITIVE",
    "TRUE_NEGATIVE",
    "FALSE_NEGATIVE",
    "UNSCOREABLE",
)
PREDICTOR_STATES = ("SHADOW", "ACTIVE", "UNAVAILABLE")
UNIT_STATUSES = ("IN_PROCESS", "COMPLETED", "REWORK", "HELD", "SCRAPPED")
SOURCE_STATES = ("LIVE", "DEGRADED", "SILENT")
RECOMMENDATION_STATUSES = ("OPEN", "QUEUED", "INSTALLED", "DECLINED")


def _one_of(column: str, values: tuple[str, ...], name: str) -> CheckConstraint:
    allowed = ", ".join(f"'{value}'" for value in values)
    return CheckConstraint(f"{column} IN ({allowed})", name=name)


def _timestamp(name: str, *, nullable: bool = False) -> Column[datetime]:
    """A timestamptz column. Every time in this schema carries its zone."""
    return Column(name, DateTime(timezone=True), nullable=nullable)


# ---------------------------------------------------------------------------
# Configuration. Everything plant-specific lives here and is loaded from YAML,
# so the same schema serves any line.

line = Table(
    "line",
    metadata,
    Column("line_id", Text, primary_key=True),
    Column("name", Text, nullable=False),
    Column("takt_s", Numeric, nullable=False),
    # The full LineDefinition as loaded, so that a prediction made months ago
    # can still be read against the configuration in force when it was made.
    Column("config", JSONB, nullable=False),
    Column("config_version", Integer, nullable=False),
    _timestamp("loaded_at"),
)

station = Table(
    "station",
    metadata,
    Column("line_id", Text, nullable=False),
    Column("station_id", Text, nullable=False),
    Column("seq", Integer, nullable=False),
    Column("zone_id", Text, nullable=False),
    Column("tier", Text, nullable=False),
    Column("transport_to_next_s", Numeric, nullable=True),
    Column("is_manual", Boolean, nullable=False, server_default="false"),
    PrimaryKeyConstraint("line_id", "station_id"),
    ForeignKeyConstraint(["line_id"], ["line.line_id"], ondelete="CASCADE"),
    UniqueConstraint("line_id", "seq"),
    _one_of("tier", TIER_VALUES, "tier"),
    Index("ix_station_line_seq", "line_id", "seq"),
)

buffer = Table(
    "buffer",
    metadata,
    Column("line_id", Text, nullable=False),
    Column("buffer_id", Text, nullable=False),
    Column("after_station_id", Text, nullable=False),
    Column("capacity", Integer, nullable=False),
    PrimaryKeyConstraint("line_id", "buffer_id"),
    ForeignKeyConstraint(["line_id"], ["line.line_id"], ondelete="CASCADE"),
    ForeignKeyConstraint(
        ["line_id", "after_station_id"],
        ["station.line_id", "station.station_id"],
    ),
    CheckConstraint("capacity > 0", name="capacity"),
)

gate = Table(
    "gate",
    metadata,
    Column("line_id", Text, nullable=False),
    Column("gate_id", Text, nullable=False),
    Column("after_station_id", Text, nullable=False),
    Column("name", Text, nullable=False),
    # Which defect classes this gate detects, which decides which model scores
    # against it.
    Column("catches", JSONB, nullable=False),
    PrimaryKeyConstraint("line_id", "gate_id"),
    ForeignKeyConstraint(["line_id"], ["line.line_id"], ondelete="CASCADE"),
    ForeignKeyConstraint(
        ["line_id", "after_station_id"],
        ["station.line_id", "station.station_id"],
    ),
)

variant = Table(
    "variant",
    metadata,
    Column("line_id", Text, nullable=False),
    Column("variant_id", Text, nullable=False),
    Column("name", Text, nullable=False),
    Column("nominal_mix_share", Numeric, nullable=False),
    PrimaryKeyConstraint("line_id", "variant_id"),
    ForeignKeyConstraint(["line_id"], ["line.line_id"], ondelete="CASCADE"),
    CheckConstraint(
        "nominal_mix_share >= 0 AND nominal_mix_share <= 1",
        name="mix_share",
    ),
)

source_mapping = Table(
    "source_mapping",
    metadata,
    Column("mapping_id", UUID(as_uuid=True), primary_key=True),
    Column("line_id", Text, nullable=False),
    Column("adapter", Text, nullable=False),
    Column("native_ref", Text, nullable=False),
    Column("event_type", Text, nullable=False),
    Column("station_id", Text, nullable=True),
    Column("transform", JSONB, nullable=True),
    ForeignKeyConstraint(["line_id"], ["line.line_id"], ondelete="CASCADE"),
    Index("ix_source_mapping_line_adapter", "line_id", "adapter"),
)

sensor_catalogue = Table(
    "sensor_catalogue",
    metadata,
    Column("option_id", Text, primary_key=True),
    Column("name", Text, nullable=False),
    Column("signal_provided", Text, nullable=False),
    Column("indicative_cost_usd", Numeric, nullable=False),
    Column("install_hours", Numeric, nullable=False),
    Column("requires_window", Boolean, nullable=False),
    Column("applicable_to", JSONB, nullable=False),
    Column("confidence_model", JSONB, nullable=False),
    # Where the indicative cost came from, so a number shown to a plant manager
    # can be traced rather than trusted.
    Column("source", Text, nullable=False),
)

# ---------------------------------------------------------------------------
# Events

event = Table(
    "event",
    metadata,
    _timestamp("ts_source"),
    Column("event_id", UUID(as_uuid=True), nullable=False),
    Column("event_type", Text, nullable=False),
    Column("line_id", Text, nullable=False),
    Column("station_id", Text, nullable=True),
    Column("unit_id", Text, nullable=True),
    _timestamp("ts_ingest"),
    Column("payload", JSONB, nullable=False),
    Column("source_adapter", Text, nullable=False),
    Column("quality_flag", Text, nullable=False),
    PrimaryKeyConstraint("ts_source", "event_id"),
    _one_of("quality_flag", QUALITY_FLAGS, "quality_flag"),
    Index("ix_event_line_station_ts", "line_id", "station_id", "ts_source"),
    Index(
        "ix_event_unit_ts",
        "unit_id",
        "ts_source",
        postgresql_where=Column("unit_id", Text).isnot(None),
    ),
    Index("ix_event_type_ts", "event_type", "ts_source"),
)

source_health = Table(
    "source_health",
    metadata,
    Column("line_id", Text, nullable=False),
    Column("source_adapter", Text, nullable=False),
    _timestamp("last_event_at", nullable=True),
    Column("events_last_min", Integer, nullable=False, server_default="0"),
    Column("estimated_skew_s", Numeric, nullable=True),
    Column("state", Text, nullable=False),
    _timestamp("checked_at"),
    PrimaryKeyConstraint("line_id", "source_adapter"),
    ForeignKeyConstraint(["line_id"], ["line.line_id"], ondelete="CASCADE"),
    _one_of("state", SOURCE_STATES, "state"),
)

# Gaps are first-class records because a forecast made during a gap has to be
# interpretable later, and because the evidence pack reports how much of an
# evaluation window was degraded.
data_gap = Table(
    "data_gap",
    metadata,
    Column("gap_id", UUID(as_uuid=True), primary_key=True),
    Column("line_id", Text, nullable=False),
    Column("source_adapter", Text, nullable=False),
    _timestamp("started_at"),
    _timestamp("ended_at", nullable=True),
    Column("affected_stations", ARRAY(Text), nullable=False),
    Column("events_lost_estimate", Integer, nullable=True),
    ForeignKeyConstraint(["line_id"], ["line.line_id"], ondelete="CASCADE"),
    Index("ix_data_gap_line_started", "line_id", "started_at"),
)

# ---------------------------------------------------------------------------
# Live state

station_state = Table(
    "station_state",
    metadata,
    _timestamp("ts"),
    Column("line_id", Text, nullable=False),
    Column("station_id", Text, nullable=False),
    Column("state", Text, nullable=False),
    _timestamp("since"),
    Column("current_unit_id", Text, nullable=True),
    Column("cycle_time_lo", Numeric, nullable=True),
    Column("cycle_time_hi", Numeric, nullable=True),
    Column("provenance", Text, nullable=False),
    Column("confidence", Numeric, nullable=False),
    # Human-readable, shown in the interface next to the value it explains.
    Column("basis", Text, nullable=False),
    PrimaryKeyConstraint("ts", "line_id", "station_id"),
    _one_of("state", STATION_STATES, "state"),
    _one_of("provenance", PROVENANCE_VALUES, "provenance"),
    CheckConstraint(
        "cycle_time_lo IS NULL OR cycle_time_hi IS NULL "
        "OR cycle_time_lo <= cycle_time_hi",
        name="bounds_ordered",
    ),
    # A measured value has equal bounds. This is what makes it impossible to
    # store an inference in the shape of a reading.
    CheckConstraint(
        "provenance <> 'MEASURED' OR cycle_time_lo IS NOT DISTINCT FROM cycle_time_hi",
        name="measured_is_a_point",
    ),
    CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence"),
    Index("ix_station_state_line_station_ts", "line_id", "station_id", "ts"),
)

buffer_state = Table(
    "buffer_state",
    metadata,
    _timestamp("ts"),
    Column("line_id", Text, nullable=False),
    Column("buffer_id", Text, nullable=False),
    Column("occupancy", Integer, nullable=False),
    Column("capacity", Integer, nullable=False),
    Column("trend", Text, nullable=False),
    PrimaryKeyConstraint("ts", "line_id", "buffer_id"),
    CheckConstraint("occupancy >= 0 AND occupancy <= capacity", name="occupancy"),
    Index("ix_buffer_state_line_buffer_ts", "line_id", "buffer_id", "ts"),
)

unit = Table(
    "unit",
    metadata,
    Column("unit_id", Text, primary_key=True),
    Column("line_id", Text, nullable=False),
    Column("variant_id", Text, nullable=False),
    _timestamp("entered_at"),
    _timestamp("exited_at", nullable=True),
    Column("current_station_id", Text, nullable=True),
    Column("status", Text, nullable=False),
    ForeignKeyConstraint(["line_id"], ["line.line_id"], ondelete="CASCADE"),
    ForeignKeyConstraint(
        ["line_id", "variant_id"], ["variant.line_id", "variant.variant_id"]
    ),
    _one_of("status", UNIT_STATUSES, "status"),
    Index("ix_unit_line_entered", "line_id", "entered_at"),
)

# The process signature, one row per station visit. Every defect question is
# answered from this table.
unit_visit = Table(
    "unit_visit",
    metadata,
    Column("visit_id", UUID(as_uuid=True), primary_key=True),
    Column("unit_id", Text, nullable=False),
    Column("line_id", Text, nullable=False),
    Column("station_id", Text, nullable=False),
    # Visit order, so a rework revisit is distinguishable from the first pass.
    Column("seq", Integer, nullable=False),
    _timestamp("arrived_at"),
    _timestamp("departed_at", nullable=True),
    Column("dwell_s", Numeric, nullable=True),
    Column("cycle_lo", Numeric, nullable=True),
    Column("cycle_hi", Numeric, nullable=True),
    Column("provenance", Text, nullable=False),
    Column("station_state_during", Text, nullable=True),
    Column("blocked_s", Numeric, nullable=True),
    Column("starved_s", Numeric, nullable=True),
    Column("process_values", JSONB, nullable=True),
    Column("process_residuals", JSONB, nullable=True),
    Column("part_lots", ARRAY(Text), nullable=True),
    Column("operator_group", Text, nullable=True),
    Column("shift_id", Text, nullable=True),
    Column("env", JSONB, nullable=True),
    ForeignKeyConstraint(["unit_id"], ["unit.unit_id"], ondelete="CASCADE"),
    ForeignKeyConstraint(
        ["line_id", "station_id"], ["station.line_id", "station.station_id"]
    ),
    _one_of("provenance", PROVENANCE_VALUES, "provenance"),
    CheckConstraint(
        "cycle_lo IS NULL OR cycle_hi IS NULL OR cycle_lo <= cycle_hi",
        name="bounds_ordered",
    ),
    CheckConstraint(
        "provenance <> 'MEASURED' OR cycle_lo IS NOT DISTINCT FROM cycle_hi",
        name="measured_is_a_point",
    ),
    UniqueConstraint("unit_id", "seq"),
    # This index is what makes the containment query fast: given a suspect
    # station and a window, find every unit that passed through it.
    Index("ix_unit_visit_station_arrived", "station_id", "arrived_at"),
    Index("ix_unit_visit_part_lots", "part_lots", postgresql_using="gin"),
)

station_distribution = Table(
    "station_distribution",
    metadata,
    Column("line_id", Text, nullable=False),
    Column("station_id", Text, nullable=False),
    Column("variant_id", Text, nullable=False),
    _timestamp("window_end"),
    Column("n", Integer, nullable=False),
    Column("median", Numeric, nullable=False),
    Column("mad", Numeric, nullable=False),
    Column("p05", Numeric, nullable=False),
    Column("p95", Numeric, nullable=False),
    # The resampling pool the discrete-event forecast draws from. Empirical
    # rather than a fitted parametric form, because fitting a lognormal to a
    # bimodal cycle time produces a confident wrong forecast.
    Column("empirical", JSONB, nullable=False),
    # Feeds the model-health view that says when the twin no longer matches the
    # line at a station (US-044).
    Column("fit_residual", Numeric, nullable=True),
    PrimaryKeyConstraint("line_id", "station_id", "variant_id", "window_end"),
    ForeignKeyConstraint(
        ["line_id", "station_id"], ["station.line_id", "station.station_id"]
    ),
    ForeignKeyConstraint(
        ["line_id", "variant_id"], ["variant.line_id", "variant.variant_id"]
    ),
    CheckConstraint("n >= 0", name="sample_count"),
)

# ---------------------------------------------------------------------------
# The ledger

prediction = Table(
    "prediction",
    metadata,
    Column("prediction_id", UUID(as_uuid=True), primary_key=True),
    Column("predictor", Text, nullable=False),
    Column("model_version", Text, nullable=False),
    Column("line_id", Text, nullable=False),
    Column("station_id", Text, nullable=True),
    Column("unit_id", Text, nullable=True),
    _timestamp("made_at"),
    _timestamp("horizon_end"),
    Column("claim", JSONB, nullable=False),
    Column("confidence", Numeric, nullable=False),
    Column("interval_lo", Numeric, nullable=True),
    Column("interval_hi", Numeric, nullable=True),
    Column("evidence", JSONB, nullable=False),
    # So a prediction can be reproduced from the inputs it was made on.
    Column("inputs_hash", Text, nullable=False),
    # False while the predictor is in SHADOW for this station.
    Column("published", Boolean, nullable=False),
    # True if the cycle ran with reduced replications.
    Column("degraded", Boolean, nullable=False, server_default="false"),
    ForeignKeyConstraint(["line_id"], ["line.line_id"], ondelete="RESTRICT"),
    CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence"),
    CheckConstraint(
        "interval_lo IS NULL OR interval_hi IS NULL OR interval_lo <= interval_hi",
        name="interval_ordered",
    ),
    CheckConstraint("horizon_end >= made_at", name="horizon_forward"),
    Index("ix_prediction_predictor_station_made", "predictor", "station_id", "made_at"),
    Index("ix_prediction_horizon_end", "horizon_end"),
)

prediction_outcome = Table(
    "prediction_outcome",
    metadata,
    Column("prediction_id", UUID(as_uuid=True), primary_key=True),
    _timestamp("resolved_at"),
    Column("result", Text, nullable=False),
    Column("actual", JSONB, nullable=False),
    Column("lead_time_s", Numeric, nullable=True),
    # Why it was unscoreable, where applicable.
    Column("note", Text, nullable=True),
    ForeignKeyConstraint(
        ["prediction_id"], ["prediction.prediction_id"], ondelete="RESTRICT"
    ),
    _one_of("result", OUTCOME_RESULTS, "result"),
    Index("ix_prediction_outcome_result", "result"),
)

# Events that occurred with no prediction in scope. Without this table recall is
# not computable, and a product that reports precision as if it were accuracy is
# exactly the product this one argues against.
missed_event = Table(
    "missed_event",
    metadata,
    Column("missed_id", UUID(as_uuid=True), primary_key=True),
    Column("line_id", Text, nullable=False),
    Column("station_id", Text, nullable=True),
    Column("event_type", Text, nullable=False),
    _timestamp("occurred_at"),
    Column("predictor", Text, nullable=False),
    ForeignKeyConstraint(["line_id"], ["line.line_id"], ondelete="CASCADE"),
    Index("ix_missed_event_predictor_occurred", "predictor", "occurred_at"),
)

predictor_state = Table(
    "predictor_state",
    metadata,
    Column("state_id", UUID(as_uuid=True), primary_key=True),
    Column("predictor", Text, nullable=False),
    Column("line_id", Text, nullable=False),
    Column("station_id", Text, nullable=True),
    Column("state", Text, nullable=False),
    _timestamp("changed_at"),
    # `reason` and `metrics_at_change` are what the interface reads when it
    # tells the floor that a predictor was withdrawn and why.
    Column("reason", Text, nullable=False),
    Column("metrics_at_change", JSONB, nullable=False),
    ForeignKeyConstraint(["line_id"], ["line.line_id"], ondelete="CASCADE"),
    _one_of("state", PREDICTOR_STATES, "state"),
    Index(
        "ix_predictor_state_predictor_station_changed",
        "predictor",
        "station_id",
        "changed_at",
    ),
)

counterfactual_run = Table(
    "counterfactual_run",
    metadata,
    Column("run_id", UUID(as_uuid=True), primary_key=True),
    Column("line_id", Text, nullable=False),
    _timestamp("made_at"),
    _timestamp("seed_state_ts"),
    Column("intervention", JSONB, nullable=False),
    Column("baseline_result", JSONB, nullable=False),
    Column("intervention_result", JSONB, nullable=False),
    Column("replications", Integer, nullable=False),
    Column("runtime_ms", Integer, nullable=False),
    Column("degraded", Boolean, nullable=False, server_default="false"),
    # These two are what allow a counterfactual to be scored later against what
    # actually happened on the line.
    Column("saved_as_decision", Boolean, nullable=False, server_default="false"),
    _timestamp("marked_executed_at", nullable=True),
    ForeignKeyConstraint(["line_id"], ["line.line_id"], ondelete="CASCADE"),
    Index("ix_counterfactual_run_line_made", "line_id", "made_at"),
)

# ---------------------------------------------------------------------------
# Sensor recommendations

sensor_recommendation = Table(
    "sensor_recommendation",
    metadata,
    Column("rec_id", UUID(as_uuid=True), primary_key=True),
    Column("line_id", Text, nullable=False),
    Column("station_id", Text, nullable=False),
    _timestamp("generated_at"),
    Column("observability_score", Numeric, nullable=False),
    Column("criticality_score", Numeric, nullable=False),
    Column("unknown_description", Text, nullable=False),
    Column("option_id", Text, nullable=False),
    Column("confidence_now", Numeric, nullable=False),
    Column("confidence_projected", Numeric, nullable=False),
    # Always an interval. The modelled value inherits the forecast's uncertainty
    # and is never shown as a point.
    Column("modelled_value_lo", Numeric, nullable=False),
    Column("modelled_value_hi", Numeric, nullable=False),
    Column("next_window", Text, nullable=True),
    Column("status", Text, nullable=False),
    _timestamp("installed_at", nullable=True),
    # Filled after install. Projected against realised is the honesty check on
    # the product's own sensor economics (SNS-06).
    Column("realised_confidence", Numeric, nullable=True),
    ForeignKeyConstraint(
        ["line_id", "station_id"], ["station.line_id", "station.station_id"]
    ),
    ForeignKeyConstraint(["option_id"], ["sensor_catalogue.option_id"]),
    _one_of("status", RECOMMENDATION_STATUSES, "status"),
    CheckConstraint("modelled_value_lo <= modelled_value_hi", name="value_interval"),
    Index("ix_sensor_recommendation_line_generated", "line_id", "generated_at"),
)

# ---------------------------------------------------------------------------
# Evaluation

evaluation_run = Table(
    "evaluation_run",
    metadata,
    Column("run_id", UUID(as_uuid=True), primary_key=True),
    Column("scenario_id", Text, nullable=False),
    Column("seed", Integer, nullable=False),
    _timestamp("started_at"),
    _timestamp("finished_at", nullable=True),
    Column("config_version", Integer, nullable=False),
    # Seed and code version are recorded so that any number in the evidence pack
    # can be reproduced exactly (NFR-07).
    Column("code_version", Text, nullable=False),
    Column("metrics", JSONB, nullable=True),
    Column("report_path", Text, nullable=True),
    Index("ix_evaluation_run_scenario_seed", "scenario_id", "seed"),
)

# ---------------------------------------------------------------------------
# Ground truth, in its own schema.
#
# The twin's database role has no grant on this schema. If the twin could read
# the simulator's ground truth, every number in the evidence pack would be
# worthless, and an accidental join is exactly the mistake that happens at 2 am
# before a deadline. Separate schema, separate role, no grant (AC-104).

scenario_injection = Table(
    "scenario_injection",
    metadata,
    Column("injection_id", UUID(as_uuid=True), primary_key=True),
    Column("run_id", UUID(as_uuid=True), nullable=False),
    Column("scenario_id", Text, nullable=False),
    Column("line_id", Text, nullable=False),
    Column("station_id", Text, nullable=True),
    _timestamp("injected_at"),
    _timestamp("ends_at", nullable=True),
    Column("mechanism", Text, nullable=False),
    Column("parameters", JSONB, nullable=False),
    schema=TRUTH_SCHEMA,
)

APPEND_ONLY_TABLES = ("prediction", "prediction_outcome")

# Which table is partitioned on which column. The migration carries its own copy
# of this deliberately: a migration is a snapshot of a moment and must not change
# meaning when application code changes.
HYPERTABLES = {
    "event": "ts_source",
    "station_state": "ts",
    "buffer_state": "ts",
}
