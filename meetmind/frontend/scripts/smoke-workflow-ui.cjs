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
    const panel = page.locator('.workflow');
    await panel.getByRole('button', { name: 'Start workflow' }).click();
    // The seeded meeting is already extracted, so the run reuses it and pauses for review.
    await panel.getByText('Review and approve commitments below').waitFor();
    assert.equal(await panel.locator('.stages li.current').textContent(), 'Review');
    const card = page.locator(`[data-id="${fixture.actions[0].id}"]`);
    await card.getByRole('button', { name: 'Review / edit' }).click();
    const reviewed = page.waitForResponse(r => r.url().endsWith('/review'));
    await card.getByRole('button', { name: 'Approve commitment', exact: true }).click();
    assert.equal((await reviewed).status(), 200);
    await panel.getByRole('checkbox').first().check();
    await panel.getByLabel(/Recipients for/).fill('sara@example.com');
    await page.screenshot({ path: path.join(runs, 'workflow-review.png'), fullPage: true });
    await panel.getByRole('button', { name: /Create 1 follow-up draft/ }).click();
    const outcome = await Promise.race([
      panel.getByText("Waiting for each owner's decision in My approvals.").waitFor({ timeout: 180000 }).then(() => 'approval'),
      panel.getByRole('button', { name: 'Retry from this step' }).waitFor({ timeout: 180000 }).then(() => 'failed')]);
    if (outcome === 'failed') {
      assert.match(await panel.locator('.error').textContent(), /Drafting unavailable|Ollama/);
      console.log('Workflow UI passed (Ollama unavailable): start, reuse extraction, review pause, recipient choice, visible draft failure with retry.');
    } else {
      await page.getByRole('link', { name: /My approvals/ }).click();
      await page.getByRole('button', { name: /your decision/ }).first().click();
      await page.getByRole('button', { name: 'Approve draft', exact: true }).click();
      await page.getByRole('button', { name: 'Open source meeting' }).click();
      await panel.getByText('not configured', { exact: false }).first().waitFor({ timeout: 30000 });
      assert.equal(await panel.locator('.pill').first().textContent(), 'completed');
      console.log('Workflow UI passed (real Ollama): review pause, drafting, owner approval, execution recorded as not configured.');
    }
    await page.screenshot({ path: path.join(runs, 'workflow-result.png'), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'Workflow mobile overflow');
    assert.deepEqual(errors, []);
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
