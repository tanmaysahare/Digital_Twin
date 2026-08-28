# RESPONSIVE_DESIGN.md

**Purpose:** how the product behaves across the four contexts it will actually be used in. Not a generic breakpoint table.
**Last updated:** 2026-08-28

---

## 1. The four real contexts

We design for four devices, in this priority order. Anything outside these is best effort.

| Context | Device | Viewport | Distance | Who | Priority |
|---|---|---|---|---|---|
| Wall | 55-inch line-side display | 1920x1080 | 3 m | Priya, and everyone walking past | 1 |
| Desk | Laptop or shift-office desktop | 1440x900 to 1920x1080 | 60 cm | All three personas | 1 |
| Floor tablet | Rugged 10-inch, landscape, gloves | 1280x800 | 40 cm | Priya | 2 |
| Meeting | Projector or shared screen | 1920x1080, viewed at 4 m | 4 m | Rakesh, Meera | 3 |
| Print | A4 landscape | 297x210 mm | Held | Rakesh | 2 |

Phone is explicitly not supported. A supervisor does not run a line from a phone, and building a phone layout would cost days that Line view needs. The application shows a plain message below 768px saying it needs a tablet or larger, with the current line state summarised in three lines so the visit is not wasted.

---

## 2. Breakpoints

Four, named for the context rather than for a device size.

```css
/* base: floor tablet, 1280 and up */
@media (min-width: 1440px) { /* desk */ }
@media (min-width: 1920px) { /* wall and meeting */ }
@media (max-width: 1279px) { /* narrow, degraded */ }
@media print { /* print */ }
```

Base is the tablet, not the desktop. Designing up from the constrained case keeps the desktop from filling with things the tablet cannot show.

---

## 3. Wall (1920 and above)

The most important context and the one usually forgotten.

**The scale rule.** Root font size goes from 16px to 26px, a factor of 1.625. Every token in DESIGN_SYSTEM.md is expressed in rem or relative to the root, so the whole system scales with one change and every ratio stays identical. Nothing is re-laid-out for the wall.

```css
@media (min-width: 1920px) {
  :root { font-size: 26px; }
}
```

**What changes beyond scale:**
- The line strip grows to 280px tall so the cycle-time range plots are readable at 3 m.
- Regions D, E and F (output, predictor record, data health) collapse to their headline lines only. At 3 m nobody reads a four-line health panel.
- The at-risk unit table shows five rows instead of eight.
- Hover states are suppressed, because nothing hovers on a wall display.
- The lead time on an action card is set at 64px. It is the single thing that must be readable from the far end of the line.

**Legibility floor.** Nothing on the wall layout is below 18px effective. Verified by an automated check that walks the rendered DOM at 1920 width and fails on any visible text below the floor.

**Burn-in.** A 55-inch panel showing a static layout for months will retain an image. The layout shifts by one pixel in a slow four-hour cycle. This is invisible to a viewer and is the only unrequested motion in the product.

---

## 4. Desk (1440 to 1919)

The reference layout. Everything in UX_SPEC.md describes this context.

- Line view fits in the viewport with no page scroll at 900px height. This is a hard constraint and it is what limits Line view to six regions.
- Plan view and Program view scroll.
- The drawer at 480px leaves the line strip fully visible at 1440px.

---

## 5. Floor tablet (1280x800, gloves)

The constrained case, and the one that sets the interaction rules for the whole product.

**Touch targets.** Minimum 44x44 CSS px for anything tappable, and 48x48 for anything Priya taps while walking. Industrial touchscreen guidance and the accessibility literature agree on roughly this floor, and gloves push it toward the upper end (S-43, S-60 to S-62). Station segments in the line strip are the exception: at 42 segments across 1280px each is about 29px wide, so the segment's tap area extends to the full 90px height and a tap within 8px of a boundary opens a two-item disambiguation list rather than guessing.

**Spacing.** All interactive elements have at least 8px of clear space between them so a gloved finger cannot hit two.

**What changes:**
- Regions B and C (actions, at-risk units) stack vertically instead of sitting side by side.
- Regions D, E and F become a horizontal scrolling row of three panels.
- The drawer becomes full width with a back action rather than a side panel.
- The counterfactual sandbox becomes full screen, since the strip is not usefully visible behind it at this width anyway.
- No hover-only information anywhere. Everything reachable by hover is also reachable by tap.

**Gloves and moisture.** Capacitive touch with gloves is unreliable at small targets, so no interaction requires precision below 44px, no interaction requires a drag, and no interaction requires a long press. Every action is a single tap.

---

## 6. Narrow (below 1280)

Degraded but functional.

- The line strip scrolls horizontally, with abnormal stations scrolled into view automatically when their state changes.
- Regions stack into a single column.
- Plan view tables scroll horizontally within their container, with the first column pinned.

Below 768px the application shows the three-line summary message described in Section 1.

---

## 7. Print

Rakesh will print Plan view and take it into a Monday meeting. This is a real requirement, not a nicety.

```css
@media print {
  /* A4 landscape, 10mm margins */
}
```

**Rules:**
- Page size A4 landscape, margins 10mm.
- All state fills convert to patterns, since the printer is likely monochrome. This is why every state in DESIGN_SYSTEM.md has a pattern as well as a colour.
- Scrollable regions expand to full height and paginate at sensible boundaries. No table row is split across pages.
- Interactive controls are hidden.
- A print header appears with line, date range, and generation timestamp, plus the simulated-data marker.
- Charts render at print resolution as SVG, not as rasterised canvas.
- Link URLs are not appended in parentheses. Nobody types a URL off a printed operations sheet.

Line view is not designed for print and prints as a one-page state summary rather than as the live layout.

---

## 8. What does not change across contexts

Stated because the temptation to diverge is strong.

- The information architecture. Every context shows the same regions in the same order, at different densities.
- The tokens. One design system, scaled.
- The data. No context hides a number that another context shows without saying that it is doing so.
- The colour rule. Greyscale by default, colour only for abnormal, everywhere including print.

---

## 9. Testing matrix

| Viewport | Checked for |
|---|---|
| 1920x1080 at 26px root | Text floor 18px, line strip legible, no page scroll on Line view |
| 1440x900 | Line view fits with no scroll, drawer leaves strip visible |
| 1280x800 | Touch targets 44px minimum, 8px separation, no hover-only content |
| 1024x768 | Strip scrolls, regions stack, nothing overlaps |
| 767x1024 | Fallback message renders with the three-line summary |
| Print A4 landscape | Patterns present, no split rows, header correct |

Each row is an automated visual regression test in the suite described in ../quality/TEST_PLAN.md.

---

**Related:** [UX_SPEC.md](UX_SPEC.md) · [ACCESSIBILITY.md](ACCESSIBILITY.md) · [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md)
