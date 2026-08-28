# MVP_SCOPE.md

**Purpose:** define exactly what ships in the Round 2 prototype, what is deferred, and where the cut lines fall if time runs short.
**Time budget:** approximately 18 working days across 3 people, part time, alongside coursework.
**Last updated:** 2026-08-28

---

## 1. The demo we are building toward

Write the demo first, then build only what it needs. This is the script:

1. `docker compose up`. The 42-station line starts running at 60 s takt on accelerated time. Line view fills.
2. **08:00 sim time.** A quiet shift. The action list says there is nothing to do. This is deliberate and it is shown first, because a system that always has something urgent to say is a system nobody believes.
3. **09:14.** Scenario SC-01 injects fixture wear at S20. Cycle time begins drifting 58 s toward 63 s, inside spec, invisible on any conventional alarm.
4. **09:26.** The drift detector flags S20. WIP is visibly pooling upstream of S20 and thinning downstream.
5. **09:29.** A stall forecast appears: line stop at S22, window 09:52 to 10:04, probability 0.71, cause attributed to S20 cycle drift, expected loss 11 units. Lead time on screen: 27 minutes.
6. The supervisor opens the counterfactual sandbox. "Add a floater at S20" returns plus 9 units per shift. "Slow takt 4 percent" returns plus 3 units. The ranked action is the floater.
7. **09:35.** Separately, six VINs carrying part lot B-4471 are flagged as elevated G3 risk with the lot named as the leading factor. They are still 14 stations from final QC.
8. **10:40.** The first B-4471 unit fails at G3. Retro-trace runs and produces a containment list of 23 units, 17 still on the line, with the lot as the shared evidence.
9. **S34 panel.** The dark station shows an interval, not a number, and a Sensor Value Card: what is unknown, what a 40 dollar clamp meter would resolve, the confidence gain, the December window, the modelled value.
10. Switch to **Plan view**: four weeks of constraint migration, the loss Pareto, the sensor investment queue.
11. Switch to **Program view**: three sites scored for readiness, the business case with the assumptions editable, modelled versus realised.
12. Open **the evidence pack**: the evaluation report. Precision, recall, lead-time distribution, calibration curve, and the false alarm rate on the quiet shift. Every claim made in steps 1 to 11 traced to a measured number.
13. Open **the predictor scorecard** in Plan view and show that two predictors are still in shadow mode because they have not cleared their gate. The system is honest about what it has not earned yet.

Anything not needed for that script is out of the MVP.

## 2. In scope

### 2.1 Line simulator (`plantsim`)
- 42 stations, 3 zones, 9 buffers, 3 model variants, 2 shifts, 3 inspection gates, 2 rework loops.
- Realistic cycle-time distributions per station per variant, with breakdowns and repairs.
- Observability tiers applied as an output filter: a Tier B station emits only cycle events, a Tier C station emits nothing except downstream scans and occasional manual checks. The simulator knows the truth; the twin does not receive it.
- Ground-truth channel written to a separate store used only by the evaluation harness, never by the twin.
- Scenario injection for SC-01 through SC-08.
- Deterministic under a seed.
- Real-time mode and accelerated mode (default 60x).

### 2.2 Twin core
- Canonical event ingest with the `SimAdapter` and `CsvReplayAdapter`.
- Live state estimation including buffers, station states and per-unit process signatures.
- Virtual sensors for Tier C stations with interval outputs and provenance.
- Cycle-time distribution fitting per station per variant.
- Discrete-event forecaster (SimPy) with Monte Carlo replication, 120-minute horizon, 2-minute cadence.
- Bottleneck attribution via average active period method plus buffer trend.
- Drift detection via EWMA and CUSUM per station per variant.
- Defect risk model: LightGBM, calibrated, conformal intervals, top-3 factor attribution.
- Retro-trace and containment list.
- Counterfactual engine for five intervention types.
- Trust ledger with automatic outcome joining, shadow mode, promotion and demotion gates.
- Sensor value scoring and card generation.
- `LineDefinition` and `SourceMapping` loaders. Topology discovery for the simulator's own stream.

### 2.3 Web application
- **Line view**, built to production quality. This is the view judges will spend the most time in and the one the problem statement most directly asks about.
- **Plan view**, built and functional, at slightly lower polish. Every panel real, none faked.
- **Program view**, built and functional, at slightly lower polish. The business case must compute from editable assumptions, not display a static picture.
- Station detail drawer, unit detail drawer, counterfactual sandbox, predictor scorecard, data health panel.

### 2.4 Evidence pack
- Offline evaluation harness: runs each scenario N times, joins predictions against ground truth, computes every metric in PRD Section 5.
- Generates a Markdown report plus charts, committed to the repo and regenerable with one command.
- This is a deliverable, not an internal tool. It is the difference between a claim and a demonstration.

### 2.5 Repository deliverables (Round 2 submission requirements)
- Public GitHub repository at `github.com/tanmaysahare/Digital_Twin`.
- `README.md`: what it is, the 90-second version, how to run it in two commands, what is simulated and what is not, architecture diagram, evaluation results summary, honest limitations.
- Demo video (target 3 to 4 minutes) following the script in Section 1.
- `docker compose up` as the only required setup path, with a documented non-Docker fallback.

## 3. Out of scope for the prototype

Deferred deliberately. Each is specified somewhere so the design is credible without the code existing.

| Deferred | Where it is specified | Why it is safe to defer |
|---|---|---|
| OPC UA, MTConnect, MQTT Sparkplug B, historian adapters | ../technical/INTEGRATIONS.md | Adapter interface is implemented and two adapters exist. Adding a third is plumbing, not proof |
| Authentication, roles, SSO | ../technical/SECURITY_REQUIREMENTS.md | The prototype ships with a persona switcher and says clearly that auth is not implemented |
| Multi-tenant deployment, per-site isolation | ../technical/ARCHITECTURE.md | Single line, single tenant is enough to prove the model |
| Kubernetes, cloud deployment, CI/CD to an environment | ../ai/IMPLEMENTATION_PLAN.md | Local-first is the judging context. Docker compose is the boundary |
| Mobile native app | ../design/RESPONSIVE_DESIGN.md | Responsive web covers the tablet case, which is the real floor device |
| Alert delivery to phone, email, Teams | ../technical/INTEGRATIONS.md | On-screen and line-side display is the primary channel and the one that matters |
| Deep learning defect models (sequence transformers, LSTM) | ../technical/TECHNICAL_SPEC.md | Gradient boosting on engineered signature features is stronger at this data scale and far more explainable. Deferred on merit, not on time |
| Real plant data | Everywhere | Not available, and the problem statement explicitly permits illustrative data |
| Buffer allocation optimisation as a solver | ../technical/TECHNICAL_SPEC.md | The twin evaluates buffer changes in the sandbox. Solving for the optimum is a separate product |
| Write-back or closed-loop control | Non-goal, permanently | Not a scope question |

## 4. Cut lines

If the build runs behind, cut in this order. Each cut leaves a coherent demo.

**Cut 1 (lowest cost).** Program view drops the site readiness assessment and keeps only the business case with editable assumptions. Recover 1.5 days.

**Cut 2.** Topology discovery becomes a documented design plus a stub that reads the `LineDefinition` directly. Recover 1 day.

**Cut 3.** Scenarios SC-07 and SC-08 move from the demo to the test suite only. Recover 0.5 days.

**Cut 4.** Plan view drops the shift comparison panel and buffer recommendation, keeps constraint migration, loss Pareto, sensor queue and scorecard. Recover 1.5 days.

**Cut 5 (painful, take only if forced).** Retro-trace ships without the shipped-units tier of the containment list, covering only units on the line and in the yard. Recover 1 day.

**Never cut.** Line view. The stall forecast with lead time. The trust ledger and shadow mode. Virtual sensors and the Sensor Value Card. The evidence pack. These five are the argument. Everything else is support.

## 5. What "done" means for the MVP

The MVP is done when all of the following are true. Full detail in ../quality/DEFINITION_OF_DONE.md.

- A clean machine runs `docker compose up` and reaches the seeded demo in under 5 minutes.
- The demo script in Section 1 runs end to end without an operator touching a terminal.
- `make evaluate` regenerates the evaluation report and every number in the README matches it.
- The quiet-shift scenario produces at most one false stall alert per simulated shift.
- Every claim in the README and the demo video traces to a number in the evaluation report or is labelled as a design intention rather than a result.
- The repository is public, the README is complete, and the demo video is linked.

## 6. Explicit anti-scope for the interface

Recorded here because interface scope creep is the most likely way this build loses days to work that adds nothing. Full rules in ../human-design/DESIGN_DONTs.md.

- No 3D. No isometric factory. No animated conveyor.
- No dark theme.
- No gradient anywhere.
- No dashboard of identical cards.
- No onboarding tour, no empty-state illustration, no confetti.
- No chatbot.
- No AI sparkle iconography.
- No loading skeletons that pretend the data is nearly there. Show what is known and its age.

---

**Related:** [PRD.md](PRD.md) · [../ai/IMPLEMENTATION_PLAN.md](../ai/IMPLEMENTATION_PLAN.md) · [../ai/TASKS.md](../ai/TASKS.md) · [../quality/DEFINITION_OF_DONE.md](../quality/DEFINITION_OF_DONE.md)
