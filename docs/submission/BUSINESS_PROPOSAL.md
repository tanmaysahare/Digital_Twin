# BUSINESS_PROPOSAL.md

**Product:** DigitalTwin.ai
**Team:** Aeronomics. Tanmay Sahare, Anuj Kumar Gupta, Sanchit Arora. IIT Kanpur
**Context:** Accenture Innovation Challenge 2026, Problem Statement 4, Round 2
**Repository:** https://github.com/tanmaysahare/Digital_Twin
**Last updated:** 2026-08-30

This document contains the six elements Round 2 asks for: problem framing, solution
design, target users, business case, phased roadmap, and risks with mitigations.

**How to read the numbers in this document.** Every quantitative claim is one of three
things and is labelled as such wherever it appears.

- **Measured.** Produced by `make evaluate` and present in `evaluation/metrics.json`.
  Reproducible from a stated seed.
- **Cited.** Traceable to a source in `RESEARCH_SOURCES.md` by its `S-nn` identifier.
- **Assumption.** Ours, with the reasoning stated. Not a quotation, not a benchmark, and
  not defensible as evidence.

All measured numbers come from a simulator we wrote, evaluated against a twin we wrote.
Section 8 treats that as the limitation it is rather than as a footnote.

---

## 1. Problem framing

### 1.1 The failure

A supervisor learns that a station has slowed when the line stops. The decision that
would have prevented the stop, moving a floater, releasing a buffer, resequencing the
mix, was available twenty minutes earlier and is now in the past. The information needed
to make it existed the whole time, in cycle timestamps the controllers were already
publishing.

The specific case this product is built around is a fixture wearing at station S20. Its
cycle time drifts from 58 seconds to 63 seconds over ninety minutes. It stays inside
specification the entire time, trips no threshold alarm, and eventually starves the
station downstream. Standard alarm limits catch excursions. They do not catch a small
sustained shift, which is the regime EWMA and CUSUM charts exist for (F-02, S-24 to
S-27).

### 1.2 The two constraints that shape everything

**Sensor coverage is uneven, and that is the problem rather than an inconvenience.** On
the reference line, 24 of 42 stations report a clock, a state word and process values,
12 report a clock only, and 6 report nothing at all except downstream scans and manual
checks. A twin that assumes uniform instrumentation either refuses to model the dark
stations or silently invents values for them. Both are wrong. Estimating an unmeasured
quantity from related measured quantities is established practice (F-04, S-11 to S-15),
and a serial line makes it easier than most cases: conservation of units through flanking
timestamps gives a bound rather than a regression estimate.

**False alarms are the failure mode, not inaccuracy.** The most consistent finding in the
practitioner literature is that teams receiving unreliable predictive alerts stop reading
them, and that the resulting distrust extends to later and better models (F-03, S-16 to
S-19). A supervisor who has learned to ignore a system has correctly concluded it is not
worth reading, and no subsequent accuracy improvement recovers that attention. The
problem statement names this risk explicitly.

### 1.3 What follows from those two constraints

Most of the design is a consequence of taking them seriously. Dark stations are reported
as intervals and never as points. Every value carries a provenance saying whether it was
measured, derived or inferred. No prediction reaches the floor until it has earned that
station by clearing a precision and recall gate, and it withdraws itself when it
degrades. These are not features that could be trimmed under time pressure. They are the
product.

---

## 2. Solution design

### 2.1 What it is

A live, read-only digital twin of a mixed-model assembly line. It reads the event stream
the plant already emits, reconstructs the state of the line including the stations
nothing watches, runs the next two hours forward every few minutes, and reports what it
expects and how confident it is entitled to be.

It writes to nothing. The read-only posture is enforced at the type level: the
`SourceAdapter` protocol has exactly three methods, `describe`, `stream` and `health`,
and a test walks every implementation in the repository and fails if any defines a method
whose name begins with a write verb. This is the posture controls engineers require
before analytics may sit near a control network (F-08, S-49 to S-53).

### 2.2 The five mechanisms

None of these methods is novel and we claim none of them are. What is unusual is the
combination, and what sits between them and the floor.

**Virtual sensors for dark stations.** A unit leaves the last instrumented station
upstream and arrives at the first one downstream. The transit, less the nominal
transports, bounds the work done in between. The upper bound is sound: a unit cannot have
worked for longer than it was gone. The lower bound is statistical, taken from the
quickest recent comparable passage, which is why the target is coverage in 90 percent of
cycles rather than in all of them. Where a span holds several dark stations with no scan
between them, the twin reports that it cannot separate them rather than dividing the
bound arbitrarily.

**Forecast.** A Monte Carlo discrete-event simulation seeded from the live state and run
forward 120 minutes. Blocking and starving propagate through the model rather than being
estimated per station, because a station that goes over takt does not slow the line by
its own excess: it slows it by that excess less whatever the buffer ahead of it absorbs,
until the buffer fills and the loss arrives at once. Only a flow model produces that
shape.

**Constraint attribution.** Average active period with a shift-boundary reset, plus a
buffer trend, reported separately. Both are classical and both are explainable to an
industrial engineer (F-01, S-06 to S-09). Where the two methods name different stations
the interface shows both rather than choosing.

**Defect risk.** LightGBM per inspection gate on the full per-unit process signature,
with a temporal split, isotonic calibration and split conformal intervals. Manufacturing
defect data is severely imbalanced and raw classifier scores are not probabilities, so
calibration plus conformal prediction is what gives coverage without distributional
assumptions (F-05, S-20 to S-23). Explanations are SHAP top three, and a feature with no
plant-language template cannot reach a screen at all (F-06, S-44 to S-48).

**The trust ledger.** Every prediction is written to an append-only ledger at the moment
it is made, before any decision about whether to publish it. Outcomes are joined
automatically when the horizon elapses. `missed_event` rows record the stalls nothing
predicted, which is the only way recall is computable at all. A predictor is promoted for
one station only after clearing a gate over enough predictions, and demotes itself when
it degrades. The ledger, not the model, decides what reaches the screen.

### 2.3 The Sensor Value Card

The twin converts each of its own blind spots into a costed instrumentation
recommendation: what is unknown, what a specific low-cost device would resolve, the
confidence it would gain, the next maintenance window in which it could be fitted, and
the modelled value. Uneven coverage stops being a limitation of the deployment and
becomes an output of it.

Every cost in the catalogue is our own assumption. The catalogue carries a `source` field
on every entry and a test fails the build if any entry omits it, so a figure cannot
quietly acquire the authority of a quotation on its way into a capital request. We have
no plant quotations and no vendor pricing.

### 2.4 Why it can be pointed at a real plant

The twin knows nothing about what produced its event stream. A test asserts that no file
under `twin/` imports the simulator. Station identifiers, buffer capacities, thresholds,
tag names and gate positions live in `config/`, and a test asserts that no plant-specific
value appears in the source tree. A structurally different second line, 18 stations
rather than 42, a different prefix, a different takt and a third of the line dark, runs
with no code change.

---

## 3. Target users

Four roles, with one primary. The personas are composites assembled from published
literature and are labelled as such in `docs/product/USER_PERSONAS.md`. **We interviewed
nobody.** Section 8 treats that as the material weakness it is.

**Primary: the floor supervisor.** Eleven years on the floor, four as a supervisor, 16
stations and 22 operators plus 2 floaters, a 55-inch line-side display and a tablet
carried in gloves at 78 dB, interrupted constantly. She is the reason the default screen
is greyscale and says nothing on a normal shift, the reason colour means abnormal and
nothing else, and the reason there is no onboarding tour. If the design serves anyone
perfectly it is her.

**The plant manager.** Wants the loss accounting to reconcile and wants to know what a
change would have been worth. Reads the Plan view, not the Line view.

**The director of manufacturing operations.** Compares sites, holds the capital budget,
and has to defend every number in a room. The Program view exists for this person, which
is why every assumption in the business case carries a source and a sensitivity range and
why the model refuses an assumption with no stated source.

**The controls and OT engineer.** Blocks anything that touches Level 2, correctly. He is
not a user of the interface. He is the person who must sign off the connector, and the
README has a section written for him that names the file and the test rather than asking
him to take our word.

**Explicit anti-persona: the executive dashboard viewer.** No screen in this product is
designed to be glanced at from a distance and felt good about.

---

## 4. Business case

### 4.1 The honest starting position

**The modelled business case for the reference line computes to zero.** The line supplies
no contribution margin per unit, and the model returns zero rather than substituting an
industry average that does not describe the site. That is deliberate. A plant that has
not given us its own figure should see zero, not a number engineered to look attractive.

This is also why this section contains no headline savings claim. We are not in a
position to make one.

### 4.2 What the value would be composed of

The Program view computes the case from editable assumptions, each carrying its source
and its own sensitivity range. The three that carry the case are:

1. **Value of a recovered unit.** Site-specific, entered by the plant. Widely quoted
   downtime figures are unreliable for this purpose: the USD 2.3 million per hour
   automotive figure is industry-specific to that study, and broader surveys give figures
   roughly an order of magnitude lower across general industry (F-10, S-04, S-05).
   Quoting the automotive figure as a universal constant is a mistake we decline to make
   in our own proposal.
2. **Share of forecast stops a supervisor can actually act on.** Our assumption, and the
   assumption the whole case is most sensitive to. We do not know the real figure. We
   have not measured what a supervisor can do inside a given lead time, and we say so in
   `docs/product/USER_RESEARCH.md` Section 3 item 1.
3. **Predictor precision.** Not an assumption. It is read from the trust ledger, which is
   to say the case is computed from the product's own measured performance rather than
   from a hoped-for one. On the reference line today that number is low, and the case
   reflects it rather than routing around it.

The sensitivity ranking is mandatory in the model rather than optional, because a case
whose most fragile assumption is not identified will not survive its first review.

### 4.3 The cost side

The deployment asks for no new hardware to start. It reads what the plant already emits.
That is the strongest commercial property the product has, and it is measurable rather
than asserted: the twin reconstructs the reference line, including the six stations that
emit nothing, from the existing stream alone.

Where instrumentation would pay for itself, the twin says so specifically rather than
generally, through the Sensor Value Card, with a device, an indicative cost, an install
effort and a maintenance window. Those costs are assumptions.

### 4.4 What is measured today

Reproduced from `evaluation/metrics.json` over 8 scenarios at 3 seeds, 620 units each, 40
replications, a 120 minute horizon and a 5 minute cadence. These are measured numbers on
simulated data.

| Measure | Target | Measured | Meets it |
|---|---|---|---|
| Dark-station interval coverage, per station | 0.90 | 1.000 | Yes |
| Dark-span interval coverage | 0.90 | 0.998 | Yes |
| False alerts per shift on a quiet line | under 1.0 | 0.70 | Yes |
| Drift detection recall | 0.80 | 1.000 | Yes |
| Defect calibration error, G1 | 0.05 | 0.005 | Yes |
| Defect calibration error, G3 | 0.05 | 0.002 | Yes |
| Conformal coverage at alpha 0.10, G1 | 0.90 | 0.983 | Yes |
| Conformal coverage at alpha 0.10, G3 | 0.90 | 0.976 | Yes |
| Defect risk lead time, G3 | 10 stations | 13 stations | Yes |
| Stall forecast precision | 0.60 | 0.250 | **No** |
| Stall forecast median lead time | 15 min | 5 min | **No** |
| Stall forecast recall | 0.50 | 0.190 | **No** |
| Drift detection precision | not set | 0.281 | |

**The stall forecaster does not meet its gate.** We are not dressing that up and we have
not tuned anything to make it pass. The stall events it is scored against on this line
are dominated by the tail of the repair-time distribution. A drifting station roughly
doubles their frequency but does not schedule one, so a forecast seeded from the current
state can raise the probability of a stall in a region and a window and cannot pinpoint
one 20 to 40 minutes ahead. Eighty-two percent of its predictions could not be scored at
all, because the horizon had not closed when the run ended or because they named a
station nothing watches. The harness counts those separately rather than scoring them as
wrong, and the precision above is over the 132 that could be scored.

What the twin does say correctly on this line is which station has become the constraint
and what the line will lose because of it.

**The consequence is visible in the product rather than hidden by it.** Because the gate
does not pass, the stall forecaster stays in shadow and the floor sees nothing from it.
The action region reads "nothing needs attention" with the count of forecasts held in
shadow beside it. That is the trust ledger doing exactly what it was built to do, and it
is the single most important thing in this submission. A competitor willing to publish
that forecaster on day one would demo better and would be wrong.

### 4.5 Competitive position, including where we lose

A competitive analysis that concludes we win everywhere is not analysis. The full
treatment is in `docs/product/COMPETITIVE_ANALYSIS.md` Sections 7 and 8.

Where we are genuinely differentiated: tier-aware modelling with virtual sensors as a
first-class concept; the trust ledger with shadow mode and automatic demotion; per-unit
process signature to containment list; and the Sensor Value Card.

Where we would lose:

1. **A plant that wants one vendor.** We are a point solution. An incumbent MES or
   automation vendor bundling something adequate beats a better standalone tool on
   procurement grounds, routinely.
2. **A plant with rich, uniform instrumentation and a strong data team.** Our core
   differentiator is worth less there, and a platform with deep signal processing will
   extract more from those signals than we will.
3. **A capital planning decision.** That is a simulation suite's job. We have
   deliberately given up the fidelity it needs.
4. **Deep single-machine health.** Bearing failure prediction from vibration spectra
   belongs to people who have spent a decade on it.
5. **Trust and procurement.** We are three students with a prototype. An incumbent has
   been in that plant for thirty years. This is the largest gap and no feature closes it.
6. **The shadow-mode cost.** Our own trust mechanic means a customer sees nothing on the
   floor for weeks. A competitor happy to show alerts on day one demos better. We are
   betting that the floor's month-three behaviour matters more than the buyer's day-one
   impression. That bet may be right operationally and wrong commercially.

---

## 5. Phased roadmap

### Phase 1: retrospective replay against one plant's historian export. Two weeks plus a data agreement

The cheapest possible path from "works on our simulator" to "found a real drift in real
data". It requires nothing from the plant except an export and an NDA, carries no
deployment risk, and touches no network. It is the single study that would most change
our confidence and it is what we would do first.

Exit condition: the mechanism finds drifts in real data that the plant recognises, or it
does not, and we know which.

### Phase 2: read-only pilot on one line, 90 days

Shadow mode for the first 30 days with nothing published to the floor. Promotion gates
cleared per station thereafter, on the stations that earn them. Measured against the
pre-pilot baseline on the same line rather than against a vendor benchmark.

Alongside it, the user research we have not done: half a shift shadowing a supervisor to
learn what lead time is actionable, structured interviews on alarm tolerance, and an
unfacilitated concept test of the Line view.

Exit condition: a measurable reduction in unplanned line-stop minutes and in units
reaching the repair yard, or an honest report that there was none.

### Phase 3: the instrumentation loop

Act on the Sensor Value Cards the pilot produced, fit the recommended devices in a normal
maintenance window, and measure the realised confidence gain against the modelled one.
This is the loop that turns the product from a reader of a plant into an improver of it,
and it is the first point at which the sensor economics are validated rather than
modelled.

### Phase 4: scale by configuration

A new line is onboarded by writing two files, a Line Definition and a Source Mapping, not
by writing code. Topology discovery drafts the first from observed event streams and
leaves blank what it cannot infer. This is the whole scalability argument and it is
deliberately unglamorous. It is already demonstrated in the prototype by a second,
structurally different line running with no code change.

### What we would build next, and what we would not

Next: the four integration adapters that are specified and not built, and alert delivery
to the channels a plant already uses. Alert delivery is deliberately sequenced after the
trust ledger is proven, because a system that pushes an unearned alert into a phone is
worse than one that does not.

Not: closed-loop control, ever. No photorealistic 3D. No replacement for MES, SCADA, QMS
or the historian.

---

## 6. Risks and mitigations

Including the ones that would embarrass us, not only the ones we have solved.

### 6.1 The risks we have not solved

**The stall forecaster does not clear its gate.** Precision 0.250 against a target of
0.60 and a median lead time of 5 minutes against 15, both measured. *Mitigation, partial:*
the trust ledger keeps it in shadow, so the failure costs the floor nothing except an
absent capability. *Residual risk:* the headline capability in the problem statement is
the one we have not yet delivered, and the diagnosis in `evaluation/report.md` Section 10
points at the stall definition rather than at a tuning parameter, which means the fix is
a specification change and not a weekend.

**We interviewed nobody.** No supervisor, plant manager or controls engineer has seen
this. Four personas, ten findings and a set of design decisions all rest on published
literature. *Mitigation:* every persona is labelled a composite, and
`docs/product/USER_RESEARCH.md` Section 3 lists the seven things we do not know,
including the two that would move a core claim: what lead time is actually actionable,
and what false alarm rate a floor tolerates. *Residual risk:* the product could be
well-built against a wrong model of its user.

**The evaluation grades our simulator against our twin.** Both were written by us, in the
same repository, in the same fortnight. *Mitigation:* ground truth lives in a separate
schema with its own database role, the application role has no grant on it, and a test
asserts the denial rather than trusting the absence of a grant. A second test asserts
that nothing under `twin/` imports the simulator. *Residual risk:* structural isolation
does not make the test independent. Only Phase 1 of the roadmap fixes this, and it is
first for that reason.

**The loss reconciliation can disagree with itself**, by up to about 8 percent of
available production time on some windows. *Mitigation:* both sides are computed from
different evidence deliberately, and the difference is displayed rather than distributed
across the causes to make it vanish. *Residual risk:* where the causes exceed the time
available, two of them are being counted over the same seconds and the twin has not
established where.

**Sensor costs are assumptions, not quotations.** *Mitigation:* every catalogue entry
carries a source field saying so, a test fails the build if one does not, and every
Sensor Value Card repeats the sentence on screen and in the CSV export. *Residual risk:* a
capital request built on our numbers would need requoting before anyone signed it.

### 6.2 The risks in deployment

**Trust collapse from a bad first month.** The failure mode that kills these systems
(F-03, S-16 to S-19). *Mitigation:* this is what the entire ledger, shadow mode,
per-station promotion and automatic demotion exist to prevent, and the demonstration
shows the mechanism working by withholding a predictor rather than by publishing one.

**Controls engineer veto.** *Mitigation:* read-only enforced at the protocol type, a test
over every adapter implementation, no endpoint that applies anything, and a section of
the README written for that reader naming the file and the test to check.

**Clock skew read as a slow station.** A correction applied to a genuinely slow station
would hide exactly what the twin is looking for. *Mitigation:* skew is estimated from
adjacent unit handoffs, reported, and never applied as a correction. Where it exceeds the
line's tolerance the twin says the number is the skew rather than publishing it as a
cycle time.

**Onboarding a line whose topology we cannot infer.** *Mitigation:* topology discovery
leaves uninferable fields blank and marks them rather than guessing a buffer capacity.

### 6.3 The commercial risks

**Procurement against an incumbent.** No feature closes this. *Mitigation:* the only
honest route is a narrow, cheap, read-only pilot on one line where the downside is a
wasted quarter rather than a wasted capital cycle. That is why Phase 2 is scoped to one
line and 90 days.

**Shadow mode demos worse than a competitor's day-one alerts.** *Mitigation:* none
available that does not compromise the product. We have written down in
`docs/quality/DEFINITION_OF_DONE.md` Section 4 that we will not remove the shadow-mode
demonstration to make the demo look stronger, so that the pressure of a deadline meets
something decided in advance.

**A platform vendor ships a live flow model.** The most likely competitive move against
us, and several have the data foundation to make it. *Mitigation:* none technical. The
differentiation would fall entirely onto the trust ledger and the sensor economics.

**No pricing research at all.** We do not know what a plant would pay. Stated rather than
estimated.

---

## 7. What is built, and what is specified but not built

Built and running: the 42-station simulator with eight scenarios, the read-only
connector, state estimation including virtual sensors for the six dark stations, the
discrete-event forecaster, drift detection, the defect models, the counterfactual
sandbox, retro-trace and containment export, sensor value scoring, the trust ledger with
promotion and demotion, all three views, and the evaluation harness that produces every
number in Section 4.4.

Specified and not built: four of the six integration adapters, alert delivery to email or
messaging, and authentication. `docs/technical/SECURITY_REQUIREMENTS.md` Section 6 lists
what else is missing.

Not verified: a screen reader pass and a 3 metre legibility check, both of which need a
person and a room.

---

## 8. Limitations

Repeated here in one place rather than distributed, because a reader deciding whether to
believe this document should be able to find them together.

- All data is simulated. The evaluation grades our simulator against our twin.
- No primary user research. The personas are composites from published literature.
- One of 121 sources was read in full. The rest were surfaced and verified through
  search, and `RESEARCH_SOURCES.md` records which is which.
- Sensor costs and the actionable-share assumption are ours, not quotations or
  measurements.
- The modelled business case computes to zero on the reference line, by design.
- The stall forecaster misses its gate on both precision and lead time.
- There is no authentication, and the persona switcher in the header is a demonstration
  affordance.
- Cross-platform verification was performed on Windows only.

---

## 9. Where to check every claim

| Claim | Where it is checkable |
|---|---|
| The measured numbers in Section 4.4 | `evaluation/metrics.json`, regenerated by `make evaluate` |
| The diagnosis of the missed gate | `evaluation/report.md` Section 10 |
| The read-only posture | `connector/protocol.py` and `tests/test_adapters.py` |
| No plant value in code | `tests/` asserts it over the whole source tree |
| Ground truth isolation | Separate schema, separate role, a test asserts the denial |
| Every source behind a finding | `RESEARCH_SOURCES.md`, by `S-nn` |
| What we do not know | `docs/product/USER_RESEARCH.md` Section 3 |
| Where we would lose | `docs/product/COMPETITIVE_ANALYSIS.md` Section 7 |
| What is still unfinished | `docs/ai/TASKS.md` and `docs/quality/DEFINITION_OF_DONE.md` Section 3 |
