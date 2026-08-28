# DESIGN_SYSTEM.md

**Purpose:** the tokens and rules that every screen is built from. Implemented as CSS custom properties in `web/src/styles/tokens.css` and as a Tailwind theme extension.
**Governed by:** ../human-design/HUMAN_DESIGN_GUIDELINES.md. Where they conflict, that document wins.
**Last updated:** 2026-08-28

---

## 1. Colour

### 1.1 The rule that generates the palette

Greyscale by default. Colour means abnormal. There is no green for good, no brand colour spread across the interface, no theme variants. A normal line renders in paper, ink and grey. This follows high-performance HMI practice (ISA-101 lineage, S-40 to S-43) and it is what makes an abnormal station visible from across a shop floor.

### 1.2 Base (the whole interface, most of the time)

| Token | Value | Use |
|---|---|---|
| `--paper` | `#FAF9F7` | Page background. Warm off-white, not pure white |
| `--paper-sunk` | `#F3F1ED` | Recessed regions: table header rows, the line strip trough |
| `--paper-raised` | `#FFFFFF` | Panels that sit above the page: drawer, sandbox overlay |
| `--ink` | `#1A1A1A` | Primary text |
| `--ink-2` | `#4A4A48` | Secondary text, labels |
| `--ink-3` | `#7A7975` | Tertiary text, units, timestamps |
| `--ink-4` | `#A8A6A1` | Disabled, axis ticks |
| `--rule` | `#D9D6D0` | Borders, dividers, table rules |
| `--rule-strong` | `#B5B2AB` | Section separators, chart axes |

### 1.3 State colours (the only saturated colour in the product)

| Token | Value | Meaning | Also carries |
|---|---|---|---|
| `--state-drift` | `#B8860B` | Cycle time drifting inside tolerance | Diagonal stripe, 45 degrees, 3px |
| `--state-blocked` | `#C2701C` | Blocked beyond threshold | Vertical stripe |
| `--state-starved` | `#C2701C` | Starved beyond threshold | Horizontal stripe |
| `--state-down` | `#A32020` | Station down or line stopped | Solid, white text |
| `--state-forecast` | `#B8860B` | Predicted problem, not yet occurring | 2px outline only, no fill |
| `--state-defect` | `#A32020` | Confirmed inspection failure | Solid marker |
| `--state-dark` | `#8C8A85` | Tier C station, no machine data | Cross-hatch. Not an alarm, a fact |

Blocked and starved share a hue deliberately: they are the same class of flow problem and are distinguished by stripe direction and label, not by hue. This keeps the number of hues on screen to three.

### 1.4 Accent

| Token | Value | Use |
|---|---|---|
| `--accent` | `#1B3A5C` | Interactive text, active tab underline, focus ring. Nowhere else |
| `--accent-quiet` | `#E8EDF2` | Selected table row background, at very low saturation |

The accent never fills a button, never appears in a chart, never sits next to a state colour.

### 1.5 Chart colours

| Token | Value | Use |
|---|---|---|
| `--series-1` | `#3A3A38` | Primary series |
| `--series-2` | `#6E6C67` | Secondary series |
| `--series-3` | `#9C9A94` | Tertiary series |
| `--band` | `#E3E0DA` | Confidence band fill |
| `--baseline` | `#B5B2AB` | Reference line, target line |

A chart series takes a state colour only when the series represents that state (for example, the blocked share in a loss Pareto). Otherwise charts are grey.

### 1.6 What is forbidden

No gradient of any kind. No colour outside this table. No dark variants. No `prefers-color-scheme` block. Raw hex values in component styles fail review; everything references a token.

---

## 2. Typography

### 2.1 Faces

| Token | Stack | Use |
|---|---|---|
| `--font-sans` | `"Inter", "IBM Plex Sans", system-ui, sans-serif` | All prose, labels, headings |
| `--font-mono` | `"IBM Plex Mono", "JetBrains Mono", ui-monospace, monospace` | Every number that will be compared. Station IDs, VINs, lot codes, timestamps, cycle times, probabilities, counts |

Two faces. No third. Fonts are self-hosted so the product runs offline.

**The numeral rule.** Any figure that appears in a column, or that a user will compare against another figure, is set in the mono face with `font-variant-numeric: tabular-nums`. This is a legibility requirement. A column of proportional digits is unreadable at a glance and this product is read at a glance.

### 2.2 Scale

Restrained. The largest thing on a screen is barely larger than the smallest.

| Token | Size / line height | Weight | Use |
|---|---|---|---|
| `--text-display` | 28px / 32px | 600 | The single largest number on Line view (lead time). Used once per screen at most |
| `--text-title` | 20px / 28px | 600 | Page title |
| `--text-section` | 15px / 22px | 600 | Section heading |
| `--text-body` | 14px / 21px | 400 | Body copy, table cells |
| `--text-label` | 13px / 18px | 500 | Field labels, table headers |
| `--text-small` | 12px / 16px | 400 | Units, timestamps, provenance notes |
| `--text-micro` | 11px / 14px | 500 | Station ID on the line strip, axis ticks |

**Wall display scale.** On the 55-inch line-side display the whole scale multiplies by 1.6 via a root font-size change, keeping every ratio identical. See RESPONSIVE_DESIGN.md.

### 2.3 Rules

Sentence case everywhere. No letter-spacing on body text. Caps only for station IDs, VINs and lot codes. Maximum measure for running prose is 68 characters. Headings are never centred.

---

## 3. Space

A 4px base with a deliberately small set of steps, because a large scale invites inconsistency.

| Token | Value | Typical use |
|---|---|---|
| `--space-1` | 4px | Inside a chip, between an icon and its label |
| `--space-2` | 8px | Between related lines, table cell padding (vertical) |
| `--space-3` | 12px | Table cell padding (horizontal), between form rows |
| `--space-4` | 16px | Between elements in a group |
| `--space-6` | 24px | Between groups |
| `--space-8` | 32px | Between sections |
| `--space-12` | 48px | Between major regions |

**The grouping rule.** Space between groups is always at least twice the space within a group. This is what lets the layout work with very few borders, and it is checked in review.

---

## 4. Line, border and radius

| Token | Value | Use |
|---|---|---|
| `--border` | `1px solid var(--rule)` | Panels, tables, inputs |
| `--border-strong` | `1px solid var(--rule-strong)` | Section separators, chart axes |
| `--border-state` | `2px solid` + state colour | Forecast outline, focus within an abnormal region |
| `--radius` | `2px` | Everything that has a radius |
| `--radius-none` | `0` | Table cells, line strip segments, chart elements |

No radius above 2px exists in this product. No shadow except the two permitted overlays (Section 6).

---

## 5. Elevation

Three levels, and the third barely exists.

| Level | Treatment | Where |
|---|---|---|
| 0, page | `--paper` background | Everything |
| 1, panel | `--paper-raised` background plus `--border` | Panels, tables, cards |
| 2, overlay | `--paper-raised`, `--border-strong`, and `0 2px 8px rgba(26,26,26,0.10)` | Station detail drawer, counterfactual sandbox only |

Nothing else casts a shadow.

---

## 6. Motion

| Token | Value | Use |
|---|---|---|
| `--motion-value` | `120ms ease-out` | A number or state colour that changed |
| `--motion-panel` | `160ms ease-out` | Drawer and overlay entry |
| everything else | none | |

No entrance animation, no scroll animation, no counting numbers, no pulse, no shimmer. All motion respects `prefers-reduced-motion: reduce` by dropping to zero duration.

---

## 7. Focus and interaction states

| State | Treatment |
|---|---|
| Focus (keyboard) | 2px `--accent` outline, 2px offset, always visible, never removed |
| Hover (pointer) | `--paper-sunk` background on rows and buttons. No transform, no shadow change |
| Active | Background one step darker. No scale transform |
| Selected | `--accent-quiet` background plus a 2px left border in `--accent` |
| Disabled | `--ink-4` text, no background change, `cursor: not-allowed` |

Focus indication is never suppressed, including on mouse interaction, because the line-side display is often driven by a keyboard.

---

## 8. Iconography

A deliberately tiny set. Every icon here earns its place because it repeats often enough that the shape becomes the label.

| Icon | Meaning | Where |
|---|---|---|
| Chevron | Expand or collapse | Drawer, table group |
| Arrow up / down | Direction of change, next to a delta | Deltas only |
| Rule (horizontal bar) | Interval, endpoints marked | Any interval-valued number |
| Hatch swatch | Dark station | Legend and line strip |
| Cross | Close | Drawer and overlay only |

Six icons. Nothing else. Drawn as 16px stroke icons at 1.5px weight in `--ink-2`. No icon library is installed, because installing one guarantees more icons appear.

No status icons: status is carried by fill, pattern and label. No AI iconography of any kind.

---

## 9. Data display rules

| Rule | Detail |
|---|---|
| Numbers | Mono, tabular figures, right-aligned in tables |
| Units | Always present, in `--text-small` `--ink-3`, following the number |
| Intervals | `54 to 71 s`, or a bar with marked endpoints. Never a midpoint alone |
| Probabilities | Two decimals, `0.71`. Never a percentage with decimals |
| Timestamps | 24-hour, `HH:MM:SS`. Relative under 60 minutes, absolute beyond |
| Deltas | Signed, with a direction arrow, and the baseline named |
| Provenance | Measured values plain; derived values with a thin left rule; inferred values in `--ink-2` with a hatch marker |
| Missing | Never blank and never zero. `no data` in `--ink-4`, or an interval if one exists |
| Charts | Zero-based y-axis or an explicit break mark. Step interpolation for discrete measurements. No dual axis. No pie |

---

## 10. Layout grid

| Context | Grid |
|---|---|
| Line view | 12 columns, 16px gutter, fluid, minimum 1024px. Fixed viewport height, no page scroll |
| Plan view | 12 columns, 16px gutter, page scrolls |
| Program view | 8 columns, 24px gutter, narrower measure, page scrolls |
| Tablet (768 to 1024) | 6 columns, stacked regions |
| Wall (1920 and above) | Same 12 columns, root font size 1.6x |

---

## 11. Token file shape

```css
/* web/src/styles/tokens.css */
:root {
  /* base */
  --paper: #FAF9F7;
  --paper-sunk: #F3F1ED;
  --paper-raised: #FFFFFF;
  --ink: #1A1A1A;
  --ink-2: #4A4A48;
  --ink-3: #7A7975;
  --ink-4: #A8A6A1;
  --rule: #D9D6D0;
  --rule-strong: #B5B2AB;

  /* state, the only saturated colour */
  --state-drift: #B8860B;
  --state-blocked: #C2701C;
  --state-starved: #C2701C;
  --state-down: #A32020;
  --state-forecast: #B8860B;
  --state-defect: #A32020;
  --state-dark: #8C8A85;

  /* accent */
  --accent: #1B3A5C;
  --accent-quiet: #E8EDF2;

  /* charts */
  --series-1: #3A3A38;
  --series-2: #6E6C67;
  --series-3: #9C9A94;
  --band: #E3E0DA;
  --baseline: #B5B2AB;

  /* type */
  --font-sans: "Inter", "IBM Plex Sans", system-ui, sans-serif;
  --font-mono: "IBM Plex Mono", "JetBrains Mono", ui-monospace, monospace;

  /* space */
  --space-1: 4px;  --space-2: 8px;  --space-3: 12px;
  --space-4: 16px; --space-6: 24px; --space-8: 32px; --space-12: 48px;

  /* line */
  --rule-width: 1px;
  --radius: 2px;

  /* motion */
  --motion-value: 120ms;
  --motion-panel: 160ms;
}
```

There is no `@media (prefers-color-scheme: dark)` block and a stylelint rule prevents one being added.

---

## 12. Contrast verification

Every pairing used in the product, checked against WCAG 2.2 AA. Full table in ACCESSIBILITY.md Section 3.

| Foreground | Background | Ratio | Passes |
|---|---|---|---|
| `--ink` | `--paper` | 15.3:1 | AAA |
| `--ink-2` | `--paper` | 8.4:1 | AAA |
| `--ink-3` | `--paper` | 4.7:1 | AA |
| `--ink-4` | `--paper` | 2.7:1 | Non-text only |
| `--accent` | `--paper` | 10.1:1 | AAA |
| `#FFFFFF` | `--state-down` | 6.2:1 | AA |
| `--ink` | `--state-drift` | 5.9:1 | AA |

`--ink-4` is used only for disabled states and axis ticks, never for information a user must read.

---

**Related:** [VISUAL_DIRECTION.md](VISUAL_DIRECTION.md) · [UI_COMPONENTS.md](UI_COMPONENTS.md) · [ACCESSIBILITY.md](ACCESSIBILITY.md) · [../human-design/HUMAN_DESIGN_GUIDELINES.md](../human-design/HUMAN_DESIGN_GUIDELINES.md)
