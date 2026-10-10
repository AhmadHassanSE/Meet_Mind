# Development evidence

## 9 October 2026 — fresh Ollama foundation

This implementation was created with Codex assistance at Rana's direction. The initial commit uses the configured local Git identity; it does not represent independent implementation by all three members. Team members must review and understand code before claiming ownership in their report.

Implemented: React/TypeScript supporting UI, FastAPI local backend, TXT/basic VTT ingestion, SQLite persistence, structured source-linked extraction through local `llama3.2:latest`, model health status and input/error handling.

Observed checks before repository packaging:

- Two backend pytest tests passed: ingestion/persistence/missing record; blank input/basic VTT handling.
- Frontend TypeScript check and Vite production build passed.
- A real local Ollama smoke request extracted `Send the project report`, owner `Sara`, deadline `Friday`, source utterance 1. The first prompt missed this commitment; a first-person example was added and the rerun succeeded. This single example is not an extraction accuracy evaluation.
- Database connection cleanup was fixed after Windows exposed an open-handle issue during smoke-test cleanup.

Pending: review/edit persistence, AMI annotation/splits, baseline F1, BERT fine-tuning, spaCy, confidence evaluation, robust VTT parsing, broader tests and browser interaction validation. No external actions execute. SQLite is a temporary local choice; PostgreSQL remains the proposal target.

The reference prototype at the repository root remains separate from the active `meetmind/` implementation. Record future checks and each member's actual contributions in their PRs and milestone logs.

## 9 October 2026 — unified ingestion checkpoints

Branch: `feat/unified-ingestion`. Work performed with Codex assistance at Rana's direction; commits use Rana's configured identity, not simulated member identities.

- Checkpoint 1 (`f1aac0b`): TXT/MD/DOCX and timestamped VTT/SRT upload/parser. Twelve tests passed before push.
- Checkpoint 2 (`c4b6cf4`): background audio/video transcription, persisted job states, bounded queue and upload/duration limits, transcript exports, and chunked Ollama extraction. Twenty backend tests passed before push. At that checkpoint media lifecycle tests used a fake transcriber; real model verification followed.
- Integration checkpoint: four upload tabs, drag/drop, media preview, real job polling, refresh recovery, evidence timestamps and download links. Twenty-one backend tests and TypeScript/Vite build passed. Browser checks verified caption upload/timestamps, refresh persistence, invalid-file errors, 390px layout without horizontal overflow and a real audio upload through to the transcript view.
- Real API smoke check used Windows-generated speech as WAV and an FFmpeg-produced MP4 with that audio, with an isolated test database. Both traversed FFmpeg and local `base.en` Whisper and returned timestamped segments; TXT/JSON/VTT downloads succeeded. Whisper rendered fixture name Sara as Sarah. This is functional validation, not WER or extraction-quality evaluation.
- The real media check found a PyAV/faster-whisper decoder argument incompatibility. Fixed by passing the already-decoded mono 16 kHz PCM float samples directly to Whisper. The nested frontend also inherited the reference project's PostCSS config; scoped its config to avoid that dependency.
- Additional real decoder/model checks passed for MP3, M4A, OGG, FLAC, AAC, MOV, MKV and WEBM, each generated from the same short speech fixture. Real silent WAV and audio-free MP4 jobs failed with clear messages and no saved meetings. This verifies the supported fixture/container paths, not arbitrary codec combinations.
- The browser-ingested WAV transcript was passed to local Ollama, which returned both fixture commitments with valid source IDs (report by Friday; room booking next Monday). This also preserved Whisper's Sara/Sarah transcription difference, reinforcing the need for review and later quality evaluation.

Known boundaries: English only, unknown audio/video speakers, no live Meet/Teams connection or cancellation, one backend worker process, no job resume after backend restart, possible OS temporary-file leftovers after forced termination, no speech/extraction accuracy benchmark. Transcript size and context-boundary limits are documented in the application README.

## 10 October 2026 — fine-tuned BERT dialogue classifier

User confirmed BERT as the primary dialogue-act classifier. Branch:
`feat/bert-dialogue-classifier`; first checkpoint `debe0eb` adds official AMI
preparation, training/evaluation and local serving. Work is Codex-assisted at
Rana's direction using Rana's configured identity, not independent member work.

Prepared official AMI v1.6.2 manual dialogue-act annotations with a custom
session-group-disjoint split: 82,294 / 13,593 / 14,882 examples from 99 / 19 / 21
meetings. Corpus-authored labels are not claimed as new team annotations.

Completed a CPU pilot fine-tuning Google's 2-layer/128-hidden BERT on 24,000
training examples, five epochs, all encoder/head parameters. Best epoch 5:
validation macro F1 0.4219 versus initial TF-IDF/logistic baseline 0.2989 and
majority 0.0296. Validation accuracy 0.5724. Final test remains unused, reserved
for the selected full model. See `meetmind/backend/reports/bert-tiny-pilot-v1`
for provenance, per-class scores, confusion matrix and limitations.

Implemented independent dialogue analysis API/UI, score/margin review flags,
local-only validated checkpoint loading, weights fingerprinting, persistence and
validation-only checkpoint selection. Dialogue acts do not automatically become
confirmed action items. Ollama extraction remains separate and optional.

30 backend tests passed; TypeScript/Vite production build passed. Real model
smoke checked API/persistence/stable inference. Browser verified real BERT
results, refresh and mobile behavior. Initial cold loading exceeded a 60-second
browser wait; completed later and warm rerun passed. Browser cold allowance is
now three minutes; no latency guarantee is claimed.
The browser check also passed after restarting the isolated test backend with
the updated allowance. Test servers used ports 8012/5182 and a separate database.

Full BERT-base training has not run. Configuration and an unexecuted portable
GPU notebook are provided for validation-only hyperparameter comparison.
Remaining: stronger/full-model training, final frozen-test evaluation,
commitment-specific labels/evaluation, spaCy/owner/deadline rules, editable
corrections and confidence calibration. AMI dialogue-act metrics are not
end-to-end task accuracy. Source code is pushed; ignored weights remain local.
