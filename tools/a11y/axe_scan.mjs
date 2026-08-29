/**
 * Automated accessibility pass over the three views. T-102, T-124, T-135.
 *
 * ACCESSIBILITY.md Section 9 asks for axe-core through Playwright over all
 * three views at every breakpoint, plus the checks axe cannot make: a visible
 * focus ring, a keyboard path into the line strip, and no text below the wall
 * legibility floor.
 *
 * Playwright is deliberately not a dependency of `web/package.json`. Adding it
 * there would make `npm ci` in CI download a browser on every run for a check
 * that needs a live API as well, and a check that cannot run in CI should not
 * pretend to by sitting in the manifest. Install it alongside instead:
 *
 *   npm install playwright @axe-core/playwright && npx playwright install chromium
 *   node tools/a11y/axe_scan.mjs
 *
 * It expects the application on http://localhost:3000 and the API behind it,
 * started as docs/technical/RUNNING.md Section 2.3 describes. Results are
 * written to docs/quality/ACCESSIBILITY_RESULTS.md.
 */

import { chromium } from 'playwright'
import AxeBuilder from '@axe-core/playwright'
import { writeFileSync } from 'node:fs'

const BASE = process.env.A11Y_BASE_URL ?? 'http://localhost:3000'
const OUT = process.env.A11Y_OUT ?? 'docs/quality/ACCESSIBILITY_RESULTS.md'

// RESPONSIVE_DESIGN.md Section 1. Phone is out of scope by decision, so the
// smallest context here is the floor tablet.
const CONTEXTS = [
  { name: 'Wall', width: 1920, height: 1080 },
  { name: 'Desk', width: 1440, height: 900 },
  { name: 'Floor tablet', width: 1280, height: 800 },
]

const VIEWS = [
  { name: 'Line', path: '/' },
  { name: 'Plan', path: '/plan' },
  { name: 'Program', path: '/program' },
]

// ACCESSIBILITY.md Section 6. Colour is carried by a pattern as well as a hue,
// so the contrast rule is run rather than suppressed.
const TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']

/** Settle: the twin is live but the first paint may still be fetching. */
async function settle(page) {
  await page.waitForLoadState('networkidle').catch(() => {})
  await page.waitForTimeout(1200)
}

/** The smallest rendered font size anywhere on the page, in CSS pixels. */
async function smallestText(page) {
  return page.evaluate(() => {
    let min = Infinity
    let where = ''
    for (const el of document.querySelectorAll('*')) {
      const text = (el.textContent ?? '').trim()
      if (!text || el.children.length > 0) continue
      const style = getComputedStyle(el)
      if (style.display === 'none' || style.visibility === 'hidden') continue
      const size = parseFloat(style.fontSize)
      if (Number.isFinite(size) && size < min) {
        min = size
        where = el.tagName.toLowerCase() + ': ' + text.slice(0, 40)
      }
    }
    return { min: min === Infinity ? null : min, where }
  })
}

/** Does the first tab stop show a focus ring that is actually drawn? */
async function focusVisible(page) {
  await page.keyboard.press('Tab')
  return page.evaluate(() => {
    const el = document.activeElement
    if (!el || el === document.body) return { ok: false, reason: 'nothing took focus' }
    const style = getComputedStyle(el)
    const outline =
      style.outlineStyle !== 'none' && parseFloat(style.outlineWidth || '0') > 0
    const ring = style.boxShadow && style.boxShadow !== 'none'
    return {
      ok: Boolean(outline || ring),
      reason: outline ? 'outline' : ring ? 'box-shadow' : 'neither outline nor shadow',
      on: el.tagName.toLowerCase(),
    }
  })
}

/**
 * The line strip is one tab stop with arrow keys inside it (AC-001, T-087).
 * A strip of 42 separate tab stops would be a keyboard trap in practice.
 */
async function ropingTabStops(page) {
  return page.evaluate(() => {
    const strip = document.querySelector('[data-testid="line-strip"], [role="listbox"]')
    if (!strip) return { found: false }
    const stops = strip.querySelectorAll('[tabindex="0"]')
    return { found: true, tabStops: stops.length }
  })
}

async function main() {
  const browser = await chromium.launch()
  const rows = []
  const violations = []
  let checked = 0

  for (const context of CONTEXTS) {
    for (const view of VIEWS) {
      // An explicit context rather than browser.newPage(): the axe builder
      // refuses a page created off the browser directly.
      const browserContext = await browser.newContext({
        viewport: { width: context.width, height: context.height },
      })
      const page = await browserContext.newPage()
      // Generous, because a development server compiles a route on first
      // request and the twin behind it may still be catching up.
      page.setDefaultNavigationTimeout(180_000)
      await page.goto(BASE + view.path, { waitUntil: 'domcontentloaded' })
      await settle(page)

      const results = await new AxeBuilder({ page }).withTags(TAGS).analyze()
      const serious = results.violations.filter(
        (v) => v.impact === 'serious' || v.impact === 'critical',
      )
      const minor = results.violations.length - serious.length
      const text = await smallestText(page)
      // AC-001 and RESPONSIVE_DESIGN.md Section 8: the page must not scroll
      // sideways at any supported context.
      const overflow = await page.evaluate(() => {
        const doc = document.documentElement
        return { scroll: doc.scrollWidth, client: doc.clientWidth }
      })
      const focus = await focusVisible(page)
      const strip = await ropingTabStops(page)

      rows.push({
        context: context.name,
        view: view.name,
        width: context.width,
        serious: serious.length,
        minor,
        passes: results.passes.length,
        smallest: text.min,
        smallestWhere: text.where,
        focus,
        strip,
        overflows: overflow.scroll > overflow.client + 1,
        // The wall is read at 3 m, so it carries a floor the other contexts
        // do not. RESPONSIVE_DESIGN.md Section 3.
        floor: context.name === 'Wall' ? 18 : null,
      })
      for (const v of serious) {
        violations.push({
          context: context.name,
          view: view.name,
          id: v.id,
          help: v.help,
          nodes: v.nodes.map((n) => ({
            target: n.target.join(' '),
            summary: (n.failureSummary ?? '').replace(/\s+/g, ' ').slice(0, 300),
            html: (n.html ?? '').replace(/\s+/g, ' ').slice(0, 160),
          })),
        })
      }
      checked += 1
      await page.close()
      await browserContext.close()
    }
  }

  await browser.close()

  const stamp = new Date().toISOString().slice(0, 10)
  const totalSerious = rows.reduce((n, r) => n + r.serious, 0)
  const lines = []
  lines.push('# ACCESSIBILITY_RESULTS.md')
  lines.push('')
  lines.push(
    '**Purpose:** the machine-checkable half of T-135, run against the live application.',
  )
  lines.push('**Generated by:** `node tools/a11y/axe_scan.mjs`')
  lines.push('**Last run:** ' + stamp)
  lines.push('')
  lines.push(
    'Generated file. Every number here came from a run against the application ' +
      'serving real API responses, not from a static render.',
  )
  lines.push('')
  lines.push('---')
  lines.push('')
  lines.push('## 1. Result')
  lines.push('')
  lines.push(
    totalSerious === 0
      ? 'axe-core reports no serious or critical violation on any view at any ' +
          'context. ' +
          checked +
          ' view and context combinations were checked against ' +
          TAGS.join(', ') +
          '.'
      : totalSerious +
          ' serious or critical violations. Section 3 lists them.',
  )
  lines.push('')
  lines.push('## 2. Per view and context')
  lines.push('')
  lines.push(
    '| Context | View | Serious or critical | Other | Rules passed | Smallest text | Wall floor 18px | Sideways scroll | Focus ring |',
  )
  lines.push('|---|---|---|---|---|---|---|---|---|')
  for (const r of rows) {
    const floor =
      r.floor === null ? 'n/a' : r.smallest >= r.floor ? 'meets it' : '**below it**'
    lines.push(
      '| ' +
        r.context +
        ' | ' +
        r.view +
        ' | ' +
        r.serious +
        ' | ' +
        r.minor +
        ' | ' +
        r.passes +
        ' | ' +
        (r.smallest === null ? 'no text' : r.smallest + 'px') +
        ' | ' +
        floor +
        ' | ' +
        (r.overflows ? '**yes**' : 'none') +
        ' | ' +
        (r.focus.ok ? 'visible, ' + r.focus.reason : 'NOT VISIBLE, ' + r.focus.reason) +
        ' |',
    )
  }
  lines.push('')
  if (violations.length > 0) {
    lines.push('## 3. Violations')
    lines.push('')
    for (const v of violations) {
      lines.push('- **' + v.id + '** on ' + v.view + ' at ' + v.context + '. ' + v.help)
      for (const n of v.nodes) {
        lines.push('  - `' + n.target + '`: ' + n.summary)
      }
    }
    lines.push('')
  }
  lines.push('## 4. What this run does not cover')
  lines.push('')
  lines.push(
    'Two checks in ACCESSIBILITY.md Section 9 need a person and are recorded as ' +
      'not done rather than inferred from the numbers above.',
  )
  lines.push('')
  lines.push(
    '- **Screen reader pass.** NVDA on Windows and VoiceOver on macOS, by a person ' +
      'listening. Automated rules confirm the semantics an assistive technology ' +
      'reads from; they cannot confirm that what it announces makes sense in order.',
  )
  lines.push(
    '- **3 metre legibility.** The smallest rendered text is reported per context ' +
      'above, which is the measurable half. Whether it is readable at 3 m on a ' +
      '55-inch panel needs the panel and the 3 m.',
  )
  lines.push('')

  writeFileSync(OUT, lines.join('\n'))
  console.log('serious or critical violations: ' + totalSerious)
  console.log('combinations checked: ' + checked)
  for (const r of rows) {
    console.log(
      [r.context, r.view, 'serious=' + r.serious, 'smallest=' + r.smallest + 'px',
        'focus=' + (r.focus.ok ? 'ok' : 'MISSING'),
        'stripTabStops=' + (r.strip.found ? r.strip.tabStops : 'strip not found'),
      ].join('  '),
    )
  }
  process.exit(totalSerious === 0 ? 0 : 1)
}

main().catch((error) => {
  console.error(error)
  process.exit(2)
})
