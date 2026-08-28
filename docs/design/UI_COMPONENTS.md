# UI_COMPONENTS.md

**Purpose:** the component inventory. Every screen is built from these and nothing else. If a screen needs something not on this list, add it here first with a justification.
**Implementation:** React function components in `web/src/components/`, TypeScript, no component library installed. Styling with Tailwind mapped to the tokens in DESIGN_SYSTEM.md.
**Why no component library:** MUI, Chakra, shadcn and the rest carry a visual opinion (radius, shadow, motion, colour) that conflicts with ../human-design/HUMAN_DESIGN_GUIDELINES.md. Overriding a library into this system costs more than writing 30 small components.
**Last updated:** 2026-08-28

---

## Component inventory

| # | Component | Used in | Priority |
|---|---|---|---|
| 1 | `AppHeader` | Global | P0 |
| 2 | `ViewTabs` | Global | P0 |
| 3 | `DataAge` | Global | P0 |
| 4 | `LineStrip` | Line view | P0 |
| 5 | `StationSegment` | LineStrip | P0 |
| 6 | `BufferBlock` | LineStrip | P0 |
| 7 | `ForecastTrack` | LineStrip | P0 |
| 8 | `RangePlot` | StationSegment, drawers | P0 |
| 9 | `IntervalBar` | Everywhere | P0 |
| 10 | `ActionCard` | Line view | P0 |
| 11 | `EvidencePanel` | ActionCard | P0 |
| 12 | `DataTable` | All views | P0 |
| 13 | `MetricLine` | All views | P0 |
| 14 | `StateChip` | Tables, drawers | P0 |
| 15 | `ProvenanceMark` | Everywhere a value appears | P0 |
| 16 | `Drawer` | Line view | P0 |
| 17 | `SandboxOverlay` | Line view | P0 |
| 18 | `Button` | Everywhere | P0 |
| 19 | `Select` | Sandbox, Plan view | P0 |
| 20 | `NumberField` | Sandbox, Program view | P0 |
| 21 | `TimeSeriesChart` | Drawers, Plan view | P0 |
| 22 | `StackedBar` | Line view, Plan view | P0 |
| 23 | `Heatmap` | Plan view | P1 |
| 24 | `ScorecardRow` | Line view, Plan view | P0 |
| 25 | `SensorValueCard` | Drawer, Plan view | P0 |
| 26 | `SignatureTimeline` | Unit drawer | P0 |
| 27 | `HealthPanel` | Line view | P0 |
| 28 | `Notice` | Everywhere | P0 |
| 29 | `AssumptionField` | Program view | P1 |
| 30 | `ReliabilityChart` | Evidence pack, Plan view | P1 |
| 31 | `SmallMultiples` | Plan view | P2 |
| 32 | `PrintFrame` | Plan view | P1 |

Thirty-two components. If the count grows past forty, something has gone wrong.

---

## 1. AppHeader
48px, `--paper`, bottom `--border`. Left: product name and line select. Centre-left: `ViewTabs`. Right: simulated-data marker (fixed text, not dismissible), `DataAge`, and in the prototype only, the persona switcher.

## 2. ViewTabs
Three text tabs, sentence case, `--text-label`. Active tab has a 2px `--accent` bottom border. No icons, no pills, no background fill. Keyboard: `1`, `2`, `3`, and arrow keys when focused.

## 3. DataAge
`Props: { timestamp: Date, staleAfterMs: number }`
Renders `14:32:06 · 38 s ago` in mono `--text-small`. Under 60 s shows seconds, under 60 min shows minutes, beyond that shows the absolute time only. When age exceeds `staleAfterMs`, the whole element takes `--state-drift` text and a hatch underline. Updates once per second, and this is the only element in the product that updates on a timer.

## 4. LineStrip
`Props: { stations: StationState[], buffers: BufferState[], forecasts: Forecast[], zones: Zone[], selectedId?: string }`
Full width, 180px. Composes `ForecastTrack`, a row of `StationSegment`, a row of `BufferBlock`, and the zone rule with gate markers. Roving tabindex across segments so the whole strip is one tab stop with arrow-key navigation inside.

Below 1024px the strip scrolls horizontally, and any station in an abnormal state is scrolled into view automatically on state change.

## 5. StationSegment
`Props: { id, tier, state, cycleTime: Value | Interval, normalRange: [number, number], provenance, selected }`
Fixed height 90px, width `1fr` within the strip. Contents: station ID top-left in mono micro; state fill per DESIGN_SYSTEM.md Section 1.3; a vertical `RangePlot` showing current cycle against normal range; the cycle value at the bottom, as a number or an interval.

Tier C segments carry a 45-degree cross-hatch at 12 percent opacity in `--state-dark` and always show an interval, never a point.

State transitions animate the fill over `--motion-value` and nothing else. No pulse, no glow, no border animation.

## 6. BufferBlock
`Props: { id, occupancy, capacity, trend }`
24px wide, 30px tall, `--paper-sunk` background with a fill from the bottom proportional to occupancy. A 1px trend mark on the right edge indicating rising, falling or steady over the last five minutes. Label below in mono micro.

## 7. ForecastTrack
`Props: { forecasts: Forecast[], horizonMinutes: number }`
A 40px band with a time axis from now to the horizon, ticks every 15 minutes. Each forecast renders as an `IntervalBar` in `--state-forecast` positioned at its window, labelled with the target station. Overlapping forecasts stack vertically rather than merging.

## 8. RangePlot
`Props: { value: number | Interval, range: [number, number], orientation }`
The small analogue indicator that appears inside every station segment. A track representing the normal range, a mark at the current value, and, when the value is an interval, a bar spanning it. Values outside the range extend past the track end and are clipped with a visible overflow mark rather than being rescaled.

This component exists because a bare number does not tell you whether 61.2 s is normal for that station, and a supervisor should not have to remember 42 baselines.

## 9. IntervalBar
`Props: { lo, hi, point?, unit, orientation }`
The product's most-used component. A rule with marked endpoints, an optional tick at a point estimate, and the numbers alongside in mono. Used for dark-station cycle times, forecast windows, defect probabilities, counterfactual outcomes and confidence bands.

Never renders a midpoint alone. Never renders as a gradient or a fade.

## 10. ActionCard
`Props: { action: RankedAction, onEvidence, onTestFix, onDidThis }`
2px `--state-forecast` left border, no fill, `--paper-raised` background, 2px radius. Title, window and probability, cause line, at-risk units, and the lead time as the one `--text-display` element on the screen. Three text buttons.

Renders the empty variant when there are no actions, with the two-line calm state from ../human-design/UX_WRITING_GUIDELINES.md Section 4. The empty variant is a first-class variant, not a fallback.

## 11. EvidencePanel
Expands inside `ActionCard` rather than opening a drawer, so the user does not lose the card. Contains a `TimeSeriesChart` of the cause station's cycle time with drift onset marked, a buffer trend chart, the active-period attribution as a small bar comparison, and one `ScorecardRow` for the predictor on that station.

## 12. DataTable
`Props: { columns, rows, sortable, density, maxRows, onRowClick }`
The workhorse. `--paper-raised`, 1px `--rule` between rows, `--paper-sunk` header row, `--text-label` headers in sentence case, numeric columns right-aligned in mono with tabular figures.

Density variants: `compact` (28px rows, Line view) and `regular` (36px rows, Plan view). Row hover is `--paper-sunk`. Selected row is `--accent-quiet` with a 2px `--accent` left border.

No zebra striping, no card wrapper, no pagination. When rows exceed `maxRows`, the table shows the top N and a line stating how many more there are.

## 13. MetricLine
`Props: { label, value, unit, interval?, provenance?, delta?, context? }`
A label, a value in mono, its unit, and optionally an interval, a signed delta with a direction arrow, and one line of context. Replaces the metric card entirely. Several MetricLines stack in a column with no borders between them, separated by `--space-2`.

This component is why there is no card grid in this product.

## 14. StateChip
`Props: { state }`
A 20px rectangular chip, 2px radius, carrying the state fill and pattern with the state name in `--text-micro`. Never a pill. Never colour alone: every state has a distinct pattern, so the chip works in greyscale print.

## 15. ProvenanceMark
`Props: { provenance: 'MEASURED' | 'DERIVED' | 'INFERRED' }`
Measured renders nothing. Derived renders a 2px left rule in `--rule-strong`. Inferred renders the value in `--ink-2` with a small hatch swatch before it. Includes a `title` and an `aria-label` so the distinction is available to assistive technology and not only visually.

Any component displaying a value from the twin must render a `ProvenanceMark`. This is enforced by making the value type a discriminated union that carries provenance, so a value cannot be rendered without it.

## 16. Drawer
`Props: { open, onClose, title, children }`
480px from the right, `--paper-raised`, `--border-strong` left edge, one permitted soft shadow. Does not cover the line strip. Escape closes. Focus is trapped inside while open and returns to the trigger on close. Enters over `--motion-panel`.

## 17. SandboxOverlay
Occupies the lower two thirds of the viewport, leaving the strip visible. Two columns: intervention form, result comparison. Footer states replication count, runtime and source state timestamp. Same shadow and focus rules as `Drawer`.

## 18. Button
Three variants, all rectangular with 2px radius, all text-only.

| Variant | Treatment |
|---|---|
| `primary` | `--ink` background, `--paper` text |
| `secondary` | `--paper` background, `--rule-strong` border, `--ink` text |
| `quiet` | No background, no border, `--accent` text with an underline on hover |

Minimum 36px height on pointer devices, 44px on touch. Label is at most three words, sentence case, no icon unless the icon is the entire control (only `Drawer` close uses this). No loading spinner: a button that triggers work becomes disabled with its label changed to the present participle ("Running").

## 19. Select
Native `<select>`, styled minimally: `--paper` background, `--rule` border, 2px radius, 36px high. No custom dropdown. A native select is keyboard-accessible, screen-reader-correct and works with gloves on a touchscreen, and a custom one is a week of work to be worse at all three.

## 20. NumberField
Numeric input in mono with tabular figures, right-aligned, unit shown as a suffix outside the field. Step controls only where a step is meaningful. Invalid values are marked with a `Notice` beneath, never with a red glow.

## 21. TimeSeriesChart
`Props: { series, band?, markers?, yZero, height }`
SVG, no charting library beyond a scale helper. Rules: step or straight-line interpolation only, never a spline. Y-axis starts at zero or carries an explicit break mark. No gridlines beyond a single baseline. Direct labels, no legend, wherever there are three or fewer series. Confidence bands in `--band`. Markers (drift onset, shift boundary, intervention) as thin vertical rules with a small label.

## 22. StackedBar
Horizontal, used for the loss split and the output-against-target bar. Segments labelled directly on the bar where they are wide enough, and in a compact row beneath where they are not. State colours only when segments are states.

## 23. Heatmap
Constraint migration in Plan view. Greyscale density, no colour ramp. Cells above a threshold carry a direct numeric label. No colour legend, because a greyscale density plus direct labels does not need one.

## 24. ScorecardRow
`Props: { predictor, station?, state, made, hits, precision, recall, medianLeadMin, falsePerShift, lastChange? }`
A single table row. In the shadow state it shows progress toward the promotion gate instead of a hit rate. In the demoted state it shows the withdrawal date and reason. Deliberately plain, and deliberately capable of looking bad.

## 25. SensorValueCard
`Props: { station, unknown, proposal, confidenceFrom, confidenceTo, cost, installEffort, window, annualValue }`
Not a card in the decorative sense: a bordered block with a heading and a definition list. Appears in the station drawer and as a row in the Plan view queue. Every number carries its provenance, and the modelled annual value carries an interval.

## 26. SignatureTimeline
`Props: { unit, stations: StationVisit[], gates }`
The unit drawer's spine. A vertical list of every station visited in order. Each row: station ID, dwell, cycle, state, and a marker where the value fell outside that station's normal range for that variant. Dark stations render hatched with an interval. Gates render as full-width rules. Scrolls within the drawer.

## 27. HealthPanel
Four `MetricLine` elements in the normal case. Degrades to include a `Notice` per affected source when something is wrong.

## 28. Notice
`Props: { tone: 'neutral' | 'attention', children }`
An inline block, `--border` left rule, `--text-small`. Used for data health warnings, predictor demotions, degraded counterfactual runs and inline errors. Never a toast, never a modal, never auto-dismissing. A notice about something that is still true stays on screen.

## 29. AssumptionField
Program view business case. A `NumberField` with a label, a source note beneath in `--text-small` `--ink-3`, and an uncertainty note. Editing recalculates the model immediately. The source note is not optional: an assumption without a stated source is a number nobody can defend.

## 30. ReliabilityChart
Calibration curve for the defect model: predicted probability against observed frequency, with the diagonal marked and bin counts shown. Appears in the evidence pack and in Plan view. Small, plain, and honest.

## 31. SmallMultiples
`Props: { items, renderItem, columns }`
A grid of small identical charts for comparing many stations or shifts. This is the one place a grid of repeated elements is correct, because the repetition is the comparison. Maximum 8 columns.

## 32. PrintFrame
Wraps Plan view for printing: fixes the width to A4 landscape, expands scrollable regions to full height, converts state fills to patterns, adds a header with line, range and generation timestamp, and suppresses interactive controls.

---

## Component rules

1. **No component library.** No MUI, Chakra, Ant, shadcn, Radix themes, or Bootstrap. Headless primitives for focus management are acceptable if they ship no styles.
2. **No icon library.** The six icons in DESIGN_SYSTEM.md Section 8 are inline SVGs in `web/src/components/icons.tsx`.
3. **No component may hard-code a colour.** Tokens only. Enforced by a stylelint rule.
4. **Every component that displays a twin value renders `ProvenanceMark`.** Enforced by the value type.
5. **Every interactive component has a keyboard path and a visible focus state.**
6. **No component sets its own animation** beyond the two motion tokens.
7. **Empty and error states are variants of the component**, not separate components, so they cannot be forgotten.
8. **Components are tested for the calm state first.** The normal-operation render is the primary test case, because it is the most common one.

---

**Related:** [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md) · [UX_SPEC.md](UX_SPEC.md) · [ACCESSIBILITY.md](ACCESSIBILITY.md) · [../human-design/DESIGN_DONTs.md](../human-design/DESIGN_DONTs.md)
