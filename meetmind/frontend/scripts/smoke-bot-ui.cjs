// Built UI, explicitly mocked bot lifecycle; real browser/audio is tested separately.
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
(async () => {
  const root = path.resolve(__dirname, '..');
  const html = fs.readFileSync(path.join(root, 'dist/index.html'), 'utf8');
  let record = null, state = 'needs_login', create;
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('http://meetmind.test/**', async route => {
      const request = route.request(), pathname = new URL(request.url()).pathname;
      if (pathname.startsWith('/api/')) {
        let data;
        if (pathname === '/api/health') data = { ollama: 'offline', bert: { status: 'not loaded' } };
        else if (pathname.endsWith('/capabilities')) data = { playwright_installed: true, ffmpeg_available: true };
        else if (pathname === '/api/meetings') data = [];
        else if (pathname === '/api/meet/bots' && request.method() === 'POST') {
          create = request.postDataJSON();
          record = { ...create, id: 'bot-fixture', state, message: 'Manual sign-in needed',
            recorded_bytes: 2048, uploaded_chunks: 1, remote_tracks: 1, events: [],
            elapsed_seconds: 15, capture_stats: {peak:0,audio_context_state:'running'} };
          data = record;
        } else if (pathname === '/api/meet/bots') data = record ? [record] : [];
        else if (pathname.endsWith('/resume')) { state = 'recording'; data = { ...record, state }; }
        else if (pathname.endsWith('/stop')) { state = 'completed'; data = { ...record, state, meeting_id: 'saved-fixture' }; }
        else data = { ...record, state, meeting_id: state === 'completed' ? 'saved-fixture' : null };
        return route.fulfill({ json: data });
      }
      if (pathname === '/') return route.fulfill({ body: html, contentType: 'text/html' });
      if (pathname.startsWith('/assets/')) return route.fulfill({ body: fs.readFileSync(path.join(root, 'dist', pathname)), contentType: pathname.endsWith('.css') ? 'text/css' : 'text/javascript' });
      return route.fulfill({ status: 404, body: '' });
    });
    await page.goto('http://meetmind.test/');
    await page.getByRole('button', { name: 'Google Meet bot', exact: true }).click();
    await page.getByLabel('Google Meet link').fill('https://meet.google.com/abc-defg-hij');
    assert.equal(await page.getByRole('button', { name: 'Send bot to meeting' }).isDisabled(), true);
    await page.getByRole('checkbox').check();
    await page.getByRole('button', { name: 'Send bot to meeting' }).click();
    await page.getByRole('button', { name: 'Continue after sign-in' }).waitFor();
    assert.equal(create.consent_confirmed, true);
    assert.equal(create.display_name, 'MeetMind Notetaker');
    await page.reload();
    await page.getByRole('heading', { name: 'Google Meet browser bot' }).waitFor();
    await page.getByRole('button', { name: 'Continue after sign-in' }).click();
    await page.getByText('No incoming sound detected yet.',{exact:false}).waitFor();
    assert.equal(await page.getByLabel('Peak incoming audio level').getAttribute('value'),'0');
    record.capture_stats.peak=40;
    await page.getByText('Sound has been detected during this recording.',{exact:true}).waitFor();
    await page.getByRole('button', { name: 'Stop and transcribe', exact: true }).click();
    await page.getByRole('button', { name: 'Open transcript' }).waitFor();
    assert.equal(await page.getByRole('button', { name: 'Cancel and discard' }).count(), 0);
    fs.mkdirSync(path.join(root, 'runs'), { recursive: true });
    await page.screenshot({ path: path.join(root, 'runs/bot-ui-desktop.png'), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
    await page.screenshot({ path: path.join(root, 'runs/bot-ui-mobile.png'), fullPage: true });
    assert.deepEqual(errors, []);
    console.log('Bot UI passed: consent, start, manual-login resume, refresh recovery, stop, transcript link and mobile. API mocked.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exit(1); });
