# 01: Line view, desk (1440x900), active forecast

Scenario SC-01 at 09:29. S20 has been drifting since 09:14. The forecast was raised
at 09:29 for a stop at S22 between 09:52 and 10:04.

```
+==========================================================================================+
| DigitalTwin.ai  Line 2 v |  Line  Plan  Program  |  Simulated data  09:29:14 · 12 s ago  |
+==========================================================================================+
|                                                                                          |
|  A. LINE STRIP                                                                           |
|  Next 120 min                                                                            |
|  +--------------------------------------------------------------------------------+     |
|  |            |----------|  S22 stop  p 0.71  09:52 to 10:04                       |     |
|  |  +0    +15    +30    +45    +60    +75    +90   +105   +120                     |     |
|  +--------------------------------------------------------------------------------+     |
|  |S01|S02|S03|...|S18|S19|[S20]|S21|S22|S23|...|S33|S34|...|S41|S42|                     |
|  | | | | | | |   | | | | | \\\ | | | | | | |   |///|///|   | | |///|                     |
|  |58.9|58.4|...  |58.4|59.1|62.1|57.4|58.5|   |54-71|54-71|  |57.9|54-71|                |
|  +--------------------------------------------------------------------------------+     |
|     [B1 3/6]     [B4 2/6]   [B5 11/12]  [B6 1/6]        [B8 6/8]      [B9 5/6]           |
|  +--------------------------------------------------------------------------------+     |
|  |--- Body construction S01-S16 ---|G1|-- Paint S17-S26 --|G2|-- Final assembly --|G3|   |
|  +--------------------------------------------------------------------------------+     |
|                                                                                          |
+---------------------------------------------------+--------------------------------------+
|  B. ACTIONS                                       |  C. AT-RISK UNITS          6 units    |
|                                                   |                                       |
|  ||  Line stop likely at S22          LEAD TIME   |  VIN          At  Gate Risk    Left   |
|  ||  09:52 to 10:04   probability 0.71            |  3C4PDCBG7JT S28  G3  0.68  14st 14m  |
|  ||  Cause: S20 cycle time drifted       27       |    lot B-4471                         |
|  ||  +4.1 s since 09:14                 min       |  3C4PDCBG9JT S26  G3  0.66  16st 16m  |
|  ||  At risk 11 units                             |    lot B-4471                         |
|  ||                                               |  3C4PDCBH1JT S24  G3  0.64  18st 18m  |
|  ||  [Show evidence] [Test a fix] [We did this]   |    lot B-4471                         |
|                                                   |  3C4PDCBH3JT S21  G3  0.61  21st 21m  |
|  ||  S31 cycle variance up 3x since 09:05         |    lot B-4471                         |
|  ||  Shift change at 09:00. No stop forecast yet. |  3C4PDCBH5JT S19  G3  0.59  23st 23m  |
|  ||  [Show evidence] [Test a fix]                 |    lot B-4471                         |
|                                                   |  3C4PDCBH7JT S17  G3  0.57  25st 25m  |
|                                                   |    lot B-4471                         |
+------------------------+--------------------------+--------------+----------------------+
|  D. OUTPUT AND LOSS    |  E. PREDICTOR RECORD                    |  F. DATA HEALTH       |
|                        |                                         |                       |
|  312 of 460 units      |  Stall forecaster    active   8 of 11    |  Sources  4 of 4 live |
|  pace 4 units behind   |                      27 min median lead  |  Last event 09:29:12  |
|  [======---------]     |  Defect risk G3      active  22 of 31    |  Clock skew max 0.8 s |
|                        |                       6 stations lead    |  Coverage 36 of 42    |
|  Lost 148 min          |  Defect risk G2      shadow   4 of 20    |    6 dark by design   |
|  [blk 51][str 34]      |  Drift detector      active  14 of 16    |                       |
|  [dwn 28][chg 22][q13] |                                          |                       |
+------------------------+------------------------------------------+----------------------+
```

## Annotations

**A. Line strip.** `\\\` marks the drift stripe on S20. `///` marks the cross-hatch on
Tier C stations (S33 to S37, S42). The vertical bar in each segment is the `RangePlot`
showing the current cycle against that station's normal range. Dark stations show an
interval (`54-71`), never a point.

**B. Actions.** `||` is the 2px `--state-forecast` left border. The card has no fill.
`27 min` is the only `--text-display` element on the screen. Two concurrent problems are
two rows, ranked by expected unit loss, never merged into one story.

**C. At-risk units.** A table, not cards. Sorted by minutes remaining ascending. The top
factor is shown inline under each VIN; the other two are in the drawer. Eight rows
maximum with a count of the rest.

**D. Output and loss.** Two elements with no border between them. The loss bar segments
carry state colours because the segments are states.

**E. Predictor record.** A predictor in shadow shows progress toward the gate, not a hit
rate, so the floor is never invited to trust something unpromoted.

**F. Data health.** Four quiet lines in the normal case.

## What is not here

No sidebar. No logo block. No hero metric row. No card grid. No icons except the six in
DESIGN_SYSTEM.md Section 8. No colour anywhere except S20's drift stripe, the forecast
marker, and the loss bar segments.
