// Run against dedicated test services/database; uses the real local NLP pipeline.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const cases = [
  { name: 'Promise and deadline', text: 'Sara: I will send the project report by Friday.' },
  { name: 'Cancellation and suggestions', text: 'Sara: I will send the project report by Friday.\nAli: Cancel the project report.\nAli: We should redesign the dashboard.' },
];
(async () => {
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const results = [];
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(process.env.MEETMIND_UI_URL || 'http://127.0.0.1:5173');
    for (const fixture of cases) {
      const title = `Commitment check ${fixture.name} ${Date.now()}`;
      await page.getByRole('button', { name: 'Upload transcript', exact: true }).click();
      await page.getByLabel('Meeting title').fill(title);
      await page.getByRole('textbox', { name: /^Transcript/ }).fill(fixture.text);
      await page.getByRole('button', { name: 'Process meeting', exact: true }).click();
      await page.getByRole('heading', { name: title, exact: true }).waitFor();
      const responsePromise = page.waitForResponse(r => r.url().endsWith('/extract'), { timeout: 240000 });
      const started = Date.now();
      await page.getByRole('button', { name: 'Extract commitments', exact: true }).click();
      const response = await responsePromise;
      assert.equal(response.status(), 200, await response.text());
      const meeting = await response.json();
      assert(meeting.actions.length, 'Expected an explicit promise');
      assert.equal(meeting.actions[0].owner, 'Sara');
      await page.locator('.commitment-result').first().waitFor();
      assert.equal(await page.locator('.commitment-result').count(), meeting.actions.length + meeting.action_candidates.length);
      assert((await page.locator('.commitment-results').textContent()).includes('by Friday'));
      if (fixture.name.startsWith('Cancellation')) {
        assert.equal(meeting.actions[0].status, 'possible_cancellation');
        await page.getByText('Possible cancellation', { exact: true }).waitFor();
        await page.getByRole('heading', { name: 'Suggestions, requests and cancellations', exact: true }).waitFor();
        assert(meeting.action_candidates.some(a => a.kind === 'suggestion'));
      }
      await page.locator('.commitment-result summary').first().click();
      assert((await page.locator('.commitment-result').first().textContent()).includes('human review required'));
      const task = meeting.actions[0];
      const card = page.locator(`[data-id="${task.id}"]`);
      await card.getByRole('button', { name: 'Review / edit', exact: true }).click();
      await card.getByLabel('Review note', { exact: true }).fill('Functional test: checked all source and cancellation evidence');
      const reviewPromise = page.waitForResponse(r => r.url().endsWith('/review'));
      await card.getByRole('button', { name: 'Approve commitment', exact: true }).click();
      const reviewed = await reviewPromise;
      assert.equal(reviewed.status(), 200, await reviewed.text());
      const saved = (await reviewed.json()).actions.find(item => item.id === task.id);
      assert.equal(saved.review_status, 'approved');
      assert.equal(saved.needs_review, false);
      assert.deepEqual(saved.evidence, task.evidence);
      await page.reload();
      await page.getByRole('heading', { name: 'Meeting library', exact: true }).waitFor();
      await page.locator('.meeting').filter({ hasText: title }).click();
      await page.locator(`[data-id="${task.id}"]`).waitFor();
      assert.equal(await page.locator('.commitment-result').count(), meeting.actions.length + meeting.action_candidates.length);
      assert.equal(await page.locator(`[data-id="${task.id}"]`).getAttribute('data-status'), 'approved');
      await page.setViewportSize({ width: 390, height: 844 });
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Mobile overflow');
      await page.setViewportSize({ width: 1440, height: 1000 });
      results.push({ name: fixture.name, result: 'pass', actions: meeting.actions.length,
        candidates: meeting.action_candidates.length, elapsed_ms: Date.now() - started });
      console.log(JSON.stringify(results.at(-1)));
    }
    assert.deepEqual(errors, []);
    if (process.argv[2]) fs.writeFileSync(process.argv[2], JSON.stringify(results, null, 2));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
