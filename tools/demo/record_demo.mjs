/**
 * Drives the running application and records it. T-142.
 *
 * This is a screen recording of the real interface reading the real API, in the
 * order MVP_SCOPE.md Section 1 sets out and DEFINITION_OF_DONE.md Section 3
 * requires. Nothing here fabricates a screen: every value that appears came
 * from the twin over HTTP while the recording was running.
 *
 * It writes two things into the output directory: the raw recording, and
 * `captions.json`, which carries the wall-clock offset of each beat from the
 * start of the recording. `tools/demo/build_video.py` turns the pair into the
 * finished MP4. The captions are kept out of the page deliberately, so that
 * what is recorded is the product rather than the product with a caption bar
 * bolted to it.
 *
 * Prerequisites, as docs/technical/RUNNING.md Section 2.3 describes: the API on
 * 8000 with its twin LIVE, and the web application on 3000. Playwright is not a
 * dependency of web/package.json, for the reason given in tools/a11y/axe_scan.mjs.
 *
 *   npm install playwright && npx playwright install chromium
 *   node tools/demo/record_demo.mjs
 */

import { chromium } from 'playwright'
import { mkdirSync, writeFileSync, readdirSync, renameSync } from 'node:fs'
import { join } from 'node:path'

const WEB = process.env.DEMO_WEB_URL ?? 'http://localhost:3000'
const API = process.env.DEMO_API_URL ?? 'http://127.0.0.1:8000'
const OUT = process.env.DEMO_OUT ?? 'submission/demo'

// The desk context. RESPONSIVE_DESIGN.md Section 1 makes it one of the two
// priority-1 contexts and it is the one a judge will watch this on.
const WIDTH = 1440
const HEIGHT = 900

const beats = []
let started = 0

/** Record that a beat begins now, with the caption that belongs to it. */
function beat(title, body) {
  beats.push({ at_ms: Date.now() - started, title, body })
  console.log(`${((Date.now() - started) / 1000).toFixed(1)}s  ${title}`)
}

const wait = (page, ms) => page.waitForTimeout(ms)

// Two kinds of pause, and the difference matters to the finished video.
//
// `wait` covers the mechanical ones: a drawer opening, a route resolving. They
// are as short as the interface allows and nobody speaks over them.
//
// `hold` is a passage a narrator talks across, so its length is set by how long
// the sentence takes to say rather than by how long the screen takes to read.
// Around 2.5 words a second is what a person actually manages narrating a
// technical walkthrough, so a 13 second hold carries about 32 words.
// docs/submission/VOICEOVER_SCRIPT.md is written against these durations and
// the two have to be changed together.
//
// DEMO_PACE=read gives the shorter silent cut, for a viewer reading the caption
// cards with no narration over them.
const PACE = process.env.DEMO_PACE ?? 'narrate'
const HOLD_SCALE = PACE === 'read' ? 0.55 : 1.0

/** Hold the current screen for a passage the narrator speaks over.
 *
 * The length is written back onto the beat it belongs to, so that the build
 * cuts a passage to the sentence that is spoken over it rather than to the
 * distance to the next caption. Those two used to be the same thing. They stop
 * being the same thing the moment a route is slow: Plan view runs its Monte
 * Carlo before it paints, and without this the twenty seconds it spends loading
 * would land in the middle of the passage before it.
 */
const hold = (page, seconds) => {
  const ms = Math.round(seconds * 1000 * HOLD_SCALE)
  if (beats.length > 0) {
    // Accumulated, not assigned. Plan and Program each hold twice under one
    // caption, once on the screen as it lands and once after a scroll, and
    // both halves belong to the passage that caption introduces.
    const current = beats[beats.length - 1]
    current.hold_ms = (current.hold_ms ?? 0) + ms
  }
  return page.waitForTimeout(ms)
}

/** Fail loudly rather than record a screen that is still a cold start. */
async function requireLive() {
  const response = await fetch(`${API}/health`)
  const body = await response.json()
  if (body.twin !== 'LIVE') {
    throw new Error(
      `the twin is ${body.twin} after ${body.cycles} cycles. ` +
        'Recording a warming twin would record a loading state, not the product. ' +
        'Wait for /health to report LIVE.',
    )
  }
  return body
}

/** The numbers the closing card states, read from the API rather than typed. */
async function closingEvidence() {
  const response = await fetch(`${API}/api/v1/lines/line2/scorecard`)
  if (!response.ok) return null
  return response.json()
}

async function main() {
  mkdirSync(OUT, { recursive: true })
  const health = await requireLive()
  console.log(`twin LIVE, ${health.cycles} cycles complete`)

  const browser = await chromium.launch()
  const context = await browser.newContext({
    viewport: { width: WIDTH, height: HEIGHT },
    recordVideo: { dir: OUT, size: { width: WIDTH, height: HEIGHT } },
    reducedMotion: 'reduce',
  })
  const page = await context.newPage()
  page.setDefaultNavigationTimeout(180_000)

  started = Date.now()

  // 1. The quiet shift. DEFINITION_OF_DONE.md Section 3 requires this first:
  // the moment where the system says nothing on a normal shift.
  await page.goto(WEB + '/', { waitUntil: 'domcontentloaded' })
  await page.waitForLoadState('networkidle').catch(() => {})
  beat(
    'A normal shift',
    'Forty-two stations, live. The action region says nothing needs attention. ' +
      'All data on screen is simulated.',
  )
  await hold(page, 13)

  // 2. The strip, and the six stations nothing watches.
  const strip = page.locator('section[aria-label="Line strip"]')
  await strip.scrollIntoViewIfNeeded().catch(() => {})
  beat(
    'Six of these stations emit nothing',
    'S33 to S37 and S42 are cross-hatched. The twin has no reading from them ' +
      'and does not pretend otherwise.',
  )
  await hold(page, 13)

  // 3. The dark station drawer. The argument of the whole product.
  const dark = page.locator('button[aria-label^="S34,"]').first()
  if (await dark.count()) {
    await dark.click()
    await wait(page, 1500)
    beat(
      'A bound, not a number',
      'S34 reports an interval. The drawer names the five stations that share ' +
        'the bound and says none of them can be separated.',
    )
    await hold(page, 14)
    beat(
      'The blind spot becomes a costed recommendation',
      'What is unknown, the device that would resolve it, the indicative cost, ' +
        'and the sentence saying the cost is our assumption.',
    )
    await page.mouse.wheel(0, 400)
    await hold(page, 14)
    await page.keyboard.press('Escape')
    await wait(page, 1200)
  }

  // 4. Drift. SC-01 is the scenario the live replay is running.
  await page.mouse.wheel(0, -600)
  await wait(page, 800)
  beat(
    'A fixture wearing at S20',
    'Cycle time drifting inside specification. No threshold alarm fires. ' +
      'EWMA and CUSUM must both signal before the twin says anything.',
  )
  await hold(page, 13)

  // 5. The counterfactual sandbox, opened the way a supervisor opens it.
  await page.keyboard.press('t')
  await wait(page, 2500)
  beat(
    'What would help, compared against doing nothing',
    'Every option runs on the same replications from the same state. The footer ' +
      'states the replication count, the runtime and the state timestamp.',
  )
  await hold(page, 14)
  await page.keyboard.press('Escape')
  await wait(page, 1200)

  // 6. Units at risk and the per-unit view.
  const unitRow = page.locator('table tbody tr').first()
  if (await unitRow.count()) {
    await unitRow.click().catch(() => {})
    await wait(page, 1500)
    beat(
      'Defect risk, before the gate that would catch it',
      'Calibrated probability with a conformal interval, the top three factors ' +
        'in plant language, and the lead time in stations.',
    )
    await hold(page, 13)
    await page.keyboard.press('Escape')
    await wait(page, 1200)
  }

  // 7. The part that matters most: the predictor that has not earned the floor.
  beat(
    'The stall forecaster has not cleared its gate',
    'Precision 0.250 against a target of 0.60, median lead 5 minutes against 15. ' +
      'It is measured, it is published, and it is not tuned away.',
  )
  await hold(page, 14)

  // 8. Plan view.
  await page.keyboard.press('2')
  await page.waitForURL('**/plan', { timeout: 60_000 }).catch(() => {})
  await page.waitForLoadState('networkidle').catch(() => {})
  await wait(page, 1500)
  beat(
    'Plan view',
    'Where the constraint moved, the loss Pareto under its reconciliation line, ' +
      'and the sensor investment queue that leaves as a CSV.',
  )
  await hold(page, 9)
  await page.mouse.wheel(0, 700)
  await hold(page, 4)

  // 9. The scorecard, in shadow. The shadow-mode moment.
  await page.mouse.wheel(0, 900)
  await wait(page, 1000)
  beat(
    'Every predictor on this line is in shadow',
    'The floor sees nothing from any of them. That is the trust ledger working, ' +
      'not the screen failing.',
  )
  await hold(page, 14)

  // 10. Program view.
  await page.keyboard.press('3')
  await page.waitForURL('**/program', { timeout: 60_000 }).catch(() => {})
  await page.waitForLoadState('networkidle').catch(() => {})
  await wait(page, 1500)
  beat(
    'Program view',
    'Site readiness scored from what each site emits, and a business case whose ' +
      'every assumption carries its source and its uncertainty.',
  )
  await hold(page, 9)
  await page.mouse.wheel(0, 700)
  await hold(page, 4)

  // 11. Back to the calm line to close where it opened.
  await page.keyboard.press('1')
  await page.waitForURL(WEB + '/', { timeout: 60_000 }).catch(() => {})
  await wait(page, 2500)
  beat('The evidence', 'Every number below is in evaluation/metrics.json.')
  await hold(page, 5)

  const total = Date.now() - started
  const evidence = await closingEvidence().catch(() => null)

  await context.close()
  await browser.close()

  // Playwright names the file after the page's guid. Give it a stable name.
  const recorded = readdirSync(OUT).filter((f) => f.endsWith('.webm'))
  let video = null
  if (recorded.length > 0) {
    video = join(OUT, 'recording.webm')
    renameSync(join(OUT, recorded[0]), video)
  }

  writeFileSync(
    join(OUT, 'captions.json'),
    JSON.stringify(
      { width: WIDTH, height: HEIGHT, total_ms: total, video, beats, evidence },
      null,
      2,
    ),
  )
  console.log(`recorded ${(total / 1000).toFixed(1)}s over ${beats.length} beats`)
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})
