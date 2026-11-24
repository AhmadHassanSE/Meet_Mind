// Real API: run the meeting workflow through the browser on a seeded, already-extracted meeting.
// Run after smoke-ui.cjs and seed_review_smoke (fixture path as argv[2]). With Ollama running the
// run reaches owner approval and completes (no connector, so nothing is sent); without Ollama it
// must fail visibly at the draft step and offer a retry.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { signIn } = require('./smoke-session.cjs');
(async () => {
  const base = process.env.MEETMIND_UI_URL || 'http://127.0.0.1:5173';
  const fixture = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  const runs = path.resolve(__dirname, '../runs');
  fs.mkdirSync(runs, { recursive: true });
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await signIn(page, base);
    await page.locator('.meeting').filter({ hasText: fixture.title }).click();
    const panel = page.locator('.next-step');
    // The seeded meeting is already extracted, so the next step is reviewing its items.
    await panel.getByRole('button', { name: 'Go to the first one' }).waitFor();
    assert.match(await panel.locator('.step-track li.current').textContent(), /Review them/);
    const card = page.locator(`[data-id="${fixture.actions[0].id}"]`);
    const reviewed = page.waitForResponse(r => r.url().endsWith('/review'));
    await card.getByRole('button', { name: 'Approve', exact: true }).click();
    assert.equal((await reviewed).status(), 200);
    // Decide the remaining items so the follow-up step opens.
    while (await page.locator('.commitment-result.is-pending').count()) {
      const rejected = page.waitForResponse(r => r.url().endsWith('/review'));
      await page.locator('.commitment-result.is-pending').first().getByRole('button', { name: 'Reject', exact: true }).click();
      assert.equal((await rejected).status(), 200);
    }
    await panel.getByText('Choose how to follow up').waitFor();
    assert.match(await panel.locator('.step-track li.current').textContent(), /Follow up/);
    await panel.getByRole('checkbox').first().check();
    await panel.getByLabel(/Recipients for/).fill('sara@example.com');
    await page.screenshot({ path: path.join(runs, 'workflow-review.png'), fullPage: true });
    // Creating follow-ups starts the workflow run, which reuses the extraction and resumes past review.
    await panel.getByRole('button', { name: /Create 1 follow-up draft/ }).click();
    const outcome = await Promise.race([
      panel.getByText("Follow-ups are waiting for each owner's approval.").waitFor({ timeout: 180000 }).then(() => 'approval'),
      panel.getByRole('button', { name: 'Try again' }).waitFor({ timeout: 180000 }).then(() => 'failed')]);
    if (outcome === 'failed') {
      assert.match(await panel.locator('.error').textContent(), /Drafting unavailable|Ollama/);
      console.log('Workflow UI passed (Ollama unavailable): review, follow-up start reusing extraction, recipient choice, visible draft failure with retry.');
    } else {
      await page.getByRole('link', { name: /My approvals/ }).click();
      await page.getByRole('button', { name: /your decision/ }).first().click();
      await page.getByRole('button', { name: 'Approve draft', exact: true }).click();
      await page.getByRole('button', { name: 'Open source meeting' }).click();
      await panel.getByText('not configured', { exact: false }).first().waitFor({ timeout: 30000 });
      await panel.getByText('All done for this meeting.', { exact: false }).waitFor();
      console.log('Workflow UI passed (real Ollama): review pause, drafting, owner approval, execution recorded as not configured.');
    }
    await page.screenshot({ path: path.join(runs, 'workflow-result.png'), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'Workflow mobile overflow');
    assert.deepEqual(errors, []);
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
