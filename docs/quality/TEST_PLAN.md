# TEST_PLAN.md

**Purpose:** how the system is verified, at what level, and what each level is responsible for.
**Principle:** the product's claim is that its predictions are honest. That makes the evaluation harness a deliverable, not a test utility.
**Last updated:** 2026-08-28

---

## 1. The levels

| Level | Tool | Count target | Runs |
|---|---|---|---|
| Unit | pytest, Vitest | ~180 | Every commit |
| Property | pytest with hypothesis | ~15 | Every commit |
| Integration | pytest with a test database | ~45 | Every commit |
| Scenario | pytest against the full stack | 8, one per SC | Every push |
| Interface | Playwright | ~30 | Every push |
| Visual regression | Playwright screenshots | ~12 | Every push |
| Accessibility | axe-core plus custom checks | 6 checks x 3 views | Every push |
| Lint and design rules | custom, stylelint, ruff, eslint | continuous | Every commit |
| Evaluation | the harness | 8 scenarios x 20 replications | Nightly and before submission |

---

## 2. Unit tests, by module

### `plantsim`
- Cycle-time sampling matches the configured distribution over 10,000 draws.
- Blocking and starving occur when and only when buffer conditions require them.
- A seeded run reproduces exactly.
- Scenario injection changes only the intended parameter, verified by comparing all other
  parameters against a control run.
- Tier filtering: a Tier C station emits zero machine events. Asserted by scanning the
  emitted stream, not by inspecting the model.

### `connector`
- Out-of-order events within the window are released in `ts_source` order.
- An event beyond the window is flagged `LATE` and triggers recomputation.
- Clock skew estimation recovers a known injected skew within 0.2 s.
- A silent source is reported after 3 takt periods, not before.
- **No adapter defines a write method.** Implemented by reflecting over every class
  implementing `SourceAdapter` and asserting the method set. AC-082.

### `twin.state`
- State machine transitions for every legal and illegal input.
- `IDLE_UNKNOWN` is produced when evidence is insufficient, and never collapsed.
- Robust location and scale are unaffected by a single 6-minute outlier.
- A distribution with fewer than 20 cycles is not usable and the station is excluded.

### `twin.state.virtual_sensors`
The most important unit tests in the project, because this module is the product's
answer to uneven sensor coverage.
- Single dark station between two instrumented stations: the derived interval contains
  the simulator's ground truth in at least 90 percent of cycles over 5,000 cycles.
- Interval width grows monotonically with the number of consecutive dark stations.
- Two adjacent dark stations with no scan between them produce `UNRESOLVED` for both,
  and no point value is emitted anywhere.
- Blocking versus starving attribution matches ground truth on a span holding one dark
  station, where the station beyond the span is the only thing that could have held the
  unit up. On a span of several it returns `UNKNOWN`: measured against the simulator, a
  blocked label there agreed with the truth 73 percent of the time against a base rate
  of 72 percent, so it was describing nothing.
- Every output carries `provenance = INFERRED`.
- No output has a width of zero, for any input. The transport is nominal rather than
  measured, so there is always uncertainty left to report.

These fixtures run two 5,000-cycle simulations and are the slowest thing in the suite by
a wide margin. They stay in the default run because the gate they carry is the one that
decides whether the project works.

### `twin.forecast`
- The DES reproduces analytically known behaviour on a two-station line with
  deterministic cycle times and a one-unit buffer.
- Average active period identifies the constraint on a synthetic line with a known
  bottleneck, across a range of buffer configurations.
- The accumulator resets at shift boundaries.
- EWMA and CUSUM detect a 1-sigma injected shift within the documented delay, and both
  must signal before an event is emitted.
- CUSUM onset estimation lands within 5 minutes of the injected onset.
- A drifting station is extrapolated in the forecast, not sampled from its stale
  distribution. Verified by comparing forecast output against a control with the drift
  extrapolation disabled.

### `twin.defect`
- Feature assembly produces the documented feature set from a known signature, including
  the missingness indicators.
- No imputation occurs anywhere in the pipeline. Asserted by checking that NaN counts
  survive feature assembly.
- Temporal split: no unit appears in both train and calibration folds, and no lot spans
  the split boundary.
- Calibration reduces expected calibration error against the uncalibrated model.
- Conformal coverage is at least 1 - alpha on a held-out fold.
- Every surfaced factor has a registered template. A feature without one cannot be
  returned. AC-022.

### `twin.ledger`
- A prediction is written at emission, before any publication decision.
- Outcome joining produces the correct result class for each documented rule.
- A prediction whose window fell inside a data gap is scored `UNSCOREABLE`.
- Promotion occurs only when all three gate conditions are met.
- Demotion occurs on the documented condition and writes a state-change record with its
  metrics.
- Recall computation includes `missed_event` rows. A test asserts that recall is not
  computable from predictions alone, by constructing a case where the two differ.
- `UPDATE` and `DELETE` against `prediction` raise.

### `web`
- Every component renders its calm state first. This is the primary test case for each,
  because it is the most common one in production.
- `ProvenanceMark` renders for every value component.
- `IntervalBar` never renders a midpoint alone.
- `ActionCard` empty variant renders the calm-state copy, not a placeholder.
- `DataAge` transitions to the drift treatment past the stale threshold.

---

## 3. Property-based tests

Where a property is easier to state than a set of examples.

| Property | Statement |
|---|---|
| Virtual sensor upper bound | For any line topology and any set of dark stations, the derived upper bound is at least the true cycle time whenever the flanking observations are complete. A unit cannot have worked for longer than it was gone |
| Virtual sensor coverage | The derived interval contains the true cycle time in at least 90 percent of cycles. Not in all of them: the lower bound comes from the quickest comparable passage recently seen, which is a statistical bound and not a guarantee (TECHNICAL_SPEC.md Section 4.3) |
| Interval monotonicity | Adding a dark station to a span never narrows the interval for any station in that span |
| Conservation | Units in equals units out plus work in progress plus scrapped, at every point in a simulated run |
| Loss accounting | Blocked plus starved plus down plus changeover plus running time equals elapsed time, per station, within rounding |
| Ledger totals | True positives plus false positives plus unscoreable equals predictions with an elapsed horizon |
| Determinism | For any scenario and seed, two runs produce byte-identical metric output |
| Estimate construction | An `Estimate` cannot be constructed without a provenance, for any input |

---

## 4. Scenario tests

One per scenario in PRD Section 6. Each runs the full stack against the simulator and
asserts the behaviour the scenario exists to demonstrate.

| Test | Asserts |
|---|---|
| SC-01 | Drift detected within 15 min of onset; stall forecast raised with median lead time between 20 and 40 min; cause attributed to S20 rather than S22 |
| SC-02 | At-risk units flagged at least 10 stations before G3; containment recall at least 0.80 after the first G3 failure |
| SC-03 | Variance shift detected; downstream starve forecast; floater recommendation ranks first in the sandbox |
| SC-04 | Humidity feature appears in the top three factors for affected units; G2 risk rises for units in the booth during the excursion |
| SC-05 | Dark station degradation detected through interval widening and flanking buffer behaviour; a Sensor Value Card is generated for S34 |
| SC-06 | At most one published stall forecast across a full simulated shift. **This test is as important as SC-01** |
| SC-07 | Source outage produces a data gap record, suppresses dependent forecasts, keeps the rest of the line forecasting, and fabricates nothing |
| SC-08 | Two ranked action rows, neither cause merged into the other |

Each scenario runs 20 replications with different seeds in the nightly job, and the
scenario test asserts on the distribution rather than on a single run. A test that passes
on one lucky seed is not evidence.

---

## 5. Interface tests

Playwright, against the running stack seeded with a recorded scenario.

| Area | Tests |
|---|---|
| Line view | All 42 stations render; drifting station carries the drift treatment; dark stations show intervals; action card appears when a forecast is published; lead time is the largest text element |
| Calm state | With SC-06 seeded, the action list shows the calm copy, the at-risk region reports the highest sub-threshold risk, and no state colour appears in the strip |
| Drawers | Station drawer opens on click and on Enter; unit drawer shows the full signature timeline; both close on Escape and return focus to the trigger |
| Sandbox | Opens pre-loaded from an action card; result renders with baseline, option and difference as intervals; degraded run states its reduction |
| Plan view | Loss Pareto shows the reconciliation line; sensor queue exports CSV; scorecard shows a demoted predictor with its reason |
| Program view | Editing an assumption recalculates; the sensitivity list renders; a negative realised gap renders correctly |
| Shadow mode | With a predictor in shadow, no action row appears, and the API response confirms `published: false`. Tested at both layers |
| Keyboard | Full traversal of each view; arrow keys move within the line strip; every shortcut works; no keyboard trap |

---

## 6. Visual regression

Twelve screenshots, compared against committed baselines with a 0.1 percent pixel
tolerance.

| Screenshot | Why |
|---|---|
| Line view, calm, 1440 | The most common state |
| Line view, SC-01 active, 1440 | The demo path |
| Line view, calm, 1920 at 26px root | Wall scaling |
| Line view, 1280 | Tablet layout |
| Line view, greyscale filter | Colour independence, AC-102 |
| Station drawer, tier A | |
| Station drawer, tier C | The dark-station treatment |
| Unit drawer with signature timeline | |
| Sandbox with three options | |
| Plan view full page | |
| Plan view print stylesheet | AC-064 |
| Program view with a negative realised gap | It must look correct when the news is bad |

---

## 7. Design rule enforcement

Automated, failing the build. These implement AC-100.

| Check | Implementation |
|---|---|
| No em dash | `grep` for U+2014 across all tracked files |
| No emoji | Unicode range scan across tracked text files |
| No banned vocabulary | Word list at `.lint/banned-words.txt`, scanned over UI strings and Markdown |
| No gradient | stylelint: `linear-gradient`, `radial-gradient`, `conic-gradient` |
| No blur | stylelint: `backdrop-filter`, `filter: blur` |
| No large radius | stylelint: `border-radius` above 2px |
| No dark theme | stylelint: `prefers-color-scheme` |
| No raw colour in components | stylelint: hex and rgb literals outside `tokens.css` |
| No exclamation mark in UI strings | scan over string files |
| No placeholder content | scan for `lorem`, `Item 1`, `John Doe`, `example.com` |
| Determinism | scan for `random.` and `np.random.` without a seeded generator |
| No external network reference in web | scan the built bundle for external hosts |

A suppression comment on any of these rules fails review. The correct response to a
failure is to fix the cause.

---

## 8. Accessibility tests

Implementing ../design/ACCESSIBILITY.md Section 10. Six automated checks across three
views at three breakpoints, plus two manual passes before submission.

Automated: axe-core rules, token contrast, rendered-component contrast, tab order and
focus visibility, keyboard trap, greyscale distinguishability, text size floor at 1920,
target size and separation at 1280.

Manual: a screen reader pass with NVDA and VoiceOver, and a 3 m legibility check on a
large display or a scaled print.

---

## 9. The evaluation harness

Not a test. A deliverable. It produces the evidence pack that makes every claim in the
README checkable.

```
make evaluate
```

**What it does**

```
For each scenario SC-01 .. SC-08:
  For each of 20 seeds:
    Run plantsim to completion, writing ground truth to the truth schema
    Run the full twin pipeline against the emitted stream
    Record every prediction to the ledger
  Join the ledger against ground truth
  Compute: precision, recall, F1, median and IQR lead time, false alerts per
           shift, PR-AUC, expected calibration error, conformal coverage,
           containment recall, virtual sensor interval coverage
Write: evaluation/report.md, evaluation/figures/*.svg, evaluation/metrics.json
```

**What the report contains**

1. Configuration and code version, and every seed used.
2. Per-scenario results with distributions, not point estimates.
3. The false alarm rate from SC-06, printed next to every accuracy figure.
4. Reliability diagrams per defect model with expected calibration error.
5. Lead-time distributions as histograms, not means.
6. Virtual sensor interval coverage against ground truth.
7. A table of every claim made in the README, with the metric that supports it.
8. A limitations section listing what the evaluation does not establish.

Item 8 is not optional. The harness evaluates a simulator against a twin, and the
simulator was written by the same team. That is a real limitation and the report says so
in its own words rather than leaving a reader to notice.

**Reproducibility.** The report records seeds, configuration version and code version.
Running the harness twice on the same commit produces identical numbers (AC-103).

---

## 10. What is not tested, and why

| Not tested | Reason |
|---|---|
| Real plant data | Not available. This is the largest gap in the whole verification story and is stated in the README and in the evaluation report |
| OPC UA, MTConnect, Sparkplug adapters | Not built. The protocol conformance test exists and will apply when they are |
| Authentication and authorisation | Not built |
| Load beyond one line | Out of scope for the prototype. NFR-03 is tested at 50 events/s only |
| Long-running stability beyond a simulated month | Time |
| Cross-browser beyond Chromium | The target is a fixed line-side device and a controlled desktop |

---

## 11. Definition of a failing build

Any of: a failing unit, property, integration, scenario, interface or accessibility test;
a design rule violation; a coverage drop below the threshold on changed files; a
dependency audit finding at high severity; an evaluation metric falling below its target
in PRD Section 5 without an accompanying documented explanation.

That last clause matters. A metric regression is allowed to land if it is explained and
the explanation is recorded, because a metric that can never move is a metric someone
will start gaming.

---

**Related:** [ACCEPTANCE_CRITERIA.md](ACCEPTANCE_CRITERIA.md) · [EDGE_CASES.md](EDGE_CASES.md) · [DEFINITION_OF_DONE.md](DEFINITION_OF_DONE.md) · [../technical/TECHNICAL_SPEC.md](../technical/TECHNICAL_SPEC.md)
