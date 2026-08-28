# ERROR_HANDLING.md

**Purpose:** how failures are detected, contained, communicated and recovered from.
**Governing rule:** degrade to less information, never to wrong information.
**Message standard:** every user-facing message follows ../human-design/UX_WRITING_GUIDELINES.md Section 5. What happened, what it means, what to do. No apology, no error code in the visible string, no emoji, no exclamation mark.
**Last updated:** 2026-08-28

---

## 1. Error taxonomy

| Class | Definition | Posture |
|---|---|---|
| **Source error** | A plant source is unreachable, silent, or sending malformed data | Fail closed on that source. Continue on the rest. Tell the user which part of the line is affected |
| **Data error** | Events arrive that cannot be reconciled with a physical line | Record, flag, continue with reduced confidence. Never repair by inventing a value |
| **Model error** | A predictor cannot run or its inputs are insufficient | Suppress that predictor's output. Say which capability is missing. Other predictors continue |
| **Budget error** | Work cannot complete in its time budget | Degrade gracefully with a visible statement of what was reduced |
| **Infrastructure error** | Database, worker or websocket failure | Show last known state with its age. Never blank, never stale-as-current |
| **User error** | An invalid input | Prevent where possible, explain inline where not. Never a modal |
| **Programming error** | A bug | Fail loudly in development, contain in production, never silently continue with a corrupted state |

---

## 2. Source errors

### A source goes silent

```
Detect:   no events from an adapter for 3 takt periods
Contain:  affected stations keep their last state, tagged with its age
          forecasts materially dependent on that source are suppressed, not degraded
          a data_gap row opens
Tell:     header warning, and the affected stations show their age on the strip
Recover:  on return, backfill by ts_source, recompute affected state, close the gap,
          record the gap in the shift log
```

**Message**
> Paint zone source stopped sending 4 min ago. Forecasts for S17 to S26 are paused. The rest of the line is unaffected.

After 15 minutes the message escalates in prominence but not in tone. It never becomes a modal, because the line does not stop for a dialog.

### A source sends malformed data

Reject the event, count the rejection per source per minute, and surface the rate. A source producing malformed events at above a configured rate is treated as degraded and its dependent forecasts are suppressed.

**Message**
> The body shop source has sent 41 unreadable events in the last minute. Its data is not being used until the rate drops.

### Every source is silent

**Message**
> No source has sent data since 14:31:02. Everything on this screen is 6 minutes old.

The view does not blank. It shows what it knew, with its age stated once, prominently, and every region carrying the same age.

### Connection refused or authentication failure

Fail closed. Do not retry in a tight loop; capped exponential backoff with a maximum interval. Raise a health event naming the endpoint. This protects the plant system from a retry storm, which is the failure mode a controls engineer is actually worried about (SEC-15).

---

## 3. Data errors

The rule: record it, flag it, never repair it by inventing a value.

| Error | Handling | Message |
|---|---|---|
| Clock skew above threshold | Estimates spanning the sources carry widened confidence, and their `basis` says why. No automatic correction | "The final assembly source clock is 3.4 s behind the body shop source. Cycle times spanning the two may be off by that much." |
| Impossible buffer occupancy | Clamp, raise, reconcile at the next observed handoff | "Buffer B5 reported 13 units against a capacity of 12. A scan was probably missed." |
| Unit at two stations | Later arrival authoritative, both retained, health event | "Unit 3C4PDCBG7JT was reported at S18 and S22 at the same time. Using the S22 reading." |
| Negative derived cycle time | Clamp to zero, mark low confidence, name the likely cause | "S34's derived cycle time came out negative, which usually means the transport time or the station order in the configuration is wrong." |
| Unit lost from the stream | Mark `LOST_TRACK`, retain signature as incomplete, suppress its risk prediction | "Unit 3C4PDCBH1JT has not been seen since S28 at 09:14." |
| Duplicate event ID | Idempotent ingest, drop the duplicate, count it | Not surfaced unless the rate is high |

Note the pattern in the messages: each names the most likely cause in plant terms. A supervisor reading "a scan was probably missed" knows what to check. A supervisor reading "data integrity constraint violation" does not.

---

## 4. Model errors

### Insufficient history

Not an error, a normal condition on every cold start and every new variant. Treated as a first-class state.

**Message**
> S27 has no cycle history for the LWB variant yet. Forecasts for this station start after 20 recorded cycles. It has 12.

### A model artefact fails to load

That predictor moves to `UNAVAILABLE`, and the interface says which capability is missing rather than showing a blank region. Other predictors continue.

**Message**
> Defect risk for G3 is unavailable. The rest of the twin is working normally.

### Calibration has degraded

If expected calibration error rises above its threshold on the rolling window, the predictor is demoted to shadow. Showing an uncalibrated number as a probability is worse than showing nothing in a product whose argument is honesty.

**Message**
> Defect risk for G3 has been withdrawn. Its probabilities stopped matching outcomes closely enough to be shown as probabilities.

### Input distribution has shifted

A population shift in features raises a model-health warning, visible to Rakesh in Plan view, not to Priya on the floor. It is a maintenance signal, not an operational one.

---

## 5. Budget errors

### The forecast cycle exceeds its budget

Reduce replications by 25 percent for the next cycle. Widen intervals accordingly. State the reduction where the forecast is shown. If three consecutive cycles miss the budget, raise a health event.

**Message**
> This forecast ran with 150 replications instead of 200. The ranges are wider than usual.

### A counterfactual exceeds its budget

Reduce replications adaptively and report in the footer, in the same place the normal footer appears, so the difference is noticed.

**Message**
> Ran 60 replications instead of 200 to stay under 5 seconds. The ranges are wider than usual.

### Retro-trace exceeds its budget

Return the hypotheses found so far, ranked, and state that the search was truncated.

**Message**
> This trace covered the last 90 minutes. Widening the window would take longer.

---

## 6. Infrastructure errors

| Failure | Behaviour | User sees |
|---|---|---|
| Database unavailable | Ingest buffers in memory to a bound, then drops and counts. API serves last cached state | Data age, and a note that the record store is unavailable |
| Worker crashes mid-cycle | Cycle abandoned, no partial forecast published, next cycle runs from current state | Nothing, unless two cycles are missed, then the data age reflects it |
| Worker cannot start | API serves state without forecasts | "Forecasting is not running. The line state on this screen is current." |
| Websocket drops | Reconnect with capped backoff. Data age becomes prominent | Age, then a one-line note after two missed heartbeats |
| Sequence gap in websocket | Re-fetch full state | Nothing. This one is invisible by design |
| Web app JavaScript error | Error boundary at the region level, not the page level. The failed region shows a message, the rest of the view keeps working | "This panel could not be drawn. The rest of the screen is unaffected." |

The region-level error boundary matters: a single chart failing must not take down the line strip, because the line strip is the part someone is relying on.

---

## 7. User errors

Prevented rather than reported, wherever possible.

| Situation | Approach |
|---|---|
| An impossible counterfactual (a second operator at an automated station) | Not offered. The `is_manual` flag gates the option list |
| An out-of-range assumption in the business case | Inline note beneath the field, immediately, with the plausible range stated. The field is not blocked, because Meera may know something the range does not |
| An export while a run is in progress | The export waits and says so |
| A stale action ("We did this" on a forecast whose window has passed) | Accepted and recorded with a note that the window had elapsed. The user knows their line better than the clock does |

No modal confirmations except where an action destroys work in progress, which in this product is exactly one case: clearing a set of compared sandbox options.

---

## 8. Programming errors

| Environment | Behaviour |
|---|---|
| Development | Fail loudly. No broad exception handlers. A caught exception that is not handled meaningfully is re-raised |
| Test | Any unexpected exception fails the test, including in a background task |
| Production | Contain at the boundary: a failing forecast cycle is abandoned, a failing region shows a message, a failing adapter is isolated. Nothing continues on a corrupted state |

**Never do this:**

```python
try:
    forecast = run_forecast(state)
except Exception:
    forecast = last_known_forecast     # silently serving a stale prediction as current
```

**Do this:**

```python
try:
    forecast = run_forecast(state)
except ForecastError as e:
    log.exception("forecast cycle %s failed", cycle_id)
    health.record_cycle_failure(cycle_id, e)
    return None          # the interface shows the previous forecast with its age
```

The difference is that the second one leaves the user able to see that the number in
front of them is four minutes old.

---

## 9. Logging

| Level | Use |
|---|---|
| `DEBUG` | Development only. Never enabled in a demo, because it slows the cycle |
| `INFO` | Cycle start and finish with timings, promotions and demotions, config reloads, gaps opening and closing |
| `WARNING` | Degraded operation: reduced replications, source degraded, clock skew, suppressed forecasts |
| `ERROR` | A failed cycle, a failed adapter, a failed model load |
| `CRITICAL` | Not used. Nothing in this product is critical, because nothing in this product stops a line |

Structured JSON logs with `line_id`, `cycle_id`, `station_id`, `prediction_id` where
applicable. No personal identifiers, ever: operator identifiers are hashed at ingest and
the hash is not logged either (SEC-31).

---

## 10. What is never done

A short list, because these are the specific temptations.

1. **Never fabricate a value to fill a gap.** Not a mean, not a last-known-value carried
   forward silently, not a plausible estimate presented as a measurement.
2. **Never show stale data as current.** Age is always visible.
3. **Never suppress an error silently.** A caught exception that is not handled
   meaningfully is re-raised.
4. **Never blank a view on error.** Show what is known and its age.
5. **Never use a modal for an operational message.** The line does not stop for a dialog.
6. **Never auto-dismiss a message about something still true.**
7. **Never show an error code as the message.** Codes go to the log and to a copyable
   detail line.
8. **Never blame the user.**
9. **Never adjust a scorecard to protect a number.** A false positive caused by an
   operator preventing the predicted event is `UNSCOREABLE` with its own count, not a
   quietly removed row (EC-25).
10. **Never retry against a plant source in a tight loop.** Capped backoff, fail closed.

---

**Related:** [EDGE_CASES.md](EDGE_CASES.md) · [../human-design/UX_WRITING_GUIDELINES.md](../human-design/UX_WRITING_GUIDELINES.md) · [../technical/API_SPEC.md](../technical/API_SPEC.md) · [../technical/SECURITY_REQUIREMENTS.md](../technical/SECURITY_REQUIREMENTS.md)
