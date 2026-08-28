# EDGE_CASES.md

**Purpose:** the awkward situations, and what the system does in each. A specification that only covers the happy path is a specification that will be discovered to be wrong during the demo.
**Rule that governs all of them:** degrade to less information, never to wrong information.
**Last updated:** 2026-08-28

---

## 1. Data and timing

**EC-01 Events arrive out of order.**
Buffer for the reorder window (30 s default) and release in `ts_source` order. Beyond the window, accept, flag `LATE`, and recompute the affected station's state. Never silently discard.

**EC-02 Two sources disagree about the same event.**
Keep both, prefer the source with the higher declared fidelity for state, and raise a data-health warning naming the disagreement. Do not average two contradictory timestamps.

**EC-03 A source clock jumps (NTP correction, daylight saving, manual set).**
A step change in estimated skew larger than 60 s is treated as a clock event, not as a process change. Mark the affected interval, exclude it from distribution fitting, and record a data gap.

**EC-04 An entire shift of events arrives at once (a backfill).**
Process at ingest rate, mark all as `LATE`, recompute state, and do not emit forecasts from a state that is being rebuilt. Forecasting resumes once the backfill drains.

**EC-05 The same unit appears at two stations simultaneously.**
Physically impossible, so it is a data error. Flag it, keep the later arrival as authoritative, and record a data-health event. Do not silently pick one.

**EC-06 A unit disappears from the stream.**
After 3 takt periods with no event, mark the unit `LOST_TRACK` with its last known position. Its process signature is retained and marked incomplete. Any risk prediction for it is suppressed rather than computed on a truncated signature.

**EC-07 A unit identifier is reused.**
Some plants recycle identifiers across days. Key units on `(unit_id, entered_at date)` internally, and surface the plant's identifier. A collision within a day raises a data-health event.

**EC-08 Cycle end without a cycle start.**
Common after a restart. Treat the cycle as unmeasured, do not infer a duration from the previous event, and mark the visit `provenance = INFERRED` with a bound if flanking evidence exists, otherwise `UNRESOLVED`.

**EC-09 Negative or absurd derived cycle time.**
A virtual sensor interval whose lower bound is negative means an assumption was wrong (transport time, station order, clock skew). Clamp the lower bound to zero, mark the estimate low-confidence, and raise a health event naming the likely cause. Do not present the clamped value as if it were derived cleanly.

**EC-10 Ingest outruns the database.**
Buffer in memory to a bound, then drop and count. Show the dropped count in the data health panel. Never apply backpressure to a plant source (SEC-13).

---

## 2. Line state

**EC-11 The line is stopped for a planned reason.**
A shift break, a planned changeover or a scheduled maintenance window is not a stall. Detect from the shift pattern in the LineDefinition and from `SHIFT_MARKER` events, exclude the interval from stall scoring, and say so on the strip.

**EC-12 The line is running below takt deliberately.**
A ramp-up, a trial build or a reduced-demand shift changes the baseline. Detect from a sustained takt change and refit rather than reporting every station as drifting. Report the takt change itself as a single event.

**EC-13 A station is bypassed.**
Some variants skip stations. The LineDefinition carries per-variant routing, and a skipped station is not a starved station. Where routing is not configured, a unit skipping a station raises a configuration warning rather than a state error.

**EC-14 A unit is removed from the line (scrapped or pulled for inspection).**
Mark `SCRAPPED` or `HELD`. Remove from work-in-progress accounting. Retain the signature, because a pulled unit is often the most informative one.

**EC-15 A unit is reinserted after rework.**
A second visit to the same station, distinguished by `unit_visit.seq`. The rework event is a feature for the defect model, not a data error.

**EC-16 Buffer occupancy goes negative or exceeds capacity.**
Both are impossible and both happen when a scan is missed. Clamp, raise a health event, and reconcile at the next unit that is observed at both flanking stations.

**EC-17 Two adjacent dark stations with no scan between them.**
Neither cycle time is separable. Both marked `UNRESOLVED`, the sum is bounded, and a Sensor Value Card is generated for the scan point that would fix it. No number is invented. STA-07.

**EC-18 The whole zone is dark.**
If a contiguous span of dark stations exceeds a configured length, the twin reports that the zone cannot be modelled and excludes it from forecasting rather than producing an interval so wide it is meaningless. The readiness assessment would have caught this at onboarding.

**EC-19 A station is added or removed while running.**
Configuration change. Requires a reload, which returns every affected predictor to shadow (API_SPEC Section 10), because the evidence a predictor was promoted on no longer describes the line.

---

## 3. Forecasting

**EC-20 Insufficient cycle history for a station or variant.**
Below 20 cycles, the station is excluded from forecasting and the interface states how many cycles remain. This happens on every cold start and after every new variant introduction, so it must look deliberate rather than broken.

**EC-21 A bimodal cycle-time distribution.**
Two operators with two habits, or two fixtures on alternate cycles. The empirical resampling distribution handles this correctly by construction; a fitted parametric form would not. Detected and reported in the model-health view because bimodality often has a cause worth knowing.

**EC-22 The forecast cannot finish inside its budget.**
Reduce replications by 25 percent for the next cycle, widen the intervals, and state the reduction. If the budget is missed three cycles running, raise a health event: the line may have grown or the machine may be under-resourced.

**EC-23 Every station is simultaneously abnormal.**
A line-wide event (power dip, a shift starting late) rather than 42 independent problems. Detected by correlation across stations, reported as one line-level event, and the action list does not fill with 42 rows.

**EC-24 The predicted stall happens earlier than the predicted window.**
Scored as a hit if within the tolerance (10 min default), and as a miss beyond it. The tolerance is reported alongside precision, so the number cannot be improved by quietly widening it.

**EC-25 The predicted stall is prevented by the operator acting on the prediction.**
The hardest scoring problem in the product. If the user marked "we did this", the prediction is scored `UNSCOREABLE` for precision and recorded separately as a probable prevented stall. Counting it as a false positive would punish the system for working; counting it as a true positive would let the system claim credit for an event that did not occur. Both are wrong, so it is excluded and reported as its own category with its own count.

**EC-26 A stall occurs with no forecast in scope.**
A `missed_event` row is written so recall is computable. Recall that is never measured is recall that is always claimed.

**EC-27 A drift reverses on its own.**
A fixture that was sticky and freed itself. The drift event is closed, and if a forecast was raised on it, it becomes a false positive. Correct: the forecast was wrong even though the observation was right. The scorecard is not adjusted to protect the number.

---

## 4. Defect prediction

**EC-28 A gate has too few failures to train on.**
Below a configured minimum of positive examples, no model is trained for that gate, and the interface says the model is not available for that gate rather than showing a model trained on 4 examples.

**EC-29 A new part lot with no history.**
The lot-level failure rate feature is missing, which the model handles natively. Confidence is lower and the conformal interval is wider, correctly.

**EC-30 A defect class the model has never seen.**
The model will not predict it. Retro-trace will still run on the failure and may find the divergence. The interface does not claim the model missed something it was never trained on; the evaluation report separates known from novel failure modes.

**EC-31 A defect with no signature difference at all.**
Some defects leave no trace in any recorded signal. The model predicts low risk and it is correct to do so given its inputs. Reported honestly: the product does not claim to detect what no sensor observed, and the evaluation report states the share of failures with no detectable signature.

**EC-32 The same unit is flagged for two gates.**
Two rows, two predictions, two independent outcomes. Not merged.

**EC-33 A prediction is made and the unit is scrapped before reaching the gate.**
Scored `UNSCOREABLE`. The share of unscoreable predictions is reported.

---

## 5. Retro-trace

**EC-34 No station shows meaningful divergence.**
Report that no signature difference was found, and say what that means: the cause is either upstream of the twin's visibility, at a dark station, or not present in any recorded signal. This is a useful answer and it is given plainly rather than by returning the least-innocent station.

**EC-35 Several stations diverge equally.**
Return all of them as co-hypotheses with their scores. Do not pick one. Multi-causal problems are the normal case (RTR-04).

**EC-36 The containment list is enormous.**
If more than a configured share of recent production matches, the hypothesis is probably wrong or the divergence threshold is too loose. Report the count, say the hypothesis is weak, and do not export a list of 400 units as if it were actionable.

**EC-37 The failing unit passed through a dark station.**
The trace cannot examine that station. Say so explicitly in the output, and generate a Sensor Value Card if that station recurs across traces.

---

## 6. Counterfactual

**EC-38 The intervention makes things worse.**
Report the negative delta plainly. A sandbox that only shows improvements is a sandbox nobody learns from.

**EC-39 The intervention is not physically possible.**
Adding a second operator to a fully automated station is meaningless. The station's `is_manual` flag gates which interventions are offered, and an impossible one is not in the list rather than being offered and returning zero.

**EC-40 The difference is inside the noise.**
When the intervention and baseline intervals overlap substantially, say so: "the difference is within the range of run-to-run variation". Do not report a 1-unit improvement as a recommendation.

**EC-41 The state changes while the sandbox is open.**
The run is seeded from the state at the time it was launched, and the timestamp is shown. If the live state has moved more than a configured amount, offer to re-run rather than silently mixing states.

---

## 7. Ledger and gates

**EC-42 A predictor sits in shadow forever.**
If it has not cleared its gate after a configured period, report it as not achieving the gate rather than as still learning. There is a difference between a predictor that needs more data and one that does not work here, and conflating them hides a real finding.

**EC-43 Precision is undefined (no predictions made).**
Show the count and no precision. Never show 0.0 or 1.0 for an empty set.

**EC-44 A predictor oscillates between promoted and demoted.**
Add hysteresis: promotion requires a higher threshold than demotion (0.70 against 0.55), and a demoted predictor cannot be re-promoted for a configured cooling period. A predictor that flickers on and off is worse for trust than one that stays off.

**EC-45 Gate thresholds are changed.**
An audited configuration event that appears in the scorecard history. Loosening a gate to promote a failing predictor is visible to anyone reading the history (SEC-65).

**EC-46 The evaluation window contains a data gap.**
Predictions whose horizon fell inside the gap are `UNSCOREABLE`. The share is reported, and if it exceeds a configured fraction, the scorecard is marked as covering a degraded period.

---

## 8. Interface

**EC-47 More than three actions at once.**
Show the top three ranked and state the count of the rest. Cognitive load is a hard constraint (../design/ACCESSIBILITY.md Section 9).

**EC-48 More than eight at-risk units.**
Show eight and state the count. If there are thirty, the plant has a containment problem, and the count communicates that more clearly than thirty rows would.

**EC-49 A station name or VIN is longer than its space.**
Truncate the VIN from the left, keeping the distinguishing suffix, with the full value available on hover and in the drawer. Never truncate a station identifier.

**EC-50 A very long factor explanation.**
Templates are length-capped at authoring time. A template that cannot be expressed within the cap is a template that needs rewriting, not a field that needs to scroll.

**EC-51 The websocket drops.**
Show the data age prominently and attempt reconnection with capped backoff. Never show stale data as current, and never blank the view.

**EC-52 A sequence gap in websocket messages.**
Re-fetch full state rather than applying a partial update to an unknown baseline.

**EC-53 The browser is left open across a shift change.**
Shift context updates from `SHIFT_MARKER` events. No reload required, and the shift summary reflects the correct shift.

**EC-54 Printing while a forecast is active.**
The print header carries the generation timestamp and the data age, so a printed page cannot be mistaken for a current one.

---

## 9. Demo-specific

Listed because a demo failure costs as much as a product failure in this context.

**EC-55 The simulator runs faster than the interface can render.**
Accelerated mode is capped at a rate the interface can follow. The demo default is 60x, tested end to end.

**EC-56 A judge clicks something unexpected mid-demo.**
Every view is independently reachable and nothing is modal. There is no wizard state to lose, and no action can break the running simulation.

**EC-57 The demo machine has no network.**
Everything runs offline (NFR-06, AC-106). Fonts are self-hosted, no CDN, no telemetry.

**EC-58 The scenario has not reached its interesting moment.**
The demo supports jumping to a seeded state so the drift and the forecast are reachable immediately, and this is documented in the README rather than being a hidden trick.

---

**Related:** [ERROR_HANDLING.md](ERROR_HANDLING.md) · [TEST_PLAN.md](TEST_PLAN.md) · [ACCEPTANCE_CRITERIA.md](ACCEPTANCE_CRITERIA.md)
