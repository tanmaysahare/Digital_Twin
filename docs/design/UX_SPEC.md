# UX_SPEC.md

**Purpose:** screen by screen, region by region, what is on it and how it behaves.
**Read with:** WIREFRAMES/ for layout, UI_COMPONENTS.md for the parts, DESIGN_SYSTEM.md for the tokens, ../human-design/UX_WRITING_GUIDELINES.md for every string.
**Last updated:** 2026-08-28

---

## 1. Global structure

### 1.1 Navigation

Three views. That is the entire navigation. No sidebar, no menu, no settings gear in the corner.

```
DigitalTwin.ai   Line 2   |  Line   Plan   Program  |   Simulated data   14:32:06 · 38 s ago
------------------------------------------------------------------------------------------
```

- Product name and line identifier on the left. The line identifier is a select when more than one line is configured.
- Three view tabs, centred-left, sentence case, active tab marked with a 2px `--accent` underline. No icons.
- On the right: the simulated-data marker (permanent in the prototype, non-removable), the current data timestamp, and its age.
- Header height 48px, `--paper` background, `--border` bottom.
- A persona switcher appears only in the prototype, at the far right, labelled "Viewing as". It is explicitly a demo affordance and the README says so.

### 1.2 Global rules

- **Data age is always visible.** Every view shows the timestamp of the state it is displaying and how old it is. When age exceeds two forecast cycles, the age indicator takes the `--state-drift` treatment.
- **Nothing blocks.** No modal ever covers the line state. The drawer and the sandbox are overlays that leave the line strip visible.
- **No page-level loading state.** Views render with the last known state and its age. If there is no state at all yet (first 60 seconds after a cold start), the view says what it is waiting for and how many cycles it needs.
- **Keyboard is a first-class input.** The line-side display is often driven by keyboard. Every action has a keyboard path.

---

## 2. Line view (Priya)

The default view. Fixed viewport, no page scroll. Wireframe: WIREFRAMES/01-line-view.md

### 2.1 Region map

```
+---------------------------------------------------------------------------+
|  HEADER                                                                   |
+---------------------------------------------------------------------------+
|  A. LINE STRIP                                            full width, 180px|
+------------------------------------+--------------------------------------+
|  B. ACTIONS                        |  C. AT-RISK UNITS                    |
|  7 cols                            |  5 cols                              |
+------------------------------------+--------------------------------------+
|  D. OUTPUT AND LOSS       |  E. PREDICTOR RECORD  |  F. DATA HEALTH       |
|  4 cols                   |  4 cols               |  4 cols               |
+---------------------------------------------------------------------------+
```

### 2.2 Region A: line strip

The signature element. Full width, 180px tall.

**Contents, top to bottom:**
1. **Forecast track** (40px). A time axis from now to now plus 120 minutes. Forecast markers sit here, positioned at their predicted window, drawn as an interval bar in `--state-forecast`, labelled with the station.
2. **Station row** (90px). 42 segments, equal width, 1px gap. Each segment carries:
   - Station ID, mono micro type, top-left
   - State fill: none for running, stripe for blocked or starved, `--state-drift` for drifting, `--state-down` solid for down, cross-hatch for Tier C
   - A cycle-time bar: a thin vertical mark showing the current cycle against the station's normal range, drawn as a small range plot. For a Tier C station this is an interval, drawn wider and hatched
   - The current cycle time in mono micro type, bottom. For Tier C, an interval
3. **Buffer row** (30px). Narrow blocks between station groups showing occupancy against capacity as a fill. Labelled B1 to B9.
4. **Zone rule** (20px). A thin rule beneath, labelled Body S01-S16, Paint S17-S26, Final assembly S27-S42, with gate markers G1, G2, G3.

**Behaviour**
- Hovering or focusing a segment shows a one-line tooltip: state, current cycle, normal range, provenance.
- Clicking or pressing Enter opens the station drawer (Section 6).
- Left and right arrow keys move between stations. Home and End jump to the ends.
- On a state change, the segment fill transitions over `--motion-value`. Nothing else animates.
- Horizontal scroll only below 1024px width, where the strip becomes scrollable with the abnormal stations pinned into view. See RESPONSIVE_DESIGN.md.

**The quiet state.** All 42 segments grey, cycle bars sitting near the middle of their ranges, buffers around half. It should look like a well-set instrument, not like an empty grid.

### 2.3 Region B: actions

At most three rows. Ranked. This is the region Priya reads first.

**When there is nothing:**
```
Nothing needs attention
42 stations running · 4 forecasts in shadow · last check 14:32:06
```
Set in `--text-body` `--ink-2`, with the second line in `--text-small` `--ink-3`. Left aligned, in the panel, not centred, no illustration.

**When there is a stall forecast:**
```
+-------------------------------------------------------------------+
| Line stop likely at S22                          LEAD TIME        |
| 09:52 to 10:04    probability 0.71                  27            |
| Cause: S20 cycle time drifted +4.1 s since 09:14    min           |
| At risk 11 units                                                  |
|                                                                   |
| [ Show evidence ]  [ Test a fix ]  [ We did this ]                |
+-------------------------------------------------------------------+
```
- 2px `--state-forecast` left border. No fill. The card is not coloured, only marked.
- Lead time is the only `--text-display` element on the screen. It is the number that determines whether Priya can act.
- Three buttons, words not icons, in a row.
- Multiple actions stack, ranked by expected unit loss. Concurrent causes are separate rows, never merged.

**Show evidence** expands the card in place (it does not open a drawer) to reveal: the cycle-time chart for the cause station with the drift onset marked, the buffer trend for the affected buffer, the active-period attribution, and one line of predictor record: "Stall forecasting has been right on 8 of 11 forecasts at S20 over the last two weeks."

**Test a fix** opens the counterfactual sandbox pre-loaded with this station.

**We did this** logs an intervention against this forecast so that its effect joins the ledger. It opens a two-field inline form (what, and when), not a modal.

### 2.4 Region C: at-risk units

A table, not cards. Sorted by minutes remaining ascending, because the most urgent is the one with the least time.

| VIN | At | Gate | Risk | Remaining | Top factor |
|---|---|---|---|---|---|
| 3C4PDCBG7JT | S28 | G3 | 0.68 (0.54-0.79) | 14 st · 14 min | lot B-4471 |
| 3C4PDCBG9JT | S26 | G3 | 0.66 (0.51-0.78) | 16 st · 16 min | lot B-4471 |

- VIN in mono, truncated to the last 11 characters with the full value on hover and in the drawer.
- Risk as a calibrated probability with its conformal interval.
- Remaining in both stations and minutes, because stations is what Priya can act on and minutes is what she can plan around.
- Top factor is the single strongest; the other two appear in the drawer.
- Clicking a row opens the unit drawer (Section 7).
- Maximum eight rows visible, with a count of the rest. Never paginate; if there are more than eight at-risk units the plant has a bigger problem and the row count says so.

### 2.5 Region D: output and loss

Two elements, no card border between them.

1. **Output against target.** A horizontal bar: units completed this shift against the shift target, with the pace line showing where the line should be now. Numbers in mono. One line of text: "312 of 460 · pace 4 units behind".
2. **Loss so far this shift**, as a horizontal stacked bar split into blocked, starved, down, changeover, quality, with minutes labelled directly on the segments rather than in a legend. The segments use state colours because the segments are states.

### 2.6 Region E: predictor record

The scorecard, compressed to what fits.

```
Stall forecaster        active     8 of 11 right    27 min median lead
Defect risk (G3)        active    22 of 31 right     6 stations lead
Defect risk (G2)        shadow     4 of 20 needed
Drift detector          active    14 of 16 right
```

One line per predictor. State in plain words. A predictor in shadow shows its progress toward the gate, not a hit rate, because a shadow hit rate invites the floor to trust something that has not been promoted.

Clicking opens the full per-station scorecard in Plan view.

### 2.7 Region F: data health

```
Sources     4 of 4 live
Last event  14:32:06 (2 s ago)
Clock skew  max 0.8 s (final assembly vs body)
Coverage    36 of 42 stations reporting · 6 dark by design
```

Normally four quiet lines. When a source goes silent, the affected line takes the `--state-drift` treatment and gains a sentence in plant language. See ../quality/ERROR_HANDLING.md.

---

## 3. Plan view (Rakesh)

Scrollable, dense, prints cleanly on A4 landscape. Wireframe: WIREFRAMES/02-plan-view.md

### 3.1 Range control
A single row at the top: range selector (last week, last 4 weeks, last quarter, custom), shift filter (all, A, B), variant filter. No date picker calendar widget; plain selects and two date fields.

### 3.2 Constraint migration
A heatmap. Rows are stations that have been the constraint at least once in the range; columns are weeks. Cell value is the share of that week the station was the momentary constraint, rendered as a greyscale density. The current constraint is marked. Direct labels on the cells above 20 percent, no legend needed.

This answers Rakesh's first question in one glance: is my constraint stable or moving.

### 3.3 Loss Pareto
A horizontal bar chart of lost minutes by cause, descending, with the reconciliation line below: "Sum of causes 1,842 min. Shift gap from plant reporting 1,861 min. Unexplained 19 min (1.0 percent)."

That reconciliation line is not optional. If the twin's loss accounting does not tie to the plant's own numbers, the twin is wrong and it must say so rather than presenting a second set of books.

### 3.4 Buffer and staffing recommendations
A table. Each row: what to change, modelled effect with an interval, the assumptions (inline, in `--text-small`), and a "Test in sandbox" action that opens the sandbox against a chosen historical state.

### 3.5 Sensor investment queue
A table of Sensor Value Cards, ranked. Columns: station, what is unknown, proposed sensor, confidence gain, indicative cost, install effort, next window, modelled annual value. An export action produces a CSV suitable for a capital request.

### 3.6 Predictor scorecard, full
Every predictor by every station. Columns: predictor, station, state, predictions, precision, recall, median lead time, false alerts per shift, last state change. Sortable. Predictors in shadow are grouped at the bottom with their progress.

A row for a demoted predictor shows when and why it was withdrawn.

### 3.7 Shift comparison (P2)
Same stations, A shift against B shift: cycle-time distributions, loss split, defect rate. Small multiples, one per station, greyscale, direct labelled.

---

## 4. Program view (Meera)

Narrower measure, more prose than the other two, designed to be projected. Wireframe: WIREFRAMES/03-program-view.md

### 4.1 Site readiness
A table of sites with a computed readiness score and its components: unit-level traceability present, cycle event coverage percentage, dark station share, historian available, MES inspection results available, clock quality. Score bands are READY, READY WITH INSTRUMENTATION, NOT READY, stated as words rather than as a number out of ten.

Clicking a site expands to exactly what is missing and what it would take, drawn from that site's own sensor queue.

### 4.2 Business case
A two-column layout. Left: assumptions, every one an editable field with its source and its uncertainty noted beneath. Right: the resulting model, recalculating on change.

Assumptions, with defaults:
- Baseline unplanned stop minutes per line per month (site-measured, no default)
- Value of a recovered unit (site-specific; the field carries a note that published per-hour downtime figures are industry-specific and should not be used as universal constants, citing S-04)
- Forecast precision (defaults to the measured value from the ledger, not to an aspiration)
- Defect escape rate and repair-yard cost multiplier
- Implementation cost per site
- Instrumentation cost per site (pulled from that site's sensor queue)

Output: modelled annual benefit with a range, payback period, and a sensitivity table showing which assumption the result is most sensitive to.

**Design rule.** The sensitivity table is mandatory. A business case that does not show what it is sensitive to is a business case that cannot be interrogated, and Meera's job is to interrogate it.

### 4.3 Modelled against realised
For any site past pilot: modelled benefit, realised benefit, and the gap, with the ledger evidence behind the realised figure. Presented plainly whether the gap is positive or negative. This region must look correct when showing a shortfall.

### 4.4 Rollout wave plan (P2)
Sites sequenced into waves by readiness and modelled value, with instrumentation prerequisites and lead times attached.

---

## 5. Counterfactual sandbox

An overlay, not a page. Occupies the lower two thirds of the viewport and leaves the line strip visible above it, because the line does not stop for a dialog.

```
+---------------------------------------------------------------------------+
| Test a fix                                                          [ x ]  |
+---------------------------------------------------------------------------+
| Intervention                        | Result                              |
|                                     |                                     |
| Type    [ Add an operator      v ]  |            Do nothing   This fix    |
| Station [ S20                  v ]  | Units this shift   441        450   |
| From    [ now                  v ]  | Range           432-449    440-459  |
|                                     | Difference                   +9     |
| [ Run ]  [ Add another option ]     |                          (+4 to +13)|
|                                     |                                     |
|                                     | P(stall) by station: [small chart]  |
+---------------------------------------------------------------------------+
| Ran 200 replications in 3.1 s from the 14:32:06 state                     |
| [ Save as decision ]                                                       |
+---------------------------------------------------------------------------+
```

- Intervention types: add or remove an operator, change takt by a percentage, resequence the model mix, change a buffer target, take a station down for N minutes.
- Up to three options compared side by side, ranked by expected units.
- The footer states replication count, runtime and the state timestamp. If replications were reduced to meet the latency budget, the footer says so in the same place and the ranges widen visibly.
- Nothing is applied. "Save as decision" records the choice for later scoring; it changes nothing on the line.

---

## 6. Station drawer

Opens from the right, 480px wide, over Line view, leaving the strip visible. Wireframe: WIREFRAMES/04-station-drawer.md

Contents:
1. Station ID, zone, tier, and current state with time in state.
2. Cycle time: current, normal range for the current variant, and a chart of the last 200 cycles with drift onset marked if detected. For a Tier C station this is an interval band, hatched, with a line explaining how it was derived.
3. What the twin knows and does not know, in plain sentences. For a dark station: "S34 has no machine data. Cycle time is bounded to 54 to 71 s from the stations either side. Blocked, starved and slow work cannot be separated."
4. Buffer state either side.
5. Predictor record for this station.
6. Sensor Value Card, if one exists for this station.
7. Recent events: andon, changeover, maintenance, drift detections.

---

## 7. Unit drawer

Opens from the right over Line view. Wireframe: WIREFRAMES/05-unit-drawer.md

Contents:
1. VIN, variant, current station, entry time, target gates.
2. Risk per remaining gate, with conformal interval and stations and minutes remaining.
3. Top three factors in plant language, each expandable to its evidence.
4. **Process signature timeline.** The spine of this drawer: every station the unit has visited, in order, with dwell time, cycle time, state, and a marker where the value was outside that station's normal range. Dark stations appear as hatched segments with an interval. This is the visual answer to "a defect introduced early surfaces much later".
5. Part lots consumed, with a link to other units sharing each lot.
6. If the unit has failed a gate: the retro-trace result and the containment list it generated.

---

## 8. Interaction inventory

| Action | Mouse | Keyboard | Touch |
|---|---|---|---|
| Switch view | Click tab | `1` `2` `3` | Tap tab |
| Select station | Click segment | Arrow keys, Enter | Tap segment |
| Open drawer | Click segment | Enter on focused segment | Tap segment |
| Close drawer or overlay | Click x, click outside | Escape | Tap x, swipe right |
| Open sandbox | Click "Test a fix" | `t` | Tap |
| Run counterfactual | Click "Run" | Enter in the form | Tap |
| Expand evidence | Click "Show evidence" | Enter | Tap |
| Sort a table | Click header | Enter on focused header | Tap header |
| Export | Click "Export" | Enter | Tap |

No gesture is the only way to do anything. No hover is the only way to reveal information that matters.

---

## 9. States every screen must handle

Specified once here, applied everywhere. Behaviour detail in ../quality/ERROR_HANDLING.md.

| State | Treatment |
|---|---|
| Normal, nothing wrong | Full information, greyscale, calm. The designed state |
| First 60 s after cold start | "Building the line state. Forecasts start after 20 recorded cycles per station." with a live count |
| A source is silent | Header warning, affected stations show state with age, forecasts for that section suppressed rather than degraded |
| All sources silent | The whole strip shows its age prominently. No fabricated state, no blank screen |
| Predictor in shadow | Nothing raised to the floor. Progress toward the gate visible in the predictor record region |
| Predictor demoted | A plain notice with the reason, persisting until acknowledged |
| Insufficient history for a station | That station's forecasts suppressed, with the count needed shown in the drawer |
| Counterfactual exceeded budget | Result shown with reduced replications, wider bands, and a footer note |
| Export failed | Inline message next to the export action, not a toast |

---

**Related:** [WIREFRAMES/](WIREFRAMES/) · [UI_COMPONENTS.md](UI_COMPONENTS.md) · [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md) · [RESPONSIVE_DESIGN.md](RESPONSIVE_DESIGN.md) · [../product/USER_FLOWS.md](../product/USER_FLOWS.md)
