# 08: Floor tablet and wall display

## Floor tablet, 1280x800, gloves

Regions B and C stack. Regions D, E and F become a horizontal scrolling row. All touch
targets at 44px minimum with 8px separation.

```
+==============================================================+
| DigitalTwin.ai  Line 2 | Line Plan Program | 09:29:14 · 12 s |
+==============================================================+
|  Next 120 min          |------| S22 09:52 to 10:04           |
|  |S01|S02|...|S20|S21|S22|...        (scrolls horizontally)  |
|  | | | | |  |\\\| | | |RED|                                  |
|  |58.9|58.4| |62.1|57.4|stop|                                |
|  [B4 2/6]  [B5 11/12]                                        |
+==============================================================+
|  ||  Line stop likely at S22             LEAD TIME           |
|  ||  09:52 to 10:04   probability 0.71                       |
|  ||  Cause: S20 drifted +4.1 s since 09:14      27           |
|  ||  At risk 11 units                          min           |
|  ||                                                          |
|  ||  [ Show evidence ]  [ Test a fix ]  [ We did this ]      |
|  ||    (44px tall, 8px apart)                                |
+==============================================================+
|  At-risk units                                     6 units   |
|  3C4PDCBG7JT  S28  G3  0.68  14 st 14 min  lot B-4471       |
|  3C4PDCBG9JT  S26  G3  0.66  16 st 16 min  lot B-4471       |
|  3C4PDCBH1JT  S24  G3  0.64  18 st 18 min  lot B-4471       |
|    (36px rows, tappable)                                     |
+==============================================================+
|  < [Output 312/460]  [Predictors]  [Data health] >           |
|      (horizontal scroll)                                     |
+==============================================================+
```

**Tablet-specific rules**
- The drawer becomes full width with a back action rather than a side panel.
- The sandbox becomes full screen.
- No hover-only information anywhere.
- Line strip: each segment is about 29px wide, below the 44px floor. The tap area
  extends to the full 90px height, and a tap within 8px of a boundary opens a two-item
  list naming both stations rather than guessing. Documented in ../ACCESSIBILITY.md
  Section 4.

## Wall display, 1920x1080 at 3 m

Root font size 26px. Every ratio identical. Regions D, E and F collapse to headlines.

```
+==========================================================================================+
|  DigitalTwin.ai   Line 2                                    09:29:14 · 12 s ago          |
+==========================================================================================+
|                                                                                          |
|   Next 120 min          |----------|  S22 stop  p 0.71  09:52 to 10:04                   |
|                                                                                          |
|   |S01|S02|S03|...      |S20|S21|S22|      ...|S41|S42|                                  |
|   |   |   |   |         |\\\|   |RED|         |   |///|      (280px tall)                |
|   |58.9|58.4|58.0|      |62.1|57.4|stop|      |57.9|54-71|                               |
|                                                                                          |
|   [B1 3/6]        [B4 2/6]  [B5 11/12]  [B6 1/6]        [B8 6/8]                         |
|   --- Body S01-S16 ---|G1|-- Paint S17-S26 --|G2|-- Final assembly S27-S42 --|G3|        |
|                                                                                          |
+==========================================================================================+
|                                                                                          |
|   ||  Line stop likely at S22                                                            |
|   ||  09:52 to 10:04   probability 0.71                     LEAD TIME                    |
|   ||  Cause: S20 cycle time drifted +4.1 s since 09:14                                   |
|   ||  At risk 11 units                                          27                       |
|   ||                                                           min                       |
|   ||                                                        (64px)                       |
|                                                                                          |
+==========================================================================================+
|   312 of 460 · 4 behind    |  Forecaster 8 of 11  |  4 of 4 sources live                 |
+==========================================================================================+
```

**Wall-specific rules**
- Nothing below 18px effective. Automated check at the 1920 breakpoint.
- Hover states suppressed.
- At-risk table shows five rows, not eight.
- The lead time at 64px is the one thing readable from the far end of the line.
- One-pixel layout shift over a four-hour cycle to prevent burn-in, disabled under
  `prefers-reduced-motion`.
