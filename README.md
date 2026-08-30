# DigitalTwin.ai

A live, read-only digital twin of a mixed-model vehicle assembly line that runs the next
two hours before the line does, using only the data the plant already emits.

## Demo video

`submission/demo/aeronomics_digital_twin_ai_demo_video_final.mp4`, 3 minutes 30 seconds,
narrated. It is committed to this repository and plays in the browser from
[the file page](https://github.com/tanmaysahare/Digital_Twin/blob/main/submission/demo/aeronomics_digital_twin_ai_demo_video_final.mp4).

Every screen in it is the running application driven against the running API, recorded
from a live session rather than assembled from stills.

## The problem it solves

A supervisor finds out that a station has slowed when the line stops. By then the
decision that would have prevented it, moving a floater, releasing a buffer, resequencing
the mix, is twenty minutes in the past. The information needed to make that decision
existed the whole time, in cycle timestamps the PLCs were already publishing, and nobody
could read it fast enough. The specific failure this addresses is a fixture wearing at
S20: cycle time drifts from 58 to 63 seconds over ninety minutes, stays inside spec the
entire time, trips no threshold alarm, and eventually starves the station downstream of
it.

## How to run it

```
make up
```

Or without Docker, two commands in two terminals:

```
python -m uvicorn twin.api.main:app --port 8000
cd web && npm run build && npm start
```

Then open `http://localhost:3000`. The API simulates the line once at start-up and
replays it at 60x, so the first minute is spent building baselines. `GET /health` reports
`WARMING` until it is ready and the interface says the same thing in words rather than
showing a spinner.

`make evaluate` regenerates the evidence pack. `make lint` runs the design rules, ruff,
mypy strict, eslint and stylelint. `make test` runs the suite. On Windows without `make`,
use `.\make.cmd <command>`.

## Dependencies

Python 3.11 and Node 20. `make up` needs only Docker and Docker Compose, and installs
everything else inside the images.

| Layer | What it needs |
|---|---|
| Database | TimescaleDB 2.15 on PostgreSQL 16, the only external service |
| API and models | simpy, numpy, scipy, pandas, pyyaml, pydantic, pydantic-settings, fastapi, uvicorn, sqlalchemy, alembic, psycopg, lightgbm, scikit-learn, shap |
| Web | next 14, react 18, react-dom, d3-scale. No component library and no icon library, by design |
| Development, `pip install -e ".[dev]"` | pytest, pytest-asyncio, pytest-cov, hypothesis, ruff, mypy, pip-audit |

Exact versions are pinned in `pyproject.toml` and `web/package.json`.

## What you will see

**Line view** opens on a quiet shift and says nothing. Forty-two stations in greyscale
at their live cycle times, buffers beneath them, output against pace, the loss
accounting, the predictor record and source health. The action region reads "nothing
needs attention" with the count of forecasts held in shadow beside it. Getting that
screen to read as a complete instrument rather than an empty one is the hardest design
problem in the product, and it is the screen a supervisor sees most days.

**S20 starts drifting.** Its segment takes an amber diagonal stripe, and it is the only
saturated thing on the display. The drift detector needs both an EWMA and a CUSUM signal
before it says anything, which roughly halves the false positive rate at a small cost in
detection delay.

**Click any dark station**, S33 to S37 or S42. The drawer says what the twin knows, what
it does not, and what it would cost to know it: a bound rather than a number, the
sentence that five stations share that bound and no one of them can be separated, the
scan point that would fix it, and a 65 dollar photo-eye with its install effort and its
next maintenance window.

**Press `t`** for the counterfactual sandbox. It opens over the line strip rather than
covering it, because the line does not stop for a dialog. Every option is compared
against doing nothing on the same replications from the same state, and the footer says
how many replications ran, how long they took, and which state timestamp they started
from.

**Plan view** has the constraint heatmap, the loss Pareto under its reconciliation line,
the modelled buffer and staffing changes with their assumptions inline, the sensor
investment queue exportable as a CSV for a capital request, and the full predictor
scorecard.

**Program view** has site readiness scored from what each site emits, and the business
case with every assumption carrying its source and its uncertainty.

**Open the scorecard and look at what is in shadow.** On this line every predictor is,
and the floor sees nothing from any of them. That is the part of the demonstration that
matters most, and the next section says why.

The full script is in `docs/product/MVP_SCOPE.md` Section 1. Screenshots, captured from
the running application against the running API rather than staged, are in
`docs/design/SCREENSHOTS/`.

## What is simulated and what is not

**All of it is simulated.** We have no access to a real plant and no primary user
research. The line, the 42 stations, the six that emit nothing, the eight scenarios and
every number on every screen come from a SimPy model we wrote. The interface carries a
non-removable simulated-data marker so that no screenshot can be mistaken for plant
results, and every CSV export carries the same sentence.

What is not simulated is the code path. The simulator emits canonical events, an
observability filter throws away everything the six dark stations would have said, a
read-only adapter reads what survives, and from there to the screen the twin does not
know it is looking at a simulation. Point it at a historian and the same code runs.

The evaluation evaluates our simulator against our twin, both written by us. That is a
real limitation and `evaluation/report.md` states it in its own words.

## Architecture

```
  plantsim              connector                twin                     web
  ----------            -----------              --------------------     -----------
  SimPy line     -->    SimAdapter        -->    StateEstimator     -->   Line view
  42 stations           read-only               VirtualSensors            Plan view
  8 scenarios           Normaliser              Forecaster (DES)          Program view
  ground truth  -.      reorder, skew,          DriftDetector
  (separate      |      source health           DefectService
   schema, no    |                              CounterfactualEngine
   grant to the  |                              RetroTracer
   app role)     |                                    |
                 |                                    v
                 '- - - - - -> evaluation  <--  LedgerStore
                    (the only thing that        append-only, gates,
                     may read ground truth)     promotion and demotion
```

Every value the twin produces is an `Estimate` carrying `MEASURED`, `DERIVED` or
`INFERRED`, and the type cannot be constructed without a provenance, so an inference
cannot be rendered as a measurement anywhere. Every prediction is written to the ledger
at the moment it is made, before any decision about whether to show it. The ledger, not
the model, decides what reaches the screen.

## How the prediction works

**None of these methods is novel and we are not claiming any of them are.** What is
unusual is the combination and what sits between them and the floor.

**Virtual sensors for dark stations.** Unit conservation through flanking timestamps. A
unit leaves the last instrumented station upstream and arrives at the first one
downstream; the transit less the nominal transports bounds the work done in between. The
upper bound is sound because a unit cannot have worked longer than it was there. The
lower bound is statistical, from the quickest recent comparable passage, and that is
exactly why the target is coverage in 90 percent of cycles rather than all of them.

**Forecast.** A Monte Carlo discrete-event simulation of the line, seeded from the live
state, run forward 120 minutes. Blocking and starving propagate through the model rather
than being estimated per station. Stations the drift detector has flagged are
extrapolated forward rather than frozen.

**Constraint attribution.** Average active period with a shift-boundary reset, plus a
buffer trend, reported separately. Where the two methods name different stations the
interface shows both rather than choosing.

**Drift detection.** EWMA and CUSUM on the residual against a robust baseline, both
required to signal. CUSUM also gives the onset estimate, which is what lets the interface
say "since 09:14" instead of "detected at 09:26".

**Defect risk.** LightGBM per gate with a temporal split, isotonic calibration, and split
conformal intervals. Gradient boosting rather than a sequence model, deliberately: the
argument is in `docs/technical/TECHNICAL_SPEC.md` Section 6.2. Explanations are SHAP top
three, and a feature with no plant-language template cannot surface at all.

**The trust ledger.** Predictions are joined to outcomes automatically when the horizon
elapses. `missed_event` rows record the stalls nothing predicted, which is the only way
recall is computable. A predictor is promoted for one station only after clearing a
precision and recall gate over enough predictions, and demotes itself when it degrades.

## Evaluation results

Regenerate with `make evaluate`. Every number below comes from
`evaluation/metrics.json`, over 8 scenarios at 3 seeds, 620 units each, 40 replications,
a 120 minute horizon and a 5 minute cadence.

| Measure | Target (PRD Section 5) | Measured | Meets it |
|---|---|---|---|
| Dark-station interval coverage, per station | 0.90 | 1.000 | Yes |
| Dark-span interval coverage | 0.90 | 0.998 | Yes |
| Stall forecast precision | 0.60 | 0.250 | **No** |
| Stall forecast median lead time | 15 min | 5 min | **No** |
| Stall forecast recall | 0.50 | 0.190 | **No** |
| Drift detection recall | 0.80 | 1.000 | Yes |
| Drift detection precision | not set | 0.281 | |
| False alerts per shift on a quiet line | under 1.0 | 0.70 | Yes |
| Defect calibration error, G1 | 0.05 | 0.005 | Yes |
| Defect calibration error, G3 | 0.05 | 0.002 | Yes |
| Conformal coverage at alpha 0.10, G1 | 0.90 | 0.983 | Yes |
| Conformal coverage at alpha 0.10, G3 | 0.90 | 0.976 | Yes |
| Defect risk lead time, G3 | 10 stations | 13 stations | Yes |

**The stall forecaster does not meet its gate and we are not going to dress that up.**
The events it is scored against on this line are dominated by the tail of the repair-time
distribution. A drifting station roughly doubles their frequency but does not schedule
one, so a forecast seeded from the current state can raise the probability of a stall in
a region and a window and cannot pinpoint one 20 to 40 minutes ahead. What the twin can
say on this line, and does say correctly, is which station has become the constraint and
what the line will lose because of it.

The consequence is visible in the product rather than hidden by it: because the gate does
not pass, the stall forecaster stays in shadow and the floor sees nothing from it. That
is the trust ledger doing exactly what it was built to do, and it is the single most
important thing in this submission.

Eighty-two percent of stall predictions are unscoreable: their horizon had not closed
when the run ended, or they named a station nothing watches. The harness counts those
separately rather than scoring them as wrong, and the precision above is over the 132
that could be scored.

`evaluation/report.md` Section 10 has the full diagnosis, and `docs/ai/TASKS.md` records
the fifteen findings across the five phases that changed a specification rather than only
the code.

## Limitations

- All data is simulated, and the evaluation evaluates our simulator against our twin.
- No supervisor, plant manager or controls engineer was interviewed. The personas are
  composites from published literature and are labelled as such.
- One of 121 sources was read in full; the rest were surfaced and verified through
  search.
- Sensor costs are our assumptions rather than quotations, and every Sensor Value Card
  carries the sentence saying so.
- The modelled business case computes to zero, because the reference line supplies no
  contribution margin per unit. A plant that has not given us its own figure sees zero
  rather than an industry average that does not describe it.
- The loss reconciliation can disagree with itself, by up to about 8 percent of the
  production time available on some windows. Both sides are computed from different
  evidence on purpose and the difference is shown rather than distributed across the
  causes. Where the causes exceed the time available, two of them are being counted over
  the same seconds somewhere and the twin has not established where.
- Four of the six integration adapters are specified and not built.
- There is no authentication. The persona switcher in the header is a demonstration
  affordance. `docs/technical/SECURITY_REQUIREMENTS.md` Section 6 says what else is
  missing.
- Fonts are referenced by family with system fallbacks rather than self-hosted, so the
  application runs offline but does not render in Inter unless the machine has it.
- The screen reader pass and the 3 m legibility check (T-135) have not been done. Both
  need a person and a room. `docs/ai/TASKS.md` names it as outstanding.

## For a controls engineer

The question you will ask first is whether this can touch the line. It cannot, and here
is where to check rather than take our word for it.

`connector/protocol.py` defines `SourceAdapter`. It has exactly three methods:
`describe`, `stream` and `health`. `WRITE_VERBS` in the same file lists the verbs that
would indicate a path back into the plant, and a test in `tests/test_adapters.py` walks
every implementation in the repository and fails if any defines a method whose name
starts with one. There is no fourth method and no configuration that adds one.

The API has no endpoint that applies anything. The counterfactual sandbox produces a
comparison and, if a supervisor asks, a record that they chose an option; the response
says in those words that nothing was sent to the line.

On clock skew: the connector estimates the offset between sources from hand-off
timestamps and reports it. Where it exceeds the line's own tolerance, a derived cycle
time at a hand-off is the skew rather than the station, and the twin says so instead of
publishing the number.

## Repository layout

```
config/         LineDefinition, SourceMapping, the sensor catalogue. No plant value in code
plantsim/       The SimPy line and the eight scenarios
connector/      Source adapters, read-only by protocol, and the normaliser
twin/           state, forecast, defect, retro, ledger, sensors, counterfactual, program, api
web/            The Next.js application, three views, no component library
evaluation/     The harness and the generated evidence pack
tests/          The test suite
docs/           The specification set. Start at docs/README.md
submission/     The narrated demo video
tools/          The lint, the design rule checks and the accessibility scan
```

A test asserts that no station identifier, buffer capacity or threshold from either line
appears in the source tree. A second line, `config/lines/line7.yaml`, is structurally
different and runs with no code change.

## Team and context

**Team Aeronomics** · Accenture Innovation Challenge 2026 · Problem Statement 4 · Round 2
Tanmay Sahare, Anuj Kumar Gupta, Sanchit Arora · IIT Kanpur

Licence: MIT. See `LICENSE`.
