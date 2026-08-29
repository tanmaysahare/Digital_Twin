# DATABASE_SCHEMA.md

**Engine:** PostgreSQL 16 with TimescaleDB. Migrations with Alembic.
**Conventions:** snake_case, singular table names, UUID primary keys except on hypertables where a composite of `(ts_source, event_id)` is used, `timestamptz` everywhere, no nullable foreign keys without a documented reason.
**Last updated:** 2026-08-28

---

## 1. Overview

```
  config                    live state                 predictions
  ----------                ----------                 -----------
  line                      station_state              prediction
  station        <-------   buffer_state               prediction_outcome
  buffer                    unit                       predictor_state
  gate                      unit_visit                 predictor_scorecard
  variant                   station_distribution       sensor_recommendation
  source_mapping                                       counterfactual_run
  sensor_catalogue
                            events                     missed_event
                            ------                     evaluation_run
                            event  (hypertable)
                            source_health
                            data_gap

  schema truth              (no grant to the application role)
  ------------
  scenario_injection        station_visit      gate_result
  unit_outcome              buffer_occupancy
```

Everything plant-specific is in `config` and is loaded from YAML, so the same schema
serves any line.

---

## 2. Configuration tables

### `line`
| Column | Type | Notes |
|---|---|---|
| `line_id` | text PK | e.g. `line2` |
| `name` | text | |
| `takt_s` | numeric | Nominal takt |
| `config` | jsonb | The full LineDefinition as loaded, for provenance |
| `config_version` | int | Incremented on reload |
| `loaded_at` | timestamptz | |

The full YAML is retained so any historical prediction can be interpreted against the
configuration in force when it was made.

### `station`
| Column | Type | Notes |
|---|---|---|
| `station_id` | text | PK with `line_id` |
| `line_id` | text FK | |
| `seq` | int | Position in the line, 1-based |
| `zone_id` | text | |
| `tier` | text | `A`, `B`, `C` |
| `transport_to_next_s` | numeric | Nominal |
| `is_manual` | boolean | Affects the operator-addition model in counterfactuals |

Index: `(line_id, seq)`.

### `buffer`
`(line_id, buffer_id)` PK, `after_station_id`, `capacity int`.

### `gate`
`(line_id, gate_id)` PK, `after_station_id`, `name`, `catches jsonb` (which defect
classes this gate detects, used to decide which model scores against it).

### `variant`
`(line_id, variant_id)` PK, `name`, `nominal_mix_share numeric`.

Every configuration key is composite with `line_id`. Two lines onboarded from
files may both call a station S20 or a buffer B5, and ONB-04 requires that they
can (AC-080).

### `source_mapping`
| Column | Type | Notes |
|---|---|---|
| `mapping_id` | uuid PK | |
| `line_id` | text FK | |
| `adapter` | text | `sim`, `csv_replay`, `opcua`, `mtconnect`, `sparkplug`, `historian` |
| `native_ref` | text | Tag path, topic, or table and column |
| `event_type` | text | Canonical target |
| `station_id` | text | Nullable for line-level sources |
| `transform` | jsonb | Unit conversion, scaling, enum mapping |

### `sensor_catalogue`
`option_id` PK, `name`, `signal_provided`, `indicative_cost_usd numeric`,
`install_hours numeric`, `requires_window boolean`, `applicable_to jsonb`,
`confidence_model jsonb`, `source text` (where the indicative cost came from).

The `source` column is there so a cost shown to a plant manager can be traced rather
than trusted.

---

## 3. Event storage

### `event` (hypertable)
| Column | Type | Notes |
|---|---|---|
| `ts_source` | timestamptz | Partitioning column |
| `event_id` | uuid | |
| `event_type` | text | |
| `line_id` | text | |
| `station_id` | text | Nullable |
| `unit_id` | text | Nullable |
| `ts_ingest` | timestamptz | |
| `payload` | jsonb | Typed per `event_type`, validated on ingest |
| `source_adapter` | text | |
| `quality_flag` | text | `OK`, `LATE`, `SKEWED`, `ESTIMATED` |

```sql
SELECT create_hypertable('event', 'ts_source', chunk_time_interval => INTERVAL '1 day');
CREATE INDEX ON event (line_id, station_id, ts_source DESC);
CREATE INDEX ON event (unit_id, ts_source) WHERE unit_id IS NOT NULL;
CREATE INDEX ON event (event_type, ts_source DESC);
```

Primary key is `(ts_source, event_id)`. Retention in the prototype is 30 simulated days
via a Timescale retention policy.

### `source_health`
`(line_id, source_adapter)` PK, `last_event_at`, `events_last_min int`,
`estimated_skew_s numeric`, `state text` (`LIVE`, `DEGRADED`, `SILENT`), `checked_at`.

### `data_gap`
`gap_id` PK, `line_id`, `source_adapter`, `started_at`, `ended_at` (nullable while
open), `affected_stations text[]`, `events_lost_estimate int`.

Gaps are first-class records because a forecast made during a gap must be interpretable
later, and because the evidence pack reports how much of an evaluation window was
degraded.

---

## 4. Live state

### `station_state` (hypertable, 1-hour chunks)
| Column | Type | Notes |
|---|---|---|
| `ts` | timestamptz | |
| `line_id`, `station_id` | text | |
| `state` | text | `RUNNING`, `BLOCKED`, `STARVED`, `DOWN`, `CHANGEOVER`, `IDLE`, `IDLE_UNKNOWN` |
| `since` | timestamptz | Entry into the current state |
| `current_unit_id` | text | Nullable |
| `cycle_time_lo` | numeric | Lower bound |
| `cycle_time_hi` | numeric | Upper bound. Equals `lo` when measured |
| `provenance` | text | `MEASURED`, `DERIVED`, `INFERRED` |
| `confidence` | numeric | 0 to 1 |
| `basis` | text | Human-readable, shown in the interface |

**Design note.** Cycle time is stored as a pair of bounds, never as a single value. A
measured value has `lo = hi`. This makes it structurally impossible to store an inferred
value as if it were a measurement, which is the failure this product exists to prevent.

### `buffer_state` (hypertable)
`ts`, `line_id`, `buffer_id`, `occupancy int`, `capacity int`, `trend text`.

### `unit`
| Column | Type | Notes |
|---|---|---|
| `unit_id` | text PK | The VIN |
| `line_id` | text FK | |
| `variant_id` | text FK | |
| `entered_at`, `exited_at` | timestamptz | |
| `current_station_id` | text | Nullable once exited |
| `status` | text | `IN_PROCESS`, `COMPLETED`, `REWORK`, `HELD`, `SCRAPPED` |

### `unit_visit`
The process signature, one row per station visit. This is the table every defect
question is answered from.

| Column | Type | Notes |
|---|---|---|
| `visit_id` | uuid PK | |
| `unit_id` | text FK | |
| `line_id` | text | Part of the composite key into `station` |
| `station_id` | text FK | With `line_id` |
| `seq` | int | Visit order, so a rework revisit is distinguishable |
| `arrived_at`, `departed_at` | timestamptz | |
| `dwell_s` | numeric | |
| `cycle_lo`, `cycle_hi` | numeric | |
| `provenance` | text | |
| `station_state_during` | text | |
| `blocked_s`, `starved_s` | numeric | |
| `process_values` | jsonb | Torque peak and angle, current, vibration, dimensional |
| `process_residuals` | jsonb | z-scores against the station's baseline for this variant |
| `part_lots` | text[] | |
| `operator_group` | text | |
| `shift_id` | text | |
| `env` | jsonb | Zone temperature, humidity |

Indexes: `(unit_id, seq)`, `(station_id, arrived_at DESC)`, GIN on `part_lots`.

The `(station_id, arrived_at)` index is what makes the containment query fast: given a
suspect station and window, find every unit that passed through it.

### `station_distribution`
The rolling baseline per station per variant.

`(line_id, station_id, variant_id, window_end)` PK, `n int`, `median numeric`,
`mad numeric`, `p05`, `p95 numeric`, `empirical jsonb` (the resampling pool used by the
DES), `fit_residual numeric`.

`fit_residual` feeds the model-health view that tells Rakesh when the twin no longer
matches the line (US-044).

---

## 5. Predictions and the ledger

### `prediction`
Append-only. No `UPDATE`, no `DELETE`. Enforced by a trigger and by a database role that
lacks those grants on this table.

| Column | Type | Notes |
|---|---|---|
| `prediction_id` | uuid PK | |
| `predictor` | text | `stall_forecaster`, `defect_risk_g3`, `drift_detector`, `counterfactual` |
| `model_version` | text | |
| `line_id`, `station_id`, `unit_id` | text | Nullable as appropriate |
| `made_at` | timestamptz | |
| `horizon_end` | timestamptz | |
| `claim` | jsonb | Typed per predictor |
| `confidence` | numeric | |
| `interval_lo`, `interval_hi` | numeric | Nullable for predictors without an interval |
| `evidence` | jsonb | What it was based on, rendered in the interface |
| `inputs_hash` | text | So a prediction can be reproduced |
| `published` | boolean | False while the predictor is in SHADOW for this station |
| `degraded` | boolean | True if the cycle ran with reduced replications |

Indexes: `(predictor, station_id, made_at DESC)`, `(horizon_end) WHERE outcome not yet joined`.

### `prediction_outcome`
| Column | Type | Notes |
|---|---|---|
| `prediction_id` | uuid PK FK | One outcome per prediction |
| `resolved_at` | timestamptz | |
| `result` | text | `TRUE_POSITIVE`, `FALSE_POSITIVE`, `TRUE_NEGATIVE`, `FALSE_NEGATIVE`, `UNSCOREABLE` |
| `actual` | jsonb | What happened |
| `lead_time_s` | numeric | Nullable |
| `note` | text | Why it was unscoreable, where applicable |

`UNSCOREABLE` exists for the honest case: a prediction whose window fell inside a data
gap cannot be scored either way, and counting it as a success or a failure would corrupt
the scorecard. The share of unscoreable predictions is itself reported.

### `missed_event`
Events that occurred with no prediction in scope, so recall is computable rather than
assumed.

`missed_id` PK, `line_id`, `station_id`, `event_type` (`STALL`, `GATE_FAILURE`),
`occurred_at`, `predictor` (which predictor should have caught it).

### `predictor_state`
Current gate state and its full history.

`state_id` PK, `predictor`, `line_id`, `station_id`, `state text` (`SHADOW`, `ACTIVE`,
`UNAVAILABLE`), `changed_at`, `reason text`, `metrics_at_change jsonb`.

`reason` and `metrics_at_change` are what the interface reads when it tells the floor a
predictor was withdrawn and why.

### `predictor_scorecard`
A continuous aggregate refreshed each cycle.

```sql
CREATE MATERIALIZED VIEW predictor_scorecard AS
SELECT
  p.predictor,
  p.line_id,
  p.station_id,
  count(*)                                              AS made,
  count(*) FILTER (WHERE o.result = 'TRUE_POSITIVE')    AS tp,
  count(*) FILTER (WHERE o.result = 'FALSE_POSITIVE')   AS fp,
  count(*) FILTER (WHERE o.result = 'UNSCOREABLE')      AS unscoreable,
  percentile_cont(0.5) WITHIN GROUP (ORDER BY o.lead_time_s) AS median_lead_s
FROM prediction p
JOIN prediction_outcome o USING (prediction_id)
WHERE p.made_at > now() - interval '14 days'
GROUP BY 1, 2, 3;
```

Recall is computed by joining `missed_event`, not from this view alone. A view that can
only see predictions cannot compute recall, and a product that quietly reports precision
as if it were accuracy is exactly the product this one is arguing against.

The view carries a unique index on `(predictor, line_id, station_id)` with
`NULLS NOT DISTINCT`, so that the per-cycle refresh can run concurrently rather
than locking the scorecard while a supervisor is reading it. `station_id` is
null for a line-level predictor, and two null station identifiers are the same
row here.

### `counterfactual_run`
`run_id` PK, `line_id`, `made_at`, `seed_state_ts`, `intervention jsonb`,
`baseline_result jsonb`, `intervention_result jsonb`, `replications int`,
`runtime_ms int`, `degraded boolean`, `saved_as_decision boolean`,
`marked_executed_at timestamptz`.

The last two columns are what allow a counterfactual to be scored later against what
actually happened.

---

## 6. Sensor recommendations

### `sensor_recommendation`
| Column | Type | Notes |
|---|---|---|
| `rec_id` | uuid PK | |
| `line_id`, `station_id` | text | |
| `generated_at` | timestamptz | |
| `observability_score` | numeric | |
| `criticality_score` | numeric | |
| `unknown_description` | text | Rendered in the interface |
| `option_id` | text FK | From `sensor_catalogue` |
| `confidence_now`, `confidence_projected` | numeric | |
| `modelled_value_lo`, `modelled_value_hi` | numeric | Always an interval |
| `next_window` | text | |
| `status` | text | `OPEN`, `QUEUED`, `INSTALLED`, `DECLINED` |
| `installed_at` | timestamptz | Nullable |
| `realised_confidence` | numeric | Nullable, filled after install for SNS-06 |

`confidence_projected` against `realised_confidence` is the honesty check on the
product's own sensor economics.

---

## 7. Ground truth and evaluation

### `scenario_injection` (schema `truth`)

What the simulator injected, when, where and with what parameters. This is the
ground truth the evaluation harness joins against, and it is the reason the
truth schema exists.

`injection_id` PK, `run_id`, `scenario_id`, `line_id`, `station_id` (nullable
for a line-level scenario), `injected_at`, `ends_at` (nullable), `mechanism`,
`parameters jsonb`.

### `station_visit` (schema `truth`)

What one unit's visit to one station really consisted of. `cycle_time_s` is the
answer the virtual sensors are graded against, and `blocked_s` with
`queued_before_s` is the answer the attribution is graded against. Blocking is a
station waiting to hand its unit on; queueing is the unit waiting to be picked
up; the two together are the whole of the non-work time inside a span.

`visit_id` PK, `run_id`, `line_id`, `unit_id`, `station_id`, `seq`,
`variant_id`, `shift_id`, `arrived_at`, `work_ended_at`, `departed_at`,
`cycle_time_s`, `blocked_s`, `queued_before_s`, `starved_before_s`, `down_s`,
`is_dark`.

`cycle_time_s` includes any repair that interrupted the work. Failures are
operation-dependent, so a station cannot fail while it is idle, and the twin
cannot separate a slow dark station from a briefly broken one. Defining truth
this way says so rather than holding the twin to a distinction it has no
evidence for.

### `unit_outcome` (schema `truth`)

One unit's life on the line. `(run_id, unit_id)` PK, `line_id`, `variant_id`,
`released_at`, `completed_at`, `status`, `rework_passes`, `lots`.

### `gate_result` (schema `truth`)

One inspection verdict and the causes that produced it. `result_id` PK,
`run_id`, `line_id`, `unit_id`, `gate_id`, `at`, `passed`,
`failure_probability`, `defect_class`, `cause_odds jsonb`.

`cause_odds` carries each contributing factor and the odds multiplier it
applied, so a retro-trace hypothesis is scored against what actually drove the
failure rather than against a label.

### `buffer_occupancy` (schema `truth`)

`run_id`, `line_id`, `buffer_id`, `at`, `occupancy`. Recorded on change.

All four are owned by `digitaltwin_truth`, and migration 0004 revokes every
privilege on them from `digitaltwin_app` and from PUBLIC explicitly rather than
relying on the absence of a grant.

---

### `evaluation_run`
`run_id` PK, `scenario_id`, `seed`, `started_at`, `finished_at`, `config_version`,
`code_version`, `metrics jsonb`, `report_path text`.

Seed and code version are recorded so any number in the evidence pack can be reproduced
exactly (NFR-07).

---

## 8. Integrity rules

The roles are `digitaltwin_app`, which the api and worker connect as, and
`digitaltwin_truth`, which owns the truth schema and which the simulator
connects as. Both are created by migration 0002 if absent. Passwords are set out
of band and are never committed.

| Rule | Enforcement |
|---|---|
| `prediction` is append-only | Trigger raising on UPDATE or DELETE, plus a role without those grants |
| A `station_state` row must carry a provenance | `NOT NULL` plus a check constraint on the allowed values |
| `cycle_time_lo <= cycle_time_hi` | Check constraint |
| A `MEASURED` value has `lo = hi` | Check constraint: `provenance <> 'MEASURED' OR cycle_time_lo = cycle_time_hi` |
| Confidence in [0, 1] | Check constraint |
| Every published prediction has a matching `ACTIVE` `predictor_state` at `made_at` | Verified by a test, not by a constraint, because the state history makes this a temporal join |
| Ground truth is never in this database | The simulator writes truth to a separate schema that the twin's database role cannot read. Enforced by grants |

That last rule matters more than it looks. If the twin could read the simulator's ground
truth, every evaluation number in the evidence pack would be worthless, and an accidental
join is exactly the kind of mistake that happens at 2 am before a deadline. Separate
schema, separate role, no grant.

---

## 9. Sizing (prototype, 30 simulated days)

| Table | Rows | Approximate size |
|---|---|---|
| `event` | ~14M | ~4 GB |
| `station_state` | ~2.4M | ~400 MB |
| `unit_visit` | ~580k | ~900 MB |
| `prediction` | ~90k | ~120 MB |
| Everything else | small | ~50 MB |

Fits comfortably on a laptop. Compression on the `event` hypertable after 2 days reduces
it by roughly an order of magnitude if disk becomes a problem.

---

**Related:** [TECHNICAL_SPEC.md](TECHNICAL_SPEC.md) · [ARCHITECTURE.md](ARCHITECTURE.md) · [API_SPEC.md](API_SPEC.md)
