# USER_STORIES.md

**Format:** `US-nnn` As [persona], I want [capability] so that [outcome]. Each story lists its acceptance criteria references (AC-nnn in ../quality/ACCEPTANCE_CRITERIA.md), the PRD requirements it satisfies, and its MVP priority.

**Priority key:** P0 ships in the MVP and is on the demo path. P1 ships in the MVP. P2 ships if time allows. P3 is post-prototype.

**Last updated:** 2026-08-28

---

## Epic A: See the line as it is now

**US-001 (P0)** As Priya, I want to see all 42 stations and their current state on one screen so that I can take in the whole line in a glance from three metres away.
Satisfies STA-01, VIS-01, VIS-05. AC-001, AC-002.

**US-002 (P0)** As Priya, I want stations that are running normally to be visually quiet, and only abnormal stations to carry colour, so that my eye goes to the problem rather than to the interface.
Satisfies VIS-01. AC-003. See ../human-design/HUMAN_DESIGN_GUIDELINES.md Section 4.

**US-003 (P0)** As Priya, I want to see buffer levels between stations so that I can see work piling up or thinning before it becomes a stop.
Satisfies STA-02, VIS-01. AC-004.

**US-004 (P0)** As Priya, I want a dark station drawn differently from a monitored one, showing a range instead of a number, so that I never mistake an inference for a measurement.
Satisfies STA-04, STA-05, VIS-01. AC-005.

**US-005 (P0)** As Priya, I want the age of the data shown on screen at all times so that I know whether I am looking at the line or at a memory of it.
Satisfies VIS-05, ING-07. AC-006.

**US-006 (P1)** As Priya, I want to tap a station and see its recent cycle times, its state history, and what the twin knows and does not know about it, so that I can check the system's picture against my own.
Satisfies STA-01, STA-05, STA-06, VIS-06. AC-007.

**US-007 (P1)** As Arjun, I want a data health panel showing which sources are live, their last event time and their estimated clock skew, so that I can tell a data problem from a line problem.
Satisfies ING-06, ING-07. AC-008.

---

## Epic B: Know what is coming

**US-010 (P0)** As Priya, I want to be told when the line is likely to stop, where, and in what time window, so that I can act before it happens rather than respond after.
Satisfies BTL-01, BTL-02, BTL-03. AC-010, AC-011.

**US-011 (P0)** As Priya, I want the lead time shown in minutes and prominently, so that I immediately know whether I have time to do anything.
Satisfies BTL-03, DEF-08. AC-012.

**US-012 (P0)** As Priya, I want the forecast to name the station causing the problem, not just the station where it will land, so that I send help to the right place.
Satisfies BTL-04. AC-013.

**US-013 (P0)** As Priya, I want to be told when a station's cycle time is drifting inside tolerance, because that is exactly the condition nothing else alarms on.
Satisfies BTL-05. AC-014.

**US-014 (P0)** As Priya, I want the expected unit loss attached to the forecast so that I can judge whether it is worth interrupting anything.
Satisfies BTL-03. AC-015.

**US-015 (P0)** As Priya, I want the system to say nothing when there is nothing to say, so that when it does speak I take it seriously.
Satisfies LGR-04, LGR-05, and scenario SC-06. AC-016. This is a pass condition with its own test.

**US-016 (P1)** As Priya, I want to see the probability and the uncertainty of a forecast, not a single confident assertion, so that I can weigh it.
Satisfies BTL-02, BTL-03. AC-017.

**US-017 (P2)** As Priya, I want concurrent problems ranked rather than merged, so that two faults do not become one wrong story.
Satisfies scenario SC-08. AC-018.

---

## Epic C: Catch the defect before the gate does

**US-020 (P0)** As Priya, I want units at elevated risk of failing a downstream inspection flagged while they are still upstream, so that I can hold or correct them in line rather than in the repair yard.
Satisfies DEF-01, DEF-07, DEF-08. AC-020, AC-021.

**US-021 (P0)** As Priya, I want each flagged unit to show the three factors driving its risk, in plant language, so that I know what to check.
Satisfies DEF-06. AC-022.

**US-022 (P0)** As Priya, I want to know how many stations and minutes remain before the gate that would catch it, so that I know whether intervention is still possible.
Satisfies DEF-08. AC-023.

**US-023 (P1)** As Priya, I want the risk expressed as a calibrated probability with an interval, so that "70 percent" means seven in ten.
Satisfies DEF-04, DEF-05. AC-024.

**US-024 (P1)** As Rakesh, I want a defect prediction that involves a dark station to say so explicitly, so that I know the limits of the evidence.
Satisfies DEF-03, STA-05. AC-025.

**US-025 (P0)** As Priya, when a unit fails at a gate, I want the system to identify which other units in process share the same suspected cause, so that I can contain the problem instead of discovering it twenty units later.
Satisfies RTR-01, RTR-02. AC-026, AC-027.

**US-026 (P1)** As Rakesh, I want the containment list exportable with its evidence so that I can hand it to quality.
Satisfies RTR-03. AC-028.

**US-027 (P1)** As Rakesh, I want retro-trace output labelled as a ranked hypothesis rather than an asserted root cause, because intermittent and multi-causal problems are the normal case.
Satisfies RTR-04. AC-029.

---

## Epic D: Test the fix before committing to it

**US-030 (P0)** As Priya, I want to try an intervention against the live state and see its effect before I commit resources, so that I am choosing rather than guessing.
Satisfies CFA-01, CFA-02. AC-030.

**US-031 (P0)** As Priya, I want the result expressed as units recovered per shift with an uncertainty band, compared against doing nothing, so that the comparison is like for like.
Satisfies CFA-02. AC-031.

**US-032 (P0)** As Priya, I want the answer in seconds, because a tool that takes ten minutes is a tool I will not open during a shift.
Satisfies CFA-03, NFR-02. AC-032.

**US-033 (P1)** As Priya, I want to compare two or three candidate interventions side by side and see them ranked.
Satisfies CFA-02. AC-033.

**US-034 (P1)** As Priya, I want to mark that I actually did something, so that the system can later tell me whether it helped.
Satisfies CFA-05, LGR-01. AC-034.

**US-035 (P2)** As Rakesh, I want to run a counterfactual against a past shift rather than the live state, so that I can learn from what happened.
Satisfies CFA-01. AC-035.

---

## Epic E: Earn and keep trust

**US-040 (P0)** As Priya, I want to see how often this system has been right about my stations, so that I can decide how much weight to give it.
Satisfies LGR-03, LGR-07. AC-040.

**US-041 (P0)** As Rakesh, I want new predictors to run silently until they have proved themselves on my line, so that the floor is not trained to ignore them during the learning period.
Satisfies LGR-04, LGR-05. AC-041.

**US-042 (P0)** As Rakesh, I want a predictor whose accuracy degrades to be withdrawn automatically and the floor told, rather than quietly continuing to be wrong.
Satisfies LGR-06. AC-042.

**US-043 (P1)** As Rakesh, I want to see false alarms per shift as a headline metric, not buried, because that is the number that determines whether my supervisors use this in month three.
Satisfies LGR-03. AC-043.

**US-044 (P1)** As Rakesh, I want to be warned when the twin's model of the line no longer matches the line, so that I know when a recalibration is due.
Satisfies BTL-07, LGR-08. AC-044.

**US-045 (P2)** As Priya, I want to mark a prediction as wrong and say why, so that my judgement enters the record.
Satisfies LGR-01. AC-045.

---

## Epic F: Make the sensor gaps into a plan

**US-050 (P0)** As Rakesh, I want to know which unmonitored stations are actually costing me forecast accuracy, so that I instrument the ones that matter rather than the ones that are easy.
Satisfies SNS-01, SNS-02. AC-050.

**US-051 (P0)** As Rakesh, I want a specific, costed sensor recommendation with the confidence gain it would deliver, so that I can put it in a budget request.
Satisfies SNS-03, SNS-04. AC-051.

**US-052 (P1)** As Rakesh, I want recommendations ranked into a queue and mapped to the next available maintenance window, because that window is the real constraint.
Satisfies SNS-05. AC-052.

**US-053 (P2)** As Rakesh, after a sensor is installed I want to see whether the promised confidence gain materialised.
Satisfies SNS-06. AC-053.

---

## Epic G: Plan the week

**US-060 (P1)** As Rakesh, I want to see which station was the constraint each week over the last quarter, so that I can tell a moving constraint from a permanent one.
Satisfies VIS-02. AC-060.

**US-061 (P1)** As Rakesh, I want the shift's lost output split into blocked, starved, down, changeover and quality, reconciling to the total gap, so that I stop arguing about which one it was.
Satisfies VIS-02. AC-061.

**US-062 (P1)** As Rakesh, I want buffer and staffing recommendations with their assumptions exposed and testable in the sandbox.
Satisfies CFA-01, VIS-02. AC-062.

**US-063 (P2)** As Rakesh, I want to compare shifts on the same stations to separate a process problem from a practice problem.
Satisfies VIS-02. AC-063.

**US-064 (P1)** As Rakesh, I want Plan view to print cleanly, because I will take it into a Monday meeting on paper.
Satisfies ../design/RESPONSIVE_DESIGN.md print rules. AC-064.

---

## Epic H: Decide the rollout

**US-070 (P1)** As Meera, I want each candidate site scored for readiness from what it actually emits, so that I sequence the rollout by fact rather than by optimism.
Satisfies VIS-03, ONB-01. AC-070.

**US-071 (P1)** As Meera, I want a business case whose assumptions I can edit, so that I own the numbers I present.
Satisfies VIS-03. AC-071.

**US-072 (P1)** As Meera, I want modelled benefit tracked against realised benefit, including where it fell short.
Satisfies VIS-03, LGR-03. AC-072.

**US-073 (P2)** As Meera, I want a rollout wave plan with instrumentation prerequisites attached per site.
Satisfies VIS-03, SNS-05. AC-073.

---

## Epic I: Bring a new line on

**US-080 (P1)** As an implementation engineer, I want to describe a line in a configuration file and have the twin run on it without a code change, so that the second line costs days rather than months.
Satisfies ONB-01, ONB-02, ONB-04. AC-080.

**US-081 (P2)** As an implementation engineer, I want a first draft of that configuration derived automatically from a recorded event stream, so that I am correcting rather than authoring.
Satisfies ONB-03. AC-081.

**US-082 (P1)** As Arjun, I want to see that the adapter interface has no write capability, so that I can approve the connector by reading the code rather than by trusting a claim.
Satisfies ING-04. AC-082.

---

## Epic J: The evidence pack (judge-facing, and the reason the rest is believable)

**US-090 (P0)** As a judge, I want to regenerate the evaluation results with one command, so that the claims in the README are verifiable rather than asserted.
Satisfies PRD Section 5. AC-090.

**US-091 (P0)** As a judge, I want the false alarm rate on a fault-free shift reported alongside every accuracy number.
Satisfies LGR-03, scenario SC-06. AC-091.

**US-092 (P0)** As a judge, I want to see clearly which data is simulated and which is real, everywhere it appears.
Satisfies MVP_SCOPE Section 2. AC-092.

**US-093 (P1)** As a judge, I want a calibration curve for the defect model, so that the probabilities can be checked rather than believed.
Satisfies DEF-04. AC-093.

---

## Story count by priority

| Priority | Count |
|---|---|
| P0 | 26 |
| P1 | 22 |
| P2 | 7 |
| P3 | 0 (deferred items live in MVP_SCOPE.md Section 3 rather than as stories) |

55 stories in total. Deferred capability lives in MVP_SCOPE.md Section 3 rather than as
P3 stories, so that the backlog does not carry work nobody intends to do.

---

**Related:** [USER_PERSONAS.md](USER_PERSONAS.md) · [USER_FLOWS.md](USER_FLOWS.md) · [PRD.md](PRD.md) · [../quality/ACCEPTANCE_CRITERIA.md](../quality/ACCEPTANCE_CRITERIA.md)
