# DESIGN_DONTs.md

**Purpose:** a checkable list of specific things not to build. HUMAN_DESIGN_GUIDELINES.md gives the reasoning; this is the reference you scan while working.
**Status:** binding.
**Last updated:** 2026-08-28

---

## How to use this

Each entry has the pattern, why it is wrong here, and what to do instead. When something in this list appears in a pull request, the correct response is to remove it, not to justify it.

---

## Surface and colour

| Do not | Why | Instead |
|---|---|---|
| Use a dark background | Poor on a factory floor under overhead lighting, poor when printed, and it is the default of every generated interface | Warm off-white paper background, `#FAF9F7` |
| Ship a theme toggle | Two themes is two designs, and the second one exists for no user | One theme, tuned properly |
| Use any gradient | The single strongest generated-interface signature. Also reduces text contrast unpredictably | Flat fills |
| Use a purple to blue accent | See above, doubled | Deep ink blue `#1B3A5C` used sparingly, never as a gradient |
| Add backdrop blur or translucency | Unreadable over content, expensive to render, purely decorative | Solid background plus a 1px border |
| Add a box shadow for elevation | Shadow soup makes everything float and nothing hierarchical | A 1px border and a background step |
| Colour a normal state green | Painting 38 normal stations green buries the 4 abnormal ones | Normal is greyscale. Colour means abnormal |
| Use colour as the only signal | Fails for colour-blind users, fails in monochrome print | Colour plus pattern plus label |
| Use a saturated brand colour across the interface | Competes with the alarm colours for attention, which is the one thing that must win | Accent on interactive text and focus rings only |

## Shape and layout

| Do not | Why | Instead |
|---|---|---|
| Use border radius above 2px | Rounded cards read as consumer software, not as an instrument | 2px, or 0 for table cells and the line strip |
| Build pill-shaped buttons or badges | Same reason, and pills waste horizontal space | Rectangles with 2px radius |
| Lay out a three-across grid of equal cards | The default output of an interface generator. Also worse than a table for comparing values | A table, or genuinely differentiated regions |
| Build a hero metric row (four big numbers with arrows) | Executive-dashboard cliché, and it strips the context that makes a number actionable | Numbers in context, next to what explains them |
| Add a left icon rail with a logo on top and an avatar at the bottom | Generic SaaS chrome | Three named view tabs. That is the whole navigation |
| Centre body text | Harder to scan, and this product is scanned | Left aligned |
| Make the page a full-bleed scrolling landing experience | This is an instrument that must fit on one screen | Fixed viewport regions for Line view |
| Nest cards inside cards | Two borders around the same content is one border too many | Whitespace and a rule |

## Typography

| Do not | Why | Instead |
|---|---|---|
| Use an em dash | Prohibited outright across the whole repository | Comma, colon, parentheses, or two sentences |
| Set headings at display sizes | Shouting at a reader who is already looking | 20px page title, 15px section, 13px label |
| Use more than two typefaces | One sans plus one mono is the whole system | Inter (or IBM Plex Sans) and IBM Plex Mono |
| Set numbers in a proportional face | Digits do not align, columns become unreadable | Monospace with tabular figures for every comparable number |
| Use Title Case for headings and buttons | Reads as marketing, and is slower to scan | Sentence case |
| Use ALL CAPS for running text or labels | Slower to read, and shouts | Caps only for station IDs, VINs and lot codes, where the plant uses caps |
| Rely on colour to indicate a link | Fails for colour-blind users | Underline plus the accent colour |

## Iconography and ornament

| Do not | Why | Instead |
|---|---|---|
| Add an AI sparkle, wand, brain or robot icon | Advertises the technology rather than the result, and is instantly recognisable as generated | Show the predictor's accuracy instead |
| Put an icon next to every menu item and label | Icons that are not carrying meaning are noise | Words |
| Use emoji anywhere | Not in UI, not in errors, not in the README, not in commits | Words |
| Add an empty-state illustration | The empty state here means the line is fine, which is information, not absence | Show the normal state fully populated |
| Add a mascot, a character, or an animated logo | No | No |
| Add decorative dividers, corner flourishes, or background patterns | Every mark competes with the alarm state | Rules only where they group |

## Motion

| Do not | Why | Instead |
|---|---|---|
| Animate elements in on load or scroll | Delays information the user came for | Render immediately |
| Count numbers up | Makes a value unreadable while it animates, and it animates every 2 minutes here | Set the value, transition the colour over 120ms |
| Pulse, glow, or shimmer anything | Peripheral motion on a wall display is genuinely distracting on a factory floor | Static |
| Use a loading skeleton | Pretends data is nearly there. Ours either is there or has an age | Show the last known value with its age |
| Add page transitions between views | Costs time, adds nothing | Instant switch |

## Copy and content

| Do not | Why | Instead |
|---|---|---|
| Write "seamless", "magic", "revolutionary", "powerful", "unlock", "empower", "transform", "leverage", "elevate", "supercharge", "streamline", "harness", "game-changing", "cutting-edge", "next-generation" | Marketing register, and a lint failure | Say what it does |
| Write "AI-powered" or "intelligent" | The product should be judged on its record, not its technique | State the accuracy |
| Use an exclamation mark | Never appropriate here | Full stop |
| Write "Oops! Something went wrong." | Tells the user nothing and sounds like a consumer app | Say what happened and what to do |
| Use lorem ipsum, "Item 1", "John Doe", "Company Name" | Immediately reads as unfinished or generated | Real plant values: S20, VIN 3C4PDCBG7JT, lot B-4471, Priya D. |
| Open a paragraph with a rhetorical question | A recognisable generated-prose rhythm | Start with the point |
| Use the "not just X, but Y" construction | Same | Say Y |
| Write three parallel clauses in a row | Same | Vary the sentence shape |
| Round a probability to a false precision | "71.34%" implies accuracy the model does not have | "0.71" or "roughly 7 in 10" |
| Hide uncertainty to look confident | The product's whole argument is that it is honest about what it knows | Show the interval |

## Data display

| Do not | Why | Instead |
|---|---|---|
| Draw a pie chart | Poor at comparison, and we always have more than three categories | Bar or stacked bar |
| Use a dual y-axis | Invites false correlation | Two aligned charts sharing an x-axis |
| Truncate a y-axis without saying so | Exaggerates a change | Start at zero, or mark the break explicitly |
| Draw a smooth spline through discrete measurements | Implies data between the points | Step or straight-line interpolation |
| Show a single number where the estimate is an interval | This is the specific failure the product exists to correct | Show the interval |
| Colour chart series by brand palette | Series colour should carry state meaning or be neutral | Neutral greys, with state colour only where the series is a state |
| Show a value without its age when it could be stale | The user cannot tell live from frozen | Timestamp or age on every live region |

## Product behaviour

| Do not | Why | Instead |
|---|---|---|
| Show an alert from a predictor that has not cleared its promotion gate | The entire trust argument depends on this | Shadow mode |
| Fill a missing value with a plausible estimate presented as measured | This is the failure mode the product exists to correct | Interval plus provenance |
| Auto-apply a counterfactual | Advisory only, permanently | Recommend, let a human act |
| Write to a PLC or any control system | Not a design decision, an architectural boundary | Read-only by type signature |
| Build a chatbot | Nobody on a factory floor wants to type a question | Direct manipulation |
| Add an onboarding tour | If it needs a tour it is wrong | Fix the interface |
| Show a modal that blocks the line state | The line does not stop for a dialog | Inline, non-blocking |
| Gamify anything | Not appropriate for a system that reports lost production | No |

---

## The five that matter most

If you remember nothing else from this document:

1. **No dark theme, no gradients, no purple-blue.**
2. **Greyscale by default. Colour means abnormal.**
3. **No em dashes, no emoji, no marketing words.**
4. **Tables, not card grids. Rules and whitespace, not shadows and radius.**
5. **Real plant data in every example, always.**

---

**Related:** [HUMAN_DESIGN_GUIDELINES.md](HUMAN_DESIGN_GUIDELINES.md) · [UX_WRITING_GUIDELINES.md](UX_WRITING_GUIDELINES.md) · [../design/DESIGN_SYSTEM.md](../design/DESIGN_SYSTEM.md)
