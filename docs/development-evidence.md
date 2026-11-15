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
validation macro F1 0.4219 versus initial TF-IDF/logistic baseline 0.2989 (fit on
the same 24,000-row pilot sample; the baseline matched to BERT-base is 0.3081) and
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

## 10 October 2026 - transcript preparation

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

## 19 October 2026 - Iteration 2 foundation

Integrated the current non-Meet BERT/multilingual core, teammate Whisper-small update and Meet extension/bot branch in an isolated worktree. Added a local Ollama/LangGraph email-drafting flow, explicit recipients, a small declarative approval policy, persistent revisioned drafts and separate content-bound human approval. Editing a draft or re-reviewing its source invalidates approval. 179 backend tests passed, including concurrency/idempotency/source and policy changes. Built browser checks use mocked APIs; a separate real Ollama/LangGraph smoke passed with synthetic English source data. No external messages were sent; auth/OAuth, delivery and full orchestration remain next work. The prior 0.5293 BERT validation score and pending GPU target are unchanged. AI-assisted implementation requires team review and ownership.

## 5 November 2026 - accounts, roles and approval queue

AI-assisted (Claude Code) on `feat/auth-rbac`: local accounts with scrypt passwords and HttpOnly sessions; Admin, Organizer (admin-approved request), Member and per-item Owner roles; every API route requires sign-in (a test walks the OpenAPI schema); meetings, jobs, captures and bots record their creator; the item owner approves follow-up drafts and admin overrides need a recorded reason; capture tokens for the Chrome extension and a short-lived token for the browser bot. Frontend gained sign-in, role-aware pages, "My approvals", Account and Admin pages. Verified: 197 backend tests passed; browser smoke checks including a new member -> organizer -> owner flow passed against a real backend; GitHub Actions run on `71d9a3d` succeeded.

## 14 November 2026 - held-out BERT test evaluation and rule baseline

Evaluated the frozen BERT-base winner (weights `5a70014d...`) once on the untouched AMI test split (14,882 utterances, 21 meetings): accuracy 0.6632, macro F1 0.5271, weighted F1 0.6623. Same rows: TF-IDF + logistic regression macro F1 0.3264, keyword rules 0.2608 (new `nlp/rules.py`, not fitted to data), majority 0.0330. The 0.73 macro F1 target is not achieved. Details, per-class scores and error analysis: `meetmind/backend/reports/bert-base-test-v1`. Also corrected stale statements in `BERT.md` and labelled the 10 October real-meeting audit as tiny-pilot only. AI-assisted (Claude Code); results come from real runs recorded with their commands.

## 14 November 2026 - extraction and capture defects from the audit

AI-assisted (Claude Code) on `fix/extraction-audit`. An internal audit found that any negation (for example "don't worry") turned a real commitment into an unapprovable cancellation, that discourse words such as "Okay" became owners, that "Note:"-style headings and clock times became speakers, that several dates erased a supported deadline, and that abandoned Meet capture sessions could block recording until restart. Fixed: negation now counts only when it applies to the task's own verb; Roman Urdu "nai" (new) and reassurances are not negation; discourse words are never owners and unverified vocative names are flagged; headings are not speakers; alternatives ("Monday or Friday") still leave the deadline open; capture sessions expire when idle, cannot be cancelled during transcription and stream audio with a size cap; classify/extract return 404 if the meeting is deleted mid-run. 27 regression tests use the audit's sentences; 19 of them fail on the previous code. Backend suite: 242 passed.

## 14 November 2026 - LangGraph meeting workflow (WP4)

AI-assisted (Claude Code) on `feat/meeting-orchestrator`. One LangGraph run per meeting: extract, pause for the organizer's commitment review (who also confirms recipients), draft, policy check, pause until every owner has decided, then execute only drafts with a still-valid approval. State is checkpointed in SQLite (`langgraph-checkpoint-sqlite`), so paused runs survive restarts and failed steps are retried from the last completed step. No connector exists yet, so execution is recorded as "not configured; nothing was sent". Verified: 249 backend tests (7 new workflow tests with real accounts, a fake extraction step and a fake model); mocked and real-backend browser checks passed, including the new workflow panel. Ollama was offline, so the browser run confirmed the visible failure and retry at the draft step; the full drafting path is covered by the backend tests with a fake model. See `meetmind/backend/WORKFLOW.md`.

## 14 November 2026 - policy rules engine (WP7)

AI-assisted (Claude Code) on `feat/policy-engine`. The follow-up policy is now evaluated rule by rule instead of partly hard-coded: channel allowlist (email, jira), the three mandatory safety rules, allowed/denied/internal domains, a recipient limit, who must approve (owner or organizer), whether execution must use the approver's account, and a second, different approver for recipients outside the organization (partial approvals are cleared by any edit). Unknown or malformed rules fail closed with the line number. An invalid policy file now blocks approvals but no longer hides the drafts list. Verified: 262 backend tests passed (13 new policy tests, including two-person approval with real accounts); mocked drafts browser check passed.

## 14 November 2026 - Gmail sending (WP5, live check pending)

AI-assisted (Claude Code) on `feat/gmail-send`. Per-user Google OAuth (PKCE, single-use state, `gmail.send` only) with refresh tokens encrypted at rest; approved drafts are sent at most once from the approver's account, from the workflow or with "Send now". Delivery state (`sent` with Gmail message id, `failed`, `not_configured`), limited retries on temporary errors, token refresh, revoke on disconnect and audit events. A send interrupted by a restart is reported, never repeated automatically. Verified: 272 backend tests passed (10 new Gmail tests against simulated Google endpoints); mocked drafts browser check passed. **Not yet verified:** a live send with a real Google account, because the team's OAuth client is not configured yet. See `meetmind/backend/GMAIL.md`.

## 14 November 2026 - Jira tickets (WP6, live check pending)

AI-assisted (Claude Code) on `feat/jira`. Admin connects one Jira Cloud site (validated token and project, token encrypted); users are mapped to Jira accounts by unique email match. Ticket drafts are generated by LangGraph `draft_ticket -> validate_ticket` nodes; project and assignee (the human-linked owner's Jira account) are fixed at drafting and covered by the approval hash. Approved tickets are created once through the shared delivery path, from the workflow or "Create issue now", with retries on temporary errors. The policy must allow the `jira` channel. Verified: 279 backend tests passed (7 new Jira tests against a simulated Jira Cloud, including a workflow ticket); mocked and real-backend browser checks passed. **Not yet verified:** a live issue on a real Jira site. See `meetmind/backend/JIRA.md`.

## 15 November 2026 - evaluation tooling, design overview and documentation refresh

AI-assisted (Claude Code) on `docs/mid1-refresh`.
- Team annotation kit: `meetmind/backend/evaluation/GUIDELINE.md`, `scripts/annotation_sample.py` (stratified test-split sample, hidden AMI key) and `scripts/annotation_score.py` (raw agreement, Cohen's kappa, each annotator vs AMI, disagreement log).
- End-to-end extraction scorer `scripts/score_extraction.py`: commitment P/R/F1, kind, owner and deadline accuracy with explicit matching rules. One synthetic format example is included and marked as such; **no team labels or end-to-end scores exist yet**.
- `docs/design/DESIGN.md`: component diagram, ERD of all 16 tables, sequence and state diagrams, FR/NFR traceability to code and tests, and a proposal-versus-implementation table for mentor sign-off. `docs/DEMO.md` is the live demo script.
- Stale statements corrected in the READMEs, ARTIFACTS.md, MULTILINGUAL.md and PREPROCESSING.md.

Verified: 325 backend tests passed locally. GitHub Actions did not run on the 14 Nov pushes: the account is locked for billing ("The job was not started because your account is locked due to a billing issue"), so no CI result exists for those commits.

## 15 November 2026 - BERT confidence calibration

Temperature scaling fitted on validation only (T = 1.2281) for the selected BERT-base weights `5a70014d...`. Held-out test expected calibration error 0.1063 -> 0.0433 (validation 0.1036 -> 0.0419); accuracy unchanged (0.6632 test) and identical to the one-time test evaluation, confirming identical inputs. Test was used only to report calibration, not to fit it. The app applies the calibration only when its weights hash matches and now reports `confidence_calibrated: true`; verified with a local inference call. Details and reliability diagram: `meetmind/backend/reports/bert-base-calibration-v1`.