# ACCEPTANCE_CRITERIA.md

**Purpose:** the testable conditions that decide whether a user story is done. Each `AC-nnn` maps to one or more stories in ../product/USER_STORIES.md and is implemented as a test in ../quality/TEST_PLAN.md.
**Format:** Given / When / Then. Every criterion is mechanically checkable.
**Last updated:** 2026-08-28

---

## Epic A: See the line as it is now

**AC-001** (US-001)
Given a configured line of 42 stations, when Line view loads at 1440x900, then all 42 stations are visible without scrolling and each shows its ID, state and current cycle value.

**AC-002** (US-001)
Given Line view at the 1920 breakpoint, when the rendered DOM is walked, then no visible text has a computed size below 18px.

**AC-003** (US-002)
Given a line where every station is running normally, when Line view renders, then no element in the line strip uses a state colour, and a pixel sample of the strip contains no saturation above the greyscale threshold.

**AC-004** (US-003)
Given 9 configured buffers, when Line view renders, then each shows occupancy against capacity and a trend indicator, and the values match the twin state within one forecast cycle.

**AC-005** (US-004)
Given station S34 with tier C, when Line view renders, then S34 displays a cross-hatch fill and an interval (two bounds), and no single point value for cycle time appears anywhere for that station.

**AC-006** (US-005)
Given any view, when it renders, then a data timestamp and its age are visible without interaction; and given the age exceeds two forecast cycles, then the age indicator takes the drift treatment.

**AC-007** (US-006)
Given a station segment, when it is clicked or activated by keyboard, then the station drawer opens within 150 ms showing cycle history, the current distribution, buffers either side, the predictor record for that station, and a plain-language statement of what the twin does and does not know about it.

**AC-008** (US-007)
Given four configured sources, when the data health panel renders, then it shows sources live against total, last event time, maximum estimated clock skew, and stations reporting against total with the dark count stated separately.

---

## Epic B: Know what is coming

**AC-010** (US-010)
Given scenario SC-01 running, when the ensemble probability of a stop at or downstream of a station exceeds 0.55 within the 120-minute horizon, then a stall forecast appears in the action list carrying the target station, a time window (not a point), the probability, the attributed cause and the expected unit loss.

**AC-011** (US-010)
Given a stall forecast is emitted, when the ledger is queried, then a prediction row exists with its horizon, confidence, evidence and inputs hash, written at the moment of emission.

**AC-012** (US-011)
Given a stall forecast is displayed, when the action card renders, then the lead time in minutes is the largest text element on the screen.

**AC-013** (US-012)
Given scenario SC-01 where S20 drifts and the stop is predicted at S22, when the forecast renders, then the cause names S20, distinct from the target S22, with the attribution method stated.

**AC-014** (US-013)
Given a station whose cycle time shifts by 1 sigma while remaining inside its tolerance band, when 15 minutes of cycles have accumulated, then both the EWMA and CUSUM charts signal and a drift event is emitted with an estimated onset time within 5 minutes of the injected onset.

**AC-015** (US-014)
Given a stall forecast, when it renders, then an expected unit loss is shown as an interval, not a point.

**AC-016** (US-015)
Given scenario SC-06 with no fault injected, when a full simulated shift completes, then at most one stall forecast is published, and the action list otherwise reads the calm state with 42 stations running and a last-check timestamp.

**AC-017** (US-016)
Given any forecast, when it renders, then a probability and an interval are shown, and no forecast is presented as a certainty.

**AC-018** (US-017)
Given scenario SC-08 with two concurrent faults, when forecasts are emitted, then two distinct action rows appear ranked by expected unit loss, and neither cause is merged into the other.

---

## Epic C: Catch the defect before the gate does

**AC-020** (US-020)
Given scenario SC-02 with part lot B-4471 raising G3 failure probability, when units carrying that lot pass S28, then they appear in the at-risk list with a calibrated probability above the gate threshold, while still at least 10 stations upstream of G3.

**AC-021** (US-020)
Given a defect risk prediction, when the predictor is in shadow mode for the contributing stations, then no at-risk row is published to the interface, and the prediction still exists in the ledger.

**AC-022** (US-021)
Given an at-risk unit, when it renders, then exactly three factors are shown, each rendered from a registered plant-language template, and no raw feature name appears anywhere in the interface.

**AC-023** (US-022)
Given an at-risk unit, when it renders, then both stations remaining and minutes remaining to the target gate are shown.

**AC-024** (US-023)
Given the defect model on held-out data, when calibration is measured, then expected calibration error is at or below 0.05, and the conformal interval achieves at least 0.90 empirical coverage at alpha 0.10.

**AC-025** (US-024)
Given a unit whose route included a tier C station, when its risk renders, then the count of dark stations visited is shown and the prediction's confidence reflects the widened inference.

**AC-026** (US-025)
Given a unit fails at G3, when retro-trace runs, then it completes within 10 seconds and returns at least one ranked hypothesis with its divergence score and the window it covers.

**AC-027** (US-025)
Given scenario SC-02, when retro-trace runs on the first G3 failure, then the containment list recalls at least 0.80 of the units that actually carried lot B-4471 and were affected.

**AC-028** (US-026)
Given a containment list, when export is invoked, then a CSV is produced with one row per unit including the evidence fields for its inclusion.

**AC-029** (US-027)
Given any retro-trace response, when it renders, then it is labelled as a ranked hypothesis with a strength, and the words "root cause" do not appear as an assertion.

---

## Epic D: Test the fix before committing to it

**AC-030** (US-030)
Given the sandbox is opened from an action card, when it renders, then the implicated station is pre-selected and the current state timestamp is shown.

**AC-031** (US-031)
Given a counterfactual is run, when the result renders, then a do-nothing baseline and the intervention are shown side by side, each with an interval, plus their difference as an interval.

**AC-032** (US-032)
Given a counterfactual at default settings on the reference line, when it runs, then it completes within 5 seconds; and given it cannot, then replications are reduced, the intervals widen, and the footer states the reduction.

**AC-033** (US-033)
Given three options are added, when the result renders, then all three plus the baseline are compared and ranked by expected units.

**AC-034** (US-034)
Given a counterfactual result, when "Save as decision" is invoked, then a run record is written with the intervention and the modelled effect, and nothing on the line changes.

**AC-035** (US-035)
Given a historical state timestamp is selected, when a counterfactual runs, then it seeds from that state rather than from now.

---

## Epic E: Earn and keep trust

**AC-040** (US-040)
Given a predictor with scored predictions on a station, when the predictor record renders, then precision, count and median lead time for that station are visible from Line view without navigation.

**AC-041** (US-041)
Given a newly deployed predictor, when it emits predictions, then `published` is false for every prediction until the station's promotion gate is met, and no such prediction appears in any interface response. Verified at the API boundary, not only in the interface.

**AC-042** (US-042)
Given a predictor whose rolling precision on a station falls below 0.55 over at least 10 predictions, when the gate evaluation runs, then the predictor is returned to shadow for that station, a state-change record is written with the metrics that caused it, and a notice appears in the interface stating the withdrawal and its reason.

**AC-043** (US-043)
Given the scorecard, when it renders, then false alerts per shift is shown as a column, not hidden behind a drill-down.

**AC-044** (US-044)
Given the fitted distribution residual for a station exceeds its configured threshold, when the model-health view renders, then that station is listed with the residual and a plain-language statement that the twin no longer matches the line there.

**AC-045** (US-045)
Given a published prediction, when a user marks it wrong with a reason, then a record is written linked to the prediction, and it is reported separately from the automatic outcome rather than overriding it.

---

## Epic F: Make the sensor gaps into a plan

**AC-050** (US-050)
Given tier C stations, when observability and criticality are computed, then each station has both scores and only stations below the observability threshold and above the criticality threshold generate a recommendation.

**AC-051** (US-051)
Given a generated recommendation, when it renders, then it states what is unknown today, the proposed sensor, the current and projected confidence, an indicative cost with its source, the install effort, the required window, and a modelled annual value as an interval.

**AC-052** (US-052)
Given multiple recommendations, when the queue renders in Plan view, then they are ranked by modelled value, each mapped to its next feasible window, and exportable as CSV.

**AC-053** (US-053)
Given a recommendation marked installed with a realised confidence recorded, when it renders, then projected and realised confidence are shown side by side.

---

## Epic G: Plan the week

**AC-060** (US-060)
Given four weeks of history, when the constraint migration heatmap renders, then each station that was the constraint at least once appears with its share per week, labelled directly, with no colour legend required.

**AC-061** (US-061)
Given a range, when the loss Pareto renders, then causes sum to a stated total, the plant's own shift gap is stated alongside, and the unexplained residual is shown as an absolute and a percentage.

**AC-062** (US-062)
Given a buffer recommendation, when it renders, then its assumptions are visible inline and a sandbox action is available that seeds from a historical state.

**AC-063** (US-063)
Given two shifts over the same stations, when the comparison renders, then cycle-time distributions, loss split and defect rate are shown per shift as small multiples.

**AC-064** (US-064)
Given Plan view, when printed to A4 landscape, then all state fills render as patterns, no table row splits across pages, and a header appears with line, range, generation timestamp and the simulated-data marker.

---

## Epic H: Decide the rollout

**AC-070** (US-070)
Given site data, when the readiness table renders, then each site shows every scored component and a banded result stated in words, and each NOT READY site expands to exactly what is missing.

**AC-071** (US-071)
Given the business case, when an assumption is edited, then the modelled result recalculates immediately, and every assumption displays its source and its uncertainty.

**AC-072** (US-072)
Given a pilot site with realised data, when the comparison renders, then modelled, realised and gap are shown for each measure, and a negative gap renders correctly without visual treatment implying failure of the interface.

**AC-073** (US-073)
Given site readiness and modelled value, when the wave plan renders, then sites are sequenced with their instrumentation prerequisites attached.

---

## Epic I: Bring a new line on

**AC-080** (US-080)
Given a second, structurally different LineDefinition and SourceMapping, when the twin starts against it, then it runs with no code change, and a test asserts that no station ID, buffer capacity or threshold from either line appears in the source tree.

**AC-081** (US-081)
Given a recorded event stream, when topology discovery runs, then it produces a LineDefinition draft with a confidence per inferred field, and fields it could not infer are left blank and marked rather than guessed.

**AC-082** (US-082)
Given the connector package, when it is inspected, then the `SourceAdapter` protocol exposes no write method, and a test asserts that no adapter implementation defines a method that writes to a source.

---

## Epic J: The evidence pack

**AC-090** (US-090)
Given a clean checkout, when `make evaluate` runs, then the full evaluation report regenerates and every quantitative claim in the README matches a value in the report.

**AC-091** (US-091)
Given the evaluation report, when it renders, then the false alarm rate from the fault-free scenario appears alongside every accuracy figure for the same predictor.

**AC-092** (US-092)
Given any view, screenshot or export, when it renders, then the simulated-data marker is present and cannot be dismissed.

**AC-093** (US-093)
Given the evaluation report, when it renders, then a reliability diagram for each defect model appears with its expected calibration error and bin counts.

---

## Cross-cutting acceptance criteria

These apply to every story and are checked on every change.

**AC-100 (design rules)** Given any tracked file, when the lint suite runs, then there are no em dashes, no emoji, no banned marketing vocabulary, no gradient declarations, no `backdrop-filter`, no `border-radius` above 2px, and no `prefers-color-scheme` block.

**AC-101 (provenance)** Given any value rendered from the twin, when the component tree is inspected, then a provenance mark is present.

**AC-102 (accessibility)** Given any view at any supported breakpoint, when axe-core runs, then there are no violations at serious or critical severity, and the contrast, target size, tab order and greyscale checks in ../design/ACCESSIBILITY.md Section 10 pass.

**AC-103 (determinism)** Given a scenario and a seed, when the evaluation runs twice, then every reported metric is identical.

**AC-104 (no ground truth leakage)** Given the running twin, when its database role attempts to read the truth schema, then permission is denied. A test asserts this rather than assuming it.

**AC-105 (cold start)** Given a clean machine with Docker installed, when `docker compose up` runs, then the seeded demo is reachable within 5 minutes.

**AC-106 (offline)** Given no network connection, when the application runs, then every view functions and no request to an external host is attempted.

---

**Related:** [../product/USER_STORIES.md](../product/USER_STORIES.md) · [TEST_PLAN.md](TEST_PLAN.md) · [DEFINITION_OF_DONE.md](DEFINITION_OF_DONE.md)
