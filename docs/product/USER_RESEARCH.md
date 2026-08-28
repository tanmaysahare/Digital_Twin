# USER_RESEARCH.md

**Purpose:** what we actually know, how we know it, and where we are guessing.
**Last updated:** 2026-08-28

---

## 1. Honest statement of method

We are a three-person student team working to a competition timeline. We did not run contextual inquiry on an assembly line, we did not interview supervisors, and we have not observed a shift handover. Anyone reading this document should weight it accordingly, and any persona detail in USER_PERSONAS.md that is not traceable to a source below is a designed assumption, not an observation.

What we did:

| Method | Volume | What it gave us |
|---|---|---|
| Literature review, operations research | ~35 papers and chapters on bottleneck detection, buffer allocation, line throughput, SPC | The mechanisms the twin has to model, and the established methods for detecting them |
| Literature review, applied ML in manufacturing | ~30 papers on predictive quality, anomaly detection, soft sensors, explainability, uncertainty | What is realistic to predict, and what published work reports about calibration and class imbalance |
| Standards and reference architectures | ISA-95, ISA-101, ISO 23247, IEC 62443, OPC UA, MTConnect, MQTT Sparkplug B | The integration and security posture the product must satisfy to be deployable |
| Practitioner literature and vendor documentation | ~40 sources | How these systems fail in practice, particularly around alarm fatigue and operator trust |
| Public datasets | Bosch Production Line Performance, UCI SECOM | Realistic shape for imbalanced, wide, partially-missing manufacturing quality data |
| Competitive desk research | ~20 vendor and analyst sources | COMPETITIVE_ANALYSIS.md |

Full list in RESEARCH_SOURCES.md.

## 2. What the evidence supports

### F-01: Bottlenecks are detectable before they bind, and there is an accepted method
The active period method (Roser, Nakano and Tanaka) and its data-driven successors identify the momentary constraint from the duration of uninterrupted active periods rather than from utilisation, and have been extended to prediction when combined with buffer inventory trends (S-06 to S-09). This matters because it gives us a non-black-box attribution mechanism that an industrial engineer will recognise and accept.

**Design consequence.** BTL-04 uses average active period plus buffer trend for attribution, alongside the DES for consequence. Two methods, both classical, both explainable.

### F-02: The dangerous drift is inside tolerance
Standard alarm limits catch excursions. The failure mode described in the problem statement, and in the SPC literature, is a small sustained shift that never trips a limit. EWMA and CUSUM charts exist precisely for small persistent shifts and outperform Shewhart charts in that regime (S-24 to S-27).

**Design consequence.** BTL-05 runs EWMA and CUSUM per station per variant, not threshold alarms.

### F-03: False alarms destroy predictive systems faster than missed detections do
This is the most consistent finding across the practitioner literature. Teams that receive unreliable predictive alerts stop reading them, and the resulting distrust extends to later, better models (S-16 to S-19). The problem statement names this risk explicitly, which suggests the panel considers it central.

**Design consequence.** The trust ledger, shadow mode, per-station promotion gates and automatic demotion (LGR-01 to LGR-08). We treat this as the product's central mechanic rather than as a monitoring feature.

### F-04: Missing instrumentation is normal and is a modelling problem, not a blocker
The soft sensor and virtual sensor literature is mature: estimating an unmeasured quantity from related measured quantities and process structure is standard practice in process industries (S-11 to S-15). Our case is easier than most, because unit conservation through a serial line gives a hard bound rather than a regression estimate.

**Design consequence.** STA-04 derives interval bounds from flanking timestamps rather than imputing point values, and STA-05 forces every consumer to see provenance.

### F-05: Probabilities from imbalanced classifiers need calibration and distribution-free intervals
Manufacturing defect data is severely imbalanced, and raw classifier scores are not probabilities. Calibration plus conformal prediction gives coverage guarantees without distributional assumptions (S-20 to S-23).

**Design consequence.** DEF-04 and DEF-05. Reliability diagrams are in the evidence pack, not hidden.

### F-06: Explanations change whether an operator acts
The explainable AI in manufacturing literature reports that interpretable attributions materially affect operator trust and uptake, and that the explanation has to be in the operator's vocabulary rather than the model's (S-44 to S-48).

**Design consequence.** DEF-06 requires top-three factors in plant language, and ../design/UX_SPEC.md specifies the phrasing pattern.

### F-07: Defect cost escalates by roughly an order of magnitude per stage
The 1-10-100 framing is a rule of thumb rather than a measured constant, but the direction is consistent across the cost-of-quality literature: prevention is cheaper than in-line correction, which is far cheaper than post-gate rework, which is far cheaper than field failure (S-31 to S-34).

**Design consequence.** DEF-08 makes lead time a first-class output, and the Program view business case exposes the multiplier as an editable assumption rather than baking in a number we cannot defend.

### F-08: Controls engineers block anything that touches Level 2, correctly
The Purdue model and IEC 62443 zone-and-conduit practice both push analytics above the control network, and unidirectional or read-only collection is the established pattern (S-49 to S-53).

**Design consequence.** ING-04 enforces read-only at the interface type level. ../technical/SECURITY_REQUIREMENTS.md is written for Arjun.

### F-09: High-performance HMI practice says use colour only for abnormality
The ISA-101 lineage argues for a low-saturation base with colour reserved for conditions requiring attention, against the older habit of colourful mimic displays (S-40 to S-43). The evidence base is operational experience rather than controlled study, but the practice is widely adopted in process industries.

**Design consequence.** The entire visual system in ../design/DESIGN_SYSTEM.md and ../design/VISUAL_DIRECTION.md. It also happens to be the strongest available argument against the generic colourful SaaS dashboard that ../human-design/DESIGN_DONTs.md prohibits.

### F-10: Downtime cost figures are widely misquoted
The USD 2.3 million per hour automotive figure is from Siemens' 2024 downtime study and is industry-specific. Broader survey figures are much lower (ABB's survey of over 3,000 maintenance leaders gives roughly USD 125,000 per hour across general industry). Quoting the automotive figure as a universal constant is a mistake we should not make in our own pitch (S-04, S-05).

**Design consequence.** The business case in Program view takes the value of a recovered unit as a site-specific editable input with a stated default and its source, rather than hard-coding a headline number.

## 3. What we do not know

Listed so that the gaps are visible rather than papered over.

1. **What lead time is actually actionable.** We target 20 to 40 minutes because it is what the mechanism plausibly delivers, not because we measured what a supervisor can do with it. Twelve minutes might be enough. Ninety might be needed for a maintenance callout. This needs one afternoon on a real floor to resolve and would change a core claim.
2. **The tolerable false alarm rate.** Our 0.70 precision gate is informed by the alarm-fatigue literature but is not a measured threshold. It may be far too low for a floor that has been burned before.
3. **Whether supervisors want the scorecard.** We believe transparency builds trust. It is also possible that publishing a hit rate invites litigation of every miss and undermines the tool. We have no evidence either way.
4. **Whether the counterfactual sandbox gets used mid-shift.** Priya is interrupted constantly. A five-second answer may still be four seconds too slow when the andon is going.
5. **How much of a Line Definition topology discovery can really infer.** We will learn this from our own simulator, which is a weak test because we generated the stream.
6. **What plants will pay.** No pricing research at all.
7. **Whether the dark-station share we assumed is representative.** 14 percent comes from the problem statement's "meaningful minority", not from a survey.

## 4. Research we would do next, in priority order

| Priority | Study | Question it answers | Effort |
|---|---|---|---|
| 1 | Half a shift shadowing a supervisor on a real line | What lead time is actionable, and what she does in the twenty minutes | 1 day plus access |
| 2 | Structured interviews, 5 supervisors across 2 plants | Alarm tolerance, current tool trust, handover practice | 1 week |
| 3 | Concept test of the Line view with 5 supervisors, no facilitation | Whether the display is readable and whether the action card is understood without training | 3 days |
| 4 | Interview 3 controls engineers on the connector design | Whether the read-only posture is sufficient for sign-off | 3 days |
| 5 | Retrospective replay against one plant's historian export | Whether the mechanism finds real drifts in real data, offline, with no deployment risk | 2 weeks plus a data agreement |
| 6 | Interview 2 plant managers on the sensor investment queue | Whether a generated capital request is credible to a budget holder | 3 days |

Study 5 is the one that would most change our confidence, and it requires nothing from the plant except a historian export and an NDA. It is the cheapest possible path from "works on our simulator" to "found a real drift in real data", and it should be the first thing pursued after Round 2.

## 5. How this research shaped the product, in one table

| Finding | Product decision |
|---|---|
| F-01 | Active period attribution alongside DES consequence |
| F-02 | EWMA and CUSUM instead of threshold alarms |
| F-03 | Trust ledger, shadow mode, promotion gates, automatic demotion |
| F-04 | Observability tiers and interval-based virtual sensors |
| F-05 | Calibration plus conformal intervals; reliability diagram published |
| F-06 | Top-three factors in plant language, mandatory |
| F-07 | Lead time as a headline output; cost multiplier as an editable assumption |
| F-08 | Read-only enforced by type; DMZ deployment; no maintenance window on day one |
| F-09 | Greyscale base, colour only for abnormality |
| F-10 | No hard-coded headline savings figure anywhere in the product |

---

**Related:** [USER_PERSONAS.md](USER_PERSONAS.md) · [COMPETITIVE_ANALYSIS.md](COMPETITIVE_ANALYSIS.md) · [PRD.md](PRD.md) · [../../RESEARCH_SOURCES.md](../../RESEARCH_SOURCES.md)
