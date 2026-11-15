// Pure speaker-hint logic with no chrome.* dependency so it can be tested in a plain page.
(function () {
  const S = globalThis.MeetMindSelectors;

  function leafTexts(node) {
    const texts = [];
    const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT);
    let current;
    while ((current = walker.nextNode())) {
      const value = current.nodeValue.replace(/\s+/g, ' ').trim();
      if (value) texts.push({ value, parent: current.parentElement });
    }
    return texts;
  }

  // A caption block is a child of the region holding a speaker name followed by what they said.
  // Structure heuristic: first text leaf = speaker name, remaining leaves = spoken text.
  function parseCaptionBlocks(region) {
    const blocks = [];
    for (const child of region.children) {
      const texts = leafTexts(child).filter((item) => !S.captionNoise.test(item.value));
      if (texts.length < 2) continue;
      const name = texts[0].value;
      const text = texts.slice(1).map((item) => item.value).join(' ');
      if (name.length > 80 || !text) continue;
      blocks.push({ name, text });
    }
    return blocks;
  }

  function findCaptionRegion(root) {
    for (const selector of S.captionRegion) {
      const found = root.querySelector(selector);
      if (found) return found;
    }
    return null;
  }

  // Turns successive caption snapshots into {t, speaker, active} events. A speaker is active
  // while their caption text keeps changing and for holdMs afterwards.
  class SpeakerTracker {
    constructor(holdMs = S.holdMs) {
      this.holdMs = holdMs;
      this.lastText = new Map();
      this.lastChange = new Map();
      this.active = new Set();
    }

    update(blocks, now) {
      const events = [];
      const present = new Set();
      for (const { name, text } of blocks) {
        present.add(name);
        if (this.lastText.get(name) !== text) {
          this.lastText.set(name, text);
          this.lastChange.set(name, now);
          if (!this.active.has(name)) {
            this.active.add(name);
            events.push({ t: now, speaker: name, active: true });
          }
        }
      }
      for (const name of [...this.active]) {
        const changed = this.lastChange.get(name);
        if (!present.has(name)) {
          this.active.delete(name);
          this.lastText.delete(name);
          events.push({ t: Math.min(now, changed + this.holdMs), speaker: name, active: false });
        } else if (now - changed > this.holdMs) {
          this.active.delete(name);
          events.push({ t: changed + this.holdMs, speaker: name, active: false });
        }
      }
      return events;
    }

    flush(now) {
      const events = [...this.active].map((name) => ({ t: now, speaker: name, active: false }));
      this.active.clear();
      this.lastText.clear();
      return events;
    }
  }

  globalThis.MeetMindHints = { parseCaptionBlocks, findCaptionRegion, SpeakerTracker };
})();
