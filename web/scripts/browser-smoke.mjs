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
  assert.match(await page.locator('.inspector .form-error').innerText(), /valid date/);
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
    await page.getByRole('button', { name: 'Reopen document for review', exact: true }).click();
    const dialog = page.getByRole('dialog');
    assert.equal(await dialog.isVisible(), true);
    assert.equal(
      await dialog.evaluate((element) => element.scrollWidth > element.clientWidth),
      false,
    );
    await dialog.screenshot({ path: resolve(screenshots, `reopen-dialog-${width}.png`) });
    await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
  }
  const storedEvents = () =>
    page.evaluate(() => JSON.parse(localStorage.getItem('pharma-date-review.events.v1')));
  const beforeReopen = await storedEvents();
  await page.selectOption('#label', 'audit');
  assert.equal(await page.locator('#field option').count(), 1);
  await page.getByRole('button', { name: 'Reopen document for review', exact: true }).click();
  const reopenDialog = page.getByRole('dialog');
  await reopenDialog.getByRole('button', { name: /Reopen all/ }).click();
  assert.deepEqual(await storedEvents(), beforeReopen, 'A required reason cannot be skipped');
  await reopenDialog
    .getByLabel('Re-review reason')
    .fill('Synthetic test: repeat the complete document review.');
  await page.evaluate(() => {
    window.originalStorageSet = Storage.prototype.setItem;
    Storage.prototype.setItem = () => {
      throw new Error('Simulated storage write failure');
    };
  });
  await reopenDialog.getByRole('button', { name: /Reopen all/ }).click();
  assert.match(await reopenDialog.getByRole('alert').innerText(), /Simulated storage/);
  assert.deepEqual(
    await storedEvents(),
    beforeReopen,
    'Failed storage must preserve all prior decisions',
  );
  await page.evaluate(() => {
    Storage.prototype.setItem = window.originalStorageSet;
  });
  await reopenDialog.getByRole('button', { name: /Reopen all/ }).click();
  const afterReopen = await storedEvents();
  assert.deepEqual(afterReopen.slice(0, beforeReopen.length), beforeReopen);
  const additions = afterReopen.slice(beforeReopen.length);
  assert.ok(additions.length > 1, 'Reopen must include document fields hidden by filters');
  assert.equal(new Set(additions.map((event) => event.reopenId)).size, 1);
  assert.ok(
    additions.every(
      (event) => event.documentId === 'fr_certificat' && event.decision === 'needs_review',
    ),
  );
  assert.equal(await page.locator('.field-value h3').innerText(), 'Unresolved date');
  assert.equal(await page.locator('input[name=candidate]:checked').count(), 0);
  await page.reload();
  await page.locator('.inspector .status-needs_review').first().waitFor();
  assert.equal(await page.locator('.field-value h3').innerText(), 'Unresolved date');
  assert.deepEqual(await storedEvents(), afterReopen);
  await page
    .locator('#reason')
    .fill('Synthetic test: prior interpretation must not carry forward.');
  await page.getByRole('button', { name: 'Accept', exact: true }).click();
  assert.match(await page.locator('.inspector .form-error').innerText(), /valid date/);
  assert.deepEqual(await storedEvents(), afterReopen);
  const reopenedExportPromise = page.waitForEvent('download');
  await page.locator('.topbar [data-action=export-json]').click();
  const reopenedExport = await reopenedExportPromise;
  assert.deepEqual(
    JSON.parse(await readFile(await reopenedExport.path(), 'utf8')).reviews,
    afterReopen,
  );
  await page.locator('nav [data-view=history]').click();
  assert.equal(await page.locator('.history-event').count(), afterReopen.length);
  assert.equal(
    await page.locator('.history-event').filter({ hasText: 'Document reopened' }).count(),
    additions.length,
  );
  await page.locator('nav [data-view=recalls]').click();
  await page.locator('.public-register tbody tr').first().waitFor();
  // Guided paths keep real evidence linked and preserve the local review session.
  await page.locator('[data-action=demo-batch]').focus();
  await page.keyboard.press('Enter');
  assert.equal(await page.locator('.public-register tbody tr').count(), 1);
  assert.equal(await page.locator('#recall-query').inputValue(), '0162858');
  assert.equal(await page.locator('#recall-role').inputValue(), 'expiry');
  assert.equal(await page.locator('.source-cell-selected').innerText(), '05/2028');
  await page.locator('[data-action=demo-unresolved]').click();
  assert.equal(await page.locator('#recall-query').inputValue(), '');
  assert.equal(await page.locator('#recall-role').inputValue(), '');
  assert.equal(await page.locator('#recall-kind').inputValue(), 'ambiguous_date');
  assert.equal(await page.locator('#recall-unresolved').isChecked(), true);
  const guidedRow = page.locator('.public-register tbody tr').last();
  const guidedSource = await guidedRow.locator('td').nth(2).innerText();
  await guidedRow.scrollIntoViewIfNeeded();
  const registerScroll = await page.locator('.public-register').evaluate((el) => el.scrollTop);
  await guidedRow.locator('.table-link').click();
  assert.equal(
    await page.locator('.public-register').evaluate((el) => el.scrollTop),
    registerScroll,
  );
  assert.equal(await page.locator('.source-cell-selected').innerText(), guidedSource);
  await page.locator('[data-action=demo-review]').click();
  assert.equal(
    await page.locator('.document-item.selected').getAttribute('data-doc'),
    'fr_certificat',
  );
  assert.equal(await page.locator('.field-value h3').innerText(), 'Unresolved date');
  assert.ok((await page.locator('input[name=candidate]').count()) > 1);
  assert.deepEqual(await storedEvents(), afterReopen);
  await page.locator('nav [data-view=recalls]').click();
  await page.locator('[data-action=demo-all]').click();
  for (const id of ['recall-query', 'recall-role', 'recall-split', 'recall-kind']) {
    assert.equal(await page.locator('#' + id).inputValue(), '');
  }
  assert.equal(await page.locator('#recall-unresolved').isChecked(), false);
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
  await page.selectOption('#recall-split', '');
  await page.selectOption('#recall-kind', 'cutoff');
  assert.equal(await page.locator('.public-register tbody tr').count(), 3);
  assert.equal(
    await page.locator('.public-register .date-cell').first().innerText(),
    'Up to 2029-05 (inclusive)',
  );
  assert.match(await page.locator('.source-cell-selected').innerText(), /05\/2029\*/);
  assert.match(await page.locator('.public-qualifier').innerText(), /footnote/);
  const cutoffDownload = page.waitForEvent('download');
  await page.locator('[data-action=export-public-json]').click();
  const cutoffFile = await cutoffDownload;
  const cutoffExport = JSON.parse(await readFile(await cutoffFile.path(), 'utf8'));
  assert.equal(cutoffExport.schemaVersion, 2);
  assert.equal(cutoffExport.records.length, 3);
  assert.ok(
    cutoffExport.records.every(
      (row) => row.normalized === null && row.candidates.length === 0 && row.cutoff.inclusive,
    ),
  );
  const cutoffCsvDownload = page.waitForEvent('download');
  await page.locator('[data-action=export-public-csv]').click();
  const cutoffCsvFile = await cutoffCsvDownload;
  const cutoffCsvText = await readFile(await cutoffCsvFile.path(), 'utf8');
  assert.match(cutoffCsvText, /"cutoff_upper","cutoff_inclusive","cutoff_precision"/);
  assert.match(cutoffCsvText, /"2029-05","true","month"/);
  await page.selectOption('#recall-kind', 'non_date');
  assert.equal(await page.locator('.public-register tbody tr').count(), 25);
  assert.match(await page.locator('.public-pagination').innerText(), /Page 1 \/ 2/);
  assert.equal(
    await page.locator('.public-register .date-cell').first().innerText(),
    'Source states: Not yet distributed',
  );
  assert.equal(await page.locator('.public-qualifier').count(), 0);
  await page.selectOption('#recall-kind', 'unparsed');
  assert.equal(
    await page.locator('.public-register .date-cell').first().innerText(),
    'Unsupported value',
  );
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
    await page.locator('#recall-query').fill('');
    await page.selectOption('#recall-kind', 'cutoff');
    await checkLayout();
    await page.screenshot({
      path: resolve(screenshots, `public-cutoffs-${width}.png`),
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
