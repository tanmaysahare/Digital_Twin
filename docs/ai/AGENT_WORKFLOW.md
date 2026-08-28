# AGENT_WORKFLOW.md

**Purpose:** how to work with Claude Code on this repository so that the output is a coherent system rather than 112 disconnected tasks.
**Audience:** the team, and the agent itself.
**Last updated:** 2026-08-28

---

## 1. The working loop

One task at a time, in the order given in TASKS.md.

```
1. Read the task in TASKS.md. Note its dependencies and its acceptance criteria IDs.
2. Read the acceptance criteria in docs/quality/ACCEPTANCE_CRITERIA.md by ID.
3. Read the section of the specification the task implements.
4. Write the test first where the behaviour is specified. Most acceptance criteria
   translate directly into a test.
5. Implement.
6. Run `make lint` and `make test`.
7. Run the DEFINITION_OF_DONE.md Section 1 checklist.
8. Commit with the task ID in the message.
9. Move to the next task.
```

The step people skip is 3. The specification documents are not background reading; they
contain the parameters, the thresholds and the reasons. Implementing T-055 without
reading TECHNICAL_SPEC.md Section 5.3 produces a drift detector with plausible defaults
and no onset estimation, which then fails AC-014 for reasons nobody can see.

---

## 2. Session structure

A session should be one coherent unit of work, typically a phase or a group of related
tasks. Long sessions accumulate context that drifts from the documents.

**Start every session by loading the context that governs the work:**

| Session on | Read first |
|---|---|
| The simulator or the twin core | `CLAUDE.md`, `PRD.md`, `TECHNICAL_SPEC.md` |
| Anything predictive | `TECHNICAL_SPEC.md` Sections 5 to 9, `USER_RESEARCH.md` |
| Any interface work | `CLAUDE.md`, `HUMAN_DESIGN_GUIDELINES.md`, `DESIGN_SYSTEM.md`, `UI_COMPONENTS.md`, the relevant wireframe |
| Any user-facing string | `UX_WRITING_GUIDELINES.md` |
| Integration or security | `SECURITY_REQUIREMENTS.md`, `INTEGRATIONS.md` |

**End every session by:** running the full lint and test suite, updating any document
that no longer matches the code, and noting in the commit which tasks closed.

---

## 3. Prompting patterns that work here

### Good: task ID plus constraints plus verification

> Implement T-040, virtual sensors for Tier C stations. Follow TECHNICAL_SPEC.md
> Section 4.3 exactly, including the multi-dark-station case and the unresolvable case
> in STA-07. Every output is an `Estimate` with `provenance = INFERRED`. Write the
> coverage test first: the interval must contain the simulator's ground truth in at
> least 90 percent of cycles over 5,000 cycles. Do not produce a point estimate for a
> dark station anywhere.

Specific, bounded, verifiable, and it names the trap.

### Good: naming the failure mode you expect

> Build the calm state of `ActionCard`. This is the most common state in the product
> and it must read as a deliberate, complete instrument rather than as an empty state.
> No illustration, no "you are all caught up", no centred text. Follow
> WIREFRAMES/02-line-view-quiet.md and HUMAN_DESIGN_GUIDELINES.md Section 7.

### Bad: open scope

> Build the dashboard.

This produces a card grid with a gradient. Every time.

### Bad: asking for improvement without a target

> Make the forecast better.

Better against which metric, measured how? The evaluation harness exists so this
question has an answer.

---

## 4. Where an agent will drift, and how to catch it

These are specific and they are all predictable. Each one has a lint rule or a test
because prevention is cheaper than review.

| Drift | Catch |
|---|---|
| Introducing a gradient, a dark theme, or a purple-blue accent | stylelint |
| Rounding corners past 2px, adding shadows, building a card grid | stylelint plus the twelve checks |
| Adding an icon library "for convenience" | Dependency review in the pull request |
| Writing "seamlessly integrates" in a docstring or a README | Banned-word lint over Markdown and strings |
| Using an em dash | Repository-wide lint |
| Collapsing an interval to a midpoint | Code review, and the fact that `Estimate` makes it awkward |
| Imputing a missing value to make a model train more easily | Test asserting NaN counts survive feature assembly |
| Publishing a prediction without going through the ledger | Import test on `twin/ledger/` |
| Adding a write method to an adapter | Reflection test |
| Hard-coding a station ID or a threshold | Source-tree grep test |
| Using an unseeded random generator | Lint rule |
| Adding a `utils.py` | Review |
| Building a chatbot, a 3D view, or a settings page | `CLAUDE.md` "What this project is not" |
| Reporting precision without the false alarm rate | Evaluation report template |

The pattern: **every rule that is easy to violate has an automated check.** A rule that
exists only in a document is a rule that will be broken at 2 am.

---

## 5. When the agent should push back

An agent that silently implements something better than the specification creates a
divergence nobody notices until integration. The correct behaviour is to say so.

Say so when:

- A specification appears internally inconsistent.
- A specified approach appears likely to fail its own acceptance criterion.
- A task's dependencies are not actually sufficient to complete it.
- An acceptance criterion is not testable as written.
- A better approach exists **and** the specification does not already argue against it.

That last clause matters. Several decisions here look suboptimal and are argued:

| Looks wrong | Argued in |
|---|---|
| LightGBM rather than a transformer | TECHNICAL_SPEC.md Section 6.2, ARCHITECTURE.md Section 9 |
| Shadow mode delaying all floor value by weeks | COMPETITIVE_ANALYSIS.md Section 7, USER_RESEARCH.md F-03 |
| No component library | UI_COMPONENTS.md preamble |
| No 3D visualisation | PRODUCT_VISION.md Section 9 |
| Read-only forever | SECURITY_REQUIREMENTS.md Section 1 |
| Greyscale with no green for good | HUMAN_DESIGN_GUIDELINES.md Section 4 |
| Both EWMA and CUSUM required to signal | TECHNICAL_SPEC.md Section 5.3 |

Proposing any of these as an improvement without addressing the argument means the
document was not read.

---

## 6. Reviewing agent output

Three questions, in order. The third one catches the most.

1. **Does it pass?** Lint, tests, acceptance criteria by ID.
2. **Does it match the specification?** Not "does it work", but "does it do the specified
   thing". A drift detector that works with different parameters is a different detector,
   and its evaluation numbers will not match the ones the documents claim.
3. **Would a human have written this?** Run the twelve checks. Read the strings aloud.
   Look for the tells: an icon that carries no meaning, a card grid, a triadic sentence,
   a suspiciously round number, an example named `Item 1`.

Question 3 is the one this project exists to get right, and it is the one an automated
suite is worst at.

---

## 7. Parallel work

Three people and one agent context is a bottleneck. Split by module boundary, not by
layer, so that two sessions rarely touch the same file.

| Boundary | Files |
|---|---|
| Simulator | `plantsim/`, `config/lines/` |
| Ingest and state | `connector/`, `twin/state/` |
| Prediction | `twin/forecast/`, `twin/defect/`, `twin/ledger/` |
| Interface | `web/` |
| Evaluation | `evaluation/` |

`twin/domain/` is shared and changes to it are coordinated, because a change to
`Estimate` touches everything.

Rebase frequently. A three-day branch on a twenty-day project is a merge problem waiting.

---

## 8. Context management

The specification set is large. Loading all of it into every session wastes context and
dilutes the parts that matter for the task at hand.

- **Always in context:** `CLAUDE.md`. It is written to be the compressed version.
- **Loaded per task:** the specification section the task implements, plus the acceptance
  criteria by ID.
- **Loaded for interface work:** the relevant wireframe, `DESIGN_SYSTEM.md`, and
  `HUMAN_DESIGN_GUIDELINES.md`. The last one is not optional and not summarisable.
- **Referenced, not loaded:** `RESEARCH_SOURCES.md`, `COMPETITIVE_ANALYSIS.md`,
  `USER_RESEARCH.md`. These inform decisions already made and recorded elsewhere.

If a session is losing coherence, the fix is a new session with the right documents
loaded, not more instructions appended to a long one.

---

## 9. What the agent must never do without being asked

- Change a threshold, a parameter or a default that is specified.
- Loosen a promotion gate.
- Remove or weaken a test.
- Suppress a lint rule.
- Add a dependency.
- Change the design tokens.
- Alter a number in the README or in the evaluation report by hand.
- Delete a limitations section, an assumption note, or a "we do not know" statement.

Every one of these is a way of making the output look better while making it less true,
which is the specific failure this product is arguing against. An agent that quietly
removes an inconvenient limitation has broken the thing the project is for.

---

**Related:** [CODING_STANDARDS.md](CODING_STANDARDS.md) · [TASKS.md](TASKS.md) · [../../CLAUDE.md](../../CLAUDE.md) · [../quality/DEFINITION_OF_DONE.md](../quality/DEFINITION_OF_DONE.md)
