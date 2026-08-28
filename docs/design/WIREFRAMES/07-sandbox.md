# 07: Counterfactual sandbox

An overlay covering the lower two thirds of the viewport. The line strip stays visible
above it, because the line does not stop for a dialog.

```
+==========================================================================================+
| DigitalTwin.ai  Line 2 v |  Line  Plan  Program  |  Simulated data  09:31:02 · 6 s ago   |
+==========================================================================================+
|  [ line strip remains visible here ]                                                     |
+==========================================================================================+
|  Test a fix                                                                         [x]  |
+------------------------------------------+-----------------------------------------------+
|  Intervention                            |  Result                                       |
|                                          |                                               |
|  Type    [ Add an operator          v ]  |                    Do nothing    Add a floater |
|  Station [ S20                      v ]  |  Units this shift        441            450    |
|  From    [ now                      v ]  |  Range               432-449        440-459    |
|                                          |  Difference                             +9     |
|  [ Run ]      [ Add another option ]     |                                    (+4 to +13) |
|                                          |                                               |
|  Options compared                        |  Stall probability by station                 |
|  1  Add a floater at S20      +9 units   |                                               |
|  2  Slow takt 4%              +3 units   |  S20 [====      ] 0.31   was 0.68              |
|  3  Do nothing                 baseline  |  S22 [===       ] 0.24   was 0.71              |
|                                          |  S31 [==        ] 0.18   was 0.19              |
|                                          |  others below 0.10                            |
|                                          |                                               |
+------------------------------------------+-----------------------------------------------+
|  Ran 200 replications in 3.1 s from the 09:31:02 state                                   |
|  [ Save as decision ]                                                                     |
+==========================================================================================+
```

## Degraded variant, when the latency budget is exceeded

```
+------------------------------------------+-----------------------------------------------+
|  ...                                     |  Units this shift        441            450    |
|                                          |  Range               428-453        434-465    |
+------------------------------------------+-----------------------------------------------+
|  Ran 60 replications in 4.8 s from the 09:31:02 state.                                   |
|  Reduced from 200 to stay under 5 seconds. The ranges are wider than usual.              |
|  [ Save as decision ]                                                                     |
+==========================================================================================+
```

## Annotations

**The comparison is always against doing nothing.** A number without a baseline is not a
decision aid.

**Every result is a range.** The `IntervalBar` component appears here as it does
everywhere an estimate is an interval.

**The footer states replication count, runtime and the source state timestamp.** When
the run was shortened, it says so in the same place rather than hiding it, and the
widened ranges are visible.

**Nothing is applied.** "Save as decision" records the choice so that its effect joins
the ledger later. It changes nothing on the line.
