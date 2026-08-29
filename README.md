# DigitalTwin.ai

**Team Aeronomics** · Accenture Innovation Challenge 2026 · Problem Statement 4 · Round 2
Tanmay Sahare, Anuj Kumar Gupta, Sanchit Arora · IIT Kanpur

---

> **The build is in progress. This file is a skeleton.**
> Task T-140 in `docs/ai/TASKS.md` replaces it with the public, judge-facing README
> once the prototype is built. Until then it describes what is in this repository,
> what runs today, and how to use it. The section order required of the final README
> is in `docs/human-design/CONTENT_STYLE_GUIDELINES.md` Section 7.

---

## What DigitalTwin.ai is

A live, read-only digital twin of a mixed-model vehicle assembly line that runs the next
two hours before the line does, using only the data the plant already emits, and hands
each stakeholder the one decision that changes the outcome.

Three things it does:

- **Mirror.** Reconstructs the line as a live state model from cycle timestamps the PLCs
  already publish and build records MES already writes. No new plant hardware on day one.
- **Foresee.** Every two minutes, rolls the line forward 120 minutes as a Monte Carlo
  discrete-event simulation, while a separate constraint detector attributes the cause.
  In parallel, scores every in-process unit for the risk of failing each downstream
  inspection gate, on the process signature it actually received.
- **Act.** A supervisor tests a fix against the live state and gets an answer in seconds:
  units recovered per shift, with an uncertainty band, compared against doing nothing.

And one thing it refuses: it never writes to a control system. Every output is advisory.

## The two ideas that make it different

**Uneven sensor coverage is the problem, not an inconvenience.** Six of the 42 stations
on the reference line emit no machine data at all. The twin infers their behaviour from
unit conservation through flanking timestamps, reports a bound rather than a number, says
plainly what it cannot separate, and turns each blind spot into a costed, window-aware
sensor recommendation. The instrumentation roadmap is an output of the product, generated
from evidence.

**False alarms are the failure mode.** A supervisor who learns to ignore this system has
correctly concluded it is not worth reading, and no later accuracy improvement recovers
that. So every prediction is written to an append-only ledger at the moment it is made,
outcomes are joined automatically when the horizon elapses, and a predictor shows nothing
on the floor until it has cleared a precision and recall gate for that specific station.
When its accuracy degrades, it withdraws itself and says so. The scorecard is visible to
the floor, including where the system is wrong.

## What is in this repository right now

```
CLAUDE.md               Project instructions for Claude Code
KICKOFF_PROMPT.md       The prompt to start the build, plus per-phase prompts
RESEARCH_SOURCES.md     121 sources, each marked read or surfaced, mapped to decisions
docs/                   The specification set. Start at docs/README.md
  product/              Vision, PRD, MVP scope, personas, stories, flows, competitive, research
  design/               UX spec, design system, visual direction, components, responsive,
                        accessibility, generated reference sheets, eight wireframes
  technical/            Architecture, technical spec, database schema, API spec,
                        security requirements, integrations
  ai/                   Implementation plan, 112 ordered tasks, coding standards,
                        agent workflow
  quality/              Acceptance criteria, test plan, edge cases, error handling,
                        definition of done
  human-design/         The binding design and writing rules
```

Thirty-six specification documents plus four generated reference sheets and eight
wireframes.

## What runs today

Phases 0 and 1 of `docs/ai/TASKS.md`.

Phase 0 is the repository skeleton, continuous integration, the five-service Docker
Compose stack, the design tokens, the lint suite, the database schema with its separate
truth schema, and the two line configurations.

Phase 1 is the line and the twin's view of it. The SimPy simulator runs 42 stations,
nine buffers, three variants, two shifts, three inspection gates and two rework loops,
and eight scenarios inject into it from a file rather than from code. Its output passes
through an observability filter that throws away everything six of the stations would
have said, and what survives is what the twin sees. The twin reconstructs the line
state from that filtered stream, bounds the cycle time at every station no sensor
watches, and says plainly which of them it cannot separate at all.

The headline number: over 5,000 cycles, the derived interval at a dark station contains
the simulator's ground truth in about 97 percent of cycles against a 90 percent target.
The five stations that sit in a row with no scan between them are reported as
`UNRESOLVED`, with the scan point that would fix them, and no cycle time is invented for
any of them. S42 is dark and last, so it has no downstream scan at all and gets no
number of any kind.

No forecast, no defect model, no views yet. Those are Phases 2 to 4.

```
make            list every command
make install    install Python and Node development dependencies
make lint       design rules, ruff, mypy strict, eslint, stylelint
make test       the test suite
make seed       rebuild the seeded demo database
make up         start the stack
```

On Windows without `make` installed, use `.\make.cmd <command>`. The commands are
identical: both delegate to `tools/tasks.py`.

The non-Docker path is in `docs/technical/RUNNING.md`.

## How to use it

1. Read `docs/README.md`, which gives the reading order.
2. Copy this whole tree into the repository root of
   `github.com/tanmaysahare/Digital_Twin`, commit and push. The specification set is a
   deliverable in its own right: if the build stalls, the repository still shows a
   complete solution design.
3. Open Claude Code in the repository root so it picks up `CLAUDE.md`.
4. Paste the kickoff prompt from `KICKOFF_PROMPT.md`.
5. Work through `docs/ai/TASKS.md` in order, one task at a time.

## What gets built

A five-service local stack: a SimPy simulator of a 42-station mixed-model line, a
read-only connector, the twin service, a Next.js application with three views, and an
offline evaluation harness that produces the evidence pack.

The demo, in one paragraph: a quiet shift where the system says nothing. Then a fixture
starts wearing at S20 and cycle time drifts from 58 to 63 seconds, inside spec, invisible
to any threshold alarm. Twelve minutes later the drift is flagged. Three minutes after
that a forecast appears: line stop at S22, between 09:52 and 10:04, probability 0.71,
caused by S20, eleven units at risk, 27 minutes of lead time. The supervisor tests two
fixes and takes the better one. Separately, six VINs carrying a suspect part lot are
flagged fourteen stations before final QC. When the first one fails, the twin traces
backwards and returns a containment list of twenty-three units. A dark station shows an
interval and a forty-dollar sensor that would close it. Then the evaluation report, where
every number just claimed can be checked.

Full script in `docs/product/MVP_SCOPE.md` Section 1.

## Honest notes

- **All data is simulated.** We have no access to a real plant. The problem statement
  permits illustrative data, and the interface carries a non-removable simulated-data
  marker so no screenshot can be mistaken for plant results.
- **No primary user research.** No supervisor, plant manager or controls engineer was
  interviewed. The personas are composites built from published literature and are
  labelled as such in `docs/product/USER_RESEARCH.md`, which also lists the seven things
  we do not know.
- **One of 121 sources was read in full.** The rest were surfaced and verified through
  search. That is stated at the top of `RESEARCH_SOURCES.md`, and it is why almost every
  number in these documents is either measured by our own harness or labelled as an
  assumption.
- **Four of the six integration adapters are specified but not built.** Every document
  that mentions them says so.
- **The evaluation evaluates our simulator against our twin, both written by us.** That
  is a real limitation and the evaluation report states it in its own words.

## Licence

MIT. See `LICENSE`.
