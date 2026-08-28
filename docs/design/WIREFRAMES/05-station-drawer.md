# 05: Station drawer

480px from the right, over Line view, leaving the line strip visible.
Two variants shown: an instrumented station that is drifting, and a dark station.

## Variant A: S20, Tier A, drifting

```
                                    +--------------------------------------------+
                                    |  S20   Body construction   Tier A     [x]  |
                                    +--------------------------------------------+
                                    |  Drifting for 15 min                       |
                                    |                                            |
                                    |  Cycle time                                |
                                    |  Now      62.1 s                           |
                                    |  Normal   57.2 to 59.4 s  (V-STD, last 200)|
                                    |                                            |
                                    |  Last 200 cycles                           |
                                    |  64 |                            .-'       |
                                    |  62 |                       _.-''          |
                                    |  60 |                  _.-''               |
                                    |  58 |~~~~~~~~~~~~~~~-''                    |
                                    |  56 |                                      |
                                    |     +----------------------------------    |
                                    |      07:00      08:00     09:00   09:29    |
                                    |                            ^ drift onset   |
                                    |                              09:14         |
                                    |                                            |
                                    |  What the twin knows                       |
                                    |  Cycle start and stop from the PLC,        |
                                    |  torque curve, motor current, part scan.   |
                                    |  Everything on this panel is measured.     |
                                    |                                            |
                                    |  Buffers                                   |
                                    |  Upstream   B4  2 of 6   falling           |
                                    |  Downstream B5 11 of 12  rising            |
                                    |                                            |
                                    |  Predictor record here                     |
                                    |  Stall forecaster   active   8 of 11 right |
                                    |                     27 min median lead     |
                                    |  Drift detector     active  14 of 16 right |
                                    |                                            |
                                    |  Recent events                             |
                                    |  09:14  drift onset detected               |
                                    |  06:12  changeover, V-SPT to V-STD         |
                                    |  W31    fixture service                    |
                                    +--------------------------------------------+
```

## Variant B: S34, Tier C, no machine data

```
                                    +--------------------------------------------+
                                    |  S34   Final assembly   Tier C        [x]  |
                                    +--------------------------------------------+
                                    |  No machine data                           |
                                    |                                            |
                                    |  Cycle time                                |
                                    |  |------------------|                      |
                                    |  54                71 s                    |
                                    |  Inferred from S32 departure and S38       |
                                    |  arrival, less 4.2 s nominal transport.    |
                                    |                                            |
                                    |  Last 200 cycles (interval band)           |
                                    |  75 |::::::::::::::::::::::::::::::        |
                                    |  65 |::::::::::::::::::::::::::::::        |
                                    |  55 |::::::::::::::::::::::::::::::        |
                                    |  45 |                                      |
                                    |     +----------------------------------    |
                                    |      07:00      08:00     09:00   09:29    |
                                    |                                            |
                                    |  What the twin cannot tell you             |
                                    |  Blocked, starved and slow work cannot be  |
                                    |  separated here. The bound widens when     |
                                    |  S35 to S37 are also busy, because five    |
                                    |  unmonitored stations sit between the two  |
                                    |  scan points.                              |
                                    |                                            |
                                    |  +--------------------------------------+  |
                                    |  |  Sensor value                        |  |
                                    |  |                                      |  |
                                    |  |  Unknown today                       |  |
                                    |  |  Cycle time bounded to 54 to 71 s.   |  |
                                    |  |  Cause of stoppage not separable.    |  |
                                    |  |                                      |  |
                                    |  |  Proposal                            |  |
                                    |  |  Clamp-on current transducer on the  |  |
                                    |  |  main drive.                         |  |
                                    |  |                                      |  |
                                    |  |  Would resolve                       |  |
                                    |  |  Cycle time to +/- 2 s.              |  |
                                    |  |  Blocking cause to about 0.85        |  |
                                    |  |  confidence, from 0.42 today.        |  |
                                    |  |                                      |  |
                                    |  |  $40 hardware, 0.5 h install,        |  |
                                    |  |  no production impact.               |  |
                                    |  |  Next window: December shutdown.     |  |
                                    |  |                                      |  |
                                    |  |  S34 sat on the critical path in 31% |  |
                                    |  |  of forecast stalls this month.      |  |
                                    |  |  Modelled value $8.2k/yr             |  |
                                    |  |  (range $3.1k to $14.8k).            |  |
                                    |  +--------------------------------------+  |
                                    |                                            |
                                    |  Recent events                             |
                                    |  09:22  andon, operator call, 3 min        |
                                    |  08:41  manual check passed                |
                                    +--------------------------------------------+
```

## Annotations

The two variants use identical structure. The difference is entirely in what can be
said. Variant B never fabricates a number, states plainly what cannot be separated, and
converts the gap into a costed proposal. That contrast is the product's argument about
sensor coverage, expressed in one screen.
