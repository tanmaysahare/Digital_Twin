# USER_PERSONAS.md

**Purpose:** four people the product is designed around. Three use it. One decides whether it is allowed to exist.
**Basis:** synthesised from published operations research, industrial HMI practice, and the alarm-fatigue and operator-trust literature listed in RESEARCH_SOURCES.md. These are composites, not interview subjects. USER_RESEARCH.md is explicit about what we did and did not observe.
**Last updated:** 2026-08-28

---

## Persona 1: Priya Deshmukh, Floor Supervisor

**Primary persona.** If the design serves anyone perfectly, it is her.

| | |
|---|---|
| Role | Shift supervisor, final assembly, Line 2 |
| Experience | 11 years on the floor, 4 as supervisor |
| Span | 16 stations, 22 operators plus 2 floaters |
| Shift | 06:00 to 14:30, handover briefing at 05:45 |
| Devices | 55-inch line-side display, a rugged 10-inch tablet carried on the floor, a shared desktop in the shift office |
| Environment | 78 dB ambient, gloves on, standing, interrupted constantly |

**A day.** She walks the line twice a shift. The rest of the time she is reacting: an andon at S31, a quality hold at G2, an operator out sick. She has a laminated card of escalation numbers and a whiteboard with today's target on it. Her performance is judged on units out and on line-stop minutes.

**What she already knows that the software does not.** That S34's operator is new this week. That the S20 fixture has been "a bit sticky since the shutdown". That the B-shift habit of running two units into the G2 buffer before break is why Monday mornings look strange. Her tacit knowledge is better than any model's on causes; the model's advantage is that it watches all 42 stations continuously and she cannot.

**Goals**
- Finish the shift on target without a stop.
- Know about a problem while she can still do something about it, which means at least 15 minutes before it lands.
- Not send a maintenance team to a station that is fine.
- Hand over cleanly at 14:30 with the next supervisor knowing what is building.

**Frustrations**
- Systems that alert on everything. She has muted two of them already, and the literature says she is typical, not difficult (S-16 to S-19).
- Being told a number without being told what to do about it.
- Being asked to log into something while wearing gloves.
- Reports that explain yesterday.

**What she needs from DigitalTwin.ai**
- One ranked action, with a number on it, at a glance from three metres.
- The lead time stated in minutes, prominently, because that is what determines whether she can act.
- The evidence in one tap, because she will not act on an unexplained instruction and she is right not to.
- A way to see the system's own hit rate on her stations, so that trust is earned rather than requested.
- Silence on a quiet shift.

**How we will know we failed her.** She glances at the screen once at handover and never again. Or she starts treating the alert region as decoration.

**Design consequences**
- Line view is the default view and needs no navigation to be useful.
- Type sizes and contrast are set for 3 m legibility, not for a designer's monitor.
- Touch targets sized for gloves (see ../design/ACCESSIBILITY.md).
- Colour is used only for abnormal state, following high-performance HMI practice (ISA-101 lineage, S-40 to S-43), so that an abnormal station is the only thing on screen with saturation.
- The action list is at most three items and is allowed to say "nothing to do".

---

## Persona 2: Rakesh Iyer, Plant Manager

| | |
|---|---|
| Role | Plant manager, 2 lines, approximately 900 units per day |
| Experience | 19 years, industrial engineering background, ran continuous improvement before this |
| Rhythm | Monday planning, Friday review, monthly with the regional director, quarterly capital cycle |
| Devices | Laptop, meeting-room screen |
| Environment | Meetings, spreadsheets, and a standing argument about where to put the next investment |

**A week.** He is trying to move a number that has three or four causes at once. He gets an OEE report that tells him availability was 84 percent and does not tell him which of blocked, starved, changeover and quality drove the gap, or how those shares moved. When he wants a real answer he asks an industrial engineer for a simulation study and gets it in three weeks, by which time the line has changed.

**Goals**
- Find where the constraint actually lives, and know whether it has moved.
- Decide buffer sizes, floater allocation and maintenance windows with evidence.
- Spend a limited retrofit budget where it returns the most.
- Defend those decisions to a regional director who asks for the assumptions.

**Frustrations**
- OEE as a single number that hides the mechanism.
- Simulation studies that are stale before they are delivered.
- Improvement claims that cannot be separated from mix, volume or seasonality.
- Being asked to fund sensors with no argument beyond "more data is good".

**What he needs from DigitalTwin.ai**
- Constraint migration over time, not a snapshot. Which station was the bottleneck each week, and for what share of each week.
- A loss Pareto that splits blocked, starved, down, changeover and quality, with the shares reconciling to the shift gap.
- Buffer and staffing recommendations he can test in the sandbox before committing.
- The sensor investment queue as a ranked, costed list with modelled value and required maintenance window, so it becomes a budget line rather than an argument.
- The predictor scorecard, because he will be asked whether the system works and needs more than an opinion.

**Design consequences**
- Plan view is dense, tabular, and printable. He will take it into a meeting.
- Every recommendation exposes its assumptions inline and lets him change them.
- Time ranges are first-class. Nothing in Plan view is "now".

---

## Persona 3: Meera Krishnan, Director of Manufacturing Operations

| | |
|---|---|
| Role | Regional operations director, 12 plants across 3 countries |
| Experience | 22 years, previously plant manager, now capital allocation and standardisation |
| Rhythm | Quarterly capital review, annual planning |
| Devices | Laptop, boardroom screen, phone for anything under a minute |

**A quarter.** She is deciding whether a thing that worked in one plant will work in eleven others whose equipment vintages span twenty years. Her scepticism is well founded: she has funded rollouts that worked in the pilot and stalled everywhere else, usually because the pilot site had data maturity the other sites did not.

**Goals**
- Decide rollout, sequencing and budget with defensible numbers.
- Know which sites are actually ready and which will need instrumentation before they see value.
- Track whether the promised benefit materialised, honestly, including where it did not.

**Frustrations**
- Business cases built on vendor benchmarks rather than on her own sites.
- Pilots that succeed because of the pilot team's attention rather than the product.
- No mechanism to compare modelled benefit against realised benefit after the fact.

**What she needs from DigitalTwin.ai**
- A site readiness score computed from what each site actually emits, not from a questionnaire.
- A rollout wave plan that sequences sites by readiness and value, with the instrumentation prerequisites attached.
- A business case whose assumptions are visible and editable, so she can run her own numbers and own the result.
- A realised-versus-modelled tracker that is allowed to show a shortfall.

**Design consequences**
- Program view leads with readiness, not with a projected saving.
- The business case is a model, not a picture. Every input is an editable field with its source and its uncertainty.
- Realised-versus-modelled is always shown, even when it is unflattering. A tool that only reports success is a tool nobody senior believes.

---

## Persona 4: Arjun Nair, Controls and OT Engineer

**Not a daily user. The gatekeeper.** No plant deploys this without his sign-off, and the fastest way to kill the product is to fail his review.

| | |
|---|---|
| Role | Controls engineer, responsible for PLC integrity and the OT network |
| Experience | 15 years, has been on call for a line-down at 02:00 more times than he wants to count |
| Concern | Anything new touching Level 2 |

**His position.** He has seen an analytics vendor's polling load slow a PLC scan cycle. He works to a maintenance window calendar with two or three slots a year and everything competes for them. His default answer to a new system is no, and that is a correct default.

**Goals**
- Nothing new on the control network.
- No unplanned load on a PLC.
- No inbound path from IT to OT.
- Clear behaviour when the connector fails, and a way to turn it off in one action.

**What he needs from DigitalTwin.ai**
- Read-only enforced at the interface level, not promised in a slide. He should be able to read the adapter type signature and see there is no write path.
- A deployment that sits in the DMZ above the control network, with a documented data flow direction.
- Documented polling rates and the option to consume from an existing broker or historian rather than adding a client to a PLC.
- No requirement for a maintenance window on day one.
- A kill switch.

**Design consequences**
- ../technical/SECURITY_REQUIREMENTS.md is written for him and is the first document a plant IT reviewer should be handed.
- The connector is documented as consuming existing infrastructure by preference and adding a client only as a last resort.
- The product's read-only posture is architectural, not a setting that could be changed.

---

## Anti-persona: the executive dashboard viewer

The person who wants a screen with a large green number and no way to check it. We are not building for them, and where their preferences conflict with the four personas above, they lose. A number without its evidence is the failure mode this product exists to correct.

---

**Related:** [USER_RESEARCH.md](USER_RESEARCH.md) · [USER_STORIES.md](USER_STORIES.md) · [USER_FLOWS.md](USER_FLOWS.md) · [../design/UX_SPEC.md](../design/UX_SPEC.md)
