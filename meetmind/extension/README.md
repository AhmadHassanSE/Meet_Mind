# MeetMind Capture (Chrome extension)

Records the audio of a Google Meet tab plus your microphone and sends it to your local MeetMind backend. Speaker names come from hints read off Meet's live captions; the transcript text itself comes from local Whisper, so it does not depend on Meet's page markup.

## Install (developer mode)

1. Start the backend (`uv run uvicorn app.main:app --host 127.0.0.1 --port 8000`, see `meetmind/README.md`). FFmpeg must be on PATH.
2. Open `chrome://extensions`, enable **Developer mode**, choose **Load unpacked** and select this `extension` folder.
3. Join a Google Meet in a tab. **Use headphones**: speaker output re-enters your microphone and gets transcribed twice.
4. Click the MeetMind Capture toolbar icon. The first time, a tab asks for microphone access; grant it and press Start again.
5. Check the title and your name (Meet shows your own speech as "You"; your name replaces it), then **Start recording**. A red banner appears on the Meet page and the badge shows REC. Captions are switched on automatically; leave them on.
6. When the meeting ends, press **Stop and transcribe**. Progress is shown in the popup; the meeting then appears in the MeetMind workspace.

## How it works

- `offscreen.js` mixes tab audio (everyone else) with the mic, records WebM/Opus in 10 s chunks and uploads them in order with retries. Tab audio is played back so you still hear the call.
- `content.js` reads the caption region, tracks which named speaker's text is changing, and sends only `{time, speaker, active}` events. Caption text is never sent.
- The backend aligns Whisper segments with those speaker intervals (`app/connectors/alignment.py`). Segments with no clear speaker stay "Unknown speaker" instead of guessing.

## Limits

- Chrome only; one capture at a time; the Meet tab must stay open.
- Transcription runs after you stop (local Whisper on CPU, up to 2 hours per meeting).
- Speaker labels are best effort. Overlapping speech and caption lag cause mislabels or unknown speakers; tune `MEETMIND_MEET_LAG_MS`.
- If Google changes Meet's markup, speaker hints may stop working (the transcript still works, with unknown speakers). Fix `selectors.js` (and `hints_core.js` if the caption block layout changes); check the selectors on a live meeting with DevTools.
- Changing the backend URL asks Chrome for permission to reach it. Only use a backend you trust.

## Tests

`powershell -File test/run.ps1` runs the speaker-tracking tests in headless Chrome (open `test/hints.test.html` in Chrome to see failures). Backend: `uv run pytest` from `meetmind/backend`.
