// Run against a dedicated test backend/database; this creates one fixture meeting.
// Requires Google Chrome installed. Override MEETMIND_UI_URL for a different port.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(process.env.MEETMIND_UI_URL || 'http://127.0.0.1:5173');
    await page.getByRole('button', { name: 'Upload transcript' }).click();
    await page.getByRole('tab', { name: 'Transcript file' }).click();
    const title = `UI fixture ${Date.now()}`;
    await page.getByLabel('Meeting title').fill(title);
    await page.getByLabel('Choose transcript file').setInputFiles({ name: 'meeting.vtt', mimeType: 'text/vtt', buffer: Buffer.from('WEBVTT\n\n00:01.000 --> 00:03.000\n<v Sara>I will send the report by Friday.</v>\n') });
    await page.getByRole('button', { name: 'Process meeting' }).click();
    await page.getByRole('heading', { name: 'Transcript evidence' }).waitFor();
    await page.getByText('#1 · Sara · 1.0s – 3.0s', { exact: true }).waitFor();
    await page.getByRole('link', { name: 'VTT', exact: true }).waitFor();
    await page.reload();
    await page.getByRole('button', { name: new RegExp(title) }).click();
    await page.getByRole('heading', { name: 'Transcript evidence' }).waitFor();
    if (process.env.MEETMIND_BERT_SMOKE === '1') {
      await page.getByRole('button', { name: 'Analyze with BERT' }).click();
      await page.locator('.dialogue-results article').first().waitFor({ timeout: 180000 });
      assert.equal(await page.locator('.dialogue-results article').count(), 1);
      await page.getByText(/Model score \d/).waitFor();
      await page.reload();
      await page.getByRole('button', { name: new RegExp(title) }).click();
      await page.locator('.dialogue-results article').first().waitFor();
      await page.setViewportSize({ width: 390, height: 844 });
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'BERT mobile overflow');
      await page.setViewportSize({ width: 1440, height: 1000 });
      console.log('Real BERT inference, result persistence and mobile layout verified through the browser.');
    }
    await page.getByRole('button', { name: 'Upload transcript' }).click();
    for (const name of ['Audio', 'Meeting recording']) {
      await page.getByRole('tab', { name, exact: true }).click();
      const transcriptionHelp = page.getByLabel('Local transcription information', { exact: true });
      await transcriptionHelp.waitFor();
      assert.match(await transcriptionHelp.textContent(), /English and Urdu speech/);
      await page.getByRole('combobox', { name: 'Meeting language', exact: true }).selectOption('ur');
      assert.equal(await page.getByRole('combobox', { name: 'Meeting language', exact: true }).inputValue(), 'ur');
    }
    await page.getByRole('tab', { name: 'Audio', exact: true }).click();
    await page.getByLabel('Choose audio file').setInputFiles({ name: 'bad.exe', mimeType: 'application/octet-stream', buffer: Buffer.from('bad') });
    await page.getByRole('alert').filter({ hasText: 'supported file' }).waitFor();
    await page.setViewportSize({ width: 390, height: 844 });
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Mobile horizontal overflow');
    if (process.env.MEETMIND_MEDIA_FIXTURE) {
      await page.getByRole('combobox', { name: 'Meeting language', exact: true }).selectOption('en');
      await page.getByLabel('Choose audio file').setInputFiles(process.env.MEETMIND_MEDIA_FIXTURE);
      await page.getByLabel('Meeting title').fill(`Media UI fixture ${Date.now()}`);
      await page.getByRole('button', { name: 'Process meeting' }).click();
      await page.getByRole('heading', { name: 'Transcript evidence' }).waitFor({ timeout: 180000 });
      assert(await page.getByText(/send the project report by Friday/i).count() > 0);
      console.log('Real audio upload and transcription verified through the browser.');
    }
    assert.deepEqual(errors, []);
    console.log('UI smoke checks passed: caption upload, timestamps, persistence, media tabs, file validation and mobile layout.');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exit(1); });
