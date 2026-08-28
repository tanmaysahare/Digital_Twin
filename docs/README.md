# docs

The specification set for DigitalTwin.ai. Written before implementation, and maintained
alongside it: if the code diverges from a document, the document is wrong and gets fixed
in the same change.

**Precedence when documents disagree:**
`human-design/HUMAN_DESIGN_GUIDELINES.md` > `product/PRD.md` > `technical/TECHNICAL_SPEC.md` > everything else.

---

## Read in this order

If you are new to the project, four documents give you the whole picture:

1. `product/PRODUCT_VISION.md` for what and why
2. `product/PRD.md` for the specification
3. `technical/TECHNICAL_SPEC.md` for how the prediction actually works
4. `human-design/HUMAN_DESIGN_GUIDELINES.md` for what it looks like and why the rules are absolute

---

## Product

| Document | What it covers |
|---|---|
| [product/PRODUCT_VISION.md](product/PRODUCT_VISION.md) | The problem, the four ideas that make it work on a real line, non-goals |
| [product/PRD.md](product/PRD.md) | The reference line, every functional requirement by ID, quality targets, the scenario catalogue, risks |
| [product/MVP_SCOPE.md](product/MVP_SCOPE.md) | The demo script, what ships, what is deferred, the cut lines |
| [product/USER_PERSONAS.md](product/USER_PERSONAS.md) | Priya, Rakesh, Meera, and Arjun the gatekeeper |
| [product/USER_STORIES.md](product/USER_STORIES.md) | 55 stories across 10 epics, with priorities |
| [product/USER_FLOWS.md](product/USER_FLOWS.md) | 10 flows including the ordinary shift and the data-failure path |
| [product/COMPETITIVE_ANALYSIS.md](product/COMPETITIVE_ANALYSIS.md) | Four market camps, the gap between them, and where we would lose |
| [product/USER_RESEARCH.md](product/USER_RESEARCH.md) | What the evidence supports, what we do not know, what to study next |

## UX and design

| Document | What it covers |
|---|---|
| [design/UX_SPEC.md](design/UX_SPEC.md) | Screen by screen, region by region |
| [design/DESIGN_SYSTEM.md](design/DESIGN_SYSTEM.md) | Tokens, the colour rule, type, space, motion |
| [design/VISUAL_DIRECTION.md](design/VISUAL_DIRECTION.md) | The four references and the signature elements |
| [design/UI_COMPONENTS.md](design/UI_COMPONENTS.md) | 32 components, and why there is no component library |
| [design/RESPONSIVE_DESIGN.md](design/RESPONSIVE_DESIGN.md) | Wall, desk, floor tablet, print |
| [design/ACCESSIBILITY.md](design/ACCESSIBILITY.md) | WCAG 2.2 AA plus the industrial requirements that go beyond it |
| [design/REFERENCE_IMAGES/](design/REFERENCE_IMAGES/) | Generated palette, state, line strip and type sheets, plus the reference brief |
| [design/WIREFRAMES/](design/WIREFRAMES/) | Eight annotated layouts including the calm state |

## Technical

| Document | What it covers |
|---|---|
| [technical/ARCHITECTURE.md](technical/ARCHITECTURE.md) | System context, components, the 2-minute cycle, the four boundaries, decisions and their costs |
| [technical/TECHNICAL_SPEC.md](technical/TECHNICAL_SPEC.md) | Every algorithm with its parameters. The longest and most load-bearing document here |
| [technical/DATABASE_SCHEMA.md](technical/DATABASE_SCHEMA.md) | Tables, integrity rules, and why cycle time is stored as a pair of bounds |
| [technical/API_SPEC.md](technical/API_SPEC.md) | Endpoints, the `Estimate` shape, and what the API deliberately does not offer |
| [technical/SECURITY_REQUIREMENTS.md](technical/SECURITY_REQUIREMENTS.md) | Written for a controls engineer. Hand this one to plant IT first |
| [technical/INTEGRATIONS.md](technical/INTEGRATIONS.md) | Adapter by adapter, with firewall rules and the gotchas that decide deployments |
| [technical/RUNNING.md](technical/RUNNING.md) | How to run the stack, with Docker and without it |

## Building it with Claude Code

| Document | What it covers |
|---|---|
| [../CLAUDE.md](../CLAUDE.md) | Project instructions. The compressed version of everything here |
| [ai/IMPLEMENTATION_PLAN.md](ai/IMPLEMENTATION_PLAN.md) | Six phases, each ending in something demonstrable |
| [ai/TASKS.md](ai/TASKS.md) | 112 ordered tasks with dependencies and verification |
| [ai/CODING_STANDARDS.md](ai/CODING_STANDARDS.md) | The rules specific to this project, and the generic ones |
| [ai/AGENT_WORKFLOW.md](ai/AGENT_WORKFLOW.md) | How to prompt, where an agent will drift, and how it is caught |

## Quality

| Document | What it covers |
|---|---|
| [quality/ACCEPTANCE_CRITERIA.md](quality/ACCEPTANCE_CRITERIA.md) | Given / When / Then for every story |
| [quality/TEST_PLAN.md](quality/TEST_PLAN.md) | Nine levels, and the evaluation harness as a deliverable |
| [quality/EDGE_CASES.md](quality/EDGE_CASES.md) | 58 awkward situations and what happens in each |
| [quality/ERROR_HANDLING.md](quality/ERROR_HANDLING.md) | Taxonomy, messages, and the ten things never done |
| [quality/DEFINITION_OF_DONE.md](quality/DEFINITION_OF_DONE.md) | Change, feature, and submission checklists |

## Human design rules

Binding. These have veto power over the design documents.

| Document | What it covers |
|---|---|
| [human-design/HUMAN_DESIGN_GUIDELINES.md](human-design/HUMAN_DESIGN_GUIDELINES.md) | 33 rules, the colour rule, the twelve checks, and how each is enforced |
| [human-design/DESIGN_DONTs.md](human-design/DESIGN_DONTs.md) | The scannable reference. What not to build, why, and what instead |
| [human-design/UX_WRITING_GUIDELINES.md](human-design/UX_WRITING_GUIDELINES.md) | Every string in the product, with the recurring patterns |
| [human-design/CONTENT_STYLE_GUIDELINES.md](human-design/CONTENT_STYLE_GUIDELINES.md) | Everything written outside the interface, including the README and the pitch |

## Sources

[../RESEARCH_SOURCES.md](../RESEARCH_SOURCES.md). 121 entries, each marked as read or
surfaced, with a map from source to design decision and an honest statement of what the
research does not establish.

---

## The two ideas the whole set serves

**Uneven sensor coverage is the problem, not an inconvenience.** Six of 42 stations emit
nothing. The twin infers their behaviour from unit conservation through flanking
timestamps, reports a bound rather than a number, says plainly what it cannot separate,
and turns each blind spot into a costed sensor recommendation.

**False alarms are the failure mode.** A supervisor who learns to ignore this system has
correctly concluded it is not worth reading. Shadow mode, per-station promotion gates,
automatic demotion and a floor-visible scorecard are the product, not features to be
trimmed under time pressure.
