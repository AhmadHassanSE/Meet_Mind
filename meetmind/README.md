# MeetMind — Iteration 1

Fresh implementation. The sibling `meeting-transcription-agent` directory is reference only.

## Run locally (two PowerShell terminals)

Prerequisites: Node.js, uv, Python 3.13 (uv can provision it), FFmpeg on PATH, and Ollama running with `llama3.2:latest` installed. Run the commands below from the repository root in separate terminals.

Backend:
```powershell
cd meetmind/backend
$env:UV_PROJECT_ENVIRONMENT='.venv-nlp'
uv sync --extra nlp --group dev
uv run --extra nlp uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Frontend:
```powershell
cd meetmind/frontend
npm.cmd install
npm.cmd run dev
```

Open the localhost URL printed by Vite. Development requests proxy to the local backend. API documentation: http://127.0.0.1:8000/docs

Configuration: backend environment variables `OLLAMA_URL`, `OLLAMA_MODEL`, `MEETMIND_DB`, `WHISPER_MODEL`, `FFMPEG_PATH`. Defaults: localhost:11434, llama3.2:latest, backend/meetmind.db, base.en, ffmpeg. Frontend `MEETMIND_BACKEND_URL` overrides the development proxy target (default localhost:8000). No hosted AI provider or API key is used. Dependency/model downloads require internet; meeting transcription and extraction run locally. First media ingestion downloads Whisper weights if not cached, so prepare the model before an offline demo. A local model directory can be supplied as `WHISPER_MODEL`.

## Google Meet capture (Chrome extension)

The `extension/` folder is a Chrome (116+) extension that records a Google Meet tab and sends it to the local backend. No Google account integration or API key is needed, so it works with free Gmail. The tab audio and your microphone are mixed and uploaded in chunks to `POST /api/meet/sessions/...`; when you stop, the backend transcribes locally with Whisper, labels speakers from hints read off Meet's live captions, and saves a `google_meet` meeting you can classify and extract like any other. See `extension/README.md` for setup and limits.

Extra configuration: `MEETMIND_MEET_LAG_MS` (default 500, how long Meet captions lag behind speech) and `MEETMIND_MEET_MIN_CONFIDENCE` (default 0.4, minimum overlap margin before a speaker name is attached; below it the utterance stays "Unknown speaker").

### Speaker separation with pyannote (optional fallback)

By default the caption hints (who Meet shows as speaking) label segments directly. With the `diarization` extra, pyannote.audio acts as a fallback: it runs only when there are no hints, or when more than 30% of segments stay unattributed. It groups the recording into distinct voices, and the hints then only name each voice. This gives separate "Speaker 1, Speaker 2" labels even when no names match.

```powershell
uv sync --extra nlp --extra diarization --group dev
uv run --extra nlp --extra diarization uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The default model `pyannote/speaker-diarization-community-1` is gated: open its page on Hugging Face and accept the conditions, create a read token, then set `HF_TOKEN` (or run `hf auth login`) before starting the backend. If pyannote or the token is missing, or it fails, the meeting still saves with caption-hint labels and the meeting page says why. Configuration: `MEETMIND_DIARIZATION` (`auto` default = fallback only, `always` = run on every meeting, `off` to disable), `MEETMIND_MEET_FALLBACK_UNATTRIBUTED` (default `0.3`, unattributed share that triggers the fallback), `MEETMIND_DIARIZATION_MODEL`, `MEETMIND_MAX_SPEAKERS` (optional upper bound). When it runs, it runs on CPU after transcription, loads the model per meeting and frees it afterwards, so expect extra minutes and memory for long meetings. A Whisper segment is assigned to one speaker, so a long segment containing two voices takes the dominant one.

Recording other people needs their knowledge. The extension shows a red banner on the Meet page and a REC badge while it records; tell participants before you start.

## Browser meeting bot

A separate browser participant is now available alongside the extension. Install the backend `bot` extra and use **Google Meet bot** in the sidebar. Host admission and, where required, manual sign-in to a dedicated bot account are required. See [browser bot setup, API and validation limits](backend/BOT.md).

## Current scope

### Fine-tuned BERT (10 October update)

The primary dialogue-act classifier now has official AMI dataset preparation,
fine-tuning, validation-only checkpoint selection, baseline evaluation and a
local classifier endpoint/UI. See [backend/BERT.md](backend/BERT.md) for exact
setup and recorded experiment boundaries. Use the `nlp` extra and `.venv-nlp`
environment for BERT. CPU pilot training is distinct from the full BERT-base
candidate; a configuration alone is not a trained model. Dialogue-act labels
are kept separate from confirmed action commitments and Ollama extraction.

The four upload tabs support:

| Input | Formats | Processing |
|---|---|---|
| Text / paste | Plain text | Normalize speaker turns |
| Transcript file | TXT, MD, DOCX, VTT, SRT | Extract text; retain available caption timing and speaker labels |
| Audio | WAV, MP3, M4A, OGG, FLAC, AAC | FFmpeg → mono 16 kHz PCM → local faster-whisper |
| Meeting recording | MP4, WEBM, MOV, MKV | Extract audio → same local transcription pipeline |

Transcript files: 2 MB maximum and 500,000 normalized characters. Pasted text: 500,000 characters. Media: 200 MB and two hours maximum. Actual codec support depends on the installed FFmpeg build. Only English speech is currently supported. Audio/video speaker labels remain unknown; diarization and live Google Meet/Teams connections are future work. A silent recording or video without an audio track produces an explicit failure.

Jobs are queued (one worker, three total admitted jobs), decoded, transcribed and saved. Polling progress comes from real backend stages/decoded time, not a simulated timer. Active job IDs survive browser refresh via localStorage. Restarting the backend marks unfinished jobs failed; re-upload is required (jobs do not auto-resume). Temporary media is deleted when a job finishes or fails; forced process termination may leave OS temporary files. Original recordings are not retained in the application database. Use a single backend process, without multiple workers, for this local job implementation. Cancellation is not implemented.

All paths produce the same transcript segment fields: `id`, `speaker`, `text`, `source`, `start`, `end`, plus source lineage. New meetings preserve the original transcript and prepare sentence-sized utterances before analysis. See [transcript preparation](backend/PREPROCESSING.md) for report cleaning, token budgets, offsets and evidence. Meeting metadata includes source type, original filename and transcription model/duration where applicable. TXT/JSON/original-text exports are available for every meeting; VTT export requires positive timestamp ranges on all segments.

SQLite persistence, meeting library/detail, health status and structured local extraction remain available. Extraction now combines BERT signals, spaCy owner/deadline evidence and Ollama proposals, with quoted sources and conservative cancellation checks. Suggestions, requests and cancellations are displayed separately. See [structured commitments](backend/COMMITMENTS.md) for setup, fields, tests and limitations. Results require review; source validation does not guarantee semantic correctness. Successful re-extraction replaces previous results. Owner/deadline editing, approval/rejection, calibrated confidence and commitment-specific annotation/evaluation remain pending. Separate AMI dialogue-act training and evaluation are documented in BERT.md. No external actions execute.

Fine-tuned BERT is the primary dialogue-act classifier following the user's confirmed decision. Ollama remains the optional local commitment extractor and does not replace BERT. SQLite is a temporary local foundation; PostgreSQL remains the proposed relational target. No authentication or production deployment is included.

## Checks
```powershell
cd backend
uv run pytest
cd ..\frontend
npm.cmd run build
```

For real decoder/model smoke checks, from `meetmind/backend` run:
```powershell
uv run python -m scripts.smoke_media path/to/speech.wav path/to/recording.mp4
```
This uses an isolated temporary database and checks real media jobs plus transcript downloads. Use short, non-sensitive fixtures with speech. It is not an accuracy benchmark.

For browser smoke checks, start backend/frontend against a dedicated test database (`MEETMIND_DB`), then from `meetmind/frontend` run `node scripts/smoke-ui.cjs`. Google Chrome is required. `MEETMIND_UI_URL` selects the frontend URL. This creates a fixture meeting in that database; it verifies caption upload, timing, persistence, validation and narrow-screen layout. Optionally set `MEETMIND_MEDIA_FIXTURE` to a short speech WAV containing "send the project report by Friday" to exercise actual media transcription through the browser as well.

Prepare Whisper before evaluation (backend directory):
```powershell
uv run python -c "from faster_whisper import WhisperModel; WhisperModel('base.en', device='cpu', compute_type='int8')"
```

API: `POST /api/meetings` (pasted JSON); `POST /api/ingestion/transcript` and `/api/ingestion/media` (multipart `title` + `file`); `GET /api/ingestion/jobs/{id}`; `GET /api/meetings/{id}/transcript?format=txt|json|vtt`. Media uploads return HTTP 202; invalid uploads return 422, oversized media 413, full queue 429, and missing FFmpeg 503. Decoding/transcription failures are reported by the job's `failed` state, without creating an empty meeting.

AI-assisted code must be reviewed and understood by its owners; disclose assistance in the evaluation report. No research performance results are claimed yet.
