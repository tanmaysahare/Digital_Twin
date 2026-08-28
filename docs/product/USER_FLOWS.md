# USER_FLOWS.md

**Purpose:** the paths people actually take through the product, including the ones where something goes wrong.
**Convention:** flows are numbered `UF-nn`. Steps in square brackets are system actions; steps in plain text are user actions. Decision points are marked with `?`.
**Last updated:** 2026-08-28

---

## UF-01: The drift-to-action loop (the core flow)

This is the flow the product exists for. Everything else supports it.

```
[Line runs normally]
        |
        v
[Twin ingests cycle events every takt]
        |
        v
[EWMA and CUSUM run per station per variant]
        |
        v
   Drift detected? --no--> [continue silently, nothing on screen changes]
        |
       yes
        |
        v
[Station marked DRIFTING on line strip; a quiet marker, not an alarm]
        |
        v
[Next 2-minute forecast cycle seeds DES from live state]
        |
        v
[200 Monte Carlo replications over 120 min]
        |
        v
   P(stall) > 0.55 in horizon? --no--> [drift marker stays, no action raised]
        |
       yes
        |
        v
[Attribute cause via average active period + buffer trend]
        |
        v
   Predictor ACTIVE for this station? --no--> [write to ledger in SHADOW,
        |                                       show nothing on the floor]
       yes
        |
        v
[Write to ledger; raise action card on Line view]
        |
        v
Priya sees: STATION | WINDOW | PROBABILITY | CAUSE | LEAD TIME | UNITS AT RISK
        |
        +--> taps card --> [evidence drawer: cycle-time chart with the drift
        |                   marked, buffer trend, active-period attribution,
        |                   this predictor's record on this station]
        |
        +--> taps "Test a fix" --> UF-02
        |
        +--> acts on the floor --> taps "We did this" --> [logged against
                                    the forecast; outcome joined at horizon]
        |
        v
[Horizon elapses]
        |
        v
[Ledger joins actual outcome automatically]
        |
        v
[Precision, recall and lead time for this predictor on this station update]
        |
        v
[Visible in the scorecard on Line view and Plan view]
```

**Timing on the demo path (scenario SC-01):** onset 09:14, drift flagged 09:26, forecast raised 09:29, predicted window 09:52 to 10:04. Lead time as displayed: 27 minutes.

**Failure branch.** If the forecast fires and no stall occurs, the ledger records a false positive, the station's precision drops, and if it crosses the demotion threshold the predictor returns to shadow and the floor is told it was withdrawn. Priya is never left wondering why an alert stopped appearing.

---

## UF-02: Counterfactual sandbox

```
Entry: from an action card ("Test a fix") or from the sandbox tab
        |
        v
[Sandbox opens pre-loaded with the current live state and, if entered from
 a card, with the implicated station pre-selected]
        |
        v
Choose an intervention:
  - Add or remove an operator at a station
  - Change takt by a percentage
  - Resequence the upcoming model mix
  - Change a buffer target
  - Take a station down for N minutes (planned intervention)
        |
        v
[Run. Same DES engine, same seed policy, reduced replications if needed]
        |
        v
[Result in under 5 s]
        |
        v
Shows:  DO NOTHING          |  THIS INTERVENTION
        units this shift    |  units this shift
        +/- band            |  +/- band
        P(stall) by station |  P(stall) by station
        DELTA: +9 units (range +4 to +13)
        |
        +--> "Add another option" --> [up to 3 compared side by side, ranked]
        |
        +--> "Save as decision" --> [logged; effect joins the ledger]
        |
        v
Exit. Nothing is applied automatically. Ever.
```

**Latency degradation.** If the run exceeds the budget, replications drop and the uncertainty band widens visibly, with a one-line note. The system never hides that it took a shortcut.

---

## UF-03: Defect risk to containment

```
[Unit enters the line, VIN assigned]
        |
        v
[Process signature accumulates station by station]
        |
        v
[After each station, the unit is re-scored for each downstream gate]
        |
        v
   Calibrated P(fail) > gate threshold AND predictor ACTIVE? --no--> [ledger only]
        |
       yes
        |
        v
[Unit appears in the At-risk units list on Line view]
   Shows: VIN | current station | target gate | stations remaining |
          minutes remaining | probability with interval | top 3 factors
        |
        +--> Priya taps the unit --> [full signature timeline: every station
        |    visited, what was normal, what was not, which stations were dark]
        |
        +--> Priya acts: inspect early, hold, or correct in line
        |
        v
[Unit reaches the gate]
        |
        v
   Failed? --no--> [ledger records outcome; if the alert was raised, it is a
        |            false positive and precision moves]
       yes
        |
        v
[Retro-trace runs automatically]
        |
        v
[Walk the failed unit's signature backwards; find the station and window
 where its signature diverged most from the contemporaneous population]
        |
        v
[Query all units through that station in that window with comparable divergence]
        |
        v
[Containment list, ranked by similarity]
   Tier 1: units still on the line   (actionable now)
   Tier 2: units in the yard         (actionable today)
   Tier 3: units already shipped     (export only, for the customer's QMS)
        |
        +--> Export CSV with evidence per row
        |
        v
[Labelled: ranked hypothesis, with strength. Not "root cause"]
```

**Demo path (SC-02):** part lot B-4471 raises G3 failure probability. Six units flagged 14 stations ahead of G3. First G3 failure at 10:40 triggers retro-trace, which returns 23 units, 17 still on the line, with the lot as shared evidence.

---

## UF-04: Dark station to sensor recommendation

```
[S34 is Tier C. No machine data at all]
        |
        v
[Virtual sensor: bound cycle time from flanking arrival timestamps
 minus nominal transport, attribute blocking or starving from flanking
 buffer occupancy]
        |
        v
[Line view draws S34 with a hatched fill and shows an interval, e.g. 54-71 s,
 never a single number]
        |
        v
[Observability score computed for S34 from provenance mix and interval width]
        |
        v
[Criticality computed: share of forecast stalls where S34 lay on the critical
 path; share of defect predictions whose confidence was limited by its darkness]
        |
        v
   Low observability AND high criticality? --no--> [no card; not every dark
        |                                            station is worth fixing]
       yes
        |
        v
[Match against the sensing catalogue; pick the cheapest option that would
 raise the limiting estimate above the target confidence]
        |
        v
[SENSOR VALUE CARD]
   What is unknown today: cycle time bounded to 54-71 s; cause of stoppage
     not separable into blocked, starved or slow
   Proposed: clamp-on current transducer on the main drive
   Would resolve: cycle time to +/- 2 s; blocking cause to 0.85 confidence
   Indicative cost: 40 USD hardware, 0.5 h install, no production impact
   Requires: scheduled window (next: December shutdown)
   Modelled annual value: [computed from criticality and unit loss]
        |
        +--> Rakesh opens Plan view --> [sensor investment queue, ranked]
        |
        +--> Export for capital request
        |
        v
[After install, realised confidence gain compared against the modelled gain]
```

---

## UF-05: Priya's shift (the ordinary day)

The flow that happens 200 times for every one time UF-01 fires. If this flow is unpleasant, nothing else matters.

```
05:45  Handover. Opens Line view on the shift office desktop.
       Sees: previous shift's action log, anything still open, current line state.
       No login ceremony. No tour. No dashboard of tiles.
         |
06:00  Shift starts. Line view goes up on the 55-inch line-side display and stays there.
         |
06:00-14:30  Glances at the display roughly every 10 minutes while walking past.
       On a normal shift: everything is greyscale, the action list reads
       "Nothing needs attention", the data age reads under 2 minutes.
       She does nothing. This is the product working.
         |
       Carries the tablet. Opens it when she wants a station's detail,
       or when an action card appears.
         |
14:20  Handover prep. Taps "Shift summary".
       Sees: units out vs target, the split of lost time by cause, actions
       raised and what happened to them, anything building for the next shift.
         |
14:30  Hands over.
```

**Design consequence.** The most common state of this product is "nothing to report". That state must look intentional and calm, not like an error or an empty state waiting to be filled. See ../human-design/HUMAN_DESIGN_GUIDELINES.md Section 7.

---

## UF-06: Rakesh's Monday

```
Opens Plan view. Range defaults to the last 4 weeks.
        |
        v
Reads the constraint migration heatmap: which station was the bottleneck
each week, and for what share of each week.
        |
        v
Notices S20 has been the constraint 3 of the last 4 weeks (it was S31 before).
        |
        +--> Drills into S20 --> [cycle-time distribution over the quarter,
        |    drift events, maintenance history, the twin's own accuracy there]
        |
        v
Reads the loss Pareto: blocked 34%, starved 22%, down 19%, changeover 15%,
quality 10%. Shares reconcile to the shift gap; the reconciliation is shown.
        |
        v
Opens buffer recommendation: "Raising B7 from 6 to 9 is modelled at +14
units/day. Assumptions: [listed, editable]."
        |
        +--> Tests it in the sandbox against last Tuesday's state
        |
        v
Opens the sensor investment queue. Three cards, ranked, total 310 USD,
all installable in the December window.
        |
        +--> Exports for the capital request
        |
        v
Opens the predictor scorecard before the meeting, because he will be asked.
        |
        v
Prints Plan view. Takes it into the meeting on paper.
```

---

## UF-07: Meera's quarterly review

```
Opens Program view.
        |
        v
Site readiness table: 12 sites scored from what each actually emits.
   Columns: unit-level traceability, cycle event coverage, dark station share,
   historian availability, MES inspection results, estimated clock quality.
   Score is computed, not surveyed.
        |
        v
   3 sites READY | 5 sites READY WITH INSTRUMENTATION | 4 sites NOT READY
        |
        +--> Opens a NOT READY site --> [exactly what is missing and what it
        |    would take; not a generic maturity level]
        |
        v
Opens the business case. Every assumption is an editable field with its source
and its uncertainty:
   - baseline unplanned stop minutes per line per month
   - value of a recovered unit
   - forecast precision assumed (defaults to measured, not to aspirational)
   - defect escape rate and repair-yard cost multiplier
   - implementation cost per site
   - instrumentation cost per site (from that site's sensor queue)
        |
        +--> Changes the assumed precision from measured 0.74 down to 0.60
        |    --> [payback recalculates and is shown]
        |
        v
Opens modelled vs realised for the pilot site.
   Modelled: 11% reduction in unplanned stop minutes.
   Realised: 7%. Shown as a shortfall, with the ledger evidence.
        |
        v
Decision: approve wave 1 (3 READY sites), fund instrumentation for wave 2.
```

**Design consequence.** Program view must be able to show a shortfall without looking broken. A tool that only reports success is not used twice.

---

## UF-08: Something is wrong with the data (the flow most products skip)

```
[An adapter stops emitting]
        |
        v
   No events for > 3 takt periods? --no--> [normal operation]
        |
       yes
        |
        v
[Data health warning appears in the header, not as a modal]
   "S17-S22 source last seen 4 min ago"
        |
        v
[Affected stations on the line strip take the STALE treatment: their state
 is shown with its age, not blanked and not silently frozen]
        |
        v
[Forecast continues on remaining sources with reduced confidence; the
 confidence reduction is shown, and forecasts that depended materially on
 the missing source are suppressed rather than degraded silently]
        |
        v
   Source returns? --yes--> [backfill by ts_source, recompute affected state,
        |                     clear the warning, note the gap in the shift log]
        |
        no (> 15 min)
        |
        v
[Escalate the warning; Priya is told which part of the line the twin can no
 longer see, in one sentence, in plant language]
```

**Rule.** The twin never fabricates a value to fill a gap and never presents stale data as current. See ../quality/ERROR_HANDLING.md.

---

## UF-09: A predictor is promoted (the trust flow)

```
[New predictor deployed, or a new station onboarded]
        |
        v
[State: SHADOW for every station. Records and scores. Raises nothing]
        |
        v
[Accumulates scoreable predictions as horizons elapse]
        |
        v
   >= 20 scoreable predictions on this station? --no--> [stay in shadow]
        |
       yes
        |
        v
   Precision >= 0.70 AND recall >= 0.50 over the window? --no--> [stay in
        |                                                          shadow]
       yes
        |
        v
[Promote to ACTIVE for this station only]
        |
        v
[Notice on Line view: "Stall forecasting is now active for S20. It has been
 right on 8 of 11 forecasts here over the last two weeks."]
        |
        v
[Ongoing monitoring]
        |
        v
   Rolling precision < 0.55? --yes--> [demote to SHADOW; tell the floor it
        |                               was withdrawn and why]
        no
        |
        v
[Stay active; scorecard keeps updating in public]
```

**Why this is a user flow and not an implementation detail.** Priya experiences this as the system asking for her attention only after it has earned it, and admitting when it stops deserving it. That experience is the product.

---

## UF-10: Onboarding a new line

```
Implementation engineer receives: a recorded event stream from the site
        |
        v
Runs topology discovery
        |
        v
[Infers station order from unit handoff sequences, transport times from
 arrival deltas, buffer behaviour from blocking and starving patterns,
 model variants from build records]
        |
        v
[Drafts LineDefinition.yaml with confidence per inferred field, and marks
 what it could not infer]
        |
        v
Engineer corrects the draft with plant knowledge (buffer capacities,
inspection gate positions, rework loops, tier assignment)
        |
        v
Writes SourceMapping.yaml: site tags and topics to canonical events
        |
        v
[Twin starts. No code change]
        |
        v
[All predictors start in SHADOW for this line]
        |
        v
[Readiness score computed and reported: what will work now, what needs
 instrumentation first]
        |
        v
[Weeks 1-4: shadow. Weeks 4-8: stations begin clearing promotion gates]
```

---

## Flow inventory

| Flow | Persona | MVP | On the demo path |
|---|---|---|---|
| UF-01 Drift to action | Priya | Yes | Yes, primary |
| UF-02 Counterfactual | Priya | Yes | Yes |
| UF-03 Defect to containment | Priya, Rakesh | Yes | Yes |
| UF-04 Dark station to sensor card | Rakesh | Yes | Yes |
| UF-05 Ordinary shift | Priya | Yes | Yes, opens the demo |
| UF-06 Monday planning | Rakesh | Yes | Briefly |
| UF-07 Quarterly review | Meera | Yes | Briefly |
| UF-08 Data health | All | Yes | Optional (SC-07) |
| UF-09 Promotion | Priya, Rakesh | Yes | Yes, closes the demo |
| UF-10 Line onboarding | Implementation | Partial (P2) | No |

---

**Related:** [USER_STORIES.md](USER_STORIES.md) · [USER_PERSONAS.md](USER_PERSONAS.md) · [../design/UX_SPEC.md](../design/UX_SPEC.md) · [../design/WIREFRAMES/](../design/WIREFRAMES/) · [../quality/ERROR_HANDLING.md](../quality/ERROR_HANDLING.md)
