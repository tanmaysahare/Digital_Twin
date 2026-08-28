# CODING_STANDARDS.md

**Scope:** Python and TypeScript in this repository.
**Enforcement:** ruff, mypy strict, eslint, stylelint, plus the custom design-rule checks. All run in `make lint` and in CI.
**Last updated:** 2026-08-28

---

## 1. The rules that are specific to this project

Generic style is handled by formatters. These are the ones that carry meaning here, and
every one of them has a test or a lint rule behind it.

### 1.1 Provenance is structural

```python
# Wrong: a bare float leaves the state layer
def cycle_time(station_id: str) -> float: ...

# Right: the caller cannot avoid seeing where the number came from
def cycle_time(station_id: str) -> Estimate: ...
```

`Estimate` cannot be constructed without a provenance. Any function returning a value the
twin derived returns an `Estimate`. Any component rendering one renders a
`ProvenanceMark`.

### 1.2 Intervals are not collapsed

```python
# Wrong: throws away exactly the information the product exists to preserve
midpoint = (est.lo + est.hi) / 2

# Right: carry the interval, or ask explicitly for a point where one exists
if est.provenance == "MEASURED":
    value = est.point
else:
    render_interval(est.lo, est.hi)
```

Taking a midpoint of an inferred interval is prohibited in production paths. Where a
scalar is genuinely required (a sort key, for example), use `Estimate.sort_key()`, which
is documented as lossy and cannot be rendered.

### 1.3 No plant-specific value in code

```python
# Wrong
if station_id == "S20":
    ...
STALL_THRESHOLD_S = 180

# Right
if station_id == config.line.critical_stations[0]:
    ...
threshold = config.forecast.stall_threshold_s
```

A test greps the source tree for station ID patterns and known configuration values.
Fixtures and tests are exempt and live under `tests/`.

### 1.4 Determinism

```python
# Wrong, all of these
random.random()
np.random.rand()
np.random.default_rng()          # unseeded

# Right
rng = np.random.default_rng(seed_for(cycle_id, replication))
```

A lint rule catches the global generators. Every stochastic function takes an explicit
generator or a seed.

### 1.5 The ledger is the only path to the screen

```python
# Wrong
if forecast.probability > threshold:
    publish(forecast)

# Right
prediction = ledger.record(forecast)
if ledger.is_active(forecast.predictor, forecast.station_id):
    publish(prediction)
```

Recording happens first, unconditionally. Publication is a separate decision made by the
ledger, not by the predictor. A test asserts that no module outside `twin/ledger/`
imports the publication path.

### 1.6 Read-only adapters

`SourceAdapter` has three methods and none of them writes. Do not add a fourth. A
reflection test enumerates every implementation and asserts its method set.

### 1.7 Errors are contained, never swallowed

```python
# Wrong
try:
    forecast = run_forecast(state)
except Exception:
    forecast = last_forecast          # serving stale data as current

# Right
try:
    forecast = run_forecast(state)
except ForecastError as e:
    log.exception("forecast cycle %s failed", cycle_id)
    health.record_cycle_failure(cycle_id, e)
    return None                       # the interface shows the previous one with its age
```

No bare `except Exception` that does not re-raise or record. Ruff enforces this.

---

## 2. Python

### Style
- Formatter: ruff format, line length 88.
- Linter: ruff, with the rule set in `pyproject.toml`.
- Types: mypy strict. No `Any` without a comment explaining why. No untyped function.
- Imports: absolute within the project, `from __future__ import annotations` at the top
  of every module.

### Structure
- `dataclass(frozen=True)` for domain objects. Domain objects are immutable.
- pydantic for anything crossing a boundary: API bodies, configuration, event payloads.
- Modules are small and named for what they do, not for what they are.
  `twin/state/virtual_sensors.py`, not `twin/state/utils.py`. There is no `utils.py`
  anywhere in this repository.
- No class where a function will do. Most of this codebase is functions over immutable
  data.

### Naming
- `snake_case` for functions and variables, `PascalCase` for types, `SCREAMING_SNAKE` for
  module-level constants that are genuinely constant, which excludes anything from
  configuration.
- Units in the name where a unit is not obvious: `cycle_time_s`, `budget_ms`,
  `horizon_min`. This is a habit worth the keystrokes: a units mismatch in a forecast is
  a wrong prediction that looks plausible.
- Booleans read as assertions: `is_manual`, `has_scan_point`, `adds_client_to_plc`.

### Async
- `async` only where there is real IO. The DES is CPU-bound and runs in a process pool,
  not in the event loop.
- No blocking call inside an async function. A lint rule catches the common ones.

### Testing
- pytest, with fixtures in `conftest.py` at the appropriate level.
- Test names state the behaviour: `test_dark_station_interval_contains_truth`, not
  `test_virtual_sensor_2`.
- One assertion concept per test. Several `assert` statements about the same concept is
  fine.
- No test depends on another test's state or on execution order.
- Every test involving randomness is seeded.

---

## 3. TypeScript

### Style
- Formatter: prettier, 2-space indent, single quotes, no semicolon omission.
- Linter: eslint with the TypeScript plugin, `strict: true` in `tsconfig`.
- No `any`. No non-null assertion (`!`) without a comment. No `as` cast without a comment.

### Components
- Function components, named exports, one component per file, file named for the
  component.
- Props typed as an explicit `interface`, never inline.
- No default exports except where Next.js requires them for a route.
- No prop drilling beyond two levels. Above that, a context.
- Every component that can be empty or in error has those as variants of itself, not as
  separate components, so they cannot be forgotten.

### Styling
- Tailwind classes mapped to the design tokens.
- No inline `style` except for a value computed at runtime (a bar width, a chart
  coordinate).
- No hard-coded colour. Tokens only. Stylelint enforces this.
- No `!important`.

### State
- Server state through the API layer, never duplicated into a client store.
- `useState` for local interaction state. No global state library.
- No `useEffect` that fetches. Fetching lives in the API layer.

### Charts
- Hand-written SVG plus `d3-scale`. No charting library.
- Every chart takes its data already shaped. Charts do not compute, they draw.

---

## 4. Comments

Comments explain why. The code says what.

```python
# Good
# Shift boundaries reset the accumulator rather than spanning it. Roser et al.
# assume continuous operation, which a two-shift line does not satisfy, and
# spanning the boundary made whichever station was running at 14:30 look like
# the constraint on every second-shift start.

# Bad
# Loop through the stations
```

Every non-obvious algorithmic choice carries a comment with its reason, and a reference
to the document or the source that argued for it. A future reader should not have to
reconstruct why EWMA and CUSUM both have to signal.

**Docstrings** on every public function: one line on what it does, then the parameters
and return only where they are not obvious from the types. No restating the signature in
prose.

**No commented-out code.** Git has it.

**No TODO without an owner and a task ID.** `# TODO(T-099): ...` is acceptable. A bare
`# TODO` is not, and a lint rule catches it.

---

## 5. Commits and pull requests

**Commits:** imperative mood, under 72 characters, body where the reason is not obvious.

```
Reset active period accumulator at shift boundaries

Spanning 14:30 inflated the accumulated active period for whichever station
happened to be running at the changeover, which made it look like the
constraint on every second-shift start.
```

No emoji. No conventional-commit prefixes with emoji. No "fix stuff", no "wip" on a
branch that will be merged.

**Pull requests** state: what changed, why, which task ID, which acceptance criteria are
now met, and how it was verified. The `DEFINITION_OF_DONE.md` Section 1 checklist is in
the template.

---

## 6. Dependencies

- A new dependency requires a line in the pull request saying why the standard library or
  an existing dependency is insufficient.
- Pinned in a lockfile. `pip-audit` and `npm audit` run in CI and fail on high severity.
- No runtime CDN. Fonts are self-hosted. The application runs offline.
- No component library, no icon library, no charting library. This is a design constraint,
  not a preference, and the reasons are in `docs/design/UI_COMPONENTS.md`.

---

## 7. Performance

Optimise when a budget is missed, not before. The budgets are in
`docs/technical/TECHNICAL_SPEC.md` Section 13, and they are the only definition of "fast
enough" this project uses.

When a budget is missed, profile first. The likely hot spots are the DES inner loop and
the per-cycle distribution refit, and both have documented degradation paths that are
preferable to premature optimisation.

---

## 8. Configuration and secrets

- Configuration in YAML under `config/`, loaded and validated at startup, with a readable
  error naming the field when validation fails.
- Secrets from the environment. Never a committed file. A pre-commit hook scans for them,
  and T-139 scans the full history before submission.
- No configuration read at call time. Load once, pass the object down.

---

## 9. Things this project does not do

| Not done | Reason |
|---|---|
| `utils.py`, `helpers.py`, `common.py` | A module named for its shape rather than its job becomes a landfill |
| Global mutable state | The forecast worker and the API share nothing but the database |
| Inheritance for code reuse | Composition. Protocols where a contract is needed |
| Metaclasses, decorators that rewrite signatures, dynamic imports | Debuggability matters more than cleverness in a system whose output people act on |
| Silent fallbacks | Every fallback is recorded and, where a user is affected, surfaced |
| Feature flags | Three people, twenty days. A flag is a branch that never gets deleted |

---

**Related:** [AGENT_WORKFLOW.md](AGENT_WORKFLOW.md) · [../quality/DEFINITION_OF_DONE.md](../quality/DEFINITION_OF_DONE.md) · [../human-design/CONTENT_STYLE_GUIDELINES.md](../human-design/CONTENT_STYLE_GUIDELINES.md)
