# REFERENCE_IMAGES

**Purpose:** the visual references the build should follow, and the generated reference sheets that define the look concretely.
**Rule from ../../human-design/HUMAN_DESIGN_GUIDELINES.md rule 32:** follow these references closely rather than inventing a visual language.
**Last updated:** 2026-08-28

---

## 1. What is in this folder

| File | What it is |
|---|---|
| `README.md` | This file. The reference brief |
| `palette.svg` | Every token in DESIGN_SYSTEM.md rendered as a swatch sheet with its hex value and contrast ratio |
| `state-patterns.svg` | The seven station states, each showing colour plus pattern plus label, and the same sheet in greyscale |
| `line-strip-study.svg` | A visual study of the signature element: 42 stations, one drifting, one down, six dark, with buffers and a forecast marker |
| `typography-scale.svg` | The type scale at desk and wall sizes, with the numeral treatment shown |

These four SVGs are the authoritative visual reference. When the built interface and these sheets disagree, the sheets are correct unless a documented reason says otherwise.

## 2. External references to collect

These are not committed to the repository, for licensing reasons. Collect them into a local scratch folder while designing, study them, and do not copy them.

### R-1: High-performance HMI screens (ISA-101 lineage)
**Search:** "ISA-101 high performance HMI example", "high performance HMI grey screen", "abnormal situation management display".
**Study for:** the grey base with colour only on abnormality, analogue indicators showing a value against its normal band, and the density they achieve without decoration.
**Do not take:** the industrial grey base colour, or the mimic-diagram layout.

### R-2: Railway and transit departure boards
**Search:** "Swiss railway timetable typography", "SBB departure board", "Deutsche Bahn Abfahrt board design".
**Study for:** how a dense grid of times and states becomes readable through alignment and weight alone, with almost no colour and no boxes.
**Do not take:** all-caps station names, or the small tap targets of a printed sheet.

### R-3: Financial terminals
**Search:** "Bloomberg terminal layout", "trading dashboard tabular figures", "market depth display".
**Study for:** numbers as the primary visual material, monospace tabular alignment, colour only on change, information density, and the practice of always showing the age of a quote.
**Do not take:** the dark background, or the colour-on-everything convention.

### R-4: Scientific and engineering print
**Search:** "Tufte small multiples", "journal figure design", "engineering drawing annotation", "control chart layout".
**Study for:** maximum data per unit of ink, direct labelling instead of legends, intervals drawn as intervals, small multiples for comparing many series.
**Do not take:** nothing much. This is the closest reference.

### R-5: Real assembly line andon boards
**Search:** "andon board automotive assembly", "line status board factory", "production status display shop floor".
**Study for:** what a plant already puts on a wall and what supervisors are already used to reading. Our line strip should feel like a descendant of these, not like a web dashboard.

## 3. Anti-references

Collect three or four of these too, and pin them next to the good ones as a reminder of what to avoid.

- Any AI product landing page from 2024 onward: dark background, purple-to-blue gradient, glass cards, sparkle icons.
- Any generic B2B SaaS analytics dashboard: hero metric row, three-column card grid, colourful sidebar, avatar in the corner.
- Any photoreal digital twin marketing render.
- Any dashboard with more than four hues visible at once.

## 4. Screenshot discipline

Every screenshot taken of the product for the README, the pitch or the video must:

- Show realistic plant data. Station S20, VIN 3C4PDCBG7JT, part lot B-4471, cycle 62.1 s. Never placeholder text.
- Show a plausible distribution: buffers at different levels, cycle times that vary, some stations dark, at least one predictor sitting in shadow mode.
- Include the simulated-data marker in the header. It is not cropped out.
- Be taken at the desk breakpoint (1440x900) unless the point of the screenshot is a different context.
- Be taken in light theme, because that is the only theme.

At least one screenshot in the README must show the calm state: a normal line with the action list reading "Nothing needs attention". That screenshot does more for the product's credibility with an operations audience than any alert screenshot.

## 5. Regenerating the reference sheets

The four SVGs in this folder are generated from the design tokens so they cannot drift from the implementation.

```
make reference-sheets
```

This reads `web/src/styles/tokens.css` and rewrites the SVGs. If a token changes and the sheets are not regenerated, CI fails.

---

**Related:** [../VISUAL_DIRECTION.md](../VISUAL_DIRECTION.md) · [../DESIGN_SYSTEM.md](../DESIGN_SYSTEM.md) · [../../human-design/DESIGN_DONTs.md](../../human-design/DESIGN_DONTs.md)
