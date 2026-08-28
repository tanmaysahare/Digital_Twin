# TECHNICAL_SPEC.md

**Purpose:** the algorithms and their parameters, specified precisely enough to implement without further design work.
**Last updated:** 2026-08-28

---

## 1. Stack

| Layer | Choice | Version target |
|---|---|---|
| Simulation and services | Python | 3.11 |
| Discrete-event simulation | SimPy | 4.x |
| Numerics | NumPy, SciPy, pandas | current |
| Gradient boosting | LightGBM | 4.x |
| Calibration and metrics | scikit-learn | 1.4+ |
| Conformal prediction | MAPIE, or a 120-line split-conformal implementation | 0.8+ |
| Explanations | SHAP (TreeExplainer) | 0.44+ |
| API | FastAPI, uvicorn, pydantic v2 | current |
| Database | PostgreSQL 16 with TimescaleDB | current |
| ORM and migrations | SQLAlchemy 2.0, Alembic | current |
| Frontend | Next.js (App Router), React, TypeScript | Next 14+, TS 5.3+ |
| Styling | Tailwind mapped to the design tokens | 3.4+ |
| Charts | Hand-written SVG plus d3-scale. No charting library | d3-scale 4.x |
| Testing | pytest, pytest-asyncio, Vitest, Playwright | current |
| Packaging | Docker Compose | Compose v2 |

**Deliberately absent:** no component library, no icon library, no charting library, no
ORM-generated admin, no message broker (the 2-minute cycle does not need one), no
Kubernetes.

---

## 2. Repository layout

```
Digital_Twin/
  CLAUDE.md
  README.md
  Makefile                   thin, delegates to tools/tasks.py
  make.cmd                   the same tasks on Windows without make
  docker-compose.yml
  docker/                    the two Dockerfiles
  alembic.ini
  migrations/                Alembic environment and versions
  .lint/                     banned word lists for the design rules
  tools/
    tasks.py                 the task runner behind the Makefile
    designlint/              the design rules from TEST_PLAN.md Section 7
  docs/                      (this specification set)
  config/
    lines/line2.yaml         LineDefinition for the reference line
    lines/line7.yaml         a structurally different line, for ONB-04
    sources/sim.yaml         SourceMapping for the simulator
    catalogue/sensors.yaml   the low-cost sensing catalogue
  plantsim/
    model.py                 the SimPy line model
    scenarios.py             SC-01 to SC-08
    emit.py                  canonical event emission with tier filtering
    truth.py                 ground-truth channel, written to a separate store
  connector/
    protocol.py              SourceAdapter, read-only by construction
    sim_adapter.py
    csv_replay_adapter.py
    normalise.py             reordering window, clock skew, health
  twin/
    db/
      schema.py              SQLAlchemy metadata, the declarative half of
                             DATABASE_SCHEMA.md
      engine.py              settings and the engine
      migration.py           running and comparing migrations
    domain/                  dataclasses: Estimate, LineState, ProcessSignature
    state/estimator.py
    state/virtual_sensors.py
    state/distributions.py
    forecast/des.py
    forecast/attribution.py
    forecast/drift.py
    defect/features.py
    defect/model.py
    defect/conformal.py
    retro/trace.py
    counterfactual/engine.py
    ledger/store.py
    ledger/gates.py
    sensors/value.py
    topology/discover.py
    api/                     FastAPI routers
    workers/cycle.py
  evaluation/
    harness.py
    metrics.py
    report.py
  web/
    src/app/(line|plan|program)/
    src/components/
    src/styles/tokens.css
    src/lib/
  tests/
```

---

## 3. Canonical event model

```python
EventType = Literal[
    "CYCLE_START", "CYCLE_END", "UNIT_ARRIVE", "UNIT_DEPART",
    "STATION_STATE", "PROCESS_VALUE", "ANDON", "INSPECTION_RESULT",
    "MANUAL_CHECK", "PART_LOT_SCAN", "ENV_READING", "SHIFT_MARKER",
]

@dataclass(frozen=True)
class CanonicalEvent:
    event_id: UUID
    event_type: EventType
    line_id: str
    station_id: str | None
    unit_id: str | None
    ts_source: datetime          # the source's clock
    ts_ingest: datetime          # ours
    payload: dict                # typed per event_type, validated by pydantic
    source_adapter: str
    quality_flag: Literal["OK", "LATE", "SKEWED", "ESTIMATED"]
```

**Reordering.** Events buffer for `reorder_window_s` (default 30) and are released in
`ts_source` order. An event arriving after its window is accepted with `quality_flag =
LATE` and triggers a recomputation of the affected station's state.

**Clock skew.** For each pair of adapters that observe the same unit handoff, the
estimator maintains a rolling median of `ts_source` differences less nominal transport
time. Skew above `skew_warn_s` (default 2.0) raises a data-health warning. Skew is not
silently corrected, because a correction applied to a genuinely slow station would hide
the thing we are looking for.

---

## 4. State estimation

### 4.1 Station state machine

```
        unit arrives, work starts
IDLE ---------------------------> RUNNING
                                    |
       work done, downstream full    |  work done, downstream has room
        +---------------------------+---------------------------+
        v                                                       v
     BLOCKED                                                  IDLE
        |  downstream frees                                     |  no unit upstream
        +--------------------> RUNNING                          v
                                                             STARVED
     any state --> DOWN (fault or andon stop) --> repaired --> previous
     any state --> CHANGEOVER (variant switch) --> RUNNING
     insufficient evidence --> IDLE_UNKNOWN
```

`IDLE_UNKNOWN` exists because a Tier C station with no flanking evidence may be idle for
a reason the twin cannot determine. It is displayed as such and never collapsed into
one of the known states.

### 4.2 Cycle-time distributions

Per station, per model variant, over a rolling window of `window_cycles` (default 200):

- Location: median.
- Scale: median absolute deviation, scaled by 1.4826 to be comparable with a standard
  deviation under normality.

Robust statistics rather than mean and standard deviation, because a single 6-minute
andon stop should not move a station's baseline. The distribution used by the DES is the
empirical distribution over the window, resampled, not a fitted parametric form. Fitting
a lognormal to a bimodal cycle time (two operators, two habits) is a classic way to
produce a confident wrong forecast.

Minimum 20 cycles before a station's distribution is usable. Below that, the station is
excluded from forecasting and the interface says how many cycles remain.

### 4.3 Virtual sensors for Tier C stations

For a dark station `k` with nearest instrumented upstream `u` and downstream `d`:

```
span_observed = ts_arrive(d, unit) - ts_depart(u, unit)
span_transport = sum(transport_time(i, i+1) for i in u..d-1)
span_work = span_observed - span_transport

cycle_time(k) in [ lo, hi ]
  where, if k is the only dark station between u and d:
      lo = span_work - sum(cycle_time(j) for j in u+1..d-1 if j is monitored).upper
      hi = span_work - sum(cycle_time(j) for j in u+1..d-1 if j is monitored).lower
  and if m dark stations share the span:
      the bound applies to their sum, and each station's individual bound is
      [ max(0, sum_lo - (m-1) * max_plausible), sum_hi ]
      which widens quickly with m. This is correct and it is shown.
```

**Blocking and starving attribution.** During `span_work`, if the buffer downstream of
`d` was at capacity, the excess is attributed to blocking; if the buffer upstream of `u`
was empty, to starving; otherwise to work. Where the flanking buffers give no signal,
the attribution is `UNKNOWN` and the interface says the three states cannot be
separated.

**Unresolvable case (STA-07).** Two or more adjacent Tier C stations with no scan point
between them yield a bound on their sum but not on either individually. Both are marked
`UNRESOLVED` and a Sensor Value Card is generated naming the scan point that would fix
it. No number is invented.

Every output of this module is an `Estimate` with `provenance = "INFERRED"` and a
confidence derived from the interval width relative to the station's plausible range.

---

## 5. Bottleneck forecasting

### 5.1 The discrete-event forecast

```
Inputs:  LineState at t0, cycle-time distributions, transport times, buffer
         capacities and occupancy, in-process units, upcoming variant sequence,
         failure and repair distributions per station
Method:  SimPy model, R replications (default 200), horizon H (default 120 min)
Seeds:   replication r uses seed = hash(cycle_id, r), so a cycle is reproducible
Outputs: per station per 5-min bucket:
           P(blocked), P(starved), E[buffer occupancy] with quantiles
         line level:
           distribution of cumulative output over H
           P(line stop) by bucket, where a stop is any station BLOCKED or STARVED
           for longer than stop_threshold_s (default 180)
```

Replications run in a process pool across available cores. If the wall-clock budget
(`forecast_budget_s`, default 20) is exceeded, R is reduced for the next cycle by 25
percent and the widened intervals are surfaced.

**Drifting stations are extrapolated, not frozen.** Where the drift detector reports a
sustained shift at station `k` with slope `m`, the forecast samples that station's cycle
time from its recent window shifted forward by `m * t`. Without this the DES would
predict from the drifting station's historical distribution and would systematically
under-predict the stall. This is the single most important detail in the forecaster.

### 5.2 Constraint attribution: average active period

Following Roser, Nakano and Tanaka, and the data-driven extension by Subramaniyan et al.
(S-06 to S-09):

```
An active period for station k is a maximal interval during which k is not
blocked and not starved (it is working, changing over, or down under its own
fault, but not waiting on a neighbour).

Over a rolling window W (default 60 min):
    avg_active(k) = mean duration of k's active periods in W

The momentary constraint is argmax_k avg_active(k).
Shift boundaries reset the accumulator rather than spanning it, since a two-shift
line does not satisfy the continuous-operation assumption in the original method.
```

The attribution reported to the user combines this with buffer trend: the constraint is
the station with the highest average active period whose downstream buffer is filling or
whose upstream buffer is emptying. Where the two signals disagree, both are reported
rather than one being chosen silently.

### 5.3 Drift detection

Per station per variant, on cycle time, two charts running in parallel:

**EWMA**
```
z_t = lambda * x_t + (1 - lambda) * z_{t-1},   lambda = 0.2
sigma_z = sigma * sqrt(lambda / (2 - lambda) * (1 - (1-lambda)^(2t)))
signal when |z_t - mu| > L * sigma_z,   L = 3.0
```

**CUSUM (tabular, two-sided)**
```
C+_t = max(0, C+_{t-1} + (x_t - mu) - k)
C-_t = max(0, C-_{t-1} - (x_t - mu) - k)
k = 0.5 * sigma       (tuned for a 1-sigma shift)
signal when C+ or C- > h,   h = 5 * sigma
```

`mu` and `sigma` come from the robust estimates in Section 4.2, computed over a
reference window that excludes the current suspected drift.

**Onset estimation.** CUSUM gives it directly: the last time the relevant cumulative sum
was zero. This is what allows the interface to say "drifted since 09:14" rather than
"drift detected at 09:26", and the difference matters to a supervisor deciding what
changed.

**Both charts must signal** before a `DRIFT` event is emitted. Requiring agreement
roughly halves the false positive rate at a small cost in detection delay, and given
what false alarms cost here (S-16 to S-19) that is the right trade.

Parameters are per-line configurable and their defaults are recorded in
`config/lines/*.yaml`, not in code.

---

## 6. Defect risk model

### 6.1 Features

Assembled per unit per candidate gate from the `ProcessSignature`.

| Group | Features |
|---|---|
| Timing | Per visited station: cycle-time z-score against that station's robust baseline for that variant; dwell time; starve time; blocked time. Aggregates: max z, count of stations above 2 sigma, sum of positive z |
| Process values | For Tier A stations: torque peak and angle residual against the station's rolling distribution, current draw residual, vibration RMS residual, dimensional residual. Aggregated as max, mean and count above threshold |
| Environment | Zone temperature and humidity at the time the unit was in the zone, and their deviation from the zone's rolling normal |
| Materials | Part lot identifiers as categorical features, plus a lot-level rolling failure rate computed from units already through the gate |
| Human and schedule | Shift, operator group, time since shift start, time since last break, position in the changeover sequence |
| Rework | Count and location of prior rework events on this unit |
| Observability | Count of dark stations visited, total inferred dwell, mean interval width across inferred values, and a per-tier visit count. **Missingness is a feature** |
| Variant | Model variant as a categorical feature, and its share of the recent mix |

### 6.2 Model

- LightGBM binary classifier per gate (G1, G2, G3). Separate models, because the causal
  paths differ and a single multi-label model would blur them.
- Class imbalance handled with `scale_pos_weight`, not with resampling. Resampling
  distorts the probabilities we then have to calibrate.
- Native categorical handling for lots, variants and shifts.
- Native missing-value handling. No imputation anywhere in the pipeline: a missing value
  means the station was dark or the sensor was absent, and that is information.
- Training split is temporal, never random. A random split leaks the future through
  shared lots and shared drift episodes, and would produce an evaluation number that
  cannot be reproduced in production.

### 6.3 Calibration

Isotonic regression on a held-out temporal fold. Reported as a reliability diagram with
expected calibration error, target ECE <= 0.05 (PRD Section 5). If ECE exceeds the
target, the model is not promoted, because an uncalibrated probability shown as a
probability is a lie in a product whose argument is honesty.

### 6.4 Conformal intervals

Split conformal on the calibration fold:

```
Calibration scores s_i = 1 - p_hat(y_i | x_i)  for the true class
q = the ceil((n+1)(1-alpha))/n quantile of s,  alpha = 0.10
Prediction interval covers all classes y with 1 - p_hat(y|x) <= q
```

Reported to the user as an interval on the failure probability. Coverage is verified on
a held-out fold and reported in the evidence pack. Conformal gives distribution-free
coverage, which is what we want under severe class imbalance where a Bayesian
posterior's calibration would depend on assumptions we cannot check (S-20 to S-23).

### 6.5 Explanations

SHAP TreeExplainer, top three features by absolute contribution, translated into plant
language by a template registry:

```python
FACTOR_TEMPLATES = {
  "torque_resid_max": "torque at {station} ran {z:.1f} sigma {dir} "
                      "for the last {n} units",
  "lot_failure_rate": "part lot {lot}",
  "dwell_z_max":      "dwell at {station} was {delta:.0f} s above normal",
  "dark_visits":      "{n} stations on this unit's route have no machine data",
  "humidity_dev":     "paint zone humidity ran {delta:.0f}% above normal "
                      "while this unit was in the booth",
}
```

A feature without a template cannot be surfaced. This forces every explainable factor to
have been thought about in plant terms before it can appear on a screen.

---

## 7. Retro-trace and containment

```
Given a failed unit f at gate G:

1. For each station s that f visited, compute the divergence of f's signature at s
   from the contemporaneous population (units through s within +/- 30 min):
       div(s) = max over features of |z_f(s) - median z_pop(s)| / MAD z_pop(s)

2. Rank stations by div(s). The top station is the leading hypothesis, and stations
   within 20 percent of the top are co-hypotheses. Multiple hypotheses are reported,
   ranked, never collapsed to one.

3. For the leading hypothesis station s* and window [t_f - w, t_f + w] (w default
   90 min, extended to cover the full lot if a lot is implicated):
       candidates = units through s* in the window
       similarity(u) = cosine similarity of u's divergence vector at s* to f's

4. Containment list = candidates with similarity above tau (default 0.75), split:
       Tier 1: still on the line          (actionable now)
       Tier 2: in the yard, not shipped   (actionable today)
       Tier 3: shipped                    (export only)

5. Each row carries its evidence: which features diverged and by how much.
```

Labelled in the interface as a ranked hypothesis with a strength, never as a root cause.
Intermittent and multi-causal problems are the normal case and the product says so
(RTR-04).

---

## 8. Counterfactual engine

The same DES with an intervention overlay applied to the seeded state.

| Intervention | Model change |
|---|---|
| Add or remove an operator at station k | Scale k's cycle-time distribution by a configured factor (default 0.88 for adding one operator at a manual station), and reduce its variance by the configured factor. Both are per-station configurable, because the effect of a second pair of hands is not universal |
| Change takt by p percent | Scale the line's pull rate |
| Resequence the model mix | Replace the upcoming variant sequence |
| Change a buffer target | Change the buffer's effective capacity |
| Take a station down for N minutes | Force `DOWN` for the interval |

**Comparison protocol.** The baseline and the intervention run on the same seeds, so the
difference is not contaminated by simulation noise. This is a common variance reduction
technique and it is what makes a `+9 units` difference meaningful at 200 replications
rather than 2000.

Latency budget 5 s. If exceeded, R reduces adaptively and the interface says so
(CFA-03).

---

## 9. Trust ledger

### 9.1 Record

```python
@dataclass(frozen=True)
class Prediction:
    prediction_id: UUID
    predictor: str            # "stall_forecaster", "defect_risk_g3", "drift_detector"
    model_version: str
    line_id: str
    station_id: str | None
    unit_id: str | None
    made_at: datetime
    horizon_end: datetime
    claim: dict               # what was predicted, typed per predictor
    confidence: float
    evidence: dict            # what it was based on, shown in the interface
    inputs_hash: str          # so a prediction can be reproduced
    published: bool           # false while the predictor is in SHADOW
```

Append-only. Never updated. The outcome is a separate row keyed to the prediction.

### 9.2 Outcome joining

A job runs each cycle over predictions whose `horizon_end` has passed:

| Predictor | Outcome rule |
|---|---|
| `stall_forecaster` | True positive if a stop of at least `stop_threshold_s` occurred at or downstream of the predicted station within the predicted window extended by `tolerance_min` (default 10). False positive otherwise. A stop with no forecast in scope is a false negative |
| `defect_risk_*` | Outcome is the actual gate result for that unit |
| `drift_detector` | True positive if the station's baseline in the following window differs from the preceding baseline by at least the reported magnitude, in the reported direction |
| `counterfactual` | Scored only where the user marked "we did this". Compared against the modelled effect, and reported as an interval overlap rather than as a point hit |

No human labels anything in the core loop. That is what makes the scorecard credible.

### 9.3 Gates

```python
PROMOTION = {"min_predictions": 20, "min_precision": 0.70, "min_recall": 0.50}
DEMOTION  = {"min_predictions": 10, "max_precision": 0.55}
WINDOW    = timedelta(days=14)
```

Per predictor per station. Promotion and demotion both write a state-change record with
the numbers that caused it, which is what the interface reads when it tells the floor
that a predictor was withdrawn and why.

Gates are configurable per line in `config/lines/*.yaml`. The defaults above are our
starting position and are informed by the alarm-fatigue literature rather than measured
(USER_RESEARCH.md Section 3, item 2).

---

## 10. Sensor value scoring

```
observability(k) = w1 * measured_share(k)
                 + w2 * (1 - normalised_interval_width(k))
                 + w3 * signal_coverage(k)      # process values available / expected

criticality(k)   = share of forecast stalls in the last 30 days where k lay on the
                   critical path
                 + share of defect predictions whose conformal interval width was
                   materially reduced in a leave-one-station-out ablation

For each k with observability below theta and criticality above phi:
    for each option in the sensing catalogue applicable to k:
        projected_confidence = model of what that signal resolves
        cost, install_effort, window = from the catalogue
    choose the cheapest option reaching the target confidence
    modelled_value = criticality * expected_unit_loss_avoided * unit_value
                     (reported as an interval, inheriting the forecast's uncertainty)
```

The sensing catalogue (`config/catalogue/sensors.yaml`) holds indicative costs for a
clamp-on current transducer, an accelerometer, a cycle photo-eye, a barcode or RFID scan
point, an ambient logger and a tablet check-capture app. Costs are indicative and
labelled as such.

`projected_confidence` is a model, and it is validated after install by comparing the
projection to the realised confidence (SNS-06). Until that validation exists, the
projection is shown as an estimate with a range.

---

## 11. Topology discovery

Input: a recorded canonical event stream. Output: a draft `LineDefinition.yaml` with a
confidence per inferred field.

| Inferred | Method |
|---|---|
| Station order | Median position of each station in unit visit sequences |
| Transport times | 5th percentile of observed inter-station gaps, on the assumption that the fastest observed handoff is close to pure transport |
| Buffer presence and capacity | Maximum observed count of units between two stations |
| Model variants | Distinct values in the build record |
| Inspection gates | Stations emitting `INSPECTION_RESULT` |
| Rework loops | Units revisiting an earlier station |
| Tier assignment | Which event types each station emits |
| Takt | Mode of the inter-departure interval at the last station |

Everything it cannot infer is left blank and marked for a human. The prototype runs this
against the simulator's own stream, which is a weak test and is described as such in
USER_RESEARCH.md Section 3.

---

## 12. Configuration files

`config/lines/line2.yaml`:

```yaml
line_id: line2
name: Line 2
takt_s: 60
shifts:
  - {id: A, start: "06:00", end: "14:30", break_min: 30}
  - {id: B, start: "14:30", end: "23:00", break_min: 30}
variants: [V-STD, V-SPT, V-LWB]
mix: {V-STD: 0.55, V-SPT: 0.30, V-LWB: 0.15}
zones:
  - {id: body,  name: Body construction, stations: [S01, S16]}
  - {id: paint, name: Paint,             stations: [S17, S26]}
  - {id: final, name: Final assembly,    stations: [S27, S42]}
stations:
  - {id: S01, tier: A, transport_to_next_s: 4.0}
  # ...
  - {id: S34, tier: C, transport_to_next_s: 4.2}
buffers:
  - {id: B5, after: S19, capacity: 12}
gates:
  - {id: G1, after: S16, name: Body-in-white}
  - {id: G2, after: S26, name: Paint inspection}
  - {id: G3, after: S42, name: Final QC}
rework:
  - {from: G1, to: S12}
forecast:
  horizon_min: 120
  cadence_s: 120
  replications: 200
  stall_threshold_s: 180
  stall_probability_threshold: 0.55
drift:
  ewma_lambda: 0.2
  ewma_L: 3.0
  cusum_k_sigma: 0.5
  cusum_h_sigma: 5.0
  require_both: true
gates_policy:
  promotion: {min_predictions: 20, min_precision: 0.70, min_recall: 0.50}
  demotion:  {min_predictions: 10, max_precision: 0.55}
  window_days: 14
```

No station ID, capacity or threshold appears anywhere in code.

---

## 13. Performance targets and how they are met

| Target | Approach |
|---|---|
| NFR-01: full forecast under 20 s | Replications across a process pool; the SimPy model uses primitive containers rather than object-per-unit where profiling shows it matters |
| NFR-02: counterfactual under 5 s | Common random numbers so fewer replications suffice; adaptive reduction with a visible note |
| NFR-03: 50 events/s ingest | Batched inserts, a single hypertable, no per-event ORM round trip |
| NFR-04: interactions under 150 ms | View state pushed over WebSocket; the client never computes a forecast |
| NFR-05: cold start under 5 min | Pre-built images, a seeded database dump, models trained ahead and committed as artefacts |
| NFR-07: determinism | Every random draw comes from a seeded generator keyed on `(cycle_id, replication)`. No use of the global RNG anywhere. Enforced by a lint rule |

---

## 14. What is specified but not built in the prototype

Stated plainly so no document implies otherwise.

| Specified here | Built? |
|---|---|
| `SimAdapter`, `CsvReplayAdapter` | Yes |
| OPC UA, MTConnect, Sparkplug B, historian adapters | No. Interfaces defined, INTEGRATIONS.md carries the design |
| Authentication, roles, SSO | No. SECURITY_REQUIREMENTS.md carries the design |
| Multi-line, multi-plant deployment | No. A second line config exists to prove ONB-04 |
| Sensor value realised-gain validation (SNS-06) | No. Requires an installed sensor |
| Topology discovery | Partial. Runs against the simulator's own stream only |

---

**Related:** [ARCHITECTURE.md](ARCHITECTURE.md) · [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) · [API_SPEC.md](API_SPEC.md) · [../product/PRD.md](../product/PRD.md) · [../quality/TEST_PLAN.md](../quality/TEST_PLAN.md)
