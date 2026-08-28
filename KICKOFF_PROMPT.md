# KICKOFF_PROMPT.md

The initial prompt to give Claude Code. Copy the block below verbatim into a fresh
Claude Code session opened in the repository root.

**Before you paste it:**

1. Copy this whole folder into your local clone of `github.com/tanmaysahare/Digital_Twin`,
   so that `CLAUDE.md`, `RESEARCH_SOURCES.md` and `docs/` sit at the repository root.
2. Commit and push the specification set first. It is a deliverable in its own right, and
   it means that if the build stalls, the repository still shows a complete solution
   design.
3. Open Claude Code in the repository root so it picks up `CLAUDE.md` automatically.
4. Paste the prompt below.

**After Phase 0, do not paste this again.** Start each subsequent session with the
shorter per-phase prompt in the section that follows.

---

## The kickoff prompt

```
This repository contains a complete specification set for a project called
DigitalTwin.ai and no implementation. You are building the implementation.

CONTEXT

We are Team Aeronomics (three final-year students at IIT Kanpur). This is our Round 2
submission for the Accenture Innovation Challenge 2026, Problem Statement 4:
DigitalTwin.ai for a vehicle assembly line. Round 1 was a concept; Round 2 requires a
working prototype that demonstrates the core predictive mechanism on realistic
production data, a public GitHub repository, a README and a demo video.

What the product is, in one sentence: a live, read-only digital twin of a mixed-model
vehicle assembly line that runs the next two hours before the line does, using only the
data the plant already emits, and hands each stakeholder the one decision that changes
the outcome.

Two things make it different from every other submission you could build, and they
govern every decision:

1. Uneven sensor coverage is the problem, not an inconvenience. Six of 42 stations emit
   no machine data at all. The twin infers their behaviour from unit conservation
   through flanking timestamps, reports a bound rather than a number, says plainly what
   it cannot separate, and turns each blind spot into a costed sensor recommendation.
   Any change that makes a dark station look like a monitored one is wrong.

2. False alarms are the failure mode. A supervisor who learns to ignore the system has
   correctly concluded it is not worth reading, and no later accuracy improvement
   recovers that. Shadow mode, per-station promotion gates, automatic demotion and a
   floor-visible scorecard are the product, not features to trim under time pressure.

FIRST, READ THE SPECIFICATION

Read these before writing any code, in this order:

  1. CLAUDE.md
  2. docs/product/PRODUCT_VISION.md
  3. docs/product/PRD.md
  4. docs/human-design/HUMAN_DESIGN_GUIDELINES.md
  5. docs/technical/TECHNICAL_SPEC.md
  6. docs/technical/ARCHITECTURE.md
  7. docs/ai/IMPLEMENTATION_PLAN.md
  8. docs/ai/TASKS.md

Then confirm back to me, in under 200 words:
  - the core predictive mechanism in your own words
  - what happens at a Tier C station and why it is never given a point value
  - why a predictor cannot show anything on the floor until it has cleared a gate
  - the first three tasks you will do

Do not write code until I have confirmed your summary is correct.

THEN BUILD PHASE 0

After I confirm, implement Phase 0 from docs/ai/TASKS.md: tasks T-001 through T-013.
That is the repository skeleton, CI, Docker Compose, design tokens, the full lint suite,
the database schema with its separate truth schema, and the two line configurations.

Work one task at a time. For each task:
  - read the acceptance criteria it references, by ID, in
    docs/quality/ACCEPTANCE_CRITERIA.md
  - write the test first where the behaviour is specified
  - implement
  - run `make lint` and `make test`
  - run the checklist in docs/quality/DEFINITION_OF_DONE.md Section 1
  - commit with the task ID in the message

Build the lint suite (T-006) before writing any interface code. It enforces the design
rules, and retrofitting them onto a built interface means rewriting the interface.

THE RULES THAT MATTER MOST

Seven rules, all enforced by a test or a lint rule, all easy to violate by accident:

  1. Read-only. The SourceAdapter protocol has three methods and none of them writes.
     Never add one.
  2. Provenance always. Every value the twin produces is an Estimate carrying MEASURED,
     DERIVED or INFERRED. An inference is never presented as a measurement.
  3. Intervals stay intervals. Never collapse a bound to a midpoint for convenience.
  4. The ledger is the only path to the screen. A predictor emits, the ledger records,
     the ledger decides whether to publish.
  5. No plant-specific value in code. Station IDs, capacities, thresholds and tag names
     live in config/.
  6. Determinism. Every random draw comes from a generator seeded on
     (cycle_id, replication). Never the global RNG.
  7. No em dashes, no emoji, no marketing vocabulary. Anywhere in the repository:
     code, comments, commit messages, UI strings, documentation.

DESIGN RULES

docs/human-design/HUMAN_DESIGN_GUIDELINES.md is binding and has veto power over every
other design document. The ones you will hit first:

  - No dark theme. Light only. No prefers-color-scheme block anywhere.
  - No gradients. Flat fills.
  - No purple-to-blue accent. The accent is #1B3A5C, used on interactive text and focus
    rings only.
  - Greyscale by default, colour means abnormal. A normally running line renders with no
    saturation at all. There is no green for good.
  - Border radius 2px or 0. No rounded cards, no pills.
  - No shadows except the drawer and the sandbox overlay.
  - Tables, not card grids. A three-across grid of identical cards is prohibited.
  - Six icons total, listed in docs/design/DESIGN_SYSTEM.md Section 8. No icon library.
    No AI sparkle iconography.
  - No component library. Every component is hand-written and listed in
    docs/design/UI_COMPONENTS.md.
  - Realistic plant data everywhere: station S20, VIN 3C4PDCBG7JT, part lot B-4471.
    Never "Item 1", never lorem ipsum.
  - No decorative motion, no loading skeletons, no empty-state illustrations, no
    onboarding tour.

The reason is not taste. This goes on a wall in a factory and is read at three metres by
someone wearing gloves who has twenty seconds. It also must not look like it was
generated, because a judge who has seen forty submissions recognises that instantly and
discounts everything behind it.

DO NOT BUILD

Even if they seem like obvious improvements:
  - 3D or isometric factory visualisation
  - Any write-back or closed-loop capability
  - A chatbot or natural-language interface
  - A dark theme or a theme toggle
  - An onboarding tour, empty-state illustration, or celebration state
  - A deep learning defect model (gradient boosting is specified; the reason is in
    TECHNICAL_SPEC.md Section 6.2)
  - Alert delivery to email, Teams or phone

PUSH BACK RATHER THAN IMPROVING SILENTLY

If a specification looks wrong, say so before implementing something different. Several
decisions look suboptimal and are argued in the documents: LightGBM over a sequence
model, shadow mode delaying all floor value by weeks, no component library, no 3D,
greyscale with no green for good, requiring both EWMA and CUSUM to signal. Proposing any
of these as an improvement without addressing the argument means the document was not
read.

If you find a genuine conflict between two documents, fix the losing one in the same
change rather than working around it. Precedence:
HUMAN_DESIGN_GUIDELINES.md > PRD.md > TECHNICAL_SPEC.md > everything else.

Start by reading. Then give me the summary.
```

---

## Per-phase prompts for later sessions

Start each subsequent session fresh with the relevant prompt. Do not continue a long
session across phases: context drifts away from the documents, and the drift shows up as
gradients and card grids.

### Phase 1

```
Continue DigitalTwin.ai. Phase 0 is complete. Implement Phase 1 from docs/ai/TASKS.md,
tasks T-020 through T-043: the SimPy line simulator with tier filtering and scenario
injection, the two read-only adapters, normalisation, the state estimator, and the
virtual sensors for dark stations.

Read docs/technical/TECHNICAL_SPEC.md Sections 3 and 4 in full before starting, and
docs/product/PRD.md Sections 1 and 6 for the reference line and the scenarios.

T-040, virtual sensors, is the most important task in this phase and possibly in the
project. Follow TECHNICAL_SPEC.md Section 4.3 exactly, including the multi-dark-station
case and the unresolvable case in STA-07. Write the coverage test first: the derived
interval must contain the simulator's ground truth in at least 90 percent of cycles over
5,000 cycles. Never produce a point estimate for a dark station anywhere.

The simulator writes ground truth to a separate schema that the twin's database role
cannot read. Verify that with a test rather than assuming it. If the twin can see ground
truth, every evaluation number we later publish is worthless.

Gate for this phase: if the T-040 coverage test is below 90 percent, stop and tell me
before starting Phase 2.
```

### Phase 2

```
Continue DigitalTwin.ai. Phase 1 is complete. Implement Phase 2 from docs/ai/TASKS.md,
tasks T-050 through T-071: the discrete-event forecaster, active period attribution,
drift detection, the trust ledger with its gates, the defect risk model, and the
evaluation harness.

Read docs/technical/TECHNICAL_SPEC.md Sections 5, 6 and 9 in full before starting.

Three details that are easy to get wrong and matter more than they look:

  - T-052, drift extrapolation. The forecaster must sample a drifting station from its
    recent window shifted forward by the estimated slope. Without this it forecasts from
    the drifting station's stale distribution and systematically under-predicts the
    stall, which is the whole demo.
  - T-055, both EWMA and CUSUM must signal before a drift event is emitted, and CUSUM
    gives the onset estimate. The interface says "drifted since 09:14", not "detected at
    09:26", and the difference matters to a supervisor.
  - T-059, missed_event rows. Without them recall cannot be computed, and a product that
    reports precision as if it were accuracy is exactly what this one argues against.

The evaluation harness (T-069, T-070) is a deliverable, not a test utility. It produces
the evidence pack that makes every claim in the README checkable. Its report includes
the false alarm rate from the fault-free scenario next to every accuracy figure, and its
own limitations section in its own words.

Gate for this phase: run `make evaluate` and show me the numbers. If median lead time is
under 15 minutes or precision is under 0.60, stop and diagnose before building any
interface.
```

### Phase 3

```
Continue DigitalTwin.ai. Phase 2 is complete and the evaluation numbers are acceptable.
Implement Phase 3 from docs/ai/TASKS.md, tasks T-080 through T-102: the API, the
component library, Line view, both drawers, the counterfactual sandbox, retro-trace and
the sensor value cards.

Before writing any interface code, read in full:
  docs/human-design/HUMAN_DESIGN_GUIDELINES.md
  docs/design/DESIGN_SYSTEM.md
  docs/design/UI_COMPONENTS.md
  docs/design/UX_SPEC.md Sections 1 and 2
  docs/design/WIREFRAMES/01-line-view.md
  docs/design/WIREFRAMES/02-line-view-quiet.md
  docs/design/REFERENCE_IMAGES/line-strip-study.svg

Build the calm state first. WIREFRAMES/02 is the most common screen in the product and
the hardest to get right: it must read as a complete, deliberate instrument telling you
the line is fine, not as an empty state waiting for content. No illustration, no "you
are all caught up", no centred text, no skeleton.

Then build the active state from WIREFRAMES/01.

Before calling any screen done, run the twelve checks in HUMAN_DESIGN_GUIDELINES.md
Section 5 and tell me the result of each. A screen passes all twelve or it is not done.

Every string goes through the checklist in docs/human-design/UX_WRITING_GUIDELINES.md
Section 7. Read each one aloud. If you would not say it standing next to someone at S20,
rewrite it.
```

### Phase 4

```
Continue DigitalTwin.ai. Implement Phase 4 from docs/ai/TASKS.md, tasks T-110 through
T-124: Plan view, Program view, the print stylesheet, topology discovery, and second-line
onboarding.

Read docs/design/UX_SPEC.md Sections 3 and 4, plus WIREFRAMES/03 and WIREFRAMES/04.

Two things must be right or these views are worse than not shipping them:

  - The loss Pareto carries its reconciliation line. If the twin's loss accounting does
    not tie to the plant's own shift reporting, it says so rather than presenting a
    second set of books.
  - The modelled-against-realised region in Program view must look correct when it shows
    a shortfall. A tool that only reports success is not opened twice.

Every assumption field in the business case carries its source and its uncertainty, and
the sensitivity ranking is mandatory. An assumption without a source is a number nobody
can defend in a capital review, which is the only room that screen appears in.

Nothing in either view is a placeholder. If a panel cannot be built with real data,
remove it rather than faking it.
```

### Phase 5

```
Continue DigitalTwin.ai. Implement Phase 5 from docs/ai/TASKS.md, tasks T-130 through
T-144: the full evaluation run, the edge case and error message passes, cross-platform
verification, the README, screenshots, and the final checklist.

Run the full evaluation (8 scenarios x 20 seeds) and then reconcile every quantitative
claim in the README against evaluation/metrics.json. If a number in the README does not
appear in the metrics file, either fix the number or remove the claim.

The README follows docs/human-design/CONTENT_STYLE_GUIDELINES.md Section 7 exactly,
including the "For your controls engineer" section from
docs/technical/SECURITY_REQUIREMENTS.md Section 9, and a real limitations section with
real limitations.

At least one screenshot shows the calm state: a normal line with the action list reading
"Nothing needs attention". That screenshot does more for our credibility with an
operations audience than any alert screenshot.

Then work through docs/quality/DEFINITION_OF_DONE.md Section 3 box by box and tell me
which ones do not pass.

Do not do any of the things in DEFINITION_OF_DONE.md Section 4, whatever the time
pressure.
```

---

## A shorter version, if you want one prompt only

Some people prefer a single opening prompt without the confirmation step. This one works
but gives up the check that the agent actually read the documents, which is where most of
the value of this specification set sits.

```
Read CLAUDE.md, then docs/README.md, then follow the reading order it gives.

Implement docs/ai/TASKS.md in order, starting at T-001, one task at a time. For each
task, read its acceptance criteria by ID in docs/quality/ACCEPTANCE_CRITERIA.md, write
the test first, implement, run `make lint` and `make test`, run the Section 1 checklist
in docs/quality/DEFINITION_OF_DONE.md, and commit with the task ID.

docs/human-design/HUMAN_DESIGN_GUIDELINES.md is binding and has veto power over every
other design document. Build the lint suite (T-006) before any interface code.

Stop and ask me at the end of each phase, and at the two gates: T-040 coverage below 90
percent, or Phase 2 median lead time below 15 minutes or precision below 0.60.

Push back rather than silently improving on a specification you disagree with.
```

---

## What to do when it goes wrong

| Symptom | Cause | Fix |
|---|---|---|
| A gradient, a dark theme or a card grid appears | Session drifted from the design documents | New session. Re-read `HUMAN_DESIGN_GUIDELINES.md` in full. Do not summarise it into the prompt, load it |
| Dark stations start showing point values | The provenance discipline slipped | Re-read `TECHNICAL_SPEC.md` Section 4.3. Check that `Estimate` still cannot be constructed without a provenance |
| Predictions appear on screen without a gate | The ledger was bypassed | Check the import test on `twin/ledger/`. A predictor is calling `publish` directly |
| Evaluation numbers look too good | Ground truth leaked | Run the T-008 permission test. This is the failure that invalidates everything |
| Marketing language in the README | Content style not loaded | Run `make lint`. If it passed, the banned-word list needs the new word |
| A task produces something bigger than asked | Scope crept | Revert, split the task, and be more specific about the boundary |
| It says "let me improve on the spec" | It has an idea | Ask it to state the idea and the argument against the document's position first. Sometimes it is right |
