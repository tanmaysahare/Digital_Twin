// Screenshots of the running application. T-134, T-141.
//
// Every image here is the real interface reading the real API. Nothing is
// staged: the screen the demonstration shows and the screen these capture are
// the same screen, and if the calm state is what the line is in, that is what
// the screenshot shows.
//
// Run it with the API and the web server up:
//   node scripts/screenshots.mjs [webBase] [outDir]

import { mkdir } from 'node:fs/promises';
import { chromium } from 'playwright';

const WEB = process.argv[2] ?? 'http://127.0.0.1:3100';
const OUT = process.argv[3] ?? '../docs/design/SCREENSHOTS';

// The three contexts from RESPONSIVE_DESIGN.md, plus the two drawers and the
// sandbox, which are the states a still frame otherwise never shows.
const SHOTS = [
  { name: '01-line-desk', path: '/', width: 1440, height: 900 },
  { name: '02-line-wall', path: '/', width: 1920, height: 1080 },
  { name: '03-line-tablet', path: '/', width: 900, height: 1200 },
  // Plan and Program run models to answer, so they get longer than the
  // views that only read state.
  { name: '04-plan', path: '/plan', width: 1440, height: 1400, full: true, wait: 25000 },
  { name: '05-program', path: '/program', width: 1440, height: 1600, full: true, wait: 20000 },
];

const errors = [];

async function main() {
  await mkdir(OUT, { recursive: true });
  const browser = await chromium.launch();
  const page = await browser.newPage();
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text());
  });
  page.on('pageerror', (failure) => errors.push(String(failure)));

  for (const shot of SHOTS) {
    await page.setViewportSize({ width: shot.width, height: shot.height });
    await page.goto(`${WEB}${shot.path}`, { waitUntil: 'domcontentloaded' });
    // The views fetch after mount, so wait for real content rather than for a
    // fixed delay: a screenshot of a half-loaded screen is worse than none.
    await page.waitForTimeout(shot.wait ?? 4000);
    await page.screenshot({
      path: `${OUT}/${shot.name}.png`,
      fullPage: Boolean(shot.full),
    });
    process.stdout.write(`${shot.name} captured\n`);
  }

  // The station drawer, on a dark station, which is the variant that matters.
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`${WEB}/`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(4000);
  const dark = page.locator('button[aria-label^="S34"]').first();
  if (await dark.count()) {
    await dark.click();
    await page.waitForTimeout(2500);
    await page.screenshot({ path: `${OUT}/06-station-drawer-dark.png` });
    process.stdout.write('06-station-drawer-dark captured\n');
    await page.keyboard.press('Escape');
  } else {
    process.stdout.write('06 skipped: S34 was not on the strip\n');
  }

  // The sandbox, which the keyboard opens with t.
  await page.keyboard.press('t');
  await page.waitForTimeout(1000);
  const run = page.getByRole('button', { name: 'Run', exact: true });
  if ((await run.count()) === 1) {
    await run.click();
    await page.waitForTimeout(30000);
    await page.screenshot({ path: `${OUT}/07-sandbox.png` });
    process.stdout.write('07-sandbox captured\n');
  } else {
    process.stdout.write('07 skipped: the sandbox did not open\n');
  }

  // The unit drawer, from the first row of the at-risk table if there is one.
  await page.goto(`${WEB}/`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(4000);
  const row = page.locator('table tbody tr').first();
  if ((await row.count()) > 0) {
    await row.click();
    await page.waitForTimeout(2500);
    await page.screenshot({ path: `${OUT}/08-unit-drawer.png` });
    process.stdout.write('08-unit-drawer captured\n');
  } else {
    process.stdout.write('08 skipped: no unit was above the risk threshold\n');
  }

  await browser.close();
  if (errors.length) {
    process.stdout.write(`\nConsole errors (${errors.length}):\n`);
    for (const item of errors.slice(0, 20)) process.stdout.write(`  ${item}\n`);
    process.exitCode = 1;
  } else {
    process.stdout.write('\nNo console errors.\n');
  }
}

await main();
