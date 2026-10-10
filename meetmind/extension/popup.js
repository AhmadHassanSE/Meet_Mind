const $ = (id) => document.getElementById(id);
const MEET_CODE = /^\/([a-z]{3}-[a-z]{4}-[a-z]{3})(?:$|[/?])/;

function setStatus(text, error = false) {
  $('status').textContent = text;
  $('status').classList.toggle('error', error);
}

async function loadSettings() {
  const saved = await chrome.storage.local.get(['backend', 'selfName']);
  if (saved.backend) $('backend').value = saved.backend;
  if (saved.selfName) $('self').value = saved.selfName;
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const code = tab && tab.url ? meetingCode(tab.url) : '';
  $('title').value = code ? `Google Meet ${code} ${new Date().toISOString().slice(0, 10)}` : '';
}

function meetingCode(url) {
  try {
    const parsed = new URL(url);
    if (parsed.origin !== 'https://meet.google.com') return '';
    const match = MEET_CODE.exec(parsed.pathname + '/');
    return match ? match[1] : '';
  } catch (error) {
    return '';
  }
}

function render(current) {
  const busy = ['starting', 'recording', 'processing'].includes(current.state);
  $('start').hidden = busy;
  $('stop').hidden = !(current.state === 'recording');
  for (const id of ['title', 'self', 'backend']) $(id).disabled = busy;
  $('warning').textContent = current.warning || '';
  if (current.state === 'recording') setStatus('Recording. Keep this Meet tab open; captions are switched on automatically.');
  else if (current.state === 'starting') setStatus('Starting...');
  else if (current.state === 'processing') setStatus(`${current.message || 'Processing'}${current.progress ? ` (${current.progress}%)` : ''}`);
  else if (current.state === 'done') setStatus('Done. Open MeetMind to see the meeting.');
  else if (current.state === 'error') setStatus(current.error || 'Something went wrong.', true);
  else setStatus('Ready. Open a Google Meet call, then press Start.');
}

async function micGranted() {
  try {
    return (await navigator.permissions.query({ name: 'microphone' })).state === 'granted';
  } catch (error) {
    return false;
  }
}

async function ensureBackendPermission(origin) {
  const granted = await chrome.permissions.contains({ origins: [origin + '/*'] });
  return granted || chrome.permissions.request({ origins: [origin + '/*'] });
}

async function start() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const code = tab && tab.url ? meetingCode(tab.url) : '';
  if (!code) return setStatus('Open a Google Meet call (meet.google.com/abc-defg-hij) in this tab first.', true);
  const title = $('title').value.trim();
  if (!title) return setStatus('Enter a meeting title.', true);
  let backend;
  try {
    backend = new URL($('backend').value.trim()).origin;
  } catch (error) {
    return setStatus('Backend URL is invalid.', true);
  }
  if (!(await ensureBackendPermission(backend))) return setStatus('Permission to reach the backend was denied.', true);
  try {
    const response = await fetch(backend + '/api/health');
    if (!response.ok) throw new Error('bad status');
  } catch (error) {
    return setStatus('MeetMind backend is not reachable at ' + backend, true);
  }
  if (!(await micGranted())) {
    setStatus('Microphone access is needed once. A permission tab was opened; grant it and press Start again.', true);
    return chrome.tabs.create({ url: chrome.runtime.getURL('permissions.html') });
  }
  await chrome.storage.local.set({ backend, selfName: $('self').value.trim() });
  try {
    const streamId = await chrome.tabCapture.getMediaStreamId({ targetTabId: tab.id });
    const result = await chrome.runtime.sendMessage({ type: 'start', tabId: tab.id, streamId, backend, title,
      selfName: $('self').value.trim(), meetingCode: code });
    if (!result.ok) setStatus(result.error, true);
  } catch (error) {
    setStatus('Could not capture this tab: ' + error.message, true);
  }
}

$('start').addEventListener('click', start);
$('stop').addEventListener('click', async () => {
  $('stop').disabled = true;
  await chrome.runtime.sendMessage({ type: 'stop' });
  $('stop').disabled = false;
});

async function refresh() { render(await chrome.runtime.sendMessage({ type: 'get-state' })); }
chrome.storage.session.onChanged.addListener(refresh);
loadSettings().then(refresh);
