# 02: Line view, the calm state

The most common screen in the product, and the hardest to get right. Nothing is wrong.
This must read as a complete, well-set instrument, not as an empty state.

```
+==========================================================================================+
| DigitalTwin.ai  Line 2 v |  Line  Plan  Program  |  Simulated data  11:04:38 · 8 s ago   |
+==========================================================================================+
|                                                                                          |
|  Next 120 min                                                                            |
|  +--------------------------------------------------------------------------------+     |
|  |                          (no forecast markers)                                   |     |
|  |  +0    +15    +30    +45    +60    +75    +90   +105   +120                     |     |
|  +--------------------------------------------------------------------------------+     |
|  |S01|S02|S03|S04|...                                        ...|S40|S41|S42|      |     |
|  | | | | | | | | |          all segments greyscale               | | | | |///|      |     |
|  |58.9|58.4|58.0|57.5|                                        |58.4|57.9|54-71|    |     |
|  +--------------------------------------------------------------------------------+     |
|     [B1 4/6]  [B2 5/8]  [B3 4/8]  [B4 3/6]  [B5 6/12] [B6 3/6] [B7 5/8] [B8 4/8]         |
|  +--------------------------------------------------------------------------------+     |
|  |--- Body construction S01-S16 ---|G1|-- Paint S17-S26 --|G2|-- Final assembly --|G3|   |
|  +--------------------------------------------------------------------------------+     |
|                                                                                          |
+---------------------------------------------------+--------------------------------------+
|  B. ACTIONS                                       |  C. AT-RISK UNITS          0 units    |
|                                                   |                                       |
|  Nothing needs attention                          |  No units above the G2 or G3          |
|  42 stations running · 4 forecasts in shadow      |  risk threshold.                      |
|  last check 11:04:38                              |                                       |
|                                                   |  Highest current risk 0.11            |
|                                                   |  (3C4PDCBJ2JT at S31, G3).            |
|                                                   |                                       |
+------------------------+--------------------------+--------------+----------------------+
|  D. OUTPUT AND LOSS    |  E. PREDICTOR RECORD                    |  F. DATA HEALTH       |
|                        |                                         |                       |
|  418 of 460 units      |  Stall forecaster    active   8 of 11    |  Sources  4 of 4 live |
|  pace on target        |                      27 min median lead  |  Last event 11:04:36  |
|  [==========-----]     |  Defect risk G3      active  22 of 31    |  Clock skew max 0.6 s |
|                        |                       6 stations lead    |  Coverage 36 of 42    |
|  Lost 62 min           |  Defect risk G2      shadow   7 of 20    |    6 dark by design   |
|  [blk 21][str 14]      |  Drift detector      active  14 of 16    |                       |
|  [dwn 9][chg 18]       |                                          |                       |
+------------------------+------------------------------------------+----------------------+
```

## Why this screen matters

Most shifts look like this. If it reads as empty, unfinished or broken, a supervisor
concludes the tool is not working and stops looking at it. Three rules make it read as
deliberate:

1. **The screen is full of information.** 42 live cycle times, 8 buffer levels, output
   against pace, loss accounting, predictor record, source health. Nothing is blank.
2. **The action region states a positive fact**, in plain words, with supporting detail.
   It does not say "no data" and it carries no illustration.
3. **The at-risk region reports the highest current risk**, so the absence of a flagged
   unit is a measurement rather than a silence.

There is no empty-state illustration, no "you are all caught up" message, no celebratory
treatment. See ../../human-design/HUMAN_DESIGN_GUIDELINES.md Section 7.
