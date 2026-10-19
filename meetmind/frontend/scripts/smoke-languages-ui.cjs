// Serverless browser check of the built UI. API responses are mocked explicitly;
// real local model checks live in backend/scripts/smoke_languages.py.
const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
(async () => {
  const root = path.resolve(__dirname, '..');
  const html = fs.readFileSync(path.join(root, 'dist/index.html'), 'utf8');
  const transcript = fs.readFileSync(path.join(root, '../backend/tests/fixtures/urdu-project-review.txt'), 'utf8').replace(/\r\n/g,'\n');
  const text = 'ہاں بالکل علی، میں دو بجے تک نیا بلڈ ٹیسٹ سرور پر اپ لوڈ کر دوں گی۔';
  let submitted;
  const meeting = { id: 'language-ui', title: 'اردو پروجیکٹ میٹنگ', status: 'uploaded', model: null,
    source_type: 'text', actions: [], original_transcript: transcript,
    language_profile: { label: 'Urdu script' },
    segments: [{ id: 1, text, source: text, speaker: 'سارا' }],
    preprocessing: { source_count: 8, utterance_count: 1, duplicate_section_removed: false, warnings: [] } };
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.route('http://meetmind.test/**', async route => {
      const request = route.request(), pathname = new URL(request.url()).pathname;
      if (pathname.startsWith('/api/')) {
        let data;
        if (pathname === '/api/health') data = { ollama: 'ready', model: 'local-fixture', bert: { status: 'checkpoint available' } };
        else if (pathname === '/api/meetings' && request.method() === 'POST') { submitted = request.postDataJSON(); data = meeting; }
        else if (pathname === '/api/meetings') data = submitted ? [meeting] : [];
        else if (pathname.endsWith('/classify')) {
          data = { ...meeting, dialogue_analysis: { model: { model_name: 'UI fixture', checkpoint_stage: 'mocked' },
            predictions: [{ source_id: 1, description: 'Offer', score: .8, needs_review: true, review_reasons: ['machine_translated_input'], possible_action: true, top_labels: [] }],
            language_processing: { warnings: ['UI fixture: translated inputs require review.'], translations: [{ source_id: 1, english: 'I will upload the new build by two o’clock.' }] } } };
        } else data = meeting;
        return route.fulfill({ json: data });
      }
      if (pathname === '/') return route.fulfill({ body: html, contentType: 'text/html' });
      if (pathname.startsWith('/assets/')) return route.fulfill({ body: fs.readFileSync(path.join(root, 'dist', pathname)), contentType: pathname.endsWith('.css') ? 'text/css' : 'text/javascript' });
      return route.fulfill({ status: 404, body: '' });
    });
    await page.goto('http://meetmind.test/');
    await page.getByRole('button', { name: 'Upload transcript', exact: true }).click();
    assert.deepEqual(await page.getByLabel('Meeting language').locator('option').evaluateAll(options=>options.map(option=>option.value)), ['auto','en','ur','roman-ur']);
    await page.getByLabel('Meeting language').selectOption('ur');
    await page.getByLabel('Meeting title').fill(meeting.title);
    await page.getByLabel('Transcript', { exact: true }).fill(transcript);
    assert.equal(await page.getByLabel('Transcript', { exact: true }).getAttribute('dir'), 'auto');
    await page.getByRole('button', { name: 'Process meeting' }).click();
    await page.getByRole('heading', { name: meeting.title }).waitFor();
    assert.equal(submitted.input_language, 'ur');
    assert.equal(submitted.transcript, transcript);
    await page.getByRole('button', { name: 'Analyze with BERT' }).click();
    await page.getByText('Review English translations used for BERT').click();
    await page.getByText('I will upload the new build by two o’clock.').waitFor();
    assert.equal(await page.locator('.columns p[dir="auto"]').first().evaluate(e => getComputedStyle(e).direction), 'rtl');
    fs.mkdirSync(path.join(root, 'runs'), { recursive: true });
    await page.screenshot({ path: path.join(root, 'runs/language-ui-desktop.png'), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
    await page.screenshot({ path: path.join(root, 'runs/language-ui-mobile.png'), fullPage: true });
    assert.deepEqual(errors, []);
    console.log('Language UI passed: selection, Urdu submission, original evidence, translation review, RTL and mobile layout. API mocked; no servers started.');
  } finally { await browser.close(); }
})().catch(e => { console.error(e); process.exit(1); });
