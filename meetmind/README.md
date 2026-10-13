# MeetMind — Iteration 1

Fresh implementation. The sibling `meeting-transcription-agent` directory is reference only.

## Run locally (two PowerShell terminals)

Prerequisites: Node.js, uv, Python 3.13 (uv can provision it), FFmpeg on PATH, and Ollama running with `llama3.2:latest` installed. Run the commands below from the repository root in separate terminals.

Backend:
```powershell
cd meetmind/backend
$env:UV_PROJECT_ENVIRONMENT='.venv-nlp'
uv sync --extra nlp --group dev
# Supply the selected checkpoint as described in backend/BERT_BASE_COMPARISON.md.
uv run --extra nlp uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Frontend:
```powershell
cd meetmind/frontend
npm.cmd install
npm.cmd run dev
```

Open the localhost URL printed by Vite. Development requests proxy to the local backend. API documentation: http://127.0.0.1:8000/docs

Configuration: backend environment variables `OLLAMA_URL`, `OLLAMA_MODEL`, `MEETMIND_DB`, `WHISPER_MODEL`, `FFMPEG_PATH`. Defaults: localhost:11434, llama3.2:latest, backend/meetmind.db, base, ffmpeg. Frontend `MEETMIND_BACKEND_URL` overrides the development proxy target (default localhost:8000). No hosted AI provider or API key is used. Dependency/model downloads require internet; meeting transcription and extraction run locally. First media ingestion downloads Whisper weights if not cached, so prepare the model before an offline demo. A local model directory can be supplied as `WHISPER_MODEL`.

## Multilingual input

English, Urdu script, Roman Urdu and mixed transcripts are accepted. Use the Meeting language selector. Urdu/Roman Urdu analysis translates locally before English BERT; original text remains evidence. Install `ollama pull qwen3:4b` for the multilingual path. See [multilingual setup and evidence limits](backend/MULTILINGUAL.md).

## Current scope

### Commitment review

After extraction, choose **Review / edit** to correct task, owner and deadline,
then save for review, approve or reject. Original evidence and a dated decision
history remain available after refresh. Suggestions/requests need explicit
approval to become commitments; cancellation evidence requires careful review.
Reviewed meetings cannot be re-extracted in place: upload a new copy to preserve
your decisions. See [backend/COMMITMENTS.md](backend/COMMITMENTS.md) for the API
and review rules. Restart the backend and frontend after updating the code.

### Fine-tuned BERT (10 October update)

The primary dialogue-act classifier now has official AMI dataset preparation,
fine-tuning, validation-only checkpoint selection, baseline evaluation and a
local classifier endpoint/UI. See [backend/BERT.md](backend/BERT.md) for exact
setup and recorded experiment boundaries. Use the `nlp` extra and `.venv-nlp`
environment for BERT. Full BERT-base GPU training is complete: the selected
3e-5 candidate achieved validation macro F1 0.5293 versus the tiny pilot's
0.4219. The default checkpoint folder is `backend/models/dialogue-bert-base-v1`;
weights are distributed separately from Git. `BERT_MODEL_PATH` overrides it.
Restart the backend after installing the selected checkpoint. Dialogue-act labels
are kept separate from confirmed action commitments and Ollama extraction.

A new [BERT-base macro F1 improvement study](backend/BERT_F1_IMPROVEMENT.md)
provides three resumable Colab candidates targeting 0.73 macro F1 on the unchanged
15-class split. The target has not been measured as achieved; the current model
and its reported score remain unchanged until returned GPU results are verified.

The four upload tabs support:

| Input | Formats | Processing |
|---|---|---|
| Text / paste | Plain text | Normalize speaker turns |
| Transcript file | TXT, MD, DOCX, VTT, SRT | Extract text; retain available caption timing and speaker labels |
| Audio | WAV, MP3, M4A, OGG, FLAC, AAC | FFmpeg → mono 16 kHz PCM → local faster-whisper |
| Meeting recording | MP4, WEBM, MOV, MKV | Extract audio → same local transcription pipeline |

Transcript files: 2 MB maximum and 500,000 normalized characters. Pasted text: 500,000 characters. Media: 200 MB and two hours maximum. Actual codec support depends on the installed FFmpeg build. English and Urdu speech are supported through multilingual Whisper; select a language explicitly for short recordings and review mixed-language output. Audio/video speaker labels remain unknown; diarization and live Google Meet/Teams connections are future work. A silent recording or video without an audio track produces an explicit failure.

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
uv run python -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8')"
```

API: `POST /api/meetings` (pasted JSON); `POST /api/ingestion/transcript` and `/api/ingestion/media` (multipart `title` + `file`); `GET /api/ingestion/jobs/{id}`; `GET /api/meetings/{id}/transcript?format=txt|json|vtt`. Media uploads return HTTP 202; invalid uploads return 422, oversized media 413, full queue 429, and missing FFmpeg 503. Decoding/transcription failures are reported by the job's `failed` state, without creating an empty meeting.

AI-assisted code must be reviewed and understood by its owners; disclose assistance in the evaluation report. No research performance results are claimed yet.
