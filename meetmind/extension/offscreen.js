// Offscreen document: mixes tab audio with the microphone, records it, and talks to the backend.
// It owns the capture session so the service worker can sleep without losing anything.
const CHUNK_MS = 10000;
const HINT_FLUSH_MS = 3000;
const HINT_BATCH = 1500;
const POLL_MS = 2000;

let state = null;
let backendUrl = '';

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function report(update) {
  chrome.runtime.sendMessage({ type: 'status', ...update }).catch(() => {});
}

async function api(path, options = {}) {
  const response = await fetch(backendUrl + path, options);
  if (!response.ok) {
    let detail = '';
    try { detail = (await response.json()).detail || ''; } catch (ignored) { /* non-JSON body */ }
    const error = new Error(detail || `Backend returned ${response.status}`);
    error.status = response.status;
    throw error;
  }
  return response.status === 204 ? null : response.json();
}

async function start(config) {
  if (state) throw new Error('A capture is already running');
  backendUrl = config.backend;
  state = { ...config, queue: [], seq: 0, hints: [], uploading: false, stopping: false, sessionId: null, failed: false };
  const tabStream = await navigator.mediaDevices.getUserMedia({
    audio: { mandatory: { chromeMediaSource: 'tab', chromeMediaSourceId: config.streamId } }, video: false });
  let micStream = null;
  try {
    micStream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true }, video: false });
  } catch (error) {
    report({ warning: 'Microphone unavailable: only other participants will be recorded. Grant access in the extension popup.' });
  }
  const context = new AudioContext();
  await context.resume();
  const destination = context.createMediaStreamDestination();
  const tabSource = context.createMediaStreamSource(tabStream);
  tabSource.connect(destination);
  tabSource.connect(context.destination); // capturing a tab mutes it, so play it back
  if (micStream) context.createMediaStreamSource(micStream).connect(destination);
  Object.assign(state, { tabStream, micStream, context });

  const recorder = new MediaRecorder(destination.stream, { mimeType: 'audio/webm;codecs=opus', audioBitsPerSecond: 32000 });
  state.recorder = recorder;
  recorder.ondataavailable = (event) => {
    if (state && event.data && event.data.size) { state.queue.push(event.data); pump(); }
  };
  recorder.onstop = () => { if (state) { state.recorderStopped = true; pump(); } };
  recorder.onerror = () => fail('Recording failed inside the browser.');
  tabStream.getAudioTracks()[0].addEventListener('ended', () => stop());
  recorder.onstart = async () => {
    state.startedAt = Date.now();
    try {
      const session = await api('/api/meet/sessions', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: config.title, meeting_code: config.meetingCode, self_name: config.selfName,
                               started_at_ms: state.startedAt }) });
      state.sessionId = session.id;
      state.hintTimer = setInterval(flushHints, HINT_FLUSH_MS);
      report({ state: 'recording', sessionId: session.id, startedAt: state.startedAt });
      pump();
    } catch (error) {
      fail('Could not start a session on the backend: ' + error.message);
    }
  };
  recorder.start(CHUNK_MS);
}

async function pump() {
  const s = state;
  if (!s || s.uploading || !s.sessionId || s.failed) return;
  s.uploading = true;
  try {
    while (state === s && s.queue.length) {
      const blob = s.queue[0];
      for (let attempt = 0; ; attempt++) {
        try {
          await api(`/api/meet/sessions/${s.sessionId}/audio?seq=${s.seq}`, { method: 'POST', body: blob });
          break;
        } catch (error) {
          if (state !== s) return;
          if (error.status && error.status >= 400 && error.status < 500 && error.status !== 429) throw error;
          report({ warning: 'Backend unreachable, retrying uploads...' });
          if (attempt >= 60) throw error;
          await sleep(Math.min(10000, 1000 * (attempt + 1)));
        }
      }
      if (state !== s) return;
      s.queue.shift();
      s.seq += 1;
      report({ warning: '', uploadedChunks: s.seq });
    }
  } catch (error) {
    s.uploading = false;
    return fail('Audio upload failed: ' + error.message);
  }
  s.uploading = false;
  if (state === s && s.recorderStopped && !s.queue.length && !s.finishing) finish();
}

async function flushHints(final = false) {
  if (!state || !state.sessionId || !state.hints.length) return;
  while (state.hints.length) {
    const batch = state.hints.slice(0, HINT_BATCH);
    try {
      await api(`/api/meet/sessions/${state.sessionId}/hints`, { method: 'POST',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ events: batch }) });
      state.hints.splice(0, batch.length);
    } catch (error) {
      if (final) report({ warning: 'Some speaker hints could not be sent; those turns may be unlabelled.' });
      return; // keep for the next flush
    }
  }
}

async function finish() {
  const s = state;
  s.finishing = true;
  clearInterval(s.hintTimer);
  try {
    await flushHints(true);
    report({ state: 'processing', message: 'Uploading finished, starting transcription' });
    const job = await api(`/api/meet/sessions/${s.sessionId}/finish`, { method: 'POST' });
    for (;;) {
      const current = await api(`/api/ingestion/jobs/${job.id}`);
      report({ state: 'processing', message: current.message, progress: current.progress });
      if (current.status === 'completed') return done({ state: 'done', meetingId: current.meeting_id });
      if (current.status === 'failed') throw new Error(current.message);
      await sleep(POLL_MS);
    }
  } catch (error) {
    if (state === s) fail('Transcription failed: ' + error.message);
  }
}

function release() {
  if (!state) return;
  clearInterval(state.hintTimer);
  for (const stream of [state.tabStream, state.micStream]) if (stream) stream.getTracks().forEach((t) => t.stop());
  if (state.context) state.context.close().catch(() => {});
}

function done(update) {
  release();
  state = null;
  report(update);
}

function fail(message) {
  if (!state) return;
  const sessionId = state.sessionId;
  const backend = backendUrl;
  state.failed = true;
  try { if (state.recorder && state.recorder.state !== 'inactive') state.recorder.stop(); } catch (error) { /* already stopped */ }
  done({ state: 'error', error: message });
  if (sessionId) fetch(`${backend}/api/meet/sessions/${sessionId}`, { method: 'DELETE' }).catch(() => {});
}

function stop() {
  if (!state || state.stopping) return;
  state.stopping = true;
  report({ state: 'processing', message: 'Finishing upload' });
  if (state.recorder.state !== 'inactive') {
    state.recorder.stop();
  } else {
    state.recorderStopped = true;
    pump();
  }
}

chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (message.target === 'offscreen') {
    if (message.type === 'start') {
      start(message.config).then(() => respond({ ok: true }), (error) => {
        const reason = error && error.name === 'NotAllowedError' ? 'Tab audio capture was not permitted.' : error.message;
        done({ state: 'error', error: reason });
        respond({ ok: false, error: reason });
      });
      return true;
    }
    if (message.type === 'stop') stop();
  } else if (message.type === 'hints' && state && !state.failed && message.events) {
    state.hints.push(...message.events);
  }
});
