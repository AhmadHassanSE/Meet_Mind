// Service worker: starts and stops captures and keeps the state the popup shows.
// The recording itself lives in the offscreen document so this worker may sleep.
const OFFSCREEN_URL = 'offscreen.html';
const IDLE = { state: 'idle' };

async function getState() {
  const { capture } = await chrome.storage.session.get('capture');
  return capture || IDLE;
}

async function setState(update, replace = false) {
  const next = replace ? update : { ...(await getState()), ...update };
  await chrome.storage.session.set({ capture: next });
  const recording = next.state === 'recording';
  await chrome.action.setBadgeText({ text: recording ? 'REC' : next.state === 'processing' ? '...' : '' });
  await chrome.action.setBadgeBackgroundColor({ color: recording ? '#b3261e' : '#555555' });
  return next;
}

async function ensureOffscreen() {
  if (await chrome.offscreen.hasDocument()) return;
  await chrome.offscreen.createDocument({
    url: OFFSCREEN_URL,
    reasons: ['USER_MEDIA'],
    justification: 'Record Google Meet tab audio and the microphone for local transcription',
  });
}

async function closeOffscreen() {
  if (await chrome.offscreen.hasDocument()) await chrome.offscreen.closeDocument();
}

async function tellContent(tabId, type) {
  try { await chrome.tabs.sendMessage(tabId, { target: 'content', type }); } catch (error) { /* tab gone or not Meet */ }
}

async function startCapture(request) {
  const current = await getState();
  if (current.state === 'recording' || current.state === 'starting' || current.state === 'processing') {
    return { ok: false, error: 'A capture is already in progress.' };
  }
  await setState({ state: 'starting', tabId: request.tabId, title: request.title, error: '', warning: '' }, true);
  await ensureOffscreen();
  const result = await chrome.runtime.sendMessage({ target: 'offscreen', type: 'start', config: {
    streamId: request.streamId, backend: request.backend, title: request.title,
    selfName: request.selfName, meetingCode: request.meetingCode } });
  if (!result || !result.ok) {
    await setState({ state: 'error', error: (result && result.error) || 'Could not start recording.' });
    await closeOffscreen();
    return { ok: false, error: (result && result.error) || 'Could not start recording.' };
  }
  await tellContent(request.tabId, 'hints-start');
  return { ok: true };
}

async function stopCapture() {
  const current = await getState();
  if (current.tabId) await tellContent(current.tabId, 'hints-stop');
  await new Promise((resolve) => setTimeout(resolve, 600)); // let the final hints reach the recorder
  await setState({ state: 'processing', message: 'Finishing upload' });
  try { await chrome.runtime.sendMessage({ target: 'offscreen', type: 'stop' }); } catch (error) { /* already closed */ }
}

chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (message.target) return; // addressed to the offscreen document or a content script
  if (message.type === 'start') { startCapture(message).then(respond); return true; }
  if (message.type === 'stop') { stopCapture().then(() => respond({ ok: true })); return true; }
  if (message.type === 'get-state') { getState().then(respond); return true; }
  if (message.type === 'status') {
    (async () => {
      const { type, ...update } = message;
      const next = await setState(update);
      if (next.tabId && (next.state === 'done' || next.state === 'error')) await tellContent(next.tabId, 'hints-stop');
      if (next.state === 'done' || next.state === 'error') await closeOffscreen();
    })();
  }
});
