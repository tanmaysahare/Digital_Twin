# IMPLEMENTATION_PLAN.md

**Purpose:** the build sequence, phase by phase, with a demonstrable outcome at each phase boundary.
**Budget:** approximately 18 working days across 3 people, part time.
**Principle:** every phase ends with something that can be shown. If the deadline arrives early, whatever phase completed last is the submission.
**Last updated:** 2026-08-28

---

## The sequencing logic

Three constraints drive the order.

1. **Nothing can be built before the simulator.** There is no data otherwise. The
   simulator is not scaffolding, it is the environment the whole system is developed
   against, and its fidelity bounds everything downstream.
2. **The evaluation harness comes early, not late.** It is what converts claims into
   evidence, and a harness written on the last day evaluates whatever was built rather
   than what was intended. Building it in Phase 2 also means every subsequent phase is
   developed against a measurable target.
3. **Line view before the other views.** It is the view the problem statement most
   directly asks about, the one judges will spend the most time in, and the one that
   sets every design decision the other views inherit.

---

## Phase 0: Foundation (2 days)

**Goal:** a repository where the rules are enforced before there is code to break them.

| Task | Detail |
|---|---|
| Repository, licence, CI | Public repo, MIT or Apache 2.0, GitHub Actions running lint and tests |
| Docker Compose | `db`, `api`, `worker`, `web`, `sim`. Verified to start on a clean machine |
| Design tokens | `web/src/styles/tokens.css` from `docs/design/DESIGN_SYSTEM.md` Section 11 |
| Lint suite | Every rule in `docs/quality/TEST_PLAN.md` Section 7, wired into CI and into `make lint` |
| Database and migrations | Alembic, the schema in `docs/technical/DATABASE_SCHEMA.md`, including the separate truth schema with its own role |
| Configuration loader | `LineDefinition` and `SourceMapping` from YAML, validated by pydantic |
| `config/lines/line2.yaml` | The 42-station reference line |
| `config/lines/line7.yaml` | A structurally different second line, for AC-080 |

**Done when:** `docker compose up` starts all five services on a clean machine, `make
lint` passes on an empty codebase, and both line configurations load and validate.

**Why the lint suite comes first.** Retrofitting a no-gradient rule onto a built
interface means rewriting the interface. Enforcing it from commit one costs nothing.

---

## Phase 1: The line runs (4 days)

**Goal:** a simulated line producing realistic events, and a twin that can see it.

| Task | Detail |
|---|---|
| SimPy line model | 42 stations, 9 buffers, 3 variants, 2 shifts, 3 gates, 2 rework loops |
| Cycle-time distributions | Per station per variant, with breakdowns and repairs |
| Tier filtering | Tier B emits cycle events only; Tier C emits nothing except downstream scans |
| Ground truth channel | Written to the separate schema the twin cannot read |
| Scenario injection | SC-01 through SC-08 |
| Determinism | Seeded reproducibility, verified by test |
| `SimAdapter`, `CsvReplayAdapter` | Read-only, protocol-conformant |
| Normalisation | Reorder window, clock skew estimation, source health |
| State estimator | `LineState`, buffers, per-unit process signatures |
| Virtual sensors | Interval bounds for Tier C, provenance, the unresolvable case |
| Distribution fitting | Robust location and scale, per station per variant |

**Done when:** the simulator runs a full simulated day, the twin reconstructs the line
state from the filtered stream, virtual sensor intervals contain ground truth in at
least 90 percent of cycles, and the unresolvable case produces `UNRESOLVED` rather than
a number.

**This is the phase that decides whether the project works.** If virtual sensors do not
produce useful bounds, the central claim about uneven coverage fails and the design
needs rethinking. Better to discover that on day 6 than on day 16.

---

## Phase 2: Prediction and evidence (4 days)

**Goal:** the twin predicts, and we can measure whether it is right.

| Task | Detail |
|---|---|
| DES forecaster | Monte Carlo, 120-minute horizon, 2-minute cadence, drift extrapolation |
| Active period attribution | With shift-boundary reset, plus buffer trend |
| Drift detection | EWMA and CUSUM, both required to signal, CUSUM onset estimation |
| Trust ledger | Append-only store, automatic outcome joining, `missed_event` rows |
| Gates | Shadow mode, promotion, demotion, hysteresis, cooling period |
| Defect feature assembly | From process signatures, including missingness features |
| Defect model | LightGBM per gate, temporal split, calibration, conformal intervals |
| Factor templates | Plant-language registry, with the rule that an untemplated feature cannot surface |
| **Evaluation harness** | Scenario runs, ledger to ground truth joining, all metrics, report generation |

**Done when:** `make evaluate` produces a report with real numbers for every metric in
`docs/product/PRD.md` Section 5, including the false alarm rate on SC-06.

**The phase boundary check.** If lead time is under 15 minutes or precision is under
0.60 at this point, stop and diagnose before building any interface. Building three
views on top of a predictor that does not work is the most expensive mistake available
here.

---

## Phase 3: Line view (4 days)

**Goal:** the view that carries the argument.

| Task | Detail |
|---|---|
| Core components | `LineStrip`, `StationSegment`, `BufferBlock`, `ForecastTrack`, `RangePlot`, `IntervalBar`, `ProvenanceMark` |
| Line strip | All 42 stations, states, tiers, buffers, zones, gates, forecast track |
| Action card | Ranked actions, the calm state variant, evidence expansion |
| At-risk table | With factors, remaining stations and minutes |
| Output, predictor record, data health regions | |
| Station drawer | Both variants: instrumented, and dark with a Sensor Value Card |
| Unit drawer | With the process signature timeline |
| Live updates | WebSocket, sequence handling, data age |
| Counterfactual engine and sandbox | Five intervention types, common random numbers, comparison |
| Retro-trace and containment | Backward divergence walk, containment list, CSV export |
| Sensor value scoring | Observability, criticality, catalogue matching, card generation |
| Responsive | Desk, tablet, wall |
| Accessibility | Full pass on this view |

**Done when:** the demo script in `docs/product/MVP_SCOPE.md` Section 1, steps 1 to 9,
runs end to end without a terminal.

**This is the phase most likely to overrun.** The line strip and the calm state are both
harder than they look. Protect them by cutting from Phase 4 rather than from here.

---

## Phase 4: Plan and Program views (3 days)

**Goal:** the two other stakeholders, at slightly lower polish, with nothing faked.

| Task | Detail |
|---|---|
| Plan view | Constraint migration, loss Pareto with reconciliation, recommendations, sensor queue, full scorecard |
| Print stylesheet | A4 landscape, patterns, no split rows |
| Program view | Site readiness, business case with editable assumptions and sensitivity, modelled against realised |
| Topology discovery | Against the simulator's own stream (P2, first candidate for the cut list) |
| Second line onboarding | Verifying AC-080 with `line7.yaml` |

**Done when:** the demo script steps 10 and 11 run, and no panel in either view is a
placeholder.

---

## Phase 5: Evidence, hardening and submission (3 days)

**Goal:** the thing a judge actually receives.

| Task | Detail |
|---|---|
| Full evaluation run | 8 scenarios x 20 seeds, report and figures regenerated |
| Every README number reconciled | Against `evaluation/metrics.json` |
| Edge case pass | Every case in `docs/quality/EDGE_CASES.md` handled and tested |
| Error message pass | Every string against `docs/human-design/UX_WRITING_GUIDELINES.md` |
| Accessibility manual passes | Screen reader, and 3 m legibility |
| Cross-platform | Windows, macOS, Linux, all three actually tested |
| Cold start timing | Verified under 5 minutes on a clean machine |
| README | Full structure, including the controls engineer section |
| Demo video | 3 to 4 minutes, following the script order |
| Business proposal | Assembled from the specification documents |
| Final `DEFINITION_OF_DONE.md` Section 3 pass | Every box |

**Done when:** every box in `docs/quality/DEFINITION_OF_DONE.md` Section 3 is ticked.

---

## Schedule

| Day | Phase | Milestone |
|---|---|---|
| 1 to 2 | 0 | Compose up on a clean machine, lint enforced |
| 3 to 6 | 1 | The line runs and the twin sees it, including dark stations |
| 7 to 10 | 2 | Predictions exist and `make evaluate` reports real numbers |
| 11 to 14 | 3 | Line view demo runs end to end |
| 15 to 17 | 4 | All three views functional |
| 18 to 20 | 5 | Submission ready |

Two days of buffer are built into the day 18 to 20 window against an 18-day budget. They
will be used.

---

## Parallelisation across three people

The phases are sequential but the work inside them is not.

| Person | Phase 1 | Phase 2 | Phase 3 | Phase 4 |
|---|---|---|---|---|
| A | Simulator, scenarios, ground truth | Forecaster, attribution, drift | Counterfactual, retro-trace | Topology discovery |
| B | Adapters, normalisation, state estimator, virtual sensors | Ledger, gates, defect model | Sensor value scoring, API | Second line onboarding |
| C | Tokens, component skeletons, Storybook-equivalent harness | Evaluation harness and report | Line view, drawers, sandbox | Plan and Program views |

Person C starting on components during Phase 1 is deliberate: the component library
cannot be built in four days alongside the view, and building components against
fixtures before the API exists is a genuine parallelisation rather than a false one.

---

## Risks to the plan

| Risk | Signal | Response |
|---|---|---|
| Virtual sensors do not produce useful bounds | Phase 1 coverage test below 90 percent | Stop. Widen the bound derivation to use more flanking evidence, or reduce the dark station share in the reference line and say so honestly |
| Forecast lead time is too short | Phase 2 median under 15 min | Diagnose whether it is the drift detector's delay or the DES horizon. The detector is the likelier cause |
| Precision is too low | Phase 2 precision under 0.60 | Raise the stall probability threshold. Precision matters more than recall here, and the trade should be made explicitly and reported |
| Line view overruns | Day 14 without the demo running | Cut Phase 4 to the Plan view only. Program view becomes wireframes in the documents |
| The forecast cannot meet its budget | Cycle time above 20 s in Phase 2 | Reduce default replications to 100 and report the wider intervals. Honest and cheap |
| Docker fails on a teammate's machine | Any time | The non-Docker path is documented in Phase 0, not discovered in Phase 5 |

---

## What we are deliberately not doing first

- **Not building authentication.** It adds days and demonstrates nothing about the
  problem statement.
- **Not deploying to a URL.** Local-first is the judging context. Deployment is a
  stretch task in `TASKS.md`, not a phase.
- **Not polishing Program view.** It is the least-used view and the first cut.
- **Not building the OPC UA adapter.** The interface exists and two adapters implement
  it. A third proves nothing new and costs two days.

---

**Related:** [TASKS.md](TASKS.md) · [../product/MVP_SCOPE.md](../product/MVP_SCOPE.md) · [../quality/DEFINITION_OF_DONE.md](../quality/DEFINITION_OF_DONE.md)
