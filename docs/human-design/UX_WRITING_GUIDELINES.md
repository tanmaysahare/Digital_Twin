# UX_WRITING_GUIDELINES.md

**Scope:** every string that appears in the product. Labels, buttons, table headers, alerts, errors, empty states, tooltips, export filenames.
**Status:** binding. Strings are reviewed like code.
**Last updated:** 2026-08-28

---

## 1. Voice

The product speaks like a competent colleague who has been on the floor for years, is telling you something useful, and is not trying to impress you.

**It is:** direct, specific, quantified, calm, honest about uncertainty.
**It is not:** enthusiastic, apologetic, chatty, clever, or reassuring in a way it has not earned.

Test every string by reading it aloud. If you would not say it standing next to someone at S20, rewrite it.

---

## 2. The register, by example

| Wrong | Right | Why |
|---|---|---|
| "Our AI has detected a potential anomaly!" | "S20 cycle time has drifted 4.1 s above its normal range over the last 40 minutes." | Names the station, the quantity, the amount and the window. No self-reference. No exclamation |
| "Optimize your line performance" | "Test a fix" | Says what the button does |
| "Insights" | "What changed this week" | An "insights" panel could contain anything |
| "Smart recommendations powered by machine learning" | "Ranked actions" | The user does not care how it was computed until they check the record |
| "Oops! Something went wrong." | "The S17 to S22 source stopped sending 4 minutes ago. Forecasts for the paint zone are paused until it returns." | Says what, where, since when, and what follows |
| "Data is loading..." | "Last updated 14:32:06, 38 s ago" | There is always a last known state and an age |
| "No data available" | "S34 has no machine data. Cycle time is bounded to 54 to 71 s from the stations either side." | Absence of a sensor is not absence of knowledge |
| "Great job! Zero defects today." | "No units failed at G3 this shift." | Reports; does not congratulate |
| "Are you sure you want to continue?" | "This will clear the three options you are comparing." | Says what happens |
| "An unexpected error occurred (E_5012)" | "The forecast could not run because S27 has no cycle history for the LWB variant yet. It will run once 20 cycles are recorded." | A code is for the log, not for the user |

---

## 3. Rules

### Structure
1. **Lead with the subject.** "S20 is drifting", not "There is a drift at S20".
2. **One idea per string.** If a message has two clauses joined by "and", consider two strings or a heading plus a line.
3. **Front-load the number when the number is the point.** "27 min of lead time" beats "You have 27 minutes".
4. **No preamble.** Never "Please note that", "It looks like", "We noticed that", "It appears".

### Grammar and mechanics
5. **Sentence case everywhere.** Headings, buttons, labels, table headers, chips.
6. **No terminal full stop on labels, buttons, table headers or chips.** Full stops on sentences in body copy, alerts and errors.
7. **No em dashes.** Comma, colon, parentheses, or a second sentence.
8. **No exclamation marks. No emoji. No ellipsis as a stylistic device** (only in a genuine truncation).
9. **Second person for instructions** ("Add a floater at S20"), third person for observations ("S20 is drifting").
10. **Present tense for current state, future for forecast, past for record.** Keep the tenses honestly separated; a forecast written in the present tense reads as a fact.

### Numbers and units
11. **Always carry the unit.** `58.4 s`, `27 min`, `11 units`, `0.71`.
12. **Precision reflects real accuracy.** Cycle times to 0.1 s. Probabilities to two decimals. Unit counts as integers. Never a probability as a percentage with decimals.
13. **Intervals where the estimate is an interval.** `54 to 71 s`, not `62 s`. `+9 units (range +4 to +13)`, not `+9 units`.
14. **Time windows, not points, for forecasts.** "between 09:52 and 10:04", not "at 09:58".
15. **24-hour clock.** Plant convention. `09:52`, not `9:52 AM`.
16. **Relative time only under 60 minutes**, absolute beyond. "38 s ago", "14:32:06".

### Terminology (use these, consistently)
17. The plant's words, not ours:

| Use | Not |
|---|---|
| station | node, asset, workstation, machine |
| unit, or VIN when specific | item, product, entity, part (a part is a component) |
| buffer | queue, WIP store, accumulator |
| blocked / starved / down / changeover | idle, offline, unavailable, inactive |
| takt | cycle rate, beat |
| gate (G1, G2, G3) | checkpoint, inspection node |
| shift | period, session |
| drift | anomaly, deviation, outlier |
| forecast | prediction (in UI copy; "prediction" is fine in documentation) |
| dark station | uninstrumented node, blind spot |
| lead time | warning time, advance notice |
| floater | flex operator, additional resource |
| repair yard | rework area, offline repair |

18. **Never say "AI", "model", "algorithm" or "machine learning" in the interface**, except inside the predictor scorecard where the object being discussed genuinely is a model, and there it is named ("Stall forecaster v3", "Defect risk model v2").

### Honesty
19. **State confidence where it exists, and never round it away.**
20. **Say what is inferred.** Any value derived rather than measured is labelled. Never present an inference as a reading.
21. **Say when you are wrong.** A withdrawn predictor produces a plain notice: "Stall forecasting for S31 has been withdrawn. It was right on 5 of 12 forecasts over the last two weeks, below the threshold for showing alerts."
22. **Never promise.** "Expected loss 11 units" not "Will cost 11 units". "Modelled at +14 units per day" not "Will deliver +14 units per day".

---

## 4. String patterns for the recurring cases

Reuse these shapes so the interface reads consistently. `{}` marks a substitution.

**Stall forecast card**
```
Line stop likely at {station}
{start_time} to {end_time}   probability {p}
Cause: {cause_station} {cause_description}
Lead time {n} min          At risk {n} units
```
Example:
```
Line stop likely at S22
09:52 to 10:04   probability 0.71
Cause: S20 cycle time drifted +4.1 s since 09:14
Lead time 27 min          At risk 11 units
```

**Drift notice**
```
{station} cycle time has drifted {delta} {direction} its normal range since {time}.
Currently {current}, normally {baseline}.
```

**Defect risk row**
```
{vin}   at {station}   {gate} risk {p} ({lo} to {hi})   {n} stations, {m} min remaining
Top factors: {f1}; {f2}; {f3}
```
Factors are written in plant language:
```
Top factors: torque at S31 ran 2.3 sigma low for the last 14 units;
part lot B-4471; dwell at S28 was 22 s above normal
```

**Dark station panel**
```
{station} has no machine data.
Cycle time bounded to {lo} to {hi} s from the stations either side.
Cannot separate blocked from starved from slow work.
```

**Sensor value card**
```
{station}: {what_is_unknown}
A {sensor} would resolve {what_it_resolves}.
Confidence {current} to about {projected}. {cost}, {install_effort}.
Next window: {window}.
```

**Empty action list (the most common state, and it must not read as an error)**
```
Nothing needs attention.
42 stations running, 4 forecasts open in shadow, last check 14:32:06.
```

**Data health warning**
```
{source} stopped sending {duration} ago.
{consequence, in plant terms}.
```
Example:
```
Paint zone source stopped sending 4 min ago.
Forecasts for S17 to S26 are paused. The rest of the line is unaffected.
```

**Predictor promotion notice**
```
Stall forecasting is now active for {station}.
It was right on {hits} of {total} forecasts here over the last {window}.
```

**Counterfactual result**
```
Do nothing        {n} units this shift ({lo} to {hi})
{intervention}    {n} units this shift ({lo} to {hi})
Difference        {delta} units ({lo} to {hi})
```

---

## 5. Error message construction

Every error answers three questions in this order, and stops.

1. **What happened**, in the user's terms, naming the specific thing.
2. **What it means for them**, in one clause.
3. **What to do**, if there is anything to do. If there is not, say the system is handling it.

No apology. No blame. No error code in the visible string (codes go in the log and in a copyable detail line). No "please".

| Situation | String |
|---|---|
| Source silent | "Paint zone source stopped sending 4 min ago. Forecasts for S17 to S26 are paused. They will resume automatically when it returns." |
| Insufficient history | "S27 has no cycle history for the LWB variant yet. Forecasts for this station start after 20 recorded cycles." |
| Counterfactual too slow | "This ran with 60 replications instead of 200 to stay under 5 seconds. The range is wider than usual." |
| Clock skew | "The final assembly source clock is 3.4 s behind the body shop source. Cycle times spanning the two may be off by that much." |
| Model in shadow | "Stall forecasting is still learning S34. It has made 7 of the 20 forecasts needed before it starts showing alerts here." |
| Export failed | "The containment list could not be written. The file may be open in another program." |
| Unresolvable station | "S35 and S36 are both unmonitored with no scan between them. Neither cycle time can be separated from the other." |

---

## 6. What to do about length

Line view is read at three metres. Constrain accordingly.

| Element | Maximum |
|---|---|
| Action card title | 40 characters |
| Action card body line | 60 characters |
| Button label | 3 words |
| Table header | 2 words |
| Chip or status label | 12 characters |
| Tooltip | 1 sentence |
| Error message | 2 sentences |

If a message does not fit, the message is too complicated, not the space too small.

---

## 7. Review checklist for any new string

- [ ] Read aloud, and it sounds like a person
- [ ] No banned word from HUMAN_DESIGN_GUIDELINES.md rule 21
- [ ] No em dash, no emoji, no exclamation mark
- [ ] Sentence case
- [ ] Uses the terminology table in Section 3
- [ ] Numbers carry units and honest precision
- [ ] Intervals shown where the estimate is an interval
- [ ] Inferred values labelled as inferred
- [ ] Fits the length limit for its element
- [ ] An error says what happened, what it means, and what to do

---

**Related:** [CONTENT_STYLE_GUIDELINES.md](CONTENT_STYLE_GUIDELINES.md) · [HUMAN_DESIGN_GUIDELINES.md](HUMAN_DESIGN_GUIDELINES.md) · [../quality/ERROR_HANDLING.md](../quality/ERROR_HANDLING.md)
