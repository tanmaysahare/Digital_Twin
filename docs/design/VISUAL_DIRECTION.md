# VISUAL_DIRECTION.md

**Purpose:** what the product should look and feel like, and the traditions it borrows from. DESIGN_SYSTEM.md gives the tokens; this explains why they are those values.
**Last updated:** 2026-08-28

---

## 1. The one-line direction

A printed operations sheet that updates itself.

---

## 2. The four references

These are traditions to study, not products to copy. The instruction in ../human-design/HUMAN_DESIGN_GUIDELINES.md rule 32 is to follow them closely rather than to invent a new visual language.

### R-1: High-performance HMI (ISA-101 lineage)
**What to take.** The central discipline: a low-saturation greyscale base with colour reserved entirely for conditions needing attention. Process industries moved to this from colourful mimic displays because operators could not find the abnormal item on a screen where everything was coloured. Also: shape and pattern carrying meaning alongside colour, analogue indicators showing a value against its normal range rather than as a bare number, and information density treated as a virtue.

**What to leave.** The literal industrial-grey aesthetic. Our base is a warm paper tone rather than a battleship grey, because our surface is also a document that gets printed and read in an office, and because a warm base is easier on the eye over an eight-hour shift.

**Sources.** S-40 to S-43.

### R-2: Swiss transit timetables and railway operations boards
**What to take.** The way a dense grid of times and states becomes readable through alignment, rules and typographic weight alone, with almost no colour and no boxes. The line strip owes its structure to this: 42 stations in a row, each a small block with a state and a number, readable as a whole and as parts. Also the confidence that a table can be beautiful.

**What to leave.** The all-caps station names, and the tightness of a printed sheet that never has to accommodate a touch target.

### R-3: Financial terminals and trading interfaces
**What to take.** Numbers as the primary visual material. Monospace tabular figures, right alignment, colour used only on change and only briefly, extreme information density, no chrome, no decoration, and a layout that assumes the user knows what they are doing. Also the practice of always showing the age of a quote.

**What to leave.** The dark background. That convention comes from a room where six screens run for twelve hours, not from a factory floor under overhead light.

### R-4: Scientific and engineering print (Tufte, journal figures, engineering drawings)
**What to take.** Maximum data per unit of ink. Charts with no gridlines they do not need, no legends that a direct label could replace, and no borders around plot areas. Small multiples for comparing 42 stations. Intervals drawn as intervals. The habit of showing the uncertainty rather than hiding it.

**What to leave.** Nothing much. This is the closest reference to the intended feel.

---

## 3. Explicitly not references

Named because they are what an interface drifts toward if nobody says otherwise.

- **Generic B2B SaaS dashboards.** Card grids, hero metric rows, a colourful sidebar, an avatar in the corner.
- **Consumer analytics products.** Rounded everything, illustrations, celebratory states, gradients.
- **Photoreal digital twin marketing.** 3D factory renders and isometric illustrations. We deliberately do not build 3D (PRODUCT_VISION.md Section 9).
- **Generated interface house style.** Dark background, purple-to-blue gradient, glass panels, sparkle icons, oversized headings. Prohibited in full in ../human-design/DESIGN_DONTs.md.

---

## 4. The three moods, one system

The same tokens produce three different densities because the three users have three different rhythms.

| View | Feels like | Density | Read at | Duration |
|---|---|---|---|---|
| Line view | A departures board | Very high, fixed viewport, no scroll | 3 m, and 40 cm on a tablet | Glances, seconds at a time |
| Plan view | A printed weekly report | High, tabular, scrollable, prints cleanly | 60 cm | Minutes, in a meeting |
| Program view | A well-set board paper | Moderate, narrower measure, more prose | 60 cm, and on a projector | Minutes, with discussion |

They share every token. They differ in grid, density and the ratio of numbers to words. This is what ../human-design/HUMAN_DESIGN_GUIDELINES.md rule 29 means by consistent but not mechanically repetitive.

---

## 5. Signature elements

Four things that should be immediately recognisable as this product.

### 5.1 The line strip
A horizontal band of 42 segments across the full width of Line view. Each segment carries the station ID in mono micro type, a fill representing state, a thin vertical bar showing current cycle time against the station's normal range, and a hatch if the station is dark. Buffers appear as narrow gaps between segments with a fill level. Forecast markers sit above the strip on a time axis.

On a normal line this is 42 grey blocks and it should look calm and intentional. When S20 drifts, one block turns amber and it is the only saturated thing on the screen. That contrast is the product's core visual idea.

### 5.2 The interval bar
Wherever an estimate is an interval, it is drawn as an interval: a horizontal rule with marked endpoints, a tick at the point estimate if one exists, and the numbers alongside. Used for cycle time at dark stations, forecast windows, defect probability, and counterfactual outcomes. This element appears constantly and it is the visual expression of the product's honesty about uncertainty.

### 5.3 The provenance mark
A one-character indicator on any value that was not directly measured. Measured values carry nothing. Derived values carry a thin left rule. Inferred values are set in `--ink-2` with a small hatch. A user should be able to tell measurement from inference without reading a legend, after five minutes with the product.

### 5.4 The scorecard row
A single table row per predictor per station: predictor name, state (shadow or active), predictions made, hit rate, mean lead time, false alerts per shift. Plain, unstyled, and unflattering where it needs to be. It appears in both Line view and Plan view. It is the visual embodiment of the trust argument, and it should look like a maintenance record, not like a marketing chart.

---

## 6. Photography and imagery

There is none. No photographs, no stock imagery, no illustration, no 3D render, no background texture. The only graphics in the product are data.

The one exception is the repository README, which may include screenshots of the product itself and an architecture diagram drawn as a plain SVG in the same token palette.

---

## 7. Sound

None. A factory floor is at 78 dB and an interface sound is either inaudible or an irritation. Escalation, where it exists, goes to the existing andon system, not to a browser notification.

---

## 8. The feeling to aim for

A supervisor should look at this and think it was made by someone who has stood on a line, not by someone who has read about one. That comes from three things: the right words (../human-design/UX_WRITING_GUIDELINES.md Section 3), plausible numbers everywhere, and the restraint to leave a normal line looking completely undramatic.

The failure to avoid is a screen that looks impressive in a slide and useless at 09:14.

---

## 9. Quick visual test

Print Line view in greyscale on A4. If every state is still distinguishable and the layout still reads, the design is correct. If it turns into an undifferentiated grid, the design is relying on colour and must be fixed.

---

**Related:** [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md) · [REFERENCE_IMAGES/README.md](REFERENCE_IMAGES/README.md) · [UX_SPEC.md](UX_SPEC.md) · [../human-design/DESIGN_DONTs.md](../human-design/DESIGN_DONTs.md)
