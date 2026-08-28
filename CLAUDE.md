# CLAUDE.md

Project instructions for Claude Code working in this repository.

**Project:** DigitalTwin.ai, a live read-only digital twin of a mixed-model vehicle assembly line.
**Context:** Accenture Innovation Challenge 2026, Problem Statement 4, Round 2. Team Aeronomics.
**Repository:** https://github.com/tanmaysahare/Digital_Twin

---

## Read these before writing code

In this order. Do not start implementing before you have read at least the first four.

1. `docs/product/PRODUCT_VISION.md` and `docs/product/PRD.md`. What we are building and why.
2. `docs/human-design/HUMAN_DESIGN_GUIDELINES.md`. **Binding, with veto power over every other design document.**
3. `docs/technical/TECHNICAL_SPEC.md` and `docs/technical/ARCHITECTURE.md`. The algorithms and the boundaries.
4. `docs/ai/IMPLEMENTATION_PLAN.md` and `docs/ai/TASKS.md`. What to build in what order.
5. Everything else in `docs/` as the task requires. Each document links to its neighbours.

If a document conflicts with another, this is the precedence order:
`HUMAN_DESIGN_GUIDELINES.md` > `PRD.md` > `TECHNICAL_SPEC.md` > everything else.
If you find a genuine conflict, fix the losing document in the same change rather than
working around it.

---

## The seven rules

These are the ones that are easy to violate without noticing. Every one of them is
enforced by a test or a lint rule, so violating one produces a failing build rather than
a quiet regression.

1. **Read-only.** No code path writes to a control system. The `SourceAdapter` protocol
   has three methods and none of them writes. Do not add one.

2. **Provenance always.** Every value the twin produces is an `Estimate` carrying
   `MEASURED`, `DERIVED` or `INFERRED`. An inference is never presented as a measurement.
   The type makes this structural: you cannot construct an `Estimate` without a
   provenance.

3. **Intervals where the estimate is an interval.** A dark station's cycle time is a
   bound, not a midpoint. Never collapse an interval to a point for convenience.

4. **The ledger is the only path to the screen.** A predictor emits a prediction, the
   ledger records it, and the ledger decides whether that predictor is `ACTIVE` for that
   station. There is no direct route from a model to the interface.

5. **No plant-specific value in code.** Station IDs, buffer capacities, thresholds, tag
   names and gate positions live in `config/`. A test asserts this.

6. **Determinism.** Every random draw comes from a generator seeded on
   `(cycle_id, replication)`. Never `random.random()`, never `np.random.rand()`. A lint
   rule catches it.

7. **No em dashes, no emoji, no marketing vocabulary.** Anywhere in the repository:
   code, comments, commits, UI strings, documentation. Lint-enforced.

---

## Design rules, compressed

The full set is in `docs/human-design/`. The ones you will hit immediately:

- **No dark theme.** Light only. There is no `prefers-color-scheme` block and stylelint
  prevents one.
- **No gradients.** Flat fills.
- **No purple-to-blue accent.** The accent is `--accent: #1B3A5C`, used on interactive
  text and focus rings only.
- **Greyscale by default. Colour means abnormal.** A normal line renders with no
  saturation at all. There is no green for good.
- **Border radius 2px or 0.** No rounded cards, no pills.
- **No shadows** except the drawer and the sandbox overlay.
- **Tables, not card grids.** A three-across grid of identical cards is prohibited.
- **Six icons total**, listed in `docs/design/DESIGN_SYSTEM.md` Section 8. No icon
  library. No AI sparkle iconography.
- **No component library.** Every component is hand-written, listed in
  `docs/design/UI_COMPONENTS.md`.
- **Realistic plant data everywhere.** Station S20, VIN 3C4PDCBG7JT, part lot B-4471.
  Never `Item 1`, never lorem ipsum.
- **No decorative motion.** Two motion tokens exist, both for showing that a value
  changed.

Before calling a screen done, run the twelve checks in `HUMAN_DESIGN_GUIDELINES.md`
Section 5.

---

## Commands

```
make up            docker compose up, seeded demo
make down
make test          full test suite
make lint          ruff, mypy strict, eslint, stylelint, and the design rule checks
make evaluate      regenerate the evidence pack (evaluation/report.md)
make seed          rebuild the seeded demo database
make reference-sheets   regenerate docs/design/REFERENCE_IMAGES/*.svg from tokens
```

`make lint` includes the design rule checks in `docs/quality/TEST_PLAN.md` Section 7.
Run it before every commit.

---

## How to work here

**Follow `docs/ai/TASKS.md` in order.** Tasks have IDs and dependencies. Do not jump
ahead: the phases are ordered so that each one produces something demonstrable.

**Small changes.** One task per change. A change that touches the forecaster and the
design tokens is two changes.

**Test first where the behaviour is specified.** Every acceptance criterion in
`docs/quality/ACCEPTANCE_CRITERIA.md` is a test that can be written before the code.

**Update the documents in the same change.** If behaviour diverges from a document, the
document is now wrong. Fix it in the same commit.

**Ask before deviating.** If a specification looks wrong, say so rather than quietly
implementing something better. Several decisions in these documents look suboptimal and
are deliberate. Two examples: LightGBM rather than a sequence model, and shadow mode
delaying all floor-visible value by weeks. Both are argued in
`docs/technical/ARCHITECTURE.md` Section 9 and `docs/product/COMPETITIVE_ANALYSIS.md`
Section 7.

**When stuck on scope, cut down the list in `docs/product/MVP_SCOPE.md` Section 4**, in
order. Never cut from `docs/quality/DEFINITION_OF_DONE.md` Section 4.

---

## What this project is not

Do not build any of these, even if they seem like obvious improvements.

- A 3D or isometric visualisation of the factory.
- A closed-loop or write-back capability of any kind.
- A chatbot or natural-language interface.
- A dark theme, a theme toggle, or a settings page for appearance.
- An onboarding tour, an empty-state illustration, or a celebration state.
- A replacement for MES, SCADA, QMS or the historian.
- A deep learning model for defect prediction. Gradient boosting is the specified choice
  and the reason is in `TECHNICAL_SPEC.md` Section 6.2.
- Alert delivery to email, Teams or a phone. Deliberately sequenced after the trust
  ledger is proven, and the reason is in `INTEGRATIONS.md` Section 14.

---

## The two things that make this project different

If you understand nothing else, understand these, because they are what the whole design
serves.

**Uneven sensor coverage is the problem, not an inconvenience.** Six of 42 stations emit
nothing. The twin infers their behaviour from unit conservation through flanking
timestamps, reports a bound rather than a number, says plainly what it cannot separate,
and converts each blind spot into a costed sensor recommendation. Any change that makes
a dark station look like a monitored one is wrong.

**False alarms are the failure mode.** A supervisor who learns to ignore this system has
correctly concluded it is not worth reading, and no later accuracy improvement recovers
that. Shadow mode, per-station promotion gates, automatic demotion and a floor-visible
scorecard are not features to be trimmed under time pressure. They are the product.

---

## Repository layout

```
CLAUDE.md              this file
README.md              the public front door, judge-facing
Makefile
docker-compose.yml
docs/                  the specification set. Start at docs/README.md
config/                LineDefinition, SourceMapping, sensor catalogue
plantsim/              the line simulator and the scenarios
connector/             source adapters, read-only by protocol
twin/                  state, forecast, defect, retro, ledger, sensors, api, workers
evaluation/            the harness and the generated evidence pack
web/                   Next.js application
tests/
```

---

## Current status

Specification complete. Implementation not started.
Begin at `docs/ai/TASKS.md`, task T-001.
