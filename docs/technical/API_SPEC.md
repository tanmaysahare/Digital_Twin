# API_SPEC.md

**Base URL:** `http://localhost:8000/api/v1`
**Format:** JSON. `application/json` for requests and responses.
**Timestamps:** RFC 3339 with offset, always. `2026-08-28T09:29:14+05:30`.
**Errors:** RFC 9457 problem details.
**Auth:** not implemented in the prototype. See SECURITY_REQUIREMENTS.md Section 6 for the design and the honest statement of what is missing.
**Last updated:** 2026-08-28

---

## 1. Conventions

### The `Estimate` shape

Every numeric value produced by the twin uses this shape. There is no bare number in
any response.

```json
{
  "lo": 54.0,
  "hi": 71.0,
  "point": null,
  "unit": "s",
  "provenance": "INFERRED",
  "confidence": 0.42,
  "basis": "Bounded from S32 departure and S38 arrival, less 4.2 s nominal transport."
}
```

For a measured value, `lo == hi == point` and `provenance` is `MEASURED`. Clients render
provenance; the API never omits it.

### Problem details

```json
{
  "type": "https://digitaltwin.ai/problems/insufficient-history",
  "title": "Not enough cycle history",
  "status": 409,
  "detail": "S27 has 12 recorded cycles for variant V-LWB. Forecasting starts at 20.",
  "instance": "/api/v1/lines/line2/forecast",
  "station_id": "S27",
  "cycles_recorded": 12,
  "cycles_required": 20
}
```

`detail` is written to the standard in ../human-design/UX_WRITING_GUIDELINES.md and can
be shown to a user without rewriting. Machine-readable fields sit alongside it.

---

## 2. State

### `GET /lines`
Configured lines.

```json
{"lines": [{"line_id": "line2", "name": "Line 2", "takt_s": 60, "stations": 42,
            "tiers": {"A": 24, "B": 12, "C": 6}, "config_version": 3}]}
```

### `GET /lines/{line_id}/state`
The complete live state. The single call that fills Line view.

```json
{
  "line_id": "line2",
  "as_of": "2026-08-28T09:29:14+05:30",
  "age_s": 12,
  "shift": {"id": "A", "started_at": "...", "target_units": 460, "completed": 312,
            "pace_delta_units": -4},
  "stations": [
    {"station_id": "S20", "seq": 20, "zone_id": "body", "tier": "A",
     "state": "RUNNING", "since": "2026-08-28T09:28:52+05:30",
     "current_unit_id": "3C4PDCBH9JT",
     "cycle_time": {"lo": 62.1, "hi": 62.1, "point": 62.1, "unit": "s",
                    "provenance": "MEASURED", "confidence": 0.98,
                    "basis": "PLC cycle start and stop"},
     "normal_range": {"lo": 57.2, "hi": 59.4, "unit": "s"},
     "flags": ["DRIFTING"]},
    {"station_id": "S34", "seq": 34, "zone_id": "final", "tier": "C",
     "state": "IDLE_UNKNOWN", "since": "...", "current_unit_id": null,
     "cycle_time": {"lo": 54.0, "hi": 71.0, "point": null, "unit": "s",
                    "provenance": "INFERRED", "confidence": 0.42,
                    "basis": "Bounded from S32 departure and S38 arrival."},
     "normal_range": null,
     "flags": ["NO_MACHINE_DATA"]}
  ],
  "buffers": [{"buffer_id": "B5", "after_station_id": "S19", "occupancy": 11,
               "capacity": 12, "trend": "RISING"}],
  "loss_this_shift_min": {"blocked": 51, "starved": 34, "down": 28,
                          "changeover": 22, "quality": 13},
  "data_health": {"sources_live": 4, "sources_total": 4,
                  "last_event_at": "...", "max_skew_s": 0.8,
                  "stations_reporting": 36, "stations_dark_by_design": 6,
                  "open_gaps": []}
}
```

### `GET /lines/{line_id}/stations/{station_id}`
Station detail for the drawer: cycle history, distribution, buffers either side,
predictor record for this station, sensor recommendation if one exists, recent events.

### `GET /lines/{line_id}/units/{unit_id}`
Unit detail for the drawer, including the full `unit_visit` process signature with
provenance per visit, risk per remaining gate, top three factors, and the containment
list if this unit generated one.

---

## 3. Predictions

### `GET /lines/{line_id}/actions`
The ranked action list. Published predictions only: a prediction from a predictor in
`SHADOW` for that station never appears here, which is the shadow-mode guarantee
expressed at the API boundary.

```json
{
  "as_of": "2026-08-28T09:29:14+05:30",
  "actions": [
    {
      "prediction_id": "0192...",
      "predictor": "stall_forecaster",
      "kind": "STALL_FORECAST",
      "station_id": "S22",
      "window": {"from": "2026-08-28T09:52:00+05:30",
                 "to":   "2026-08-28T10:04:00+05:30"},
      "probability": 0.71,
      "lead_time_min": 27,
      "cause": {"station_id": "S20",
                "description": "cycle time drifted +4.1 s since 09:14",
                "attribution": ["AVERAGE_ACTIVE_PERIOD", "BUFFER_TREND"],
                "agreement": true},
      "expected_unit_loss": {"lo": 7, "hi": 15, "point": 11, "unit": "units",
                             "provenance": "DERIVED", "confidence": 0.71,
                             "basis": "200 replications from the 09:29:14 state"},
      "evidence_url": "/api/v1/predictions/0192.../evidence",
      "predictor_record": {"state": "ACTIVE", "made": 11, "hits": 8,
                           "median_lead_min": 27}
    }
  ],
  "shadow_count": 4
}
```

`shadow_count` is returned so the interface can say "4 forecasts in shadow" in the calm
state without exposing the forecasts themselves.

### `GET /lines/{line_id}/units-at-risk`
```json
{
  "units": [
    {"unit_id": "3C4PDCBG7JT", "current_station_id": "S28", "gate_id": "G3",
     "risk": {"lo": 0.54, "hi": 0.79, "point": 0.68, "unit": null,
              "provenance": "DERIVED", "confidence": 0.68,
              "basis": "defect_risk_g3 v2, conformal alpha 0.10"},
     "stations_remaining": 14, "minutes_remaining": 14,
     "factors": [
       {"label": "part lot B-4471", "detail": "11 of 47 units from this lot have failed G3 in the last 6 h, against a 1.8% base rate.", "contribution": 0.31},
       {"label": "torque at S12 ran 2.1 sigma low", "contribution": 0.18},
       {"label": "dwell at S23 was 19 s above normal", "contribution": 0.11}
     ]}
  ],
  "threshold": 0.45,
  "highest_below_threshold": {"unit_id": "3C4PDCBJ2JT", "risk_point": 0.11}
}
```

`highest_below_threshold` exists so the calm state can report a measurement rather than
a silence (WIREFRAMES/02).

### `GET /lines/{line_id}/forecast`
The full DES output: per station per 5-minute bucket, blocked and starved probabilities,
buffer trajectories, and the output distribution. Used by charts.

### `GET /predictions/{prediction_id}/evidence`
Everything behind a prediction: the cycle-time series with the drift onset marked, the
buffer trend, the attribution comparison, the inputs hash, the model version, and the
predictor's record on that station.

---

## 4. Counterfactuals

### `POST /lines/{line_id}/counterfactual`
```json
{
  "seed_state_ts": "2026-08-28T09:31:02+05:30",
  "options": [
    {"label": "Add a floater at S20",
     "interventions": [{"type": "ADD_OPERATOR", "station_id": "S20", "count": 1,
                        "from": "now"}]},
    {"label": "Slow takt 4%",
     "interventions": [{"type": "CHANGE_TAKT", "percent": -4, "from": "now"}]}
  ],
  "replications": 200,
  "budget_ms": 5000
}
```

Intervention types: `ADD_OPERATOR`, `REMOVE_OPERATOR`, `CHANGE_TAKT`, `RESEQUENCE_MIX`,
`CHANGE_BUFFER_TARGET`, `STATION_DOWN`.

Response:

```json
{
  "run_id": "0192...",
  "seed_state_ts": "2026-08-28T09:31:02+05:30",
  "replications_used": 200,
  "runtime_ms": 3104,
  "degraded": false,
  "baseline": {"units_this_shift": {"lo": 432, "hi": 449, "point": 441, "unit": "units",
                                    "provenance": "DERIVED", "confidence": 0.9,
                                    "basis": "200 replications, common random numbers"},
               "stall_probability": {"S20": 0.68, "S22": 0.71, "S31": 0.19}},
  "options": [
    {"label": "Add a floater at S20",
     "units_this_shift": {"lo": 440, "hi": 459, "point": 450, "unit": "units", "...": "..."},
     "delta": {"lo": 4, "hi": 13, "point": 9, "unit": "units", "...": "..."},
     "stall_probability": {"S20": 0.31, "S22": 0.24, "S31": 0.18},
     "rank": 1}
  ]
}
```

Baseline and options share seeds (common random numbers), which is why a 9-unit
difference is meaningful at 200 replications. When `degraded` is true, the interface
must state it (CFA-03).

### `POST /counterfactual/{run_id}/mark-executed`
Records that the intervention was actually carried out, so its effect joins the ledger.
Body: `{"executed_at": "...", "note": "floater assigned 09:34"}`.

---

## 5. Retro-trace

### `GET /units/{unit_id}/retro-trace`
```json
{
  "unit_id": "3C4PDCBG7JT",
  "failed_at_gate": "G3",
  "failed_at": "2026-08-28T10:40:12+05:30",
  "hypotheses": [
    {"rank": 1, "station_id": "S12", "window": {"from": "...", "to": "..."},
     "divergence": 3.2, "strength": "leading",
     "description": "torque peak ran 2.1 sigma below the contemporaneous population",
     "shared_attribute": {"type": "PART_LOT", "value": "B-4471"}},
    {"rank": 2, "station_id": "S23", "divergence": 2.6, "strength": "co-hypothesis",
     "description": "dwell ran 19 s above normal while B6 was full"}
  ],
  "containment": {
    "on_line": [{"unit_id": "3C4PDCBG9JT", "similarity": 0.91, "at": "S26",
                 "evidence": ["lot B-4471", "torque at S12 -2.0 sigma"]}],
    "in_yard": [],
    "shipped": [],
    "counts": {"on_line": 17, "in_yard": 6, "shipped": 0}
  },
  "disclaimer": "Ranked hypothesis, not a confirmed root cause. Intermittent and multi-causal conditions are common."
}
```

The `disclaimer` field is part of the contract, not a UI decoration. Any client
rendering this response renders it.

### `GET /units/{unit_id}/retro-trace/export`
CSV containment list with evidence per row. `Content-Type: text/csv`.

---

## 6. The ledger

### `GET /lines/{line_id}/scorecard`
```json
{
  "window_days": 14,
  "predictors": [
    {"predictor": "stall_forecaster", "station_id": "S20", "state": "ACTIVE",
     "made": 11, "true_positive": 8, "false_positive": 3, "unscoreable": 0,
     "missed": 4, "precision": 0.73, "recall": 0.67,
     "median_lead_min": 27, "false_per_shift": 0.4,
     "state_changed_at": "...", "state_reason": "Promoted: 0.73 precision over 11 predictions."},
    {"predictor": "stall_forecaster", "station_id": "S31", "state": "SHADOW",
     "made": 6, "precision": null,
     "state_changed_at": "...",
     "state_reason": "Withdrawn: precision fell to 0.42 over the previous two weeks."},
    {"predictor": "stall_forecaster", "station_id": "S34", "state": "SHADOW",
     "made": 7, "required": 20, "precision": null,
     "state_reason": "Learning. 7 of the 20 predictions needed before alerts start here."}
  ]
}
```

A shadow-state entry never returns a precision, even when one could be computed.
Exposing an unpromoted hit rate invites the floor to trust something that has not
cleared its gate, and the gate is the product's argument.

### `GET /lines/{line_id}/predictions`
Paginated ledger query. Filters: `predictor`, `station_id`, `from`, `to`, `result`,
`published`. Used by the evaluation harness and by Plan view.

---

## 7. Sensor value

### `GET /lines/{line_id}/sensor-recommendations`
```json
{
  "recommendations": [
    {"rec_id": "0192...", "station_id": "S34",
     "unknown": "Cycle time bounded to 54 to 71 s. Cause of stoppage not separable.",
     "option": {"option_id": "clamp_current", "name": "Clamp-on current transducer",
                "indicative_cost_usd": 40, "install_hours": 0.5,
                "requires_window": true,
                "cost_source": "indicative, vendor list price range 2026"},
     "confidence_now": 0.42, "confidence_projected": 0.85,
     "criticality": {"critical_path_share": 0.31, "defect_confidence_impact": 0.18},
     "modelled_annual_value": {"lo": 3100, "hi": 14800, "point": 8200, "unit": "USD",
                               "provenance": "DERIVED", "confidence": 0.5,
                               "basis": "criticality x expected unit loss avoided x unit value"},
     "next_window": "December shutdown",
     "status": "OPEN"}
  ]
}
```

### `GET /lines/{line_id}/sensor-recommendations/export`
CSV for a capital request.

---

## 8. Program view

### `GET /program/sites`
Readiness per site with its computed components.

### `GET /program/business-case` and `POST /program/business-case`
GET returns the current assumptions with their sources and the modelled result. POST
accepts edited assumptions and returns a recalculated result including the sensitivity
ranking. Assumptions are not persisted globally by a POST; the caller receives a
`scenario_id` it can save explicitly.

### `GET /program/realised`
Modelled against realised per site, with links into the ledger evidence.

---

## 9. Live updates

### `WS /ws/lines/{line_id}`
Server pushes on state change and on each forecast cycle. Message envelope:

```json
{"type": "STATE_DELTA" | "ACTIONS" | "UNITS_AT_RISK" | "HEALTH" | "SCORECARD" | "NOTICE",
 "as_of": "...", "seq": 4471, "payload": {}}
```

- `seq` is monotonic. A client that detects a gap re-fetches full state rather than
  applying a partial update.
- Heartbeat every 15 s. A client that misses two heartbeats shows its data age
  prominently rather than reconnecting silently.
- `NOTICE` carries predictor promotions and demotions, data gaps opening and closing,
  and degraded-run warnings. These are the messages the interface renders as `Notice`
  components.

---

## 10. Operations

### `GET /health`
`{"status": "ok", "db": "ok", "worker_last_cycle_at": "...", "cycle_lag_s": 4}`

### `GET /config/lines/{line_id}`
The LineDefinition as loaded, with its version and load time. So a prediction made
under an older configuration can be interpreted.

### `POST /admin/reload-config`
Reloads configuration from disk, increments `config_version`, and moves every predictor
back to `SHADOW` for any station whose definition changed. Changing a line's structure
invalidates the evidence a predictor was promoted on, so the gate is re-earned rather
than inherited.

---

## 11. What the API deliberately does not offer

| Not offered | Reason |
|---|---|
| Any write to a control system | Architectural boundary, permanent |
| An endpoint that applies a counterfactual | Advisory only |
| An endpoint returning a bare number without provenance | Structurally prevented by the `Estimate` shape |
| An endpoint returning shadow-mode predictions to the floor client | The gate is enforced server-side, not by client discipline |
| Ground truth from the simulator | The API's database role cannot read that schema |

---

**Related:** [TECHNICAL_SPEC.md](TECHNICAL_SPEC.md) · [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) · [SECURITY_REQUIREMENTS.md](SECURITY_REQUIREMENTS.md) · [../quality/ERROR_HANDLING.md](../quality/ERROR_HANDLING.md)
