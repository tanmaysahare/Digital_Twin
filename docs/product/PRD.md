# PRD.md

**Product:** DigitalTwin.ai
**Document owner:** Team Aeronomics
**Audience:** the build agent (Claude Code), the team, and the Round 2 judging panel
**Last updated:** 2026-08-28

This is the contract for what gets built. MVP_SCOPE.md says what makes it into the Round 2 prototype; this document defines the whole product so that the cut lines are visible.

---

## 1. Reference line (the modelled system)

All specifications, seed data and acceptance tests use one reference line. It is fictional but dimensioned from the problem statement's directional parameters.

**Plant:** a single mixed-model vehicle assembly line, "Line 2".

| Property | Value |
|---|---|
| Stations | 42 |
| Zones | Body construction S01 to S16, Paint S17 to S26, Final assembly S27 to S42 |
| Nominal takt | 60 s |
| Shifts | 2 x 8 h, 30 min break, 20 min changeover between shifts |
| Nominal output | 440 to 460 units per day |
| Model variants | 3 (V-STD, V-SPT, V-LWB), scheduled mix approximately 55 / 30 / 15 |
| Buffers | 9 inter-station buffers, capacity 3 to 12 units |
| Inspection gates | G1 body-in-white after S16, G2 paint inspection after S26, G3 final QC after S42 |
| Rework loops | 2 (G1 to S12, G3 to repair yard, off-line) |

**Observability tiers**

| Tier | Stations | Count | Signals available |
|---|---|---|---|
| A (rich) | S01-S06, S08-S12, S17-S22, S27-S31, S38-S39 | 24 | Cycle start/stop, torque curve or process value, motor current, vibration RMS, zone temperature and humidity, part-lot scan |
| B (basic) | S07, S13-S16, S23-S26, S32, S40-S41 | 12 | Cycle start/stop only |
| C (dark) | S33-S37, S42 | 6 | No machine data. Manual checklist result, andon events, unit scan at entry to the next instrumented station |

14 percent of stations are dark. This is the case the product exists to handle.

## 2. Users and jobs

Full personas in USER_PERSONAS.md. Compressed here:

| Persona | Horizon | Primary job | Success signal |
|---|---|---|---|
| Priya, floor supervisor | 0 to 2 h | "Tell me the one thing to do in the next 20 minutes and what it is worth" | Acts on a prediction before the event, and the event does not happen |
| Rakesh, plant manager | 1 week to 1 quarter | "Show me where the constraint actually lives and what it would cost to move it" | Buffer, staffing or sensor decision made from the twin instead of from a spreadsheet |
| Meera, operations director | 1 to 3 years | "Should we roll this to eleven more plants, and what will it return" | Rollout decision defensible in a capital review |
| Arjun, controls engineer (gatekeeper, not a daily user) | Approval | "Prove this cannot touch my network or my PLCs" | Signs off the connector without a maintenance window |

## 3. Functional requirements

Requirements are grouped by subsystem. Each carries a stable ID used in ACCEPTANCE_CRITERIA.md, TASKS.md and TEST_PLAN.md.

### 3.1 Ingest and canonicalisation (ING)

- **ING-01** The system ingests a stream of canonical events. The canonical event types are: `CYCLE_START`, `CYCLE_END`, `UNIT_ARRIVE`, `UNIT_DEPART`, `STATION_STATE`, `PROCESS_VALUE`, `ANDON`, `INSPECTION_RESULT`, `MANUAL_CHECK`, `PART_LOT_SCAN`, `ENV_READING`, `SHIFT_MARKER`.
- **ING-02** Every event carries: `event_id`, `event_type`, `line_id`, `station_id`, `unit_id` (nullable), `ts_source`, `ts_ingest`, `payload`, `source_adapter`, `quality_flag`.
- **ING-03** Source adapters translate a site's native protocol into canonical events. The prototype ships a `SimAdapter` (reads the built-in line simulator) and a `CsvReplayAdapter` (reads a recorded event file). Adapter interfaces for OPC UA, MTConnect, MQTT Sparkplug B and historian query are specified in INTEGRATIONS.md but not implemented in the prototype.
- **ING-04** All adapters are read-only by construction. The adapter interface exposes no write method. This is enforced by type signature, not by convention.
- **ING-05** Events arriving out of order within a bounded window (default 30 s) are reordered by `ts_source`. Events arriving later than the window are accepted, flagged `LATE`, and trigger a state recomputation for the affected station.
- **ING-06** Clock skew between sources is estimated per adapter from unit handoff pairs and reported. Skew above a configurable threshold (default 2 s) raises a data-health warning rather than silently corrupting cycle-time estimates.
- **ING-07** A gap in a source (no events from an adapter for longer than 3 takt periods) is detected and surfaced as a data-health event. The twin continues on the remaining sources with degraded confidence rather than stopping.

### 3.2 State estimation (STA)

- **STA-01** The twin maintains a live `LineState`: for each station, its current state (`RUNNING`, `BLOCKED`, `STARVED`, `DOWN`, `CHANGEOVER`, `IDLE_UNKNOWN`), time in state, current unit, and the last N completed cycle times.
- **STA-02** For each buffer, the twin maintains occupancy, capacity, and a short occupancy history.
- **STA-03** For each in-process unit, the twin maintains a `ProcessSignature`: the ordered list of stations visited with, per station, dwell time, cycle time, station state during the visit, process values observed, part-lot IDs consumed, operator or shift identifier, and ambient readings.
- **STA-04 (virtual sensors)** For a Tier C station, cycle time is derived as an interval bound from the departure timestamp at the nearest upstream instrumented station and the arrival timestamp at the nearest downstream instrumented station, less nominal transport time. Blocking and starving are attributed from the flanking buffer occupancy during the interval.
- **STA-05** Every estimated quantity carries a `confidence` in [0, 1] and a `provenance` field of `MEASURED`, `DERIVED`, or `INFERRED`. No consumer of state may read a value without its provenance.
- **STA-06** Cycle-time distributions are maintained per station per model variant as a rolling window (default 200 cycles), with robust location and scale estimates so that a single outlier does not shift the baseline.
- **STA-07** A station whose observability is insufficient to estimate any cycle time (for example two adjacent Tier C stations with no scan between them) is reported as `UNRESOLVED` and the twin states which sensor would resolve it. It is never given a fabricated value.

### 3.3 Bottleneck and throughput forecasting (BTL)

- **BTL-01** A discrete-event simulation of the line runs on a 2-minute cadence, seeded from the current `LineState`, over a 120-minute horizon, as a Monte Carlo ensemble (default 200 replications).
- **BTL-02** The forecast output is, per station and per 5-minute bucket: probability of blocked, probability of starved, expected buffer occupancy, and the ensemble distribution of cumulative line output.
- **BTL-03** A `StallForecast` is emitted when the ensemble probability of a line stop at or downstream of a station exceeds a configurable threshold (default 0.55) within the horizon. It carries: the predicted station, a time window rather than a point, the probability, the attributed cause, and the expected unit loss.
- **BTL-04 (attribution)** The station responsible is attributed using the average active period method (Roser, Nakano and Tanaka; Subramaniyan et al.) computed over a rolling window, combined with buffer trend. The forecast names a cause, not just a location.
- **BTL-05 (drift detection)** Per station, an EWMA chart and a CUSUM chart run on cycle time conditioned on model variant. A sustained shift inside tolerance is detected and reported as `DRIFT` with its estimated onset time and magnitude. This is the mechanism that catches the fixture wearing from 58 s to 62 s.
- **BTL-06** Every forecast is written to the trust ledger at emission (see LGR).
- **BTL-07** Simulation parameters (distributions, transport times, buffer capacities, failure and repair distributions) are fitted from observed history, not hand-tuned, and the fit residuals are reported in a model-health view.

### 3.4 Defect risk prediction (DEF)

- **DEF-01** Each in-process unit is scored for the probability of failing each downstream inspection gate it has not yet reached.
- **DEF-02** Features are assembled from the unit's `ProcessSignature`: per-station cycle-time z-score against that station's own recent distribution for that variant, dwell and starve time, process-value residuals (for example torque peak and angle versus the station's rolling distribution), count of upstream rework events, part-lot identifiers, operator or shift identifier, ambient temperature and humidity in the paint zone, and explicit tier-aware missingness indicators.
- **DEF-03** Missingness is a feature, not a hole. A Tier C station contributes a `visited_dark` indicator and an inferred dwell bound. The model is trained with the same missingness structure it will see in production.
- **DEF-04** The model is a gradient-boosted tree classifier, calibrated (isotonic or Platt) so that the emitted probability is a probability. Calibration quality is reported as a reliability diagram in the evaluation pack.
- **DEF-05** Each prediction carries a conformal prediction interval so that the uncertainty is distribution-free and honest under class imbalance.
- **DEF-06** Each prediction carries its top three contributing factors, expressed in plant language ("torque at S31 ran 2.3 sigma low for the last 14 units", not "feature_31_zscore = -2.3").
- **DEF-07** A `DefectRisk` alert is raised only when calibrated probability exceeds the per-gate promotion threshold and the predictor has cleared shadow mode for the contributing stations.
- **DEF-08** Lead time is a first-class output: the alert states how many stations and how many minutes remain before the gate that would otherwise catch it.

### 3.5 Retro-trace and containment (RTR)

- **RTR-01** When an `INSPECTION_RESULT` records a failure, the twin walks the failed unit's process signature backwards and identifies the station and time window where its signature diverged most from the contemporaneous population.
- **RTR-02** The twin then queries all units that passed through that station in that window with a comparable divergence and produces a ranked **containment list**: units still on the line, units in the yard, and units already shipped, each with a similarity score.
- **RTR-03** The containment list is exportable as CSV and includes the evidence for each inclusion.
- **RTR-04** Retro-trace output is explicitly labelled as a hypothesis with a strength, not a root cause. Multi-causal and intermittent conditions are the norm; the interface says so.

### 3.6 Counterfactual sandbox (CFA)

- **CFA-01** A user can define an intervention on the current live state and re-run the forecast: add or remove an operator at a station, change takt by a percentage, resequence the upcoming model mix, change a buffer target, take a station down for a planned intervention of N minutes.
- **CFA-02** The result is returned as the delta in expected units per shift with an uncertainty band, plus the change in stall probability by station, compared side by side against the do-nothing baseline.
- **CFA-03** Counterfactual runs complete within 5 seconds at default replication count. If they cannot, replication count is reduced adaptively and the widened band is shown.
- **CFA-04** Counterfactuals are never auto-applied. The output is a recommendation with a number on it.
- **CFA-05** A counterfactual that a supervisor marks as "we did this" is recorded, so that its predicted and actual effects join the trust ledger.

### 3.7 Trust ledger and validation (LGR)

- **LGR-01** Every prediction (stall forecast, defect risk, drift detection, counterfactual) is appended to an immutable ledger at emission with its horizon, confidence, inputs hash, model version and evidence.
- **LGR-02** When a horizon elapses, the actual outcome is joined automatically from the event stream. No human labels anything for the core loop.
- **LGR-03** The system computes, per predictor per station per rolling window: precision, recall, F1, mean and median lead time, and false alarms per shift.
- **LGR-04 (shadow mode)** A predictor begins in `SHADOW` for every station. It records and scores but raises nothing to the floor.
- **LGR-05 (promotion gate)** A predictor is promoted to `ACTIVE` for a station only when, over a configurable evaluation window, precision is at or above the gate (default 0.70), recall is at or above the gate (default 0.50), and it has produced at least a minimum number of scoreable predictions (default 20). Gates are configurable per plant.
- **LGR-06 (demotion)** A predictor whose rolling precision falls below the demotion threshold (default 0.55) is automatically returned to `SHADOW` and the floor is told it was withdrawn and why.
- **LGR-07** The performance record is visible to the floor, not just to the data team. Supervisors can see the system's hit rate on their own station.
- **LGR-08** Model and data drift are monitored. A population shift in input features or a degradation in calibration raises a model-health warning.

### 3.8 Sensor value recommendation (SNS)

- **SNS-01** The twin maintains an observability score per station, derived from provenance mix and the width of confidence intervals on its estimates.
- **SNS-02** For each low-observability station, the twin computes its criticality: the share of forecast stalls in which it lay on the critical path, and the share of defect predictions whose confidence was materially limited by its darkness.
- **SNS-03** From a configurable catalogue of low-cost sensing options (clamp-on current transducer, accelerometer, cycle photo-eye, barcode or RFID scan point, ambient logger, tablet check capture), the twin recommends the cheapest option that would raise the limiting estimate above a target confidence.
- **SNS-04** The recommendation is issued as a **Sensor Value Card** carrying: the station, what is unknown today, what the sensor would resolve, the estimated confidence gain, the indicative cost, the install effort, the required maintenance window, and the modelled annual value.
- **SNS-05** Cards are ranked into an investment queue and exportable for a capital request.
- **SNS-06** Estimated confidence gain is presented as an estimate with its own uncertainty, and is validated after install by comparing predicted gain to realised gain.

### 3.9 Views (VIS)

Detailed layouts in ../design/UX_SPEC.md and ../design/WIREFRAMES/.

- **VIS-01 Line view (floor supervisor).** Live line strip across all 42 stations, current state and tier for each, buffer levels, the ranked action list, the at-risk unit list, the counterfactual sandbox, and the station detail drawer.
- **VIS-02 Plan view (plant manager).** Constraint migration heatmap over weeks, loss Pareto by cause, buffer and staffing recommendations, shift comparison, sensor investment queue, predictor scorecard.
- **VIS-03 Program view (leadership).** Site readiness assessment, rollout wave plan, business case with editable assumptions, modelled versus realised benefit tracking.
- **VIS-04** All three views read the same model. There is no separate reporting pipeline and no metric that exists in one view and not another with a different definition. A single metric registry defines every number once.
- **VIS-05** Line view updates on the 2-minute forecast cadence and on state change; it never requires a manual refresh and never silently shows stale data. Data age is always visible.
- **VIS-06** Every number in every view can be traced to its evidence in at most two interactions.

### 3.10 Onboarding a new line (ONB)

- **ONB-01** A line is described by a `LineDefinition` YAML file: stations, zones, order, transports, buffers and capacities, inspection gates, rework loops, model variants, takt, shift pattern, and observability tier per station.
- **ONB-02** A `SourceMapping` YAML file maps a site's native tags, topics or tables to canonical events.
- **ONB-03** A `topology discovery` pass consumes a recorded event stream and drafts a `LineDefinition` (station order, transport times, buffer behaviour) for a human to correct. The prototype implements this for the simulator's own output as the proof of the mechanism.
- **ONB-04** Adding a line requires no code change. This is verified by an acceptance test that onboards a second, structurally different line from files alone.

## 4. Non-functional requirements

| ID | Requirement | Target |
|---|---|---|
| NFR-01 | Forecast cadence | Full 42-station, 200-replication, 120-minute forecast completes in under 20 s on a laptop |
| NFR-02 | Counterfactual latency | Under 5 s at default settings, under 2 s at reduced replications |
| NFR-03 | Ingest throughput | Sustains 50 events/s on a laptop with no growth in queue depth |
| NFR-04 | Line view responsiveness | Interactions under 150 ms; no interaction blocks on a forecast |
| NFR-05 | Cold start | `docker compose up` to a running seeded demo in under 5 minutes on a clean machine |
| NFR-06 | Offline operation | The full demo runs with no internet connection after install |
| NFR-07 | Determinism | A seeded scenario replay produces identical results, so evaluation numbers are reproducible |
| NFR-08 | Accessibility | WCAG 2.2 AA for all three views (see ../design/ACCESSIBILITY.md) |
| NFR-09 | Readability at distance | Line view legible at 3 m on a 55-inch display at 1920x1080 |
| NFR-10 | Data retention | Prototype retains 30 simulated days of events and the full ledger |

## 5. Prediction quality targets

These are the numbers the evaluation harness must report. They are targets for the prototype on simulated scenarios, not claims about a real plant.

| Metric | Target | Measured how |
|---|---|---|
| Stall forecast lead time (median) | 20 to 40 min | Ledger, over scenarios SC-01, SC-03, SC-05 |
| Stall forecast precision | >= 0.70 | Ledger, all scenarios including the null scenario |
| Stall forecast recall | >= 0.60 | Against injected ground-truth stalls |
| False stall alarms on a quiet shift | <= 1 per shift | Scenario SC-06 (no fault injected) |
| Defect risk PR-AUC | >= 0.55 at ~2% base rate | Held-out replications |
| Defect risk lead time (median) | >= 6 stations before the catching gate | Ledger |
| Calibration error (ECE) | <= 0.05 | Reliability diagram on held-out data |
| Containment list recall | >= 0.80 of units sharing the injected cause | Scenario SC-02 |
| Virtual sensor cycle-time error at Tier C | Interval covers truth in >= 90% of cycles | Against simulator ground truth |

The null scenario matters as much as the fault scenarios. A system that predicts stalls on a quiet shift is the system the problem statement warns about.

## 6. Scenario catalogue

The simulator can inject each of these. They are the spine of the demo, the tests and the evaluation.

| ID | Scenario | Mechanism | What the twin should do |
|---|---|---|---|
| SC-01 | Fixture wear at S20 | Cycle time drifts 58 s to 63 s over 90 min, inside spec | Detect DRIFT within 15 min of onset, forecast the S22 stall 20 to 40 min ahead, attribute to S20 |
| SC-02 | Off-spec part lot at S07 | Lot B-4471 raises defect probability at G3 fivefold | Flag at-risk units before G3, and on the first G3 failure produce a containment list that recovers the lot |
| SC-03 | Operator changeover at S31 | Cycle-time variance triples for 40 min after a shift swap | Detect the variance shift, forecast the resulting starve downstream, recommend a floater |
| SC-04 | Paint humidity excursion | Zone humidity rises past threshold for 2 h | Raise defect risk at G2 for affected units, attribute to the environmental feature |
| SC-05 | Dark station degradation at S34 | A Tier C station slows by 8 s, invisible to any sensor | Detect via virtual sensor bound widening and flanking buffer behaviour, and emit a Sensor Value Card for S34 |
| SC-06 | Quiet shift | No fault injected | Raise no stall alert. This is a pass condition, not an absence of one |
| SC-07 | Source outage | An adapter goes silent for 12 min | Degrade confidence, warn on data health, continue forecasting, do not fabricate |
| SC-08 | Concurrent faults | SC-01 and SC-03 together | Rank the two, do not merge them into one incorrect story |

## 7. Out of scope for the product (not just the MVP)

- Writing to any control system.
- Photorealistic or 3D visualisation.
- Weld, paint chemistry or robot kinematic physics.
- Scheduling optimisation as a solver product (the twin evaluates a proposed sequence; it does not replace an APS).
- Supplier quality management, warranty analytics, or dealer-side data.
- Anything requiring a plant to pause production to install.

## 8. Assumptions, stated so they can be attacked

1. PLC cycle start and stop timestamps are available read-only via at least one of OPC UA, MTConnect, MQTT or a historian, at most sites, without a maintenance window. Where they are not, the site is scored as not ready and the readiness assessment says so.
2. MES holds a build record keyed to a unit identifier and records inspection results. Without a unit key, per-unit defect prediction is not possible and the product says that rather than degrading silently.
3. Transport times between stations are approximately known or learnable from arrival timestamps.
4. A plant will accept an advisory system before a closed-loop one, and the path to value does not require closed loop.
5. Instrumentation changes happen only in scheduled windows, typically two to four per year, so the sensor recommendation queue is planned around windows rather than raised as immediate requests.
6. Simulated data is acceptable for Round 2 and is explicitly labelled as such everywhere it appears.

## 9. Risks and mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Predictions look good on simulated data and fail on real data | High | High | Ship shadow mode and promotion gates as core mechanics, not as a later feature. Never present simulated results as plant results. Publish the null-scenario false alarm rate alongside every hit rate |
| False alarms destroy floor trust in week one | High | High | Promotion gates, per-station thresholds, automatic demotion, and a visible scorecard the floor can check |
| Sensor coverage assumptions do not hold at a given site | Medium | High | Readiness assessment before commitment. Virtual sensors and interval outputs so partial coverage still produces something honest |
| Controls or IT block the connector | Medium | High | Read-only by type signature, DMZ deployment above Purdue Level 2, no inbound path to the control network, an outage-safe design. Documented in SECURITY_REQUIREMENTS.md for the controls engineer, not for us |
| Simulation calibration drifts as the line changes | Medium | Medium | Continuous refit with reported residuals and a model-health view that flags when the twin no longer matches the line |
| Multi-causal root causes get presented as single causes | High | Medium | Retro-trace output is a ranked hypothesis set with strengths, never a single asserted cause |
| Scope creep into 3D and closed loop | Medium | High | Non-goals written into PRODUCT_VISION.md, MVP_SCOPE.md and this document |
| The prototype does not finish | Medium | High | Phased plan with explicit cut lines in ../ai/IMPLEMENTATION_PLAN.md; Phase 1 alone is demonstrable |

## 10. Open questions

Tracked, not hidden.

1. What is the right default promotion gate for a plant that has never run a predictive system? 0.70 precision is our starting position and it is a guess informed by the alarm-fatigue literature, not a measured value.
2. Should the counterfactual sandbox allow interventions the plant cannot actually execute (for example, changing takt)? Showing them is educational; recommending them is not.
3. How much of the Line Definition can topology discovery realistically infer without a human? The prototype will tell us.
4. For units already shipped, is a containment list a product feature or a legal liability that belongs in the customer's own QMS? Present as an export, not as an action.

---

**Related:** [PRODUCT_VISION.md](PRODUCT_VISION.md) · [MVP_SCOPE.md](MVP_SCOPE.md) · [USER_STORIES.md](USER_STORIES.md) · [../technical/TECHNICAL_SPEC.md](../technical/TECHNICAL_SPEC.md) · [../quality/ACCEPTANCE_CRITERIA.md](../quality/ACCEPTANCE_CRITERIA.md)
