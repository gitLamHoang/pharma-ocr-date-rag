import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { mkdir, readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { chromium } from 'playwright';

const base = process.env.WEB_BASE_URL || 'http://127.0.0.1:4174';
const screenshots = resolve(process.env.SCREENSHOT_DIR || 'test-results');
const server = process.env.WEB_BASE_URL
  ? null
  : spawn(
      process.execPath,
      [
        'node_modules/vite/bin/vite.js',
        'preview',
        '--host',
        '127.0.0.1',
        '--port',
        '4174',
        '--strictPort',
      ],
      { stdio: 'inherit' },
    );
let browser;
try {
  for (let i = 0; i < 50; i++) {
    try {
      if ((await fetch(base)).ok) break;
    } catch {}
    if (i === 49) throw new Error('Preview did not become ready.');
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  await mkdir(screenshots, { recursive: true });
  browser = await chromium.launch({
    channel: process.env.BROWSER_CHANNEL || undefined,
    headless: true,
  });
  const errors = [];
  const context = await browser.newContext({ viewport: { width: 1512, height: 1100 } });
  const page = await context.newPage();
  page.on('pageerror', (error) => errors.push(error.message));
  const checkLayout = async () => {
    assert.equal(
      await page.evaluate(() => document.documentElement.scrollWidth > innerWidth),
      false,
      'Page overflows viewport',
    );
  };
  await page.goto(new URL('#workspace', base).href);
  await page.locator('.source-highlight.selected').waitFor();
  await page.evaluate(() => document.fonts.ready);
  assert.equal(await page.locator('.document-item').count(), 8);
  assert.equal(await page.locator('.field-value h3').innerText(), 'Unresolved date');
  assert.ok(
    await page.locator('.paper img').evaluate(async (image) => {
      await image.decode();
      return image.complete && image.naturalWidth > 0;
    }),
  );
  await checkLayout();
  await page.screenshot({ path: resolve(screenshots, 'review-workspace.png'), fullPage: true });

  // The viewer uses rendered fixture pages, not measured OCR bounding boxes.
  const assets = await page.evaluate(async () => {
    const data = await (await fetch('data/workspace.json')).json();
    const loaded = [];
    for (const doc of data.documents) {
      const image = new Image();
      image.src = doc.image;
      await image.decode();
      loaded.push(image.naturalWidth === doc.page.width && image.naturalHeight === doc.page.height);
    }
    return loaded;
  });
  assert.ok(assets.every(Boolean));
  await page.getByRole('button', { name: 'Zoom in', exact: true }).click();
  assert.equal(await page.locator('.zoom > span').innerText(), '110%');
  await page.getByRole('button', { name: 'Zoom out', exact: true }).click();
  await page.getByRole('button', { name: 'Text', exact: true }).click();
  assert.equal(await page.locator('.source-text mark').innerText(), '09/10/2026');
  await page.getByRole('button', { name: 'Page', exact: true }).click();
  await page
    .locator('#reason')
    .fill('Synthetic test: date convention still requires confirmation.');
  await page.getByRole('button', { name: 'Accept', exact: true }).click();
  assert.match(await page.locator('.form-error').innerText(), /valid date/);
  await page.locator('input[name=candidate]').last().check();
  await page
    .locator('#reason')
    .fill('Synthetic test: explicitly selected day/month interpretation.');
  await page.getByRole('button', { name: 'Accept', exact: true }).click();
  assert.equal(await page.locator('.inspector .pane-heading .status').innerText(), 'Accepted');
  await page.reload();
  await page.locator('.inspector .status-accepted').first().waitFor();
  assert.equal(await page.locator('.field-value h3').innerText(), '2026-10-09');
  const downloadPromise = page.waitForEvent('download');
  await page.locator('.topbar [data-action=export-json]').click();
  const download = await downloadPromise;
  const session = JSON.parse(await readFile(await download.path(), 'utf8'));
  assert.equal(session.reviews.length, 1);
  assert.equal(session.reviews[0].resolved, '2026-10-09');

  await page.locator('nav [data-view=register]').click();
  assert.equal(await page.locator('tbody tr').count(), 42);
  await page.selectOption('#language', 'fr');
  await page.selectOption('#label', 'expiry');
  await page.locator('#query').fill('expiry');
  assert.equal(await page.locator('tbody tr').count(), 1);
  await page.locator('tbody .table-link').click();
  assert.equal(await page.locator('#field option').count(), 1);
  await page.getByRole('button', { name: 'Next field', exact: true }).click();
  assert.equal(await page.locator('.type-label').textContent(), 'Expiry');
  await page.locator('nav [data-view=register]').click();
  const csvPromise = page.waitForEvent('download');
  await page.locator('[data-action=export-csv]').click();
  const csv = await csvPromise;
  assert.match(await readFile(await csv.path(), 'utf8'), /fr_certificat.txt/);
  await page.locator('#query').fill('unfindableevidence');
  assert.equal(await page.locator('tbody tr').count(), 0);
  await page.locator('nav [data-view=workspace]').click();
  assert.equal(
    await page.locator('.source-pane').count(),
    0,
    'No-match search must not show stale evidence',
  );
  await page.getByRole('button', { name: 'Clear filters' }).click();
  await page.locator('nav [data-view=register]').click();
  await page.screenshot({ path: resolve(screenshots, 'date-register-web.png'), fullPage: true });
  await page.locator('nav [data-view=benchmarks]').click();
  assert.equal(await page.locator('tbody tr').count(), 42);
  await page.getByRole('button', { name: 'Explicit language', exact: true }).click();
  await page.selectOption('#benchmark-language', 'vi');
  assert.equal(await page.locator('tbody tr').count(), 6);
  assert.match(await page.locator('.benchmark-score > strong').innerText(), /42/);
  await page.screenshot({ path: resolve(screenshots, 'benchmark-lab.png'), fullPage: true });
  await page.locator('nav [data-view=history]').click();
  assert.equal(await page.locator('.history-event').count(), 1);
  await page.locator('.history-event .table-link').click();
  assert.equal(await page.locator('.field-value h3').innerText(), '2026-10-09');
  await page.locator('#reason').fill('Synthetic follow-up: return this evidence to review.');
  await page.locator('[data-decision=needs_review]').click();
  await page.locator('nav [data-view=history]').click();
  assert.equal(await page.locator('.history-event').count(), 2);
  await checkLayout();

  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('button', { name: 'Toggle navigation' }).click();
  await page.locator('nav [data-view=workspace]').click();
  await checkLayout();
  await page.screenshot({ path: resolve(screenshots, 'mobile-workspace.png'), fullPage: true });
  await page.locator('#field').selectOption({ index: 0 });
  await page.locator('#reason').fill('Synthetic mobile test: rejected for demonstration.');
  await page.locator('[data-decision=rejected]').click();
  assert.equal(await page.locator('.inspector .pane-heading .status').innerText(), 'Rejected');
  for (const view of ['register', 'benchmarks', 'history']) {
    await page.getByRole('button', { name: 'Toggle navigation' }).click();
    await page.locator(`nav [data-view=${view}]`).click();
    await checkLayout();
  }
  assert.deepEqual(errors, []);
  for (const width of [320, 768, 1024, 1920]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto(new URL('?viewport=' + width + '#workspace', base).href);
    await page.locator('.source-highlight.selected').waitFor();
    await checkLayout();
  }
  await page.locator('nav [data-view=recalls]').click();
  await page.locator('.public-register tbody tr').first().waitFor();
  assert.equal(await page.locator('.public-register tbody tr').count(), 25);
  await page.getByRole('button', { name: 'Next public records', exact: true }).click();
  assert.match(await page.locator('.public-pagination').innerText(), /Page 2/);
  await page.locator('#recall-query').pressSequentially('0162858');
  assert.equal(await page.locator('.public-register tbody tr').count(), 2);
  await page.selectOption('#recall-role', 'expiry');
  assert.equal(await page.locator('.public-register tbody tr').count(), 1);
  assert.equal(await page.locator('.source-cell-selected').innerText(), '05/2028');
  assert.match(
    await page.locator('.public-source a').getAttribute('href'),
    /^https:\/\/www.gov.uk\/drug-device-alerts\//,
  );
  const publicDownload = page.waitForEvent('download');
  await page.locator('[data-action=export-public-json]').click();
  const publicSaved = await publicDownload;
  const exportedPublic = JSON.parse(await readFile(await publicSaved.path(), 'utf8'));
  assert.equal(exportedPublic.records.length, 1);
  assert.equal(exportedPublic.records[0].batch, '0162858');
  assert.match(exportedPublic.attribution, /Open Government Licence/);
  const publicCsvDownload = page.waitForEvent('download');
  await page.locator('[data-action=export-public-csv]').click();
  const publicCsv = await publicCsvDownload;
  const publicCsvText = await readFile(await publicCsv.path(), 'utf8');
  assert.match(publicCsvText, /0162858/);
  assert.match(publicCsvText, /Open Government Licence/);
  await page.locator('#recall-query').fill('not-a-real-medicine-name');
  assert.equal(await page.locator('.public-source').count(), 0);
  await page.locator('#recall-query').fill('');
  await page.selectOption('#recall-role', '');
  await page.selectOption('#recall-split', 'test');
  await page.locator('#recall-unresolved').check();
  assert.ok(await page.locator('.public-register tbody tr').count());
  for (const width of [1512, 390, 320]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto(new URL('?publicViewport=' + width + '#recalls', base).href);
    await page.locator('.public-register tbody tr').first().waitFor();
    await page.locator('#recall-query').fill('0162858');
    await page.selectOption('#recall-role', 'expiry');
    await checkLayout();
    await page.screenshot({
      path: resolve(screenshots, `public-notices-${width}.png`),
      fullPage: true,
    });
  }
  assert.deepEqual(errors, []);
  console.log(
    'Browser checks passed: synthetic review/persistence; public MHRA search, filters, pagination, original table evidence and export; desktop/mobile layouts.',
  );
} finally {
  await browser?.close();
  if (server) server.kill();
}
