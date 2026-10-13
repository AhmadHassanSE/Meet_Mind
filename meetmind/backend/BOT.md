# Browser meeting bot and participant extension

Both approaches are retained on `feat/google-meet-integration`:

| Approach | Participant | Audio capture | Trigger |
|---|---|---|---|
| Chrome extension | The user's existing Meet tab | Tab audio plus optional microphone | Extension Start/Stop |
| Browser bot | A separate visible browser participant | Incoming WebRTC audio only; mic/camera denied | MeetMind Google Meet bot screen or CLI |

Both create the same `google_meet` meeting records through the existing ordered
audio-chunk, speaker-hint, FFmpeg/Whisper and preparation pipeline. Records now
include `capture_method` (`extension` or `browser_bot`) and optional `bot_id`.
This branch does not merge the later commitment-review or multilingual branches.

## Install and run

Google Chrome, FFmpeg and Python/uv must be installed. From `meetmind/backend`:

```powershell
$env:UV_PROJECT_ENVIRONMENT='.venv-nlp'
uv sync --extra nlp --extra bot --group dev
# Optional: point BERT_MODEL_PATH at your validated local classifier.
uv run --extra nlp --extra bot uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Start the frontend from `meetmind/frontend` with `npm.cmd run dev`, then choose
**Google Meet bot** in the sidebar. Enter a Meet URL, meeting title, guest bot name,
maximum duration and recording confirmation. The bot opens a separate browser,
asks to join if available, waits for host admission and then records. Use **Stop
and transcribe** to leave and queue transcription, or **Cancel and discard** to
leave and discard unfinished capture. Results open in the ordinary meeting UI.

Starting the bot is a user action. The host and participants must know audio is
being recorded. The bot does not send chat messages automatically. Its microphone
and camera are denied by Chrome permission controls; it captures other
participants' incoming audio, not the user's system sound or another tab.

## Dedicated Google account/profile

Guest admission depends on the meeting's access rules. If Google requires an
account, prepare a dedicated bot profile before joining. Stop active bots first,
then from backend:

```powershell
uv run --extra bot python -m scripts.setup_bot_profile
```

This opens **normal interactive Chrome**, without automating login. Sign in
manually to a dedicated account, complete any Google challenge yourself and close
the window. Later bot runs use that same isolated profile. Meet uses the signed-in
account's display name, so name the dedicated account appropriately and inform the
host. The guest-name field cannot rename a signed-in Google account.

The default profile is `backend/.bot-profile/`, ignored by Git. Never point it at
your everyday Chrome profile, copy cookies from another profile, commit it,
upload it, or run two browser processes against it. MeetMind does not ask for or
read passwords/verification codes and does not export cookies. The profile still
contains sensitive session data and must be treated as private. Google login,
CAPTCHA and access restrictions are not bypassed; a blocked account/session must
be resolved with Google/host settings rather than stealth flags.

The bot can pause at **needs login** for manual browser interaction and exposes
**Continue after sign-in**. An explicit Google rejection without an actionable
sign-in control fails the run instead of falsely reporting admission. Invalid or
expired meetings and restricted guest access need a new allowed meeting or an
invited signed-in account.

## API and states

- `GET /api/meet/bots/capabilities` — installed runtime/FFmpeg and browser choice.
- `POST /api/meet/bots` — start with `title`, `meeting_url`, `display_name`,
  `max_duration_minutes` and `consent_confirmed: true`.
- `GET /api/meet/bots` and `GET /api/meet/bots/{id}` — recent/persisted state.
- `POST /api/meet/bots/{id}/resume`, `/stop`, `/cancel` — explicit controls.

Typical flow:

```text
queued -> launching -> [needs_login] -> waiting_for_admission -> recording
       -> stopping -> transcribing -> completed
Any running stage can fail or be cancelled before transcription submission.
```

Only validated HTTPS `meet.google.com/abc-defg-hij` URLs are accepted; arbitrary
URLs, credentials, ports and redirect query strings are rejected. One active bot
uses the dedicated profile at a time. `meeting_bots(id, payload)` persists status,
history, counters and links to the shared ingestion job/meeting. Browser sessions
cannot resume after a backend restart; orphaned runs are marked failed. Once a
transcription job is submitted, cancel/review it through its own lifecycle rather
than pretending the browser can revoke a completed upload.

## Implementation and limitations

Playwright launches a visible Chrome participant. A script installed before Meet
navigation observes incoming `RTCPeerConnection` track events, mixes those audio
tracks with Web Audio and records WebM/Opus. It does not capture local senders or
desktop loopback. Audio is uploaded in order through an exposed binding limited
to the bot page, using the existing bounded capture API. The existing extension
caption selectors/tracker supply best-effort speaker activity hints; transcript
text still comes from local Whisper. Silence/no incoming tracks is not considered
a successful transcript. Recordings are bounded by the existing 200 MB/two-hour
limits; temporary media is deleted after completion/failure/cancellation.

Google Meet's UI and media implementation are not a stable public automation API.
DOM labels, media in workers/frames, account restrictions, device prompts, host
admission and network interruptions can break a run. The interface is targeted at
English Meet UI labels, and this branch's speech model remains English-only.
Speaker names/diarization remain best effort. There is no production auth/RBAC,
multi-host scheduling, reconnect/resume, public bot service or silent autonomous
admission. Use one backend process with loopback binding. Do not run the standalone
CLI concurrently with a backend using the same profile/capture storage.

Configuration (server environment only):

| Variable | Default / purpose |
|---|---|
| `MEETMIND_BOT_PROFILE` | Separate `backend/.bot-profile` directory |
| `MEETMIND_BOT_BROWSER` | `chrome`, the Playwright browser channel |
| `MEETMIND_BOT_CHROME_EXECUTABLE` | Optional normal Chrome executable for manual profile setup |
| `MEETMIND_BOT_JOIN_TIMEOUT` | 300 seconds for sign-in/admission |

After abrupt OS/process termination, close any orphaned bot browser manually
before retrying. Normal stop/cancel/server shutdown attempts to leave and close
the browser. Session histories are retained in the local DB; raw recordings and
browser profiles are excluded from Git/release bundles.

## Verification

```powershell
# Backend unit/integration tests (browser is faked in lifecycle tests):
uv run --extra nlp --extra bot --group dev python -m pytest -q
# Real Chrome, local WebRTC speech, MediaRecorder, API and real Whisper; no Google call:
uv run --extra nlp --extra bot python -m scripts.smoke_bot_browser path/to/short-speech.wav
# Authorized live call, host admission required; stops after 20 seconds of recording:
uv run --extra nlp --extra bot python -m scripts.run_meet_bot https://meet.google.com/abc-defg-hij --confirm-recording --seconds 20
```

Frontend: `npm.cmd run build`, then `node scripts/smoke-bot-ui.cjs`. This browser
check mocks API responses and tests consent, start, login resume, refresh recovery,
stop, transcript link and narrow layout. It is not a live Google Meet test.

The local real-audio smoke passed with 12 seconds of captured incoming WebRTC
speech and a four-segment saved transcript. Initial live attempts reached Google
but were rejected before admission, including a retry after the user confirmed
dedicated-account sign-in; they did not validate live capture. Native local
fixtures, synthetic lifecycle tests and real Google meetings are reported
separately; no diarization/ASR accuracy score is claimed.

Primary references:
- [Playwright persistent browser contexts](https://playwright.dev/python/docs/api/class-browsertype#browser-type-launch-persistent-context)
- [Chrome permissions protocol](https://chromedevtools.github.io/devtools-protocol/tot/Browser/#method-setPermission)
- [W3C WebRTC incoming track events](https://www.w3.org/TR/webrtc/#event-track)

AI-assisted implementation must be reviewed and understood by its team owner.
