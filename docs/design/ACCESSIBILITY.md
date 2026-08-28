# ACCESSIBILITY.md

**Target:** WCAG 2.2 Level AA for all three views, plus the industrial-context requirements in Section 6 that go beyond WCAG.
**Status:** binding. Accessibility failures block a merge in the same way a failing test does.
**Last updated:** 2026-08-28

---

## 1. Why this is not a compliance exercise here

The primary user reads this display at three metres, in 78 dB of noise, while wearing gloves, under overhead lighting, having been interrupted twice in the last minute. Every accessibility requirement below improves that experience, and several of them (contrast, target size, colour independence) are the difference between the product working on a shop floor and not.

Around 8 percent of men have some form of colour vision deficiency. On a line with 22 operators and 4 supervisors, that is not hypothetical.

---

## 2. Colour independence

**The rule: colour is never the sole carrier of meaning, anywhere.**

Every state in DESIGN_SYSTEM.md Section 1.3 carries three signals:

| State | Colour | Pattern | Text |
|---|---|---|---|
| Running | none (greyscale) | none | cycle time shown |
| Drifting | `--state-drift` | diagonal stripe 45deg | "drifting" in chip, delta shown |
| Blocked | `--state-blocked` | vertical stripe | "blocked" in chip |
| Starved | `--state-starved` | horizontal stripe | "starved" in chip |
| Down | `--state-down` | solid | "down" in chip |
| Forecast | `--state-forecast` | 2px outline, no fill | window and probability shown |
| Dark (Tier C) | `--state-dark` | cross-hatch | "no machine data" in drawer |

The verification test is in VISUAL_DIRECTION.md Section 9: print Line view in greyscale, and every state must remain distinguishable. This is an automated test that renders the view with a greyscale filter and compares state regions for distinguishability.

Charts follow the same rule: series are distinguished by direct label and by line style, not by colour alone. There are no colour legends in the product.

---

## 3. Contrast

All values verified against WCAG 2.2 SC 1.4.3 (text) and 1.4.11 (non-text).

| Pairing | Ratio | Requirement | Result |
|---|---|---|---|
| `--ink` on `--paper` | 15.3:1 | 4.5:1 | Pass AAA |
| `--ink-2` on `--paper` | 8.4:1 | 4.5:1 | Pass AAA |
| `--ink-3` on `--paper` | 4.7:1 | 4.5:1 | Pass AA |
| `--ink-3` on `--paper-sunk` | 4.5:1 | 4.5:1 | Pass AA, at the boundary |
| `--ink-4` on `--paper` | 2.7:1 | 3:1 non-text | Fails. Restricted to decorative axis ticks and disabled controls, never to information |
| `--accent` on `--paper` | 10.1:1 | 4.5:1 | Pass AAA |
| `#FFFFFF` on `--state-down` | 6.2:1 | 4.5:1 | Pass AA |
| `--ink` on `--state-drift` | 5.9:1 | 4.5:1 | Pass AA |
| `--ink` on `--state-blocked` | 5.1:1 | 4.5:1 | Pass AA |
| `--rule` on `--paper` | 1.4:1 | 3:1 for meaningful boundaries | Decorative rules only. Meaningful boundaries use `--rule-strong` at 3.1:1 |
| Focus ring `--accent` on `--paper` | 10.1:1 | 3:1 | Pass |

**Disabled state exception.** WCAG exempts disabled controls from contrast requirements. We still keep disabled text above 3:1 where practical, because a supervisor needs to read why a control is unavailable.

Contrast is checked in CI over the token file and over rendered component snapshots. A new token pairing that fails is a build failure.

---

## 4. Target size

WCAG 2.2 SC 2.5.8 requires 24x24 CSS px minimum. We exceed it because of gloves.

| Context | Minimum | Rationale |
|---|---|---|
| Pointer, desk | 36x36 | Comfortable, denser than touch |
| Touch, tablet | 44x44 | Apple and WCAG AAA guidance floor |
| Touch, tablet, while walking | 48x48 | Action card buttons, drawer close |
| Spacing between targets | 8px minimum | Prevents a gloved double-hit |

**The line strip exception.** At 42 segments across 1280px, each segment is roughly 29px wide, below the 44px floor. The mitigations, applied together:
- The tap area extends to the full 90px segment height, giving 29x90.
- A tap within 8px of a boundary opens a two-item disambiguation list naming both stations rather than guessing.
- Every station is also reachable through the at-risk table, the action card, and a keyboard search, so the strip is never the only route to a station.
- Below 1280px the strip scrolls, widening each segment past 44px.

This exception is documented rather than hidden, and the disambiguation behaviour is a tested requirement.

---

## 5. Keyboard

Full keyboard operation, because the line-side display is frequently driven by a keyboard on a shelf rather than by touch.

| Requirement | Implementation |
|---|---|
| Every interactive element reachable | Verified by an automated tab-order test per view |
| Visible focus, always | 2px `--accent` outline, 2px offset. `:focus-visible` is not used to hide focus from mouse users; the ring shows on any focus |
| No keyboard trap | Drawer and sandbox trap focus while open and release on Escape. Verified by test |
| Logical order | DOM order matches visual order in every view. No positive `tabindex` anywhere |
| Skip link | First tab stop skips to the line strip |
| Roving tabindex in the strip | The strip is one tab stop; arrow keys move between stations, Home and End jump to the ends |

**Shortcuts** (single keys, active only when focus is not in a field):

| Key | Action |
|---|---|
| `1` `2` `3` | Line, Plan, Program |
| `t` | Open the counterfactual sandbox |
| `/` | Focus the station search |
| `Escape` | Close the topmost overlay |
| `?` | Show the shortcut list |

Shortcuts are discoverable through `?` and are listed in the drawer footer. No shortcut is the only way to do anything.

---

## 6. Requirements beyond WCAG, specific to this context

These come from the industrial setting rather than from the standard, and they matter more here than several WCAG criteria do.

| Requirement | Detail |
|---|---|
| Legible at 3 m | No visible text below 18px effective at the wall breakpoint. Automated check |
| Readable under glare | High contrast base, no low-contrast decorative text, no thin weights below 400 |
| Operable with gloves | 44px minimum, 8px separation, no drag, no long press, no precision gesture |
| Readable in monochrome | Every state carries a pattern. Greyscale render test |
| No reliance on sound | There is no sound in the product |
| No reliance on motion | All information is present in the static render. Motion only marks that a value changed |
| Interruptible | No timed interaction anywhere. No auto-dismissing message. No session timeout that loses state |
| Resumable | A supervisor interrupted mid-task returns to the same state. No wizard, no multi-step flow that can be lost |

The interruptible requirement deserves emphasis. Priya is interrupted constantly. Any interaction that punishes an interruption (a timed toast carrying important information, a multi-step form, an auto-closing panel) is a design failure in this product regardless of what WCAG says.

---

## 7. Screen reader support

Not the primary use case, and supported properly anyway.

| Area | Implementation |
|---|---|
| Landmarks | `header`, `nav`, `main`, and named `region` per Line view region |
| Line strip | An `application`-role grid with each segment as a labelled cell. The label reads "S20, body construction, drifting, cycle 62.1 seconds, normal 57.2 to 59.4" |
| Provenance | `ProvenanceMark` carries an `aria-label`: "measured", "derived", "inferred". The distinction is never visual only |
| Intervals | `IntervalBar` announces "54 to 71 seconds" rather than reading two unlabelled numbers |
| Live regions | The action list is `aria-live="polite"`. The data health panel is `aria-live="polite"`. Nothing is `assertive`, because nothing in this product should interrupt speech mid-sentence |
| Charts | Every chart has a text alternative giving the shape and the key values, and a table equivalent behind a "Show as table" control |
| Tables | Real `table` markup with `scope` on headers. Sort state announced via `aria-sort` |
| Dynamic updates | The line strip does not announce every 2-minute update. Only state changes are announced, and they are batched into one message |

That last point matters: a naive live region on a 42-station strip updating every two minutes would produce continuous speech and be unusable.

---

## 8. Motion and vestibular safety

`prefers-reduced-motion: reduce` sets both motion tokens to zero. Since the product has almost no motion by design, the reduced-motion experience is nearly identical to the default, which is the correct outcome.

The burn-in prevention shift described in RESPONSIVE_DESIGN.md Section 3 is one pixel over four hours and is below any perceptual threshold, but it is also disabled under reduced motion.

---

## 9. Cognitive load

Not a WCAG conformance area at AA, and central to this product.

| Principle | Application |
|---|---|
| At most three actions at once | The action list is capped at three rows. If there are more, the top three show and the rest are counted |
| One number per decision | The action card carries lead time as its one large number. Everything else supports it |
| Consistent position | Every region is in the same place every time. Nothing reorders itself |
| Plain language | ../human-design/UX_WRITING_GUIDELINES.md, plant terminology, no jargon from the model |
| No hidden state | Data age, source health, and predictor state are always on screen |
| Nothing to learn | No tour, no modes, no hidden gestures |

---

## 10. Testing

| Test | Tool | Runs |
|---|---|---|
| Automated rule check | axe-core via Playwright, all three views, all breakpoints | Every CI run |
| Contrast over tokens | Custom script over `tokens.css` | Every CI run |
| Contrast over rendered components | axe-core colour-contrast rule on component snapshots | Every CI run |
| Tab order and focus visibility | Playwright script per view | Every CI run |
| Keyboard trap | Playwright, open and Escape each overlay | Every CI run |
| Greyscale distinguishability | Render with a greyscale filter, compare state region histograms | Every CI run |
| Text size floor at wall breakpoint | DOM walk at 1920 width | Every CI run |
| Target size and separation | DOM walk at 1280 width | Every CI run |
| Screen reader pass | Manual, NVDA on Windows, VoiceOver on macOS | Before submission |
| 3 m legibility | Manual, printed at scale or shown on a large display | Before submission |

Automated tools catch roughly a third of accessibility problems. The manual passes are not optional.

---

**Related:** [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md) · [RESPONSIVE_DESIGN.md](RESPONSIVE_DESIGN.md) · [UI_COMPONENTS.md](UI_COMPONENTS.md) · [../quality/TEST_PLAN.md](../quality/TEST_PLAN.md)
