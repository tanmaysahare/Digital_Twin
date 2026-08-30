# PRODUCT_VISION.md

**Product:** DigitalTwin.ai
**Team:** Aeronomics (Tanmay Sahare, Anuj Kumar Gupta, Sanchit Arora)
**Context:** Accenture Innovation Challenge 2026, Problem Statement 4, Round 2
**Status:** Vision baseline for the Round 2 prototype build
**Last updated:** 2026-08-28

---

## 1. The one-sentence version

DigitalTwin.ai runs the next two hours of a vehicle assembly line before the line does, using only the data the plant already emits, and hands each stakeholder the one decision that changes the outcome.

## 2. What we said in Round 1, and what stands

Round 1 established four commitments. All four survive into Round 2 unchanged, because the judges' feedback and our own research both point the same way: the hard part of this problem is not the modelling, it is being useful on a line that was never designed to be modelled.

| Round 1 commitment | Status | Why it stands |
|---|---|---|
| Build on data the plant already emits, no new sensor network on day one | Kept | Retrofit budget and maintenance windows are the real constraint, not algorithms |
| Model only what changes a decision: time, flow, variation | Kept | Photoreal 3D and weld-level physics are cost centres that do not move a supervisor's hands |
| Dark stations get inferred, not ignored | Kept and expanded into the observability tier system (Section 5) |
| Every prediction carries a confidence score, and where it is low the twin names the cheap sensor that would fix it | Kept and expanded into the Sensor Value Card |

One thing changed: the working name. The Round 1 video used "PulseTwin" for the engine. We are dropping that. The product is DigitalTwin.ai throughout.

## 3. The problem, stated precisely

A mixed-model vehicle line is a serial system locked to a single takt. Its failure modes are not dramatic. They are slow.

**Throughput.** A fixture starts wearing. Cycle time at one station drifts from 58 seconds to 62. Nothing alarms, because 62 seconds is inside spec. Work in progress starts pooling in the buffer upstream and thinning downstream. Twenty to forty minutes later the buffer empties, the line blocks, and a maintenance team arrives to a stopped line. Siemens' 2024 downtime study puts an idle hour in automotive at roughly USD 2.3 million, an industry-specific figure that should be quoted in its original context rather than as a universal constant (see RESEARCH_SOURCES.md, S-04, S-05). The drift was in the data from minute one. Nobody was reading the data that way.

**Quality.** A torque result lands at the low edge of tolerance. A gap measures 0.3 mm out. Neither halts anything. Final inspection catches it thirty vehicles later, and every unit built in the interval carries the same undetected condition into the repair yard, where it costs an order of magnitude more to fix than it would have in line. This is the 1-10-100 escalation that quality engineering has documented for decades (S-31 to S-34), applied to a line that moves one unit a minute.

**The structural gap.** SCADA, MES and historians are excellent recorders and poor forecasters. They tell you what a station did, after it did it. Bottleneck explanations arrive in tomorrow's shift review. Defect root causes take an analyst days. And the oldest stations emit almost nothing, so they are invisible to both.

**The complication that makes this hard, not just laborious.** Real lines are patchworks. A 2015 robot cell streams torque curves at 100 Hz next to a 1998 manual station whose only record is a supervisor's clipboard. Any twin that assumes uniform instrumentation is a twin for a factory that does not exist.

## 4. What DigitalTwin.ai is

A read-only, station-level digital twin of a mixed-model assembly line that does three things and refuses to do a fourth.

**Mirror.** It reconstructs the line as a live state model: station states (running, blocked, starved, down, changeover), buffer occupancy, per-station cycle-time distributions conditioned on model variant, and a per-unit build record keyed to VIN. All of it derived from cycle start and stop timestamps that PLCs already publish and build records that MES already writes.

**Foresee.** Every two minutes it rolls the line forward 120 minutes. Two engines run side by side, deliberately:
- A discrete-event simulation seeded from the live state, run as a Monte Carlo ensemble, which answers *what happens*.
- A shift and constraint detector (EWMA and CUSUM on cycle time, plus the average active period method for bottleneck attribution) which answers *who is causing it*.

In parallel, a per-unit defect risk model scores each VIN on the process signature it actually received, and flags likely defects while the body is still several stations upstream of the gate that would catch them.

**Act.** A supervisor runs counterfactuals against the same simulation: add a floater at S20, slow takt by 4 percent, resequence the model mix, pull the buffer target up. The answer comes back as units recovered per shift with an uncertainty band, in seconds, not as a simulation study booked for next Thursday.

**And what it refuses.** It never writes to a PLC. Not in v1, not in v3. Every output is advisory and a human executes it. This is not timidity, it is the only posture that gets a pilot approved by a plant's controls engineer.

## 5. The four ideas that make it work on a real line

These are the parts we would defend in a technical review. Everything else is execution.

### 5.1 Observability tiers
Every station is classified and the whole system keys off that classification.

- **Tier A (rich).** Process values plus cycle events: torque curves, vibration, temperature, current draw, dimensional checks. Roughly 24 of 42 stations in our reference line.
- **Tier B (basic).** Cycle start and stop timestamps from the PLC, nothing else. Roughly 12 of 42.
- **Tier C (dark).** No machine data at all. A manual checklist, an andon button, maybe a scanner. Roughly 6 of 42, about 14 percent, which matches the "meaningful minority" the problem statement describes.

Tier drives model behaviour, confidence, and how the station is drawn in the interface. A Tier C station is never presented as if it were understood.

### 5.2 Virtual sensors, not imputation
For a dark station we do not fill in a plausible number. We derive an observable one. The arrival timestamp at the next instrumented station, minus the transport time, minus the arrival timestamp at the previous instrumented station, bounds the dark station's cycle time. Whether the downstream buffer was full or the upstream buffer empty during that interval separates blocking from starving from genuine slow work. This is inference from conservation of units, not a statistical guess, and it degrades honestly: the wider the dark span, the wider the bound, and the interface says so.

### 5.3 The trust ledger
This is the mechanic we consider our strongest answer to the problem statement's warning that false alarms erode floor trust faster than accurate ones build it.

Every prediction is written to an append-only ledger at the instant it is made, with its horizon, its confidence, and the evidence behind it. When the horizon elapses, the actual outcome is joined in automatically. The interface shows the resulting precision, recall and mean lead time per predictor per station, in public, including where the model is wrong.

Consequence: a new predictor ships in **shadow mode**. It records and scores but raises nothing on the floor until it clears a promotion gate for that specific station. Supervisors do not get told to trust the system. They get shown its record and decide.

### 5.4 The Sensor Value Card
When a prediction's confidence is limited by missing instrumentation rather than by genuine randomness, the twin says exactly what would fix it and what it is worth:

> S34 is dark. Its cycle time is currently bounded to 54 to 71 seconds from flanking arrivals. A clamp-on current transducer on the main drive, roughly 40 US dollars plus a half-hour install, would narrow that to plus or minus 2 seconds and raise blocking-cause confidence from 0.42 to an estimated 0.85. S34 sits on the critical path in 31 percent of forecast stalls this month. Next feasible window: December shutdown.

This turns "we handle sensor gaps" into a queue of costed, ranked, schedulable retrofits that the plant manager can take to a budget meeting. It is the instrumentation roadmap, generated by the twin, from evidence.

## 6. Who it is for

Three stakeholders, one model, three genuinely different products. Detail in USER_PERSONAS.md.

- **Priya, floor supervisor.** Horizon: the next two hours. Needs one action, ranked, with a number on it, readable from three metres away on a line-side screen and on a tablet with gloves on.
- **Rakesh, plant manager.** Horizon: the next quarter. Needs constraint migration over weeks, a loss Pareto that separates blocked from starved from quality from changeover, buffer and staffing recommendations, and the sensor investment queue.
- **Meera, operations director.** Horizon: the rollout. Needs a per-site readiness score, a business case with the assumptions visible and editable, and honest tracking of realised versus modelled benefit.

## 7. Why us, why this shape

The market is not empty. Siemens Tecnomatix, AnyLogic, FlexSim and Simio build excellent offline simulations that are re-validated by consultants on a project cadence. Sight Machine, Braincube, Oden and Falkonry build excellent data platforms that surface anomalies without a flow model behind them. Full analysis in COMPETITIVE_ANALYSIS.md.

The gap sits between them: a **live** flow model that is **cheap to stand up on a brownfield line** and that **audits its own predictions in public**. Offline simulation cannot tell you what to do at 09:14. Anomaly platforms can tell you something is odd at S20 but not that it will empty the S22 buffer at 09:41 and cost you eleven units. Neither publishes its own hit rate.

## 8. What success looks like

**Round 2 (this build).** A judge opens the repository, runs two commands, watches a 42-station line run, sees a bottleneck predicted 20 to 40 minutes before it lands, sees six at-risk VINs flagged before final QC catches them, runs a counterfactual, and then opens the evaluation report and checks the precision, recall and lead-time numbers against the scenarios. The claims are checkable, not asserted.

**Pilot (one line, one plant, 90 days).** Shadow mode for the first 30 days. Promotion gates cleared on the majority of instrumented stations by day 60. A measurable reduction in unplanned line-stop minutes and in units reaching the repair yard, measured against the pre-pilot baseline on the same line, not against a vendor benchmark.

**Scale.** A new line is onboarded by writing two files, a Line Definition and a Source Mapping, not by writing code. Topology discovery drafts the first from observed event streams. This is the whole scalability argument and it is deliberately unglamorous.

## 9. Non-goals

Stated plainly so that scope creep has to argue against something written down.

- No photorealistic 3D. No Omniverse-class visualisation. A line strip and a Gantt communicate more per second to a supervisor than a rendered factory does.
- No weld-level thermal physics, no per-robot kinematics, no CFD in the paint booth.
- No closed-loop control. No PLC writes. Ever.
- No replacement for MES, SCADA, QMS or the historian. DigitalTwin.ai reads from them and writes to none of them.
- No claim to detect defects that leave no trace in any recorded signal. If the process signature is identical, the twin will say so rather than invent a reason.

## 10. The principles we will be judged against

1. **Earn the alert.** An alert the floor learns to ignore is worse than no alert. Shadow mode and the trust ledger are not features, they are the licence to operate.
2. **Say what you do not know.** A wide confidence band shown honestly beats a narrow one invented. Dark stations are drawn as dark.
3. **Model what changes a decision.** If a fidelity increase does not change an action, it is cost.
4. **Read-only until proven, advisory after.** The plant's safety and controls posture is not ours to spend.
5. **Generalise through configuration, not through code.** Every plant-specific fact belongs in a file, not a branch.

---

**Related:** [PRD.md](PRD.md) · [MVP_SCOPE.md](MVP_SCOPE.md) · [COMPETITIVE_ANALYSIS.md](COMPETITIVE_ANALYSIS.md) · [../technical/ARCHITECTURE.md](../technical/ARCHITECTURE.md)
