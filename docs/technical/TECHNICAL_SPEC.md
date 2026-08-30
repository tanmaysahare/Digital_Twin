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
    plantsim/line2.yaml      the simulator's own parameters. The twin never
    plantsim/line7.yaml      loads these: they are the answer, not the question
    plantsim/scenarios.yaml  SC-01 to SC-08 as configuration, not as code
  plantsim/
    parameters.py            the plant model, loaded from config/plantsim/
    model.py                 the SimPy line model
    scenarios.py             scenario injection
    emit.py                  canonical event emission with tier filtering
    truth.py                 ground-truth channel, written to a separate store
  connector/
    protocol.py              SourceAdapter and CanonicalEvent, read-only by
                             construction
    payloads.py              one pydantic model per canonical event type
    sim_adapter.py
    csv_replay_adapter.py
    normalise.py             reordering window, clock skew, health
  twin/
    config/
      line.py                LineDefinition and its policies
      sources.py             SourceMapping
      catalogue.py           the sensing catalogue
      loader.py              YAML loading, with errors that name the field
    db/
      schema.py              SQLAlchemy metadata, the declarative half of
                             DATABASE_SCHEMA.md
      engine.py              settings and the engine
      migration.py           running and comparing migrations
    domain/                  dataclasses: Estimate, LineState, ProcessSignature
      shifts.py              the production calendar, from the shift pattern
      seeds.py               deterministic seeding for every stochastic path
    state/estimator.py
    state/virtual_sensors.py
    state/distributions.py
    forecast/des.py            the tandem-line kernel and the seeded state
    forecast/aggregate.py      replications to probabilities
    forecast/attribution.py
    forecast/drift.py
    forecast/stall.py          the StallForecast, as it leaves the forecaster
    forecast/stops.py          what a stall is, and how the twin sees one happen
    defect/features.py
    defect/model.py
    defect/conformal.py
    defect/explain.py          SHAP and the plant-language template registry
    defect/risk.py             one risk per unit per gate, with its lead time
    pipeline.py                the one place the pieces meet
    retro/trace.py
    counterfactual/engine.py
    ledger/store.py
    ledger/gates.py
    sensors/value.py
    topology/discover.py
    api/                     FastAPI routers
    workers/cycle.py
  evaluation/
    harness.py                 scenario runs across a process pool
    metrics.py                 every figure PRD Section 5 asks for
    report.py                  the evidence pack and its own limitations
    run.py                     what `make evaluate` calls
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

For a run of `m` dark stations with the nearest instrumented station upstream `u` and
the nearest one downstream `d`, the twin has four things: the departure scan at `u`, the
arrival scan at `d`, the nominal transports from the `LineDefinition`, and unit
conservation. How many units are inside the span at any moment is the count that went in
less the count that came out, and that count is exact wherever both flanking sources are
complete.

```
transit    = ts_arrive(d, unit) - ts_depart(u, unit) - non_production_overlap
transport  in [ nominal * (1 - transport_tolerance),
                nominal * (1 + transport_tolerance) ]
work       in [ transit - transport.upper, transit - transport.lower ]

sum of the dark stations' cycle times in [ lo, hi ]
    hi = work.upper
    lo = work.lower                where free flow is certified
       = min(work.lower, floor)    otherwise
```

**The upper bound is sound.** A unit cannot have done more work than the time it spent,
and waiting is never negative.

**The lower bound is the difficult half**, and it is where the honesty of the module
sits. A unit that took 340 s across a span may have worked for 340 s or for 268 s, and
no timestamp at either end separates those. Two things bound it.

*Free flow.* If the span held only this unit for the whole passage and the station beyond
it was never occupied, the unit had nothing to wait for and `work.lower` holds. Both
conditions are observable: occupancy comes from conservation, and `d` is instrumented, so
when it was busy is a reading rather than a guess.

*The free-flow floor.* Otherwise the bound comes from the same reasoning Section 11 uses
for transport times: the quickest observed passage is close to pure work. The floor is
the `free_flow_quantile` of recent transits for the same variant, less
`free_flow_slack`. It is a statistical bound and not a guarantee, which is exactly why
the target in PRD Section 5 is coverage in 90 percent of cycles rather than in all of
them. Below `min_cycles` comparable passages there is no floor, the lower bound is only
that work is not negative, and the interface says how many cycles remain (EC-20).

Non-production time inside the passage is subtracted before any of this. A shift break
inside a span would otherwise read as slow work, and the shift pattern and the
`SHIFT_MARKER` stream both say when the line was stopped (EC-11).

**Several dark stations in one span.** The bound applies to their sum. Each station's own
bound is then

```
[ max(0, sum_lo - (m - 1) * max_plausible), sum_hi ]
      where max_plausible = takt_s * max_plausible_cycle_takts
```

which widens quickly with `m`. This is correct and it is shown.

**Blocking and starving attribution.** The bound on non-work always starts at zero,
because no pair of flanking timestamps can prove that a unit waited. What can be
established is that a passage took longer than the quickest comparable one, and that is
the evidence a label rests on:

| Label | Evidence |
|---|---|
| `WORK` | The passage is no longer than a free-flowing one |
| `BLOCKED` | It is longer, and the station beyond the span was occupied for at least the excess |
| `STARVED` | It is longer, and the span was empty when the unit entered, so its first station had been waiting |
| `UNKNOWN` | Anything else, which is most of a congested shift. Another unit shared the dark run and nothing at either end says which of the three states this one was in |

A label is only attempted where the span holds one dark station. Where it holds
several, the answer is always `UNKNOWN`: the station beyond the span is occupied for
most of a takt on any line running to takt, so its occupancy says nothing about which of
the unobserved stations delayed a unit, or whether any of them did. Measured against the
simulator on Line 2, a `BLOCKED` label on the five-station run agreed with the truth 73
percent of the time against a base rate of 72 percent.

The interface prints `UNKNOWN` rather than the most plausible of the three.

**Unresolvable case (STA-07).** Two or more adjacent Tier C stations with no scan point
between them yield a bound on their sum but not on any one of them. All of them are
marked `UNRESOLVED` and a Sensor Value Card is generated naming the scan point that
would fix it. No number is invented.

A dark station with no instrumented station on both sides of it gets nothing at all.
On Line 2 that is S42, which is dark and last: there is no second timestamp, so there is
no span, so there is no bound. It is reported as `UNRESOLVED` with the sensor that would
resolve it, and no cycle time appears for it anywhere.

**An inspection result is not a downstream anchor.** Its timestamp says when a verdict
was recorded, not when a unit stopped moving, and a gate carries a real latency. Using
one as a timing anchor would make the last dark station look monitored when it is not.
The same holds for a manual checklist result, which is filled in when the operator gets
to it.

**A dark run longer than the line allows is not modelled at all** (EC-18). Past
`max_dark_span` contiguous stations, the twin reports that the zone cannot be modelled
rather than producing an interval so wide it says nothing.

Every output of this module is an `Estimate` with `provenance = "INFERRED"` and a
confidence derived from the interval width relative to the station's plausible range.

---

## 5. Bottleneck forecasting

### 5.1 The discrete-event forecast

```
Inputs:  LineState at t0, cycle-time distributions, transport times, buffer
         capacities and occupancy, in-process units, upcoming variant sequence
Method:  tandem-line event recursion, R replications (default 200),
         horizon H (default 120 min)
Seeds:   replication r uses seed = hash(cycle_id, r), so a cycle is reproducible
Outputs: per station per 5-min bucket:
           P(stall), P(blocked), P(starved), E[buffer occupancy] with quantiles
         line level:
           distribution of cumulative output over H
           P(line stop) by bucket
```

**What a stop is.** A stall at station k over a five-minute bucket is: the
production time k lost to blocking or starving inside that bucket exceeds
`stall_threshold_s`. This sentence used to read "any station BLOCKED or STARVED
for longer than `stop_threshold_s` (default 180)", and on a paced line those two
readings are not the same thing. A station whose work content is under takt waits
a few seconds on every single cycle, because that is what takt means, so a
*continuous* wait past a threshold happens only inside a long repair. Measured on
Line 2 over a full simulated day, the only continuous waits past 180 s were the
line filling at the start of the run, identical in the fault scenarios and in the
null one, carrying no information at all. The accumulated wait inside a bucket is
what a supervisor recognises as the line falling behind and it is what a drifting
station actually produces, so that is the reading implemented, in the forecast, in
the twin's own observation and in the evaluation harness alike. If those three
disagreed, every precision figure in the evidence pack would be measuring three
different things.

`stall_threshold_s` is per line and is calibrated against that line's own physics
rather than carried over as a round number. It has to sit above the routine idle
of the least loaded station, which is a fixed share of every bucket, and below
what a supervisor would call a stoppage. On Line 2 a station's lost time per
bucket runs to a median of 53 s and a 99th percentile of 116 s on a quiet shift,
and the configured value is 140 s: nearly half the bucket, about four and a half
occurrences a shift across the whole line, and roughly doubled by the fault
scenarios.

**The forecast is not run while any station is still learning.** A station below
`min_cycles` has no baseline and the flow model falls back to takt for it.
Blocking and starving propagate the length of the line, so one assumed station
makes every station's forecast an assumption. The cycle produces no stall claim
at all and the interface says how many cycles remain (EC-20).

**A stall is never claimed at a station nothing watches.** The six dark stations
are in the flow model and cause stalls at the instrumented stations around them,
which is where the claim is made. A claim at S34 could never be confirmed or
refuted, and the ledger exists to make every claim checkable.

**Uncertainty about a dark station is not variability of it.** A dark station's
bound is what the twin does not know about a station that is the same station all
afternoon. A replication draws one position inside that bound and holds it for the
whole run, so the width of the bound comes out as spread across replications
rather than as spread within one. Drawing a fresh point per unit treats epistemic
uncertainty as process variability, and queueing is convex in variability: the
forecast then manufactures congestion inside the dark run that the real line does
not have. Measured on Line 2 it predicted about 170 s lost per bucket at each of
S33 to S37 while those stations were running perfectly well.

**The rare tail is held apart from the rolling window.** A station that fails once
in five thousand cycles has a four percent chance that any given 200-cycle window
holds one of those failures. Where it does, resampling that window gives the
station a failure every two hundred cycles, twenty-five times its real rate; where
it does not, the forecast believes the station never fails at all. Averaged over
the line the two errors cancel, which is why the forecast's mean lost time looked
well calibrated while its alarms were noise. The window is therefore split: the
core is resampled, and the rare component is drawn at a rate estimated over the
station's whole history, pooled with the line's where the station has not been
watched long enough to have one of its own.

Replications run across available cores. If the wall-clock budget
(`forecast_budget_s`, default 20) is exceeded, R is reduced for the next cycle by
25 percent and the widened intervals are surfaced.

**On the kernel.** ARCHITECTURE.md Section 9 chose SimPy for this forecast, and
that choice does not survive its own performance target. `plantsim` runs about
1,300 station visits a second, and one replication of a 120 minute horizon over 42
stations is about 6,000 visits, so 200 replications would take some fifteen
minutes against the 20 second budget in NFR-01. `twin/forecast/des.py` is
therefore a hand-written event recursion for a tandem line with finite links,
which is the standard formulation for blocking-after-service and is exact for the
same model `plantsim` assembles out of SimPy primitives. `plantsim` keeps SimPy,
where fidelity matters more than speed and where being a different implementation
from the forecaster is a feature rather than a cost.

**Measured behaviour, Line 2.** The forecaster is close to silent on a line where
nothing is wrong: over a quiet shift, fewer than one station-cycle in four
thousand crosses the probability threshold. Under SC-01 the probability at the
stations downstream of the drift goes to near one across the whole horizon. The
discrimination is sharp. What the forecast cannot do on this line is say *when*,
because the stalls it is scored against are largely repair-driven and no forecast
seeded from the current state can foresee a random failure. The evidence pack
reports both halves of that rather than the flattering one.

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

The two estimates need very different amounts of data, and treating them as one
number makes the chart either blind or noisy. `mu` is a median, which is cheap:
25 cycles put its own standard error near a fifth of a sigma. It is per variant,
because a long-wheelbase body genuinely takes longer at the same station. `sigma`
is a median absolute deviation, which is expensive: from 20 points its standard
error is about 20 percent of itself, and the whole of the chart's arithmetic is in
units of it, so an underestimate shrinks `k` and `h` together and the chart
signals on ordinary noise. Measured on a stable simulated station, a 20-cycle
reference produced a first signal at cycle 50 on a process that never moved.
`sigma` is therefore estimated from 100 cycles and pooled across the variants at a
station, on the relative deviation from each variant's own median: the spread of a
station's cycle time is a property of its fixture and its operator rather than of
the body on it, and pooling reaches a usable estimate three times sooner.

The exponentially weighted average starts at the target rather than at the first
observation. Seeding it with the observation makes the statistic equal to that
observation while its own standard deviation is still a fifth of the process
sigma, and the chart then signals on the first cycle after any reset more than
half the time. Both charts reset together when an episode closes, because an
average that still carries the old episode re-signals the moment the cumulative
sum next crosses, and one drift is then reported as four.

**Onset estimation.** CUSUM gives it directly: the last time the relevant cumulative sum
was zero. This is what allows the interface to say "drifted since 09:14" rather than
"drift detected at 09:26", and the difference matters to a supervisor deciding what
changed.

**Both charts must signal** before a `DRIFT` event is emitted. Requiring agreement
roughly halves the false positive rate at a small cost in detection delay, and given
what false alarms cost here (S-16 to S-19) that is the right trade.

**A signal is not a slope.** Whether a station has moved and whether the move is
worth forecasting from are two questions. The forecaster extrapolates only where
the movement is at least as large as the station's own noise. A chart pair tuned
to catch a one-sigma shift signals on an in-control process every couple of
hundred cycles by construction, and across 42 stations and three variants that is
several a shift. Those signals belong in the ledger, where they are scored and
where a station that produces them keeps its predictor in shadow. They do not
belong in the forecast's extrapolation, where a spurious slope on eleven stations
at once turns a useful forecast into a wall of alarm. The evidence pack prints the
drift detector's measured false positive rate rather than only its hit rate.

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
state:
  window_cycles: 200
  min_cycles: 20
  # How far a real transport may sit either side of the nominal one. This is why
  # a lone dark station between two instrumented ones still yields an interval.
  transport_tolerance: 0.15
  max_plausible_cycle_takts: 2.5
  # The free-flow floor in Section 4.3. Tuned against the simulator: at the
  # first percentile with a ten percent slack the derived interval contains
  # ground truth in about 97 percent of cycles.
  free_flow_quantile: 0.01
  free_flow_slack: 0.10
  max_dark_span: 6
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

`config/plantsim/*.yaml` holds the simulator's own parameters: true cycle times,
failure and repair distributions, defect causes, environment, materials and the
plant's unit identifier scheme. The twin never loads them, for the same reason
the ground truth they produce lives in a database schema the twin's role cannot
read. `config/plantsim/scenarios.yaml` holds SC-01 to SC-08, so a scenario is a
row in a file rather than a branch in the simulator.

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
