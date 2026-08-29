# TASKS.md

**Purpose:** the ordered task list. Work through it in order. Each task states its dependencies, the acceptance criteria it satisfies, and how it is verified.
**Convention:** `T-nnn`. Dependencies are hard: do not start a task whose dependencies are open.
**Sizing:** S is under 2 hours, M is half a day, L is a full day.
**Last updated:** 2026-08-28

---

## Phase 0: Foundation

| ID | Task | Size | Depends | Verify |
|---|---|---|---|---|
| T-001 | Initialise the repository, licence, `.gitignore`, `README.md` skeleton, `Makefile` | S | | `make` targets exist and print help |
| T-002 | GitHub Actions workflow running `make lint` and `make test` | S | T-001 | A trivial commit passes CI |
| T-003 | `docker-compose.yml` with `db`, `api`, `worker`, `web`, `sim` | M | T-001 | `docker compose up` starts all five on a clean machine |
| T-004 | Document and test the non-Docker path | S | T-003 | A teammate without Docker can run it |
| T-005 | `web/src/styles/tokens.css` from DESIGN_SYSTEM.md Section 11 | S | T-001 | Every token present, no dark block |
| T-006 | Lint suite: em dash, emoji, banned words, gradient, blur, radius, dark theme, raw colour, placeholder content, unseeded random, external network reference | L | T-002, T-005 | Each rule has a fixture that fails and a fixture that passes. AC-100 |
| T-007 | Alembic setup and the full schema from DATABASE_SCHEMA.md | L | T-003 | Migrations apply and roll back cleanly |
| T-008 | Separate truth schema with its own role and no grant to the application role | S | T-007 | A test asserts permission is denied. AC-104 |
| T-009 | Append-only trigger and role grants on `prediction` and `prediction_outcome` | S | T-007 | UPDATE and DELETE raise |
| T-010 | `LineDefinition` and `SourceMapping` pydantic models and YAML loader | M | T-001 | Invalid configuration produces a readable error naming the field |
| T-011 | `config/lines/line2.yaml`, the 42-station reference line | M | T-010 | Loads and validates |
| T-012 | `config/lines/line7.yaml`, a structurally different second line | S | T-010 | Loads and validates. Different station count, different zone structure, different tier distribution |
| T-013 | `config/catalogue/sensors.yaml` with indicative costs and their sources | S | T-010 | Every entry carries a `source` field |

**Phase 0 exit:** T-001 to T-013 closed. `make lint` green on an empty codebase.

---

## Phase 1: The line runs

| ID | Task | Size | Depends | Verify |
|---|---|---|---|---|
| T-020 | SimPy line model: stations, buffers, transports, takt, shifts | L | T-011 | A day runs to completion, output within 5 percent of nominal |
| T-021 | Model variants and mix scheduling | M | T-020 | Observed mix matches the configured mix |
| T-022 | Cycle-time distributions per station per variant, with breakdowns and repairs | M | T-020 | Sampled distribution matches configuration over 10,000 draws |
| T-023 | Inspection gates, defect generation with realistic causes, rework loops | L | T-021 | Base failure rate matches configuration; causes are traceable in ground truth |
| T-024 | Ground truth channel writing to the truth schema | S | T-023, T-008 | Truth rows exist and the application role cannot read them |
| T-025 | Observability tier filtering on event emission | M | T-020 | Tier C stations emit zero machine events, asserted by scanning the stream |
| T-026 | Deterministic seeding throughout the simulator | S | T-020 | Two runs with the same seed are byte-identical |
| T-027 | Scenario SC-01, fixture wear drift | S | T-022, T-026 | Drift is present in ground truth and invisible to any threshold alarm |
| T-028 | Scenarios SC-02, SC-03, SC-04 | M | T-027 | Each changes only its intended parameter, verified against a control run |
| T-029 | Scenarios SC-05, SC-06, SC-07, SC-08 | M | T-028 | SC-06 injects nothing, which is the point |
| T-030 | Accelerated time mode, default 60x, capped to what the interface can follow | S | T-020 | 60x runs stably. EC-55 |
| T-031 | `SourceAdapter` protocol, read-only by construction | S | T-001 | Reflection test asserts no write method on any implementation. AC-082 |
| T-032 | `SimAdapter` | M | T-031, T-025 | Emits canonical events conforming to the schema |
| T-033 | `CsvReplayAdapter` with a speed multiplier | S | T-031 | Replays a recorded file deterministically |
| T-034 | Normalisation: reorder window, late flagging, recomputation trigger | M | T-032 | Out-of-order events release in order; late events flag and trigger recompute. EC-01 |
| T-035 | Clock skew estimation and reporting | M | T-034 | Recovers a known injected skew within 0.2 s |
| T-036 | Source health and data gap detection | M | T-034 | A silent source is reported after 3 takt periods, not before. EC-01, SC-07 |
| T-037 | `Estimate` type with mandatory provenance | S | T-001 | Cannot be constructed without a provenance |
| T-038 | State estimator: station state machine, buffers | L | T-034, T-037 | Every transition tested including `IDLE_UNKNOWN` |
| T-039 | Per-unit process signature accumulation | L | T-038 | A completed unit's signature matches its simulated route exactly |
| T-040 | **Virtual sensors for Tier C stations** | L | T-038 | Interval contains ground truth in at least 90 percent of cycles over 5,000 cycles. AC-005 |
| T-041 | Blocking and starving attribution at dark stations | M | T-040 | Matches ground truth where flanking buffers give a signal, returns `UNKNOWN` otherwise |
| T-042 | The unresolvable case: adjacent dark stations with no scan between | M | T-040 | Both marked `UNRESOLVED`, no point value emitted anywhere. STA-07, EC-17 |
| T-043 | Robust distribution fitting per station per variant | M | T-039 | Unaffected by a single 6-minute outlier; below 20 cycles the station is excluded |

**Phase 1 exit:** T-020 to T-043 closed. **Gate: if T-040's coverage is below 90 percent, stop and reassess before Phase 2.**

**Closed.** The gate passes. Over 5,000 cycles on both lines the derived interval
contains the simulator's ground truth in about 97 percent of cycles, against the 90
percent target in PRD Section 5. Four findings from the phase are recorded because they
changed the specification rather than only the code:

1. **The bound in TECHNICAL_SPEC.md Section 4.3 could not be implemented as written.** It
   defined `u` and `d` as the nearest instrumented stations either side of a dark run,
   then subtracted the cycle times of monitored stations between them. By that
   definition there are none, so the sum was always empty and the bound collapsed to
   `lo = hi = span_work`: a point value for a dark station, which contradicts rule 3 in
   CLAUDE.md, STA-04's own wording, and the closing line of the same section, which
   derives a confidence from the interval width. Section 4.3 is rewritten around what
   the evidence actually supports.
2. **A gate result is not a timing anchor.** An inspection verdict carries the latency of
   the inspection, so using it to bound a cycle time would make the last dark station
   look monitored. S42 therefore has no downstream scan at all and yields no number,
   which is the honest outcome and generates a Sensor Value Card rather than a bound.
3. **The lower bound on a dark span is statistical, not structural.** No pair of flanking
   timestamps can separate a long passage from a slow one. The bound comes from the
   quickest comparable passage recently seen, which is why the target is coverage in 90
   percent of cycles rather than in all of them. TECHNICAL_SPEC.md Section 4.3 now says
   so explicitly.
4. **Blocking cannot be attributed on a span of several dark stations.** Measured against
   the simulator, a blocked label on the five-station run agreed with the truth 73
   percent of the time against a base rate of 72 percent. It carried no information, so
   the span reports `UNKNOWN`. On a separable span the same label agrees 81 percent of
   the time against a 75 percent base rate and is kept.

---

## Phase 2: Prediction and evidence

| ID | Task | Size | Depends | Verify |
|---|---|---|---|---|
| T-050 | DES forecaster seeded from live state | L | T-038, T-043 | Reproduces analytic behaviour on a two-station line |
| T-051 | Monte Carlo replication across a process pool | M | T-050 | 200 replications, 120 min, 42 stations in under 20 s. NFR-01 |
| T-052 | **Drift extrapolation in the forecast** | M | T-050, T-055 | Forecast differs measurably from a control with extrapolation disabled. TECHNICAL_SPEC 5.1 |
| T-053 | Forecast aggregation: per-station bucket probabilities, buffer trajectories, output distribution | M | T-051 | Matches BTL-02 |
| T-054 | Average active period attribution with shift-boundary reset, plus buffer trend | L | T-050 | Identifies the constraint on a synthetic line with a known bottleneck. AC-013 |
| T-055 | EWMA and CUSUM drift detection, both required to signal, with onset estimation | L | T-043 | Detects a 1-sigma shift within the documented delay; onset within 5 min. AC-014 |
| T-056 | `StallForecast` emission with cause, window, probability and expected loss | M | T-053, T-054 | AC-010, AC-015 |
| T-057 | Ledger store: append-only prediction records with inputs hash | M | T-009, T-037 | Written at emission, before any publication decision. AC-011 |
| T-058 | Automatic outcome joining for every predictor type | L | T-057 | Each documented rule produces the correct result class |
| T-059 | `missed_event` recording so recall is computable | M | T-058 | A constructed case shows precision and recall diverging. EC-26 |
| T-060 | `UNSCOREABLE` handling for gaps, scrapped units and prevented stalls | M | T-058 | EC-25, EC-33, EC-46 |
| T-061 | Promotion and demotion gates with hysteresis and cooling period | L | T-058 | AC-041, AC-042, EC-44 |
| T-062 | Scorecard aggregation including recall from `missed_event` | M | T-059, T-061 | A test asserts recall is not computable from predictions alone |
| T-063 | Defect feature assembly including missingness features | L | T-039 | Produces the documented feature set; NaN counts survive |
| T-064 | LightGBM per gate with a temporal split | L | T-063 | No unit or lot spans the split boundary |
| T-065 | Isotonic calibration and reliability reporting | M | T-064 | ECE at or below 0.05. AC-024 |
| T-066 | Split conformal intervals | M | T-065 | Empirical coverage at least 0.90 at alpha 0.10 |
| T-067 | SHAP top-3 with the plant-language template registry | M | T-064 | An untemplated feature cannot surface. AC-022 |
| T-068 | Defect risk emission with lead time in stations and minutes | M | T-066, T-057 | AC-020, AC-023 |
| T-069 | **Evaluation harness: scenario runs, ledger to truth join, all metrics** | L | T-024, T-058 | AC-090 |
| T-070 | Evaluation report generation with figures and a limitations section | M | T-069 | AC-091, AC-093, and the report writes its own limitations |
| T-071 | Determinism verification across the whole pipeline | S | T-069 | Two runs produce identical metrics. AC-103 |

**Phase 2 exit:** `make evaluate` reports real numbers for every metric in PRD Section 5. **Gate: if median lead time is under 15 min or precision is under 0.60, stop and diagnose before Phase 3.**

**Closed, and the gate does not pass.** `make evaluate` runs and reports every
metric. The stall forecaster's precision and lead time are both below the gate,
and the diagnosis is in `evaluation/report.md` Section 10 and summarised here.
Phase 3 does not start until the decision in point 5 below is taken.

Seven findings from the phase are recorded because each of them changed the
specification, the configuration or the simulator rather than only the code.

1. **The stall definition in TECHNICAL_SPEC.md Section 5.1 could not be measured
   as written.** "Any station BLOCKED or STARVED for longer than 180 s" does not
   happen on a paced line: a station under takt waits a few seconds on every
   cycle by construction, so a continuous wait past a threshold occurs only inside
   a long repair. Over a full simulated day the only such episodes were the line
   filling at the start of the run, identical in the fault scenarios and in the
   null one. Section 5.1 now defines a stall as the production time a station
   loses inside a five-minute bucket, and `stall_threshold_s` on Line 2 is
   calibrated against that line's own distribution at 140 s rather than left at
   180.

2. **Two defects in the Phase 1 simulator corrupted every Phase 2 number.** A
   `cycle_drift` reverted at the end of its ramp, so SC-01 was a fault that healed
   itself after 90 minutes and disappeared before a 120 minute forecast horizon
   could close on it; a ramp now holds at its target, because a worn fixture stays
   worn. And a station waiting for the first unit of the run was recorded as
   starved, which put a 20 minute stop in the ground truth of every station on
   every run and swamped every genuine stop the evaluation was meant to count.

3. **The canonical event order was wrong at a hand-off.** `UNIT_ARRIVE` sorted
   before `UNIT_DEPART` on a shared timestamp, so the next unit's arrival was
   recorded and the previous unit's departure then cleared it. The twin saw 20 of
   42 stations holding a unit where 31 really were, and every forecast seeded from
   that state predicted a starvation wave rolling down a line that was running
   perfectly well. A station gives its unit up before it takes the next one, and
   `plantsim/emit.py` now says so.

4. **Every draw in the simulator is keyed on the unit it is about.** With a
   sequential stream per station, one unit scrapped at G2 shifted every subsequent
   draw at every station past S26, and a scenario then differed from its control
   everywhere downstream of the divergence rather than only where it was injected.
   Measured on SC-01, that showed as changed cycle times at seventeen stations
   when only S20 had been touched. Keyed on the unit, the same comparison changes
   exactly S20.

5. **A stall on this line is mostly an unpredictable event, and that is the
   finding the gate rests on.** The events the forecaster is scored against are
   dominated by the tail of the repair-time distribution. A drifting station
   roughly doubles their frequency but does not schedule one, so a forecast seeded
   from the current state can raise the probability of a stall in a region and a
   window and cannot pinpoint one 20 to 40 minutes ahead. The forecaster
   discriminates sharply between a quiet line and a drifting one, and its false
   alarm rate on a quiet shift is inside the PRD target; its precision and its
   lead time are not. What the twin can say on this line, and says correctly, is
   which station has become the constraint and what the line will lose because of
   it. Whether to change the reference line's parameters so that drift produces a
   genuine stoppage, or to change what the stall forecaster claims, is a product
   decision and it is open.

6. **Four modelling errors in the forecaster, each measured before it was fixed.**
   A stall claimed at a station nothing watches can never be checked. A rolling
   window misrepresents a rare heavy tail by a factor of twenty-five in either
   direction. A dark station's bound is uncertainty about a station, not
   variability of it, and sampling it per unit manufactured congestion inside the
   dark run. And the flow model cannot be run at all while a station is still
   learning its baseline, because one assumed station makes every station's
   forecast an assumption. All four are recorded in TECHNICAL_SPEC.md Section 5.1.

7. **The average active period needs the period that is still open.** The
   constraint's active periods merge across cycles precisely because it never
   waits, so on a line where one station has worked without a break for three
   hours it has a single unclosed period. Counting only closed periods dropped the
   bottleneck out of the ranking entirely: measured on SC-01, S20's active period
   ran to 11,330 s and the method named S11 instead. Periods are now clipped to
   the window and the open one is counted, and the method names S20 with its
   average an order of magnitude above the next station.

---

## Phase 3: Line view

| ID | Task | Size | Depends | Verify |
|---|---|---|---|---|
| T-080 | API: `/lines`, `/lines/{id}/state` | M | T-038 | Matches API_SPEC Section 2 |
| T-081 | API: `/actions`, `/units-at-risk`, `/forecast`, `/predictions/{id}/evidence` | M | T-056, T-068, T-061 | Shadow-mode filtering enforced server-side. AC-041 |
| T-082 | WebSocket with sequence numbers and heartbeat | M | T-080 | A gap triggers a full re-fetch. EC-52 |
| T-083 | `ProvenanceMark`, `IntervalBar`, `RangePlot`, `MetricLine`, `StateChip`, `Notice`, `Button`, `Select`, `NumberField` | L | T-005 | Each renders its calm state first |
| T-084 | `DataTable` with both densities | M | T-083 | No pagination, no zebra, right-aligned mono numerics |
| T-085 | `TimeSeriesChart`, `StackedBar` | M | T-083 | Step interpolation, zero-based axis, direct labels, no legend |
| T-086 | `StationSegment`, `BufferBlock`, `ForecastTrack` | L | T-083 | Tier C shows an interval and a cross-hatch |
| T-087 | `LineStrip` with roving tabindex and arrow navigation | L | T-086 | 42 stations at 1440 without scrolling. AC-001 |
| T-088 | `ActionCard` with the calm variant and evidence expansion | L | T-083 | Calm state matches WIREFRAMES/02. AC-016 |
| T-089 | At-risk table region | M | T-084 | Eight rows plus a count. EC-48 |
| T-090 | Output, predictor record and data health regions | M | T-083 | AC-008, AC-040, AC-043 |
| T-091 | `Drawer` with focus trap and Escape | M | T-083 | No keyboard trap |
| T-092 | Station drawer, both variants | L | T-091, T-086 | The dark variant matches WIREFRAMES/05 Variant B. AC-007 |
| T-093 | `SignatureTimeline` and the unit drawer | L | T-091 | Dark stations hatched, gates as full-width rules |
| T-094 | Counterfactual engine with common random numbers | L | T-050 | Baseline and options share seeds |
| T-095 | Counterfactual API and adaptive replication reduction | M | T-094 | Under 5 s, or degraded with a stated reduction. AC-032 |
| T-096 | `SandboxOverlay` with up to three compared options | L | T-095, T-083 | AC-030, AC-031, AC-033 |
| T-097 | Retro-trace: backward divergence walk and co-hypotheses | L | T-039 | AC-026, AC-029, EC-34, EC-35 |
| T-098 | Containment list with tiers and CSV export | M | T-097 | Recall at least 0.80 on SC-02. AC-027, AC-028 |
| T-099 | Sensor value scoring and card generation | L | T-040, T-056 | AC-050, AC-051 |
| T-100 | `SensorValueCard` component | M | T-099, T-083 | Matches WIREFRAMES/05 |
| T-101 | Responsive: desk, tablet, wall | L | T-087 | AC-002, target sizes at 1280, boundary disambiguation on the strip |
| T-102 | Accessibility pass on Line view | L | T-101 | AC-102, and the greyscale distinguishability test |

**Phase 3 exit:** demo script steps 1 to 9 run end to end without a terminal.

---

## Phase 4: Plan and Program views

| ID | Task | Size | Depends | Verify |
|---|---|---|---|---|
| T-110 | API: `/scorecard`, `/predictions`, `/sensor-recommendations` | M | T-062, T-099 | Shadow entries return no precision. API_SPEC Section 6 |
| T-111 | `Heatmap` and the constraint migration region | M | T-084 | Greyscale density, direct labels, no legend. AC-060 |
| T-112 | Loss Pareto with the reconciliation line | M | T-085 | Reconciliation is mandatory and visible. AC-061 |
| T-113 | Recommendations table with inline assumptions and sandbox links | M | T-084, T-096 | AC-062 |
| T-114 | Sensor investment queue with export | M | T-100 | AC-052 |
| T-115 | Full predictor scorecard including demoted rows with reasons | M | T-110 | A demoted row shows when and why. AC-042 |
| T-116 | `PrintFrame` and the print stylesheet | M | T-111 to T-115 | AC-064 |
| T-117 | Site readiness computation and API | M | T-036, T-043 | Computed from emitted data, not surveyed. AC-070 |
| T-118 | Business case model with sensitivity ranking | L | T-062 | Recalculates on edit; sensitivity list is mandatory. AC-071 |
| T-119 | `AssumptionField` with mandatory source note | M | T-083 | An assumption without a source fails review |
| T-120 | Modelled against realised region | M | T-118 | Renders correctly with a negative gap. AC-072 |
| T-121 | Shift comparison with small multiples (P2) | M | T-085 | AC-063 |
| T-122 | Topology discovery against the simulator stream (P2) | L | T-039 | Uninferable fields left blank and marked. AC-081 |
| T-123 | Second line onboarding with no code change | M | T-012 | A test asserts no plant-specific value in the source tree. AC-080 |
| T-124 | Accessibility pass on Plan and Program views | M | T-116, T-120 | AC-102 |

**Phase 4 exit:** demo script steps 10 and 11 run, no panel is a placeholder.

---

## Phase 5: Evidence, hardening, submission

| ID | Task | Size | Depends | Verify |
|---|---|---|---|---|
| T-130 | Full evaluation run, 8 scenarios x 20 seeds | M | T-070 | Report and figures regenerated |
| T-131 | Reconcile every README number against `metrics.json` | S | T-130 | AC-090 |
| T-132 | Edge case pass: every case in EDGE_CASES.md handled and tested | L | Phase 4 | Each has a test |
| T-133 | Error message pass against the UX writing standard | M | Phase 4 | Each message reviewed against the Section 7 checklist |
| T-134 | Visual regression baselines, all twelve | M | Phase 4 | Committed and reviewed, not blindly accepted |
| T-135 | Manual accessibility: screen reader and 3 m legibility | M | T-124 | Both completed and recorded |
| T-136 | Cross-platform verification on Windows, macOS and Linux | M | Phase 4 | Actually run on all three |
| T-137 | Cold start timing on a clean machine | S | T-136 | Under 5 minutes. AC-105 |
| T-138 | Offline verification | S | T-136 | No external request attempted. AC-106 |
| T-139 | Secret scan across the full git history | S | Phase 4 | Clean |
| T-140 | README, full structure including the controls engineer section | L | T-131 | CONTENT_STYLE_GUIDELINES Section 7 |
| T-141 | Screenshots, including the calm state | M | T-134 | REFERENCE_IMAGES/README.md Section 4 |
| T-142 | Demo video, 3 to 4 minutes | L | T-140 | Follows the script order, including the shadow-mode moment |
| T-143 | Business proposal assembled from the documents | L | T-131 | All six Round 2 elements present |
| T-144 | Final `DEFINITION_OF_DONE.md` Section 3 pass | M | Everything | Every box |

---

## Stretch tasks

Only after T-144. Each is genuinely optional.

| ID | Task | Value |
|---|---|---|
| T-150 | Deploy to a public URL | Judges could click without cloning. Adds live-failure risk during the pitch |
| T-151 | An OPC UA adapter against a public demo server | Proves the integration story with running code rather than a specification |
| T-152 | Retrospective replay tooling for a real historian export | The single highest-value next step per USER_RESEARCH.md Section 4 |
| T-153 | Sensor value realised-gain validation | Requires an installed sensor. Not possible before a pilot |

---

## Task count and sizing

| Phase | Tasks | Estimated days |
|---|---|---|
| 0 | 13 | 2 |
| 1 | 24 | 4 |
| 2 | 22 | 4 |
| 3 | 23 | 4 |
| 4 | 15 | 3 |
| 5 | 15 | 3 |
| Total | 112 | 20 |

Against an 18-day budget with three people working part time. The gap is real and is why
`docs/product/MVP_SCOPE.md` Section 4 exists.

---

**Related:** [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) · [AGENT_WORKFLOW.md](AGENT_WORKFLOW.md) · [../quality/ACCEPTANCE_CRITERIA.md](../quality/ACCEPTANCE_CRITERIA.md) · [../product/MVP_SCOPE.md](../product/MVP_SCOPE.md)
