# ARCHITECTURE.md

**Purpose:** how the system is put together, and why each boundary is where it is.
**Last updated:** 2026-08-28

---

## 1. System context

```
   PLANT (Purdue Level 0 to 2)                 |  DMZ (3.5)      |  APPLICATION (Level 3+)
                                               |                 |
   +----------+  +----------+  +----------+    |                 |
   |   PLCs   |  |  SCADA   |  |   MES    |    |                 |
   +----+-----+  +----+-----+  +----+-----+    |                 |
        |             |             |          |                 |
        +------+------+------+------+          |                 |
               |             |                 |                 |
        +------v-----+  +----v-----+           |                 |
        | OPC UA srv |  | Historian|           |                 |
        | MTConnect  |  | (PI,     |           |                 |
        | MQTT broker|  |  Ignition|           |                 |
        +------+-----+  +----+-----+           |                 |
               |             |                 |                 |
               +------+------+                 |                 |
                      |                        |                 |
                      |   READ ONLY            |                 |
                      +========================+=====>  +----------------+
                                               |        | SITE CONNECTOR |
                          NO PATH BACK         |        | (adapters)     |
                      <=========X==============+        +--------+-------+
                                               |                 |
                                               |                 v
                                               |        +----------------+
                                               |        |  TWIN SERVICE  |
                                               |        +--------+-------+
                                               |                 |
                                               |                 v
                                               |        +----------------+
                                               |        |    WEB APP     |
                                               |        +----------------+
```

Three properties of this diagram are architectural commitments, not configuration:

1. **The arrow across the DMZ boundary points one way.** There is no code path from the
   application to a control system. Enforced by the adapter interface having no write
   method (Section 5.1).
2. **The connector prefers existing infrastructure.** It consumes an OPC UA server, an
   MTConnect agent, an MQTT broker or a historian that the plant already runs. Adding a
   new client to a PLC is a last resort and requires an explicit configuration flag plus
   a documented polling rate.
3. **Nothing in the plant depends on the twin.** If the twin stops, production is
   unaffected. This is what makes a pilot approvable.

---

## 2. Component view

```
+----------------------------------------------------------------------------------+
|  plantsim  (prototype only)                                                       |
|  SimPy model of the 42-station line. Emits canonical events on a stream.          |
|  Writes ground truth to a separate store the twin cannot read.                    |
+---------------------------------+------------------------------------------------+
                                  | canonical events
+---------------------------------v------------------------------------------------+
|  connector                                                                        |
|  SimAdapter | CsvReplayAdapter | (specified, not built: OpcUaAdapter,             |
|  MTConnectAdapter, SparkplugAdapter, HistorianAdapter)                            |
|  Normalisation, reordering window, clock skew estimation, source health           |
+---------------------------------+------------------------------------------------+
                                  |
+---------------------------------v------------------------------------------------+
|  twin service (FastAPI + async workers)                                           |
|                                                                                   |
|  +------------------+  +------------------+  +------------------+                 |
|  | state estimator  |  | virtual sensors  |  | distribution fit |                 |
|  | LineState, units |  | Tier C bounds    |  | per station,     |                 |
|  | buffers, signat. |  | provenance       |  | per variant      |                 |
|  +--------+---------+  +--------+---------+  +--------+---------+                 |
|           |                     |                     |                           |
|           +----------+----------+----------+----------+                           |
|                      |                     |                                      |
|  +-------------------v------+  +-----------v----------+  +--------------------+   |
|  | forecaster               |  | defect risk          |  | retro-trace        |   |
|  | SimPy DES, Monte Carlo   |  | LightGBM, calibrated |  | divergence walk,   |   |
|  | active period attribution|  | conformal intervals  |  | containment query  |   |
|  | EWMA / CUSUM drift       |  | SHAP top-3 factors   |  |                    |   |
|  +-------------------+------+  +-----------+----------+  +---------+----------+   |
|                      |                     |                       |              |
|                      +----------+----------+-----------------------+              |
|                                 |                                                 |
|  +------------------------------v-----------------------------------------+       |
|  | trust ledger                                                           |       |
|  | append-only predictions, automatic outcome join, precision / recall /  |       |
|  | lead time, shadow mode, promotion and demotion gates                   |       |
|  +------------------------------+-----------------------------------------+       |
|                                 |                                                 |
|  +------------------------------v----------+  +------------------------------+    |
|  | counterfactual engine                   |  | sensor value scorer          |    |
|  | same DES, intervention overlay          |  | observability + criticality  |    |
|  +-----------------------------------------+  +------------------------------+    |
+---------------------------------+------------------------------------------------+
                                  | REST + WebSocket
+---------------------------------v------------------------------------------------+
|  web app (Next.js, TypeScript)                                                    |
|  Line view | Plan view | Program view                                             |
+----------------------------------------------------------------------------------+

+----------------------------------------------------------------------------------+
|  evaluation harness (offline)                                                     |
|  Runs scenarios N times, joins ledger against plantsim ground truth,              |
|  writes the evidence pack (report + charts)                                       |
+----------------------------------------------------------------------------------+
```

---

## 3. Runtime processes

Five processes under `docker compose`.

| Process | Image | Responsibility |
|---|---|---|
| `db` | postgres:16 with TimescaleDB | Events, state snapshots, ledger, config |
| `sim` | python | The line simulator, when running in demo mode |
| `api` | python | FastAPI: REST, WebSocket, and the ingest worker |
| `worker` | python | The 2-minute forecast cycle, model scoring, retro-trace |
| `web` | node | Next.js |

`api` and `worker` share a codebase and differ by entrypoint. Splitting them keeps a
200-replication Monte Carlo run from blocking an HTTP request, which is the single most
likely cause of a bad demo.

---

## 4. Data flow, the 2-minute cycle

```
  t+0s   Worker wakes
  t+0s   Read LineState from the state estimator (already current from ingest)
  t+1s   Refit any cycle-time distributions whose window has advanced
  t+2s   Run EWMA and CUSUM per station per variant, emit DRIFT events
  t+3s   Seed the DES from LineState: station states, buffer occupancy,
         in-process units, upcoming model mix from the MES schedule
  t+3s   Run 200 replications over 120 min (parallel across cores)
  t+15s  Aggregate: P(blocked), P(starved), buffer trajectory, output distribution
  t+16s  Attribute constraint via average active period + buffer trend
  t+16s  Emit StallForecast where P(stall) > threshold
  t+17s  Score every in-process unit for each downstream gate
  t+18s  Write every prediction to the ledger with horizon, confidence, evidence
  t+18s  Filter by predictor state (SHADOW predictions are recorded, not published)
  t+19s  Publish the new view state over WebSocket
  t+19s  Join any horizons that elapsed since the last cycle, update scorecards
  t+20s  Sleep until t+120s
```

Budget: 20 s of a 120 s cycle. The remaining 100 s is headroom for a larger line, and
the cycle degrades by reducing replications rather than by skipping a cycle.

---

## 5. Key boundaries

### 5.1 The read-only boundary

```python
class SourceAdapter(Protocol):
    """A source of canonical events. There is no write method, deliberately."""

    def describe(self) -> AdapterInfo: ...
    async def stream(self) -> AsyncIterator[CanonicalEvent]: ...
    async def health(self) -> SourceHealth: ...
```

Three methods. None of them writes. A controls engineer can verify the read-only claim
by reading eight lines of a protocol definition, which is the point. See
SECURITY_REQUIREMENTS.md.

### 5.2 The provenance boundary

Every value that leaves the state estimator carries its provenance and cannot be
constructed without it:

```python
@dataclass(frozen=True)
class Estimate:
    value: float | Interval
    provenance: Literal["MEASURED", "DERIVED", "INFERRED"]
    confidence: float
    basis: str          # human-readable, shown in the interface
```

A consumer cannot read `.value` without having `.provenance` in hand. The interface
layer refuses to render an `Estimate` without a `ProvenanceMark`. This is how
"never present an inference as a reading" is enforced structurally rather than by
discipline.

### 5.3 The publication boundary

The ledger sits between every predictor and the interface. A predictor cannot publish
directly; it emits a prediction, the ledger records it, and the ledger decides whether
that predictor is `ACTIVE` for that station. Shadow mode is therefore not a flag a
developer can forget to check, it is the only path to the screen.

### 5.4 The configuration boundary

Every plant-specific fact lives in `LineDefinition.yaml` and `SourceMapping.yaml`. No
station ID, buffer capacity, gate position or tag name appears in code. Verified by an
acceptance test that onboards a structurally different second line from files alone
(ONB-04).

---

## 6. Storage

TimescaleDB (PostgreSQL with a hypertable extension) for one reason: the workload is a
time-series ingest plus relational queries over units, stations and predictions, and
splitting those across two stores would add an operational burden the prototype does not
need. Full schema in DATABASE_SCHEMA.md.

| Data | Table type | Retention (prototype) |
|---|---|---|
| Canonical events | Hypertable, 1-day chunks | 30 simulated days |
| State snapshots | Hypertable, 1-hour chunks | 7 simulated days |
| Process signatures | Relational, JSONB detail | Full |
| Predictions and outcomes | Relational, append-only | Full, never pruned |
| Scorecards | Materialised view, refreshed per cycle | Derived |
| Configuration | Relational, versioned | Full history |

The ledger is never pruned. It is the product's evidence.

---

## 7. Scaling story

The prototype runs one line on a laptop. The path beyond that, in order of what breaks
first:

| Scale | What changes |
|---|---|
| 1 line, 42 stations | Nothing. This is the prototype |
| 1 line, 200 stations | Replications parallelised across cores. Forecast budget rises to about 60 s of the 120 s cycle. Still one machine |
| 4 lines, one plant | One worker per line, one shared database. Lines are independent; there is no cross-line coupling to model |
| 12 plants | One deployment per plant (data residency and OT segmentation both argue for this). A central rollup reads only aggregated scorecards and business-case inputs, never raw events |
| Beyond | Partition the event hypertable by line, move the forecast workers to a queue, and the architecture is unchanged |

The design does not attempt a multi-tenant cloud service. Plant data does not want to
leave the plant, and the product does not need it to.

---

## 8. Failure behaviour

| Failure | Behaviour |
|---|---|
| A source goes silent | Affected stations show state with age. Forecasts materially dependent on that source are suppressed, not degraded silently. Warning surfaced in plant language |
| All sources silent | The whole view shows its age. No fabricated state |
| Worker crashes mid-cycle | The cycle is abandoned. The next cycle runs from current state. No partial forecast is published |
| Worker cannot meet the budget | Replications reduce adaptively, bands widen visibly, and the reduction is stated in the interface |
| Database unavailable | Ingest buffers in memory up to a bound, then drops with a counted, surfaced loss. The interface shows last known state with its age |
| Model fails to load | That predictor moves to `UNAVAILABLE` and the interface says which capability is missing. Other predictors continue |
| Clock skew beyond threshold | Warning raised, cycle times spanning the affected sources marked with widened confidence |

The governing rule: **degrade to less information, never to wrong information.**
Detail in ../quality/ERROR_HANDLING.md.

---

## 9. Decisions and their reasons

| Decision | Reason | What we gave up |
|---|---|---|
| SimPy for the plant simulator rather than a commercial engine | Free, scriptable, embeddable, adequate fidelity for flow | Validated engine, 3D, vendor support |
| A hand-written tandem-line recursion for the forecaster rather than SimPy | SimPy runs about 1,300 station visits a second, and 200 replications of a 120 minute horizon is about 1.2 million: fifteen minutes against a 20 second budget. The recursion is the standard blocking-after-service formulation and is exact for the same model. Measured, not assumed, and recorded in TECHNICAL_SPEC.md Section 5.1 | A second implementation to keep correct, which is also why the simulator keeps SimPy: the two disagreeing is a signal |
| Two engines (DES for consequence, active period for attribution) | Each answers a different question, and both are explainable to an industrial engineer | Simplicity |
| LightGBM rather than a sequence model | Better at this data scale, handles missingness natively, explains itself through SHAP | Possible accuracy on long-range temporal patterns |
| Conformal intervals rather than a Bayesian model | Distribution-free coverage under severe class imbalance, cheap to compute | Richer uncertainty decomposition |
| TimescaleDB rather than a separate time-series store | One store, one query language, one backup story | Peak ingest performance |
| FastAPI plus a separate worker | A long simulation must never block a request | An extra process |
| Next.js rather than a SPA | Server rendering for the wall display, file-based routing, simple deployment | Some bundle weight |
| No component library | Every library carries a visual opinion that conflicts with the design rules | Development speed |
| Read-only, permanently | It is the only posture a controls engineer approves without a maintenance window | Closed-loop value, deliberately |
| Local-first, Docker Compose | The judging context is a laptop, and a plant pilot is on-premises anyway | Cloud convenience |

---

**Related:** [TECHNICAL_SPEC.md](TECHNICAL_SPEC.md) · [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) · [API_SPEC.md](API_SPEC.md) · [INTEGRATIONS.md](INTEGRATIONS.md) · [SECURITY_REQUIREMENTS.md](SECURITY_REQUIREMENTS.md)
