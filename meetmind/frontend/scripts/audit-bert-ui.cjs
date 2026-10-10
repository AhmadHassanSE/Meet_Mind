// Run against a dedicated test database. Uses local fixtures from audit_bert_meetings.
const { chromium } = require('playwright');
const fs = require('node:fs');
const assert = require('node:assert/strict');
(async () => {
  const fixtures = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const results = [];
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(process.env.MEETMIND_UI_URL || 'http://127.0.0.1:5173');
    for (const [index, fixture] of fixtures.entries()) {
      await page.getByRole('button', { name: 'Upload transcript', exact: true }).click();
      await page.getByRole('tab', { name: 'Transcript file', exact: true }).click();
      const title = `BERT audit ${index + 1} ${fixture.name} ${Date.now()}`;
      await page.getByLabel('Meeting title').fill(title);
      await page.getByLabel('Choose transcript file').setInputFiles(fixture.file);
      await page.getByRole('button', { name: 'Process meeting', exact: true }).click();
      await page.getByRole('heading', { name: title, exact: true }).waitFor();
      const responsePromise = page.waitForResponse(response => response.url().endsWith('/classify'), { timeout: 180000 });
      const started = Date.now();
      await page.getByRole('button', { name: 'Analyze with BERT', exact: true }).click();
      const response = await responsePromise;
      assert.equal(response.status(), 200, await response.text());
      const meeting = await response.json();
      await page.locator('.dialogue-results article').first().waitFor();
      assert.equal(await page.locator('.dialogue-results article').count(), fixture.segments);
      assert.equal(meeting.dialogue_analysis.predictions.length, fixture.segments);
      if (meeting.dialogue_analysis.predictions.some(prediction => prediction.target_text_truncated)) {
        await page.locator('.dialogue-results .mint').filter({ hasText: 'target text truncated' }).first().waitFor();
      }
      await page.reload();
      await page.getByRole('button', { name: new RegExp(title.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')) }).click();
      await page.locator('.dialogue-results article').first().waitFor();
      assert.equal(await page.locator('.dialogue-results article').count(), fixture.segments);
      await page.setViewportSize({ width: 390, height: 844 });
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `${fixture.name}: mobile overflow`);
      await page.setViewportSize({ width: 1440, height: 1100 });
      const result = { name: fixture.name, segments: fixture.segments, analysis_and_refresh_ms: Date.now() - started, result: 'pass' };
      results.push(result);
      console.log(JSON.stringify(result));
    }
    assert.deepEqual(errors, [], 'Unexpected browser errors');
    if (process.argv[3]) fs.writeFileSync(process.argv[3], JSON.stringify(results, null, 2));
    console.log('All real-transcript browser checks passed.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
