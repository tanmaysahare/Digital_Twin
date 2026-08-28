# 06: Unit drawer, with process signature timeline

```
                                    +--------------------------------------------+
                                    |  3C4PDCBG7JT   V-STD                  [x]  |
                                    +--------------------------------------------+
                                    |  At S28, entered line 08:47                |
                                    |                                            |
                                    |  Risk at remaining gates                   |
                                    |  G3 final QC   0.68  |----|--------|       |
                                    |                      0.54 0.68   0.79      |
                                    |                14 stations, about 14 min   |
                                    |                                            |
                                    |  Top factors                               |
                                    |  1  part lot B-4471                    [v] |
                                    |     11 of 47 units from this lot have      |
                                    |     failed G3 in the last 6 h, against a   |
                                    |     1.8% base rate.                        |
                                    |  2  torque at S12 ran 2.1 sigma low    [>] |
                                    |  3  dwell at S23 was 19 s above normal [>] |
                                    |                                            |
                                    |  Process signature                         |
                                    |                                            |
                                    |  S01  dwell 61 s  cycle 58.2  running      |
                                    |  S02  dwell 60 s  cycle 57.9  running      |
                                    |  ...                                       |
                                    |  S12  dwell 63 s  cycle 59.1  running  !   |
                                    |       torque peak 41.2 Nm, normal          |
                                    |       43.8 to 46.1 Nm                      |
                                    |  ...                                       |
                                    |  S16  dwell 60 s  cycle 58.4  running      |
                                    |  ====  G1 body-in-white   passed  ====     |
                                    |  S17  dwell 59 s  cycle 58.0  running      |
                                    |  ...                                       |
                                    |  S23  dwell 81 s  cycle 58.7  blocked  !   |
                                    |       held 22 s waiting on B6              |
                                    |  ...                                       |
                                    |  S26  dwell 60 s  cycle 58.9  running      |
                                    |  ====  G2 paint       passed       ====    |
                                    |  S27  dwell 60 s  cycle 58.1  running      |
                                    |  S28  in process, 34 s elapsed             |
                                    |                                            |
                                    |  ---- ahead ----                           |
                                    |  S29 to S32   monitored                    |
                                    |  S33 to S37   ///// no machine data /////  |
                                    |  S38 to S41   monitored                    |
                                    |  S42          ///// no machine data /////  |
                                    |  ====  G3 final QC    ahead        ====    |
                                    |                                            |
                                    |  Parts consumed                            |
                                    |  B-4471  front subframe bolt set           |
                                    |          [ 47 other units on this lot ]    |
                                    |  A-2210  wiring harness                    |
                                    |  C-0918  seal kit                          |
                                    +--------------------------------------------+
```

## Annotations

**The signature timeline is the spine.** It is the visual answer to the problem
statement's point that a defect introduced early may not surface until much later. The
`!` markers show where a value fell outside that station's own normal range for this
variant. Dark stations appear as hatched segments so the user can see exactly where the
record has gaps.

**The "ahead" section matters.** It shows which of the remaining stations can be
observed and which cannot, so the supervisor knows how much more the twin will learn
before G3.

**Part lot links to the population.** One tap from a suspect lot to every other unit
carrying it. This is the same query that produces the containment list after a
confirmed failure.
