// Real API: admin, organizer request and owner assignment across two browser sessions.
// Run after smoke-ui.cjs and seed_review_smoke (fixture path as argv[2]); no model required.
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
    const admin = await (await browser.newContext({ viewport: { width: 1440, height: 1000 } })).newPage();
    const member = await (await browser.newContext({ viewport: { width: 1440, height: 1000 } })).newPage();
    const errors = [];
    for (const page of [admin, member]) page.on('pageerror', e => errors.push(e.message));
    await signIn(admin, base);
    const email = `member-${Date.now()}@meetmind.test`;
    await member.goto(base + '/signup');
    await member.getByLabel('Name').fill('Bilal Member');
    await member.getByLabel('Email').fill(email);
    await member.getByLabel('Password').fill('member-password-1');
    await member.getByRole('button', { name: 'Create account' }).click();
    await member.getByText('Meetings appear here when an organizer assigns you an action item').waitFor();
    assert.equal(await member.getByRole('link', { name: 'Upload transcript' }).count(), 0);
    assert.equal(await member.getByRole('link', { name: 'Admin' }).count(), 0);
    await member.screenshot({ path: path.join(runs, 'roles-member-home.png'), fullPage: true });

    // Member asks for organizer access; the admin approves it.
    await member.getByRole('link', { name: 'Account' }).click();
    await member.getByLabel('Why do you need it?').fill('I run the weekly product sync');
    await member.getByRole('button', { name: 'Request organizer access' }).click();
    await member.getByText('Waiting for an admin decision.').waitFor();
    await admin.getByRole('link', { name: 'Admin' }).click();
    const request = admin.locator('.admin-row').filter({ hasText: email });
    await request.getByRole('button', { name: 'Approve' }).click();
    await admin.getByText('Bilal Member is now an organizer.').waitFor();
    await admin.screenshot({ path: path.join(runs, 'roles-admin.png'), fullPage: true });
    await member.reload();
    await member.getByRole('link', { name: 'Upload transcript' }).waitFor();

    // The organizer links the commitment to the member, who then sees it as owner.
    await admin.getByRole('link', { name: 'Meetings' }).click();
    await admin.locator('.meeting').filter({ hasText: fixture.title }).click();
    const card = admin.locator(`[data-id="${fixture.actions[0].id}"]`);
    const linked = admin.waitForResponse(r => r.url().endsWith('/assignee'));
    await card.getByLabel('Owner account').selectOption({ label: `Bilal Member (${email})` });
    assert.equal((await linked).status(), 200);
    await card.getByText(`Owner account: Bilal Member <${email}>`, { exact: true }).waitFor();
    await admin.screenshot({ path: path.join(runs, 'roles-organizer-meeting.png'), fullPage: true });
    await member.getByRole('link', { name: 'Meetings' }).click();
    await member.reload();
    await member.locator('.meeting').filter({ hasText: fixture.title }).click();
    await member.getByText('Your role:').waitFor();
    assert.match(await member.locator('.pill').filter({ hasText: 'Owner' }).first().textContent(), /Owner/);
    assert.equal(await member.getByRole('button', { name: 'Extract commitments' }).count(), 0);
    assert.equal(await member.getByRole('button', { name: 'Review / edit' }).count(), 0);
    await member.locator(`[data-id="${fixture.actions[0].id}"]`).getByText('assigned to you', { exact: false }).waitFor();
    await member.setViewportSize({ width: 390, height: 844 });
    assert(await member.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'Owner view mobile overflow');
    await member.screenshot({ path: path.join(runs, 'roles-owner-mobile.png'), fullPage: true });

    // Signing out returns to the sign-in screen and protects the API.
    await member.setViewportSize({ width: 1440, height: 1000 });
    await member.getByRole('button', { name: 'Sign out' }).click();
    await member.getByRole('heading', { name: 'Sign in' }).waitFor();
    assert.equal((await member.request.get(base + '/api/meetings')).status(), 401);
    assert.deepEqual(errors, []);
    console.log('Roles UI passed: member sign-up, organizer request and approval, owner linking, owner-only view, sign-out.');
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exitCode = 1; });
