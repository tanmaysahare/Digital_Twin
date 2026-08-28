# HUMAN_DESIGN_GUIDELINES.md

**Status: binding.** This document has veto power over every other design document in this repository. If UX_SPEC.md, DESIGN_SYSTEM.md or any implementation conflicts with a rule here, this document wins and the other document is wrong and must be corrected.

**Who this is for:** whoever is building the interface, human or agent. Read this before writing a single line of CSS.

**Last updated:** 2026-08-28

---

## 0. Why this document exists

Interfaces generated quickly converge on a recognisable house style: dark background, purple-to-blue gradient, rounded cards in a three-column grid, glass panels, oversized headings, an icon on every label, and copy that describes ordinary functionality as seamless and revolutionary. That style is a tell. A judge who has seen forty submissions will recognise it in two seconds and will discount everything behind it.

There is a second, better reason. This product goes on a wall in a factory. It is read at three metres by someone wearing gloves in 78 dB of noise who has twenty seconds. Decorative interface effects are not neutral there; they cost legibility. The high-performance HMI tradition arrived at low-saturation, low-ornament displays through operational experience, not through taste.

So the constraints below serve two masters at once, and that is why they are non-negotiable.

---

## 1. The hard prohibitions

These are absolute. There is no case in this product where any of them is correct.

### Typography and punctuation
1. **No em dashes.** Not in UI copy, not in documentation, not in code comments, not in commit messages, not in the README. Use a comma, a colon, parentheses, or a full stop and a second sentence. If a sentence seems to need an em dash, it needs restructuring.
2. **No oversized headings everywhere.** One page-level heading per screen at a restrained size. Section headings are smaller than you expect. Hierarchy comes from weight, spacing and rules, not from scale escalation.
3. **No decorative letter-spacing on body text**, no all-caps paragraphs, no centred blocks of running text.

### Colour and surface
4. **No dark theme.** The product ships light only. A light interface is what a plant floor under overhead lighting reads best, and it is what prints. There is no theme toggle.
5. **No gradients.** Not on backgrounds, not on buttons, not on charts, not as a subtle 2 percent overlay that someone will argue is not really a gradient. Flat fills only.
6. **No purple-to-blue or blue-to-cyan colour scheme.** This is the single most recognisable generated-interface signature. Our accent is a deep ink blue used sparingly and never as a gradient partner.
7. **No glassmorphism.** No backdrop blur, no translucent panels, no frosted overlays.
8. **No excessive shadows.** Elevation is communicated by a 1px border and background separation. Shadows are permitted in exactly two places: the counterfactual sandbox overlay and the station detail drawer, and only as a single soft shadow at low opacity.
9. **No neon, no glow, no saturated colour used decoratively.** Colour is reserved for state. See Section 4.

### Shape and layout
10. **No excessively rounded cards.** Border radius is 2px or 0. Nothing in this product has a 16px radius.
11. **No pill-shaped UI.** No fully rounded buttons, no pill badges, no capsule tabs. Status indicators are rectangular chips with a 2px radius.
12. **No repetitive card grids.** A three-across grid of identical bordered boxes is the default output of an interface generator and it is prohibited. Related numbers go in a table. Different things get different treatments.
13. **No generic SaaS dashboard aesthetic.** No hero metric row of four big numbers with an up-arrow and a percentage. No sidebar of icons with a logo at the top and an avatar at the bottom.
14. **No full-bleed hero sections.** This is an instrument, not a landing page.

### Iconography and ornament
15. **No excessive icons.** An icon appears only where it carries meaning a word cannot carry faster, or where it repeats often enough that the shape becomes the label. Menu items are words. Buttons are words.
16. **No AI sparkle icons.** No four-pointed star, no wand, no glowing orb, no brain, no robot. The product does not advertise that it uses models; it shows its accuracy instead.
17. **No emoji.** Not in the UI, not in error messages, not in the README, not in commit messages.
18. **No illustrations, no mascots, no empty-state artwork, no confetti, no celebration animation.**

### Motion
19. **No decorative animation.** No fade-in on scroll, no staggered list entrance, no counting-up numbers, no pulsing dots, no animated gradient borders, no shimmer.
20. Motion is permitted only where it conveys information: a value that changed may transition over 120ms so the eye can see it changed. Nothing else moves.

### Copy
21. **No marketing language.** Banned outright: magic, magical, revolutionary, seamless, seamlessly, effortless, effortlessly, unlock, unleash, empower, transform, game-changing, cutting-edge, state-of-the-art, next-generation, powerful, robust (as a compliment), leverage (as a verb), delve, journey, elevate, supercharge, streamline, harness, "at the speed of", "in real time" used as a boast rather than a specification.
22. **No AI self-reference as a selling point.** The interface never says "AI-powered", "powered by machine learning", "our AI thinks", or "intelligent". It states what it predicts and how often it has been right.
23. **No exclamation marks.** Anywhere.
24. **No lorem ipsum and no obviously synthetic placeholder content.** Every string in every screenshot, wireframe and demo is a plausible plant value. Station S20. VIN 3C4PDCBG7JT. Part lot B-4471. Never "Item 1", never "Lorem ipsum dolor", never "John Doe".

---

## 2. The positive rules

Prohibitions alone produce something bland. These are what the interface should actually be.

25. **Restrained, editorial hierarchy.** Think a well-set operations sheet or a printed timetable: rules, alignment, weight contrast, and generous but purposeful whitespace. The reference is print, not the web.
26. **Whitespace is structural, not decorative.** It groups. Space between groups is larger than space within a group, consistently, and that consistency is what makes the layout readable without borders everywhere.
27. **Tables are the default for repeated data.** Dense, aligned, scannable. A supervisor comparing eight stations wants rows, not eight cards.
28. **Numerals are tabular and monospaced.** Every figure that will be compared vertically uses a monospace face with tabular figures so digits align. This is a legibility requirement, not a style choice.
29. **Consistent but not mechanically repetitive.** Components behave identically wherever they appear, but a screen is not built by stamping the same block five times. Line view, Plan view and Program view have genuinely different structures because they serve genuinely different rhythms.
30. **Every visual element must earn its place.** Before adding anything, answer: what decision does this change? If there is no answer, it does not ship. This applies to a border, a label, an icon and a chart equally.
31. **Usability over visual effect, always.** If a treatment looks better and reads worse, it reads worse and it is wrong.
32. **Follow the visual references.** VISUAL_DIRECTION.md names specific reference traditions. Follow them closely rather than inventing.
33. **Realistic data everywhere.** See rule 24. This also means realistic distributions: cycle times that vary, buffers that are not all half full, a scorecard that shows a predictor doing badly.

---

## 3. UI text rules

Full detail in UX_WRITING_GUIDELINES.md. The headline rules:

34. **Human-sounding error messages.** Say what happened, in plant language, and what to do. "S17 to S22 source last seen 4 minutes ago. Forecasts for that section are paused." Not "Error: connection timeout (code 504)". Not "Oops! Something went wrong."
35. **Natural, concise UI text.** Write what a competent colleague would say out loud. Read every string aloud; if you would not say it, rewrite it.
36. **No repetitive AI-style copy patterns.** Avoid the rhythm of three parallel clauses, the "not just X, but Y" construction, the rhetorical question opener, and starting consecutive strings with the same word.
37. **Sentence case for everything.** Headings, buttons, labels, table headers. No Title Case, no ALL CAPS except for station identifiers and unit codes where the plant itself uses caps.
38. **Numbers carry units and precision that reflect real accuracy.** "27 min" not "27.0000 minutes". "0.71" for a probability, not "71.3%" implying precision we do not have. An interval where the estimate is an interval.

---

## 4. The colour rule, stated separately because it governs everything

This is the single most important design decision in the product.

**The interface is greyscale by default. Colour means abnormal.**

A line running normally is rendered entirely in ink, grey and paper. There is no green for "good", because painting 38 normal stations green makes the four abnormal ones harder to find, not easier. Normal is the absence of colour.

Colour appears only for:

| State | Treatment |
|---|---|
| Drifting | Amber fill, dark ink text |
| Blocked or starved beyond threshold | Amber fill with a pattern |
| Down or stopped | Red fill, white text |
| Predicted problem | Amber outline with the forecast marker |
| Confirmed defect at a gate | Red marker on the unit |
| Dark station (Tier C) | Not a colour. A diagonal hatch in grey, because darkness is not an alarm |

Nothing else in the interface is coloured. Not the navigation. Not the buttons. Not the charts, except where a series represents one of the states above. The single accent colour (deep ink blue) appears on interactive text and the focus ring, nowhere else.

Consequence: an abnormal station is the only saturated thing on a 42-station display, and it is visible from across the shop floor without reading anything. This is the entire point.

Colour is never the sole carrier of meaning. Every state also has a distinct fill pattern, a label, or a position, so the display works for a colour-blind supervisor and in monochrome print. See ../design/ACCESSIBILITY.md.

---

## 5. The "does this look generated" test

Before any screen is considered done, run it:

1. Is there a gradient anywhere? Fail.
2. Is the background dark? Fail.
3. Are there three or more cards of the same size in a row? Fail.
4. Is any border radius above 2px? Fail.
5. Is there an icon next to a label that would be clear without it? Fail.
6. Does any string contain a banned word from rule 21? Fail.
7. Is there an em dash anywhere in the codebase? Fail.
8. Would this screen look at home on a generic B2B SaaS marketing site? Fail.
9. Is any placeholder text not a plausible plant value? Fail.
10. Is there colour on a screen where nothing is abnormal? Fail.
11. Does anything animate that is not communicating a change? Fail.
12. Is any heading larger than it needs to be to establish hierarchy? Fail.

Twelve checks. A screen passes all twelve or it is not done. This list is also encoded as a lint rule and a checklist item in ../quality/DEFINITION_OF_DONE.md.

---

## 6. Enforcement

These are not aspirations. They are checked.

| Rule | Enforcement |
|---|---|
| No em dashes | Repository-wide lint rule failing CI on the character U+2014 in any tracked file |
| No banned marketing words | Lint rule over UI string files and Markdown, with the word list in `.lint/banned-words.txt` |
| No emoji | Lint rule over tracked text files |
| No gradients, blur, large radius | Stylelint rules banning `linear-gradient`, `radial-gradient`, `backdrop-filter`, and `border-radius` values above 2px |
| No dark theme | No dark-mode media query permitted; a stylelint rule bans `prefers-color-scheme` |
| Colour only for state | Design tokens are named by state (`--state-drift`, `--state-down`); raw hex values in component CSS fail review |
| Contrast and target size | Automated accessibility checks in CI, see ../design/ACCESSIBILITY.md |
| The twelve checks | Manual, in the PR template, as a required checklist |

If an agent is generating this interface, these lint rules are the feedback loop. Run them, read the failures, and fix the cause rather than suppressing the rule. Suppressing a lint rule from this list is never an acceptable resolution.

---

## 7. The calm state is the designed state

The most common condition of this product is: nothing is wrong. Most shifts, most hours, there is no drift, no forecast stall, no at-risk unit.

That state must look deliberate. It should read as a quiet, complete, well-set instrument panel that is telling you the line is fine. It must not read as empty, unfinished, loading, or waiting for content. There is no empty-state illustration and no "no data yet" placeholder, because there is data: the data is that everything is normal, and it should be shown as such.

Concretely, on a quiet shift the Line view shows all 42 stations in greyscale with their live cycle times, the buffer levels, the current output against target, the data age, and an action list whose single row reads "Nothing needs attention". That is a full screen of useful information containing no alarm, and getting it to feel calm rather than blank is the hardest design problem in this product.

---

## 8. If you are unsure

Ask: what would this look like if it were printed on paper and pinned to a board next to the line, and had to be read by someone walking past?

That is the design.

---

**Related:** [DESIGN_DONTs.md](DESIGN_DONTs.md) · [CONTENT_STYLE_GUIDELINES.md](CONTENT_STYLE_GUIDELINES.md) · [UX_WRITING_GUIDELINES.md](UX_WRITING_GUIDELINES.md) · [../design/DESIGN_SYSTEM.md](../design/DESIGN_SYSTEM.md) · [../design/VISUAL_DIRECTION.md](../design/VISUAL_DIRECTION.md)
