# 03: Plan view (Rakesh, plant manager)

Scrollable, dense, prints to A4 landscape.

```
+==========================================================================================+
| DigitalTwin.ai  Line 2 v |  Line  Plan  Program  |  Simulated data  11:04:38 · 8 s ago   |
+==========================================================================================+
| Range [Last 4 weeks v]   Shift [All v]   Variant [All v]        [Export]  [Print]        |
+==========================================================================================+
|                                                                                          |
|  Constraint migration                                                                    |
|              W31    W32    W33    W34                                                    |
|  S20         12%    31%    44%    51%   <- current constraint                            |
|  S31         38%    29%    18%    14%                                                    |
|  S22          9%    14%    16%    18%                                                    |
|  S07         21%    11%     8%     6%                                                    |
|  S34          8%     7%     9%     8%   <- no machine data, inferred                     |
|  other       12%     8%     5%     3%                                                    |
|                                                                                          |
|  The constraint moved from S31 to S20 over four weeks.                                   |
|                                                                                          |
+------------------------------------------------------------------------------------------+
|                                                                                          |
|  Where the time went, last 4 weeks                                                       |
|                                                                                          |
|  Blocked      [==============================]  1,204 min   34%                          |
|  Starved      [===================]              778 min   22%                           |
|  Down         [================]                 672 min   19%                           |
|  Changeover   [=============]                    531 min   15%                           |
|  Quality      [========]                         354 min   10%                           |
|                                                                                          |
|  Sum of causes 3,539 min. Shift gap from plant reporting 3,572 min.                      |
|  Unexplained 33 min (0.9%).                                                              |
|                                                                                          |
+------------------------------------------------------------------------------------------+
|                                                                                          |
|  Recommendations                                                                         |
|  Change                        Modelled effect        Assumptions                         |
|  Raise B7 from 6 to 9          +14 units/day          current mix, current S20 cycle      |
|                                (+8 to +19)            distribution, 2 shifts   [Test]     |
|  Add a floater covering        +9 units/shift         floater available 60% of shift      |
|  S19 to S21                    (+4 to +13)                                     [Test]     |
|  Move S20 fixture service      -22 min unplanned      based on 3 observed drift           |
|  to a 2-week interval          stop per month         events since W31         [Test]     |
|                                                                                          |
+------------------------------------------------------------------------------------------+
|                                                                                          |
|  Sensor investment queue                                          [Export for capital]   |
|  Station  Unknown today          Proposal        Gain      Cost  Effort  Window   Value  |
|  S34      cycle time 54-71 s,    clamp-on         0.42     $40   0.5 h   Dec      $8.2k  |
|           cause not separable    current sensor   to 0.85                          /yr    |
|  S36      cycle time 51-68 s     clamp-on         0.39     $40   0.5 h   Dec      $5.1k  |
|                                  current sensor   to 0.83                          /yr    |
|  S42      no unit scan at exit   barcode scan     0.51     $230  2 h     Dec      $3.4k  |
|                                  point            to 0.91                          /yr    |
|                                                                                          |
|  Three retrofits, $310 total, all installable in the December window.                    |
|  Modelled value carries the same uncertainty as the forecasts behind it.                 |
|                                                                                          |
+------------------------------------------------------------------------------------------+
|                                                                                          |
|  Predictor record                                             [sort by precision v]      |
|  Predictor        Station  State    Made  Prec  Recall  Lead    False/shift  Changed     |
|  Stall forecaster S20      active     11  0.73   0.67   27 min      0.4      W32         |
|  Stall forecaster S22      active      9  0.78   0.60   24 min      0.3      W32         |
|  Stall forecaster S31      shadow      6  ----   ----   ----        ----     W34 (down)  |
|    Withdrawn W34: precision fell to 0.42 over the previous two weeks.                    |
|  Stall forecaster S34      shadow   7/20  ----   ----   ----        ----     W33         |
|  Defect risk     G3        active     31  0.71   0.58    6 st       0.6      W32         |
|  Defect risk     G2        shadow   7/20  ----   ----   ----        ----     W34         |
|  Drift detector  all       active     16  0.88   0.81   12 min      0.2      W31         |
|                                                                                          |
+------------------------------------------------------------------------------------------+
```

## Annotations

**Constraint migration.** A greyscale density heatmap with direct numeric labels, so no
colour legend is needed. The current constraint is marked in text, not in colour.

**Loss Pareto.** The reconciliation line is mandatory. If the twin's accounting does not
tie to the plant's own shift reporting, the twin says so rather than presenting a second
set of books.

**Recommendations.** Assumptions are inline, in small type. Each row opens the sandbox
against a chosen historical state.

**Sensor investment queue.** The output of the twin's own blind spots. Exportable as a
capital request.

**Predictor record.** Deliberately capable of looking bad. The withdrawn row for S31 is
shown with its reason, because a system that quietly hides its failures is a system
nobody checks twice.
