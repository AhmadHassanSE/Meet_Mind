// Runs on meet.google.com. While a capture is active it turns the live captions into speaker
// hints and sends them to the extension; it never reads or sends caption text.
(function () {
  const S = globalThis.MeetMindSelectors;
  const H = globalThis.MeetMindHints;
  let timer = null;
  let tracker = null;
  let banner = null;
  let captionsTried = false;

  function showBanner(on) {
    if (!on) {
      if (banner) banner.remove();
      banner = null;
      return;
    }
    if (banner) return;
    banner = document.createElement('div');
    banner.textContent = 'MeetMind is recording this meeting\'s audio for local transcription';
    banner.setAttribute('role', 'status');
    banner.style.cssText = 'position:fixed;left:12px;bottom:84px;z-index:2147483647;padding:6px 10px;' +
      'background:#b3261e;color:#fff;font:12px/1.3 sans-serif;border-radius:6px;pointer-events:none';
    document.documentElement.appendChild(banner);
  }

  function enableCaptions() {
    if (captionsTried) return;
    for (const button of document.querySelectorAll('button[aria-label]')) {
      if (S.captionToggleOn.test(button.getAttribute('aria-label'))) {
        captionsTried = true;
        button.click();
        return;
      }
    }
  }

  function send(events) {
    if (events.length) chrome.runtime.sendMessage({ type: 'hints', events }).catch(() => {});
  }

  function tick() {
    enableCaptions();
    const region = H.findCaptionRegion(document);
    if (!region) return;
    send(tracker.update(H.parseCaptionBlocks(region), Date.now()));
  }

  function start() {
    if (timer) return;
    tracker = new H.SpeakerTracker();
    captionsTried = false;
    timer = setInterval(tick, S.pollMs);
    showBanner(true);
  }

  function stop() {
    if (!timer) return;
    clearInterval(timer);
    timer = null;
    send(tracker.flush(Date.now()));
    showBanner(false);
  }

  chrome.runtime.onMessage.addListener((message) => {
    if (message && message.target === 'content') {
      if (message.type === 'hints-start') start();
      if (message.type === 'hints-stop') stop();
    }
  });
})();
