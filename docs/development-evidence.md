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

## 10 October 2026 — seven-file real transcript verification

Used actual file upload and Analyze with BERT on five deterministically selected
full AMI validation meetings plus two existing workspace reports. On 1,625
annotated AMI utterances, 900 labels were correct: accuracy 0.5538, macro F1
0.4070. This reuses a subset of validation and is not new test-set evidence;
final test remains untouched. Workspace reports have no verified labels, so no
accuracy is claimed for them.

Found and fixed missing truncation review flags and mobile overflow from long
report separators. Model weights/predicted labels remain unchanged. Reports
still need cleaning/segmentation; the truncation fix warns about partial input
coverage rather than recovering discarded text. Scores remain uncalibrated;
131 incorrect AMI labels were not flagged by the heuristic review rules.

After fixes, all seven files passed API source/persistence/export checks and
real Chrome upload/analysis/refresh/mobile checks. 31 tests and production build
passed. Compact evidence is in
`meetmind/backend/reports/real-meeting-audit-2026-10-10`; full local fixtures are
ignored. Private transcript text was not pushed. Work remains Codex-assisted at
Rana's direction under Rana's configured Git identity.

## 10 October 2026 ? transcript preparation

Rana Ahmad directed AI-assisted implementation on `feat/transcript-preprocessing`. Added conservative report cleanup, sentence/token segmentation, speaker/time parsing, exact source lineage, original-text downloads and UI source inspection. First checkpoint: `811aa8a`. Verified 38 backend tests, production build and seven complete API/browser cases. No final test data or new accuracy claim; segmentation changes invalidate direct comparison against old act boundaries. See `meetmind/backend/PREPROCESSING.md` and tracked compact audit evidence. Other members? work is not attributed by these commits.

## 10 October 2026 - structured commitment extraction

Rana Ahmad directed AI-assisted implementation on `feat/structured-commitments`. First pushed checkpoint `7143e84` added BERT-assisted local Ollama proposals, real spaCy parsing/NER, deadline token rules, exact quotation/source checks, owner resolution, and cancellation review flags. The second checkpoint adds evidence/candidate UI, additional validation cases, setup documentation and compact synthetic functional evidence. Verified 58 backend tests, frontend production build, four actual local BERT/spaCy/Ollama API cases and two real Chrome UI cases including persistence and mobile layout. These are synthetic functional checks, not held-out accuracy or F1. Existing AMI model/test split and weights were unchanged. All proposals require review; editing/approval and end-to-end labelled evaluation remain pending. Commits use the configured Rana identity; other members are not credited with this implementation.

## 10 October 2026 - full BERT-base experiment tooling

At the user's explicit request, new checkpoint commits on `feat/bert-base-comparison`
use author `samxxr200-glitch <samxxr200@gmail.com>` and pushes authenticate as that
GitHub account through device authorization. Implementation remains AI-assisted;
the identity does not imply the account owner manually wrote the code.

Checkpoint `26b2362` adds CUDA-required full-data configurations, FP16 training,
epoch resume state, validation-only comparison and experiment tests. The next
checkpoint provides Colab execution, byte-exact public AMI input export and GPU
evaluation. 66 local backend tests pass, including interrupted/resumed training
with exactly matching final weights on a small BERT fixture. Notebook code cells
compile but have not executed in Colab. The full BERT-base candidates have not
yet trained; no new F1 or superiority claim is made. The existing tiny pilot
remains active. The input package excludes final-test data and private meetings.
# Full BERT-base results imported: 10 October 2026

The user completed the Colab notebook on Tesla T4 and returned both fine-tuned
checkpoints. The 3e-5 candidate at epoch 3 won by validation macro F1 0.5292777,
versus 0.5235926 for 2e-5 and 0.4219068 for the earlier tiny pilot. Both full
candidates used 82,294 train rows and all 13,593 validation rows. No final-test
evaluation was performed. Hashes, architecture, per-class metric aggregation,
dataset identity and best-epoch history were checked on import.

The selected checkpoint is now the local default `models/dialogue-bert-base-v1`;
the pilot is preserved and `BERT_MODEL_PATH` supports explicit rollback. All 67
backend tests, real checkpoint API persistence checks, two real AMI-excerpt
Chrome checks and four synthetic local commitment checks passed. A local full
validation rerun did not complete while Windows reported paging-memory
exhaustion during concurrent checks. Full scores are the imported Colab
results, not a claimed independent local reproduction. See
`meetmind/backend/reports/bert-base-comparison-v1/` for compact evidence.

Implementation and validation were AI-assisted at the user's direction.
Commits use the explicitly authorized team account; this does not assert
that the named account holder manually authored the implementation.
# Commitment review implemented: 10 October 2026

Branch `feat/commitment-review` builds on the completed BERT-base comparison.
Added editable task/owner/deadline fields, approval/rejection, candidate promotion
and reopening, preserved originals/evidence, and dated before/after decision
history. Reviews persist in SQLite; stale item revisions return 409. Reviewed
meetings cannot be re-extracted in place, and in-flight classification/extraction
does not overwrite review decisions. Cancellation proposals cannot be approved
as tasks; a possible-cancellation action requires an approval note.

74 backend tests passed, the frontend built, and Chrome passed both deterministic
review checks and existing ingestion checks. Two real local NLP browser cases
also extracted and approved commitments, preserved evidence, and verified saved
approvals after refresh. CI includes the deterministic review browser suite.
Compact evidence is in `meetmind/backend/reports/commitment-review-2026-10-10/`.
These are functional checks, not an extraction accuracy benchmark. Reviewer
identity remains unauthenticated in this local workspace. Implementation and
validation were AI-assisted at the user's direction; the authorized account is
used for checkpoint commits without claiming manual authorship by its owner.

## 10 October 2026 - Google Meet capture extension

AI-assisted implementation on `feat/google-meet-integration`, pushed per checkpoint: speaker-hint alignment (`85a09fc`), backend capture session API (`ea50756`), caption-based speaker hints and the Chrome extension audio recorder (see branch history), and a Meet source note in the UI. Verified so far: 18 new backend tests (alignment and session API with a mocked transcriber), the existing backend suite unchanged, and the speaker-tracking logic in headless Chrome. Not yet verified: recording in a real Meet call, caption selectors against live markup, hint lag defaults and the frontend production build (Node was unavailable in the authoring environment). No accuracy claim is made for speaker attribution.

## 11 October 2026 - optional pyannote speaker separation for Meet capture

AI-assisted addition on `feat/google-meet-integration`: an optional `diarization` extra runs pyannote.audio (default `pyannote/speaker-diarization-community-1`) on the decoded Meet audio, names its voice clusters from the caption hints, and falls back to caption-hint labels if pyannote, its Hugging Face token or the model access is unavailable. Verified: 84 backend tests passed (alignment and session tests use a fake diarizer; no model was loaded) and the frontend production build passed. The real model was also run once on a 21-second synthetic recording of two Windows text-to-speech voices: it separated two clusters whose turn boundaries matched the script, taking about 24 seconds warm on CPU including model load. This is a functional check on synthetic speech, not an accuracy or speed benchmark. Not yet verified: a real Meet recording, memory and run time on long meetings, and speaker-label accuracy. No accuracy claim is made.

## 19 October 2026 ? Iteration 2 foundation

Integrated the current non-Meet BERT/multilingual core, teammate Whisper-small update and Meet extension/bot branch in an isolated worktree. Added a local Ollama/LangGraph email-drafting flow, explicit recipients, a small declarative approval policy, persistent revisioned drafts and separate content-bound human approval. Editing a draft or re-reviewing its source invalidates approval. 179 backend tests passed, including concurrency/idempotency/source and policy changes. Built browser checks use mocked APIs; a separate real Ollama/LangGraph smoke passed with synthetic English source data. No external messages were sent; auth/OAuth, delivery and full orchestration remain next work. The prior 0.5293 BERT validation score and pending GPU target are unchanged. AI-assisted implementation requires team review and ownership.
