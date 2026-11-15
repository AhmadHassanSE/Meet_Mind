// Every Google Meet page selector or label lives here. Meet's markup is not a public API and
// changes without notice, so when speaker hints stop working this is the first file to fix.
// Prefer aria-label / role over generated class names. Verify these on a live meeting with DevTools.
globalThis.MeetMindSelectors = {
  // The live-caption region. The first selector that matches is used.
  captionRegion: [
    '[role="region"][aria-label^="Captions"]',
    '[role="region"][aria-label*="aption"]',
    'div[aria-label^="Captions"]',
  ],
  // Button that turns captions on; clicked only while its label says captions are off.
  captionToggleOn: /turn on captions/i,
  // Text that means a speaker block is not a caption line (UI hints inside the region).
  captionNoise: /^(captions?|language|font size|jump to bottom|turn off captions)/i,
  // How long after its last text change a caption speaker is still considered speaking (ms).
  holdMs: 1200,
  pollMs: 400,
};
