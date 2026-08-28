# 04: Program view (Meera, operations director)

Narrower measure, more prose, designed to be projected and argued with.

```
+==========================================================================================+
| DigitalTwin.ai  Line 2 v |  Line  Plan  Program  |  Simulated data  11:04:38 · 8 s ago   |
+==========================================================================================+
|                                                                                          |
|  Site readiness                                                                          |
|  Scored from what each site actually emits, not from a questionnaire.                    |
|                                                                                          |
|  Site           Unit ID  Cycle cov  Dark  Historian  Inspection  Clock   Readiness       |
|  Pune L2          yes       94%     14%     yes         yes      good    READY           |
|  Pune L1          yes       91%     18%     yes         yes      good    READY           |
|  Chennai L1       yes       88%     22%     yes         yes      fair    READY           |
|  Chennai L2       yes       61%     39%     yes         yes      fair    READY WITH      |
|                                                                       INSTRUMENTATION    |
|  Sanand L1        yes       58%     42%     no          yes      fair    READY WITH      |
|                                                                       INSTRUMENTATION    |
|  Bidadi L3        no        44%     51%     no          partial  poor    NOT READY       |
|    Missing: no unit-level identifier at station level. Per-unit defect prediction         |
|    is not possible until a scan point exists at S01. Everything else would work.          |
|                                                                                          |
+------------------------------------------------------------------------------------------+
|                                                                                          |
|  Business case                                                                           |
|                                                                                          |
|  Assumptions                              |  Modelled result                             |
|                                           |                                              |
|  Unplanned stop min per line per month     |  Annual benefit per line                     |
|  [ 1,240 ]  site-measured, Pune L2, W28-34 |    $412k  (range $180k to $690k)             |
|                                           |                                              |
|  Value of a recovered unit                 |  Implementation cost per line                |
|  [ $1,850 ]  site contribution margin.     |    $95k first line, $38k thereafter          |
|  Note: published per-hour downtime figures |                                              |
|  are industry-specific (S-04) and are not  |  Instrumentation cost                        |
|  used as a default here.                   |    $310 (Pune L2 sensor queue)               |
|                                           |                                              |
|  Forecast precision                        |  Payback                                     |
|  [ 0.73 ]  measured from the ledger,       |    3.1 months  (range 1.8 to 7.4)            |
|  not assumed                               |                                              |
|                                           |  Most sensitive to                           |
|  Share of forecasts acted on               |    1. share of forecasts acted on            |
|  [ 0.55 ]  assumption, not measured        |    2. value of a recovered unit              |
|                                           |    3. forecast precision                     |
|  Defect escape rate                        |                                              |
|  [ 1.8% ]  site-measured                   |  Changing "share acted on" from 0.55 to      |
|                                           |  0.30 moves payback to 5.7 months.           |
|  Repair yard cost multiplier               |                                              |
|  [ 8x ]  assumption. The 1-10-100 framing  |                                              |
|  (S-31) is a rule of thumb, not a constant |                                              |
|                                                                                          |
+------------------------------------------------------------------------------------------+
|                                                                                          |
|  Modelled against realised, Pune L2 pilot, weeks 28 to 34                                |
|                                                                                          |
|                          Modelled     Realised    Gap                                    |
|  Unplanned stop minutes    -11%          -7%      -4 pts                                 |
|  Units to repair yard      -18%         -21%      +3 pts                                 |
|  Forecast precision        0.70          0.73     +0.03                                  |
|                                                                                          |
|  The stop-minute shortfall traces to 4 of 11 forecasts at S20 where no action was         |
|  taken before the window elapsed. The prediction was correct; the response was not        |
|  available. Evidence in the ledger.                                                      |
|                                                                                          |
+------------------------------------------------------------------------------------------+
```

## Annotations

**Every assumption carries its source.** An assumption without a source is a number that
cannot be defended in a capital review, which is the only room this screen appears in.

**The sensitivity list is mandatory.** Meera's job is to interrogate the model. A model
that does not expose what it is sensitive to cannot be interrogated.

**Modelled against realised shows a shortfall and explains it honestly.** This region
must look correct when the news is bad. That is the design requirement.
