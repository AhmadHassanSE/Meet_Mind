# Structured commitment extraction

`POST /api/meetings/{id}/extract` now runs the local fine-tuned BERT dialogue classifier, spaCy English parsing/NER plus deadline rules, and Ollama structured proposal extraction. BERT signals are supplied for all utterances; offers/suggestions are not treated as confirmed commitments and low BERT scores do not exclude a turn. This change does not retrain BERT or calibrate confidence.

Prepared children are rejoined within their original speaker turn so task and deadline context survive token segmentation. Source turns above 6,000 characters use prepared children instead. Legacy oversized turns fail explicitly. Ollama receives bounded batches with one-turn overlap when space permits. Cross-batch general discourse/coreference remains limited; cancellation reconciliation inspects later source sentences across the entire meeting, including sentences omitted by Ollama.

Every proposal must identify a supplied source ID and quote an exact contiguous substring of that source turn. Invalid IDs, quotes, schema or truncated model output fail the extraction without replacing saved results. Task wording must have lexical support in the quote, but this does not establish semantic correctness. All accepted results remain proposals requiring review.

## Fields and lifecycle

- `actions`: explicit commitment proposals. Each includes task, owner, verbatim deadline, source IDs, quoted evidence with parent character offsets, BERT signals and review reasons.
- `action_candidates`: suggestions, requests and cancellations kept separately. Questions, modal suggestions and negated sources cannot become active commitments through the model's kind field alone.
- `extraction`: pipeline version, spaCy model version, discarded unsupported proposals and limitations.
- `dialogue_analysis`: current BERT results, saved atomically with successful extraction.

Owners resolve from a task's grammatical subject, explicit addressee/agent, or the speaker for first-person statements. Recipient mentions alone do not establish ownership. Unresolved pronouns such as “we” remain null. Speaker IDs from captions are retained as IDs; no real identity or diarization is inferred.

Deadline candidates combine spaCy DATE/TIME entities with token patterns for weekday, relative date and duration phrases. A model deadline must occur verbatim in the supporting quote and overlap a recognized candidate. A single candidate can fill a missing model deadline; multiple expressions remain unresolved and flagged. Relative deadlines are not converted to dates without a meeting date/timezone. `deadline_normalized` remains null. Even a recognized date can be contextual rather than a true deadline, so review is required.

Negated work is separated from active proposals. A later cancellation with overlapping task objects, or a nearby “cancel it”, marks the earlier proposal `possible_cancellation` and attaches the later evidence. This applies within a source turn and across turns/batches. It does not prove task identity or the cancelling speaker's authority, and never automatically approves or deletes a task. “Do not cancel” is protected from being interpreted as an instruction to cancel.

## Setup and testing

From `meetmind/backend`, using PowerShell:

```powershell
$env:UV_PROJECT_ENVIRONMENT='.venv-nlp'
uv sync --extra nlp --group dev
uv run --extra nlp uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The `nlp` extra now installs spaCy and its official `en_core_web_sm` 3.8.0 model alongside BERT dependencies. Downloads need internet once; inference uses local BERT weights, spaCy and Ollama. Configure the existing BERT checkpoint as described in [BERT.md](BERT.md). Ollama must be running with `llama3.2:latest` (or the configured `OLLAMA_MODEL`). `/api/health` includes spaCy installation status. Missing NLP components return HTTP 503; invalid model output returns 502. `SPACY_MODEL` can select a compatible installed English model/path.

```powershell
uv run --extra nlp python -m pytest -q
uv run --extra nlp python -m scripts.smoke_commitments --output runs/commitment-smoke.json
```

The smoke script uses real BERT, spaCy, Ollama and an isolated temporary database. It checks a promise with a deadline, suggestions/negation, later cancellation and an ambiguous owner. These synthetic functional checks are not an extraction accuracy benchmark. The browser script is `frontend/scripts/smoke-commitments-ui.cjs`; point `MEETMIND_UI_URL` at dedicated frontend/backend services and a separate `MEETMIND_DB`.

The meeting page shows evidence and review details, separates action candidates,
and highlights possible cancellations. Existing records receive stable item IDs
when opened. Accepted cross-turn assignments, date normalization and labelled
end-to-end precision/recall evaluation remain future work.

## Human review

Choose **Review / edit** to correct task, owner or deadline and optionally add
a note. **Save changes for review** leaves the item pending (and reopens a
previous approval); **Approve commitment** records approval; **Reject** records
rejection without deleting the item. Blank owner/deadline fields remain null.
Suggestions and requests have **Approve as commitment**, which moves the item
into `actions` through an explicit human decision. Its original model kind stays
unchanged as provenance. Reopening/rejecting a promoted candidate returns it to
`action_candidates`. Cancellation candidates cannot become approved tasks.
An action with possible cancellation evidence requires a note before approval.

`POST /api/meetings/{meeting_id}/commitments/{item_id}/review` accepts
`revision`, `task`, nullable `owner` and `deadline`, `decision` (`pending`,
`approved`, `rejected`) and optional `note`. It returns the saved meeting.
Unknown IDs return 404; invalid fields/decisions return 422; stale revisions
return 409 without changing saved work. Reload after a conflict.

Each item has a stable `id`, integer `revision`, `review_status`, immutable
`original` extraction and append-only `review_history` entries with UTC time,
before/after field values, decision and note. Source quotes, offsets, BERT
signals and original extraction review reasons are retained. Manual corrections
are not claimed to be source-grounded model predictions. `needs_review` is false
for approved/rejected items; editing for review sets it true again. Relative
deadline wording is free text; this flow does not normalize calendar dates.

Reviews use an atomic SQLite transaction and item revisions to prevent lost
updates. Classification merges analysis without overwriting current reviews.
Re-extraction is blocked once any edit/decision history exists, including rejected
or reopened items. An extraction in flight also fails with 409 if review or
another extraction changed the meeting. Upload a new copy to re-extract while
preserving reviewed work. Approval records a local decision; it does not send
messages, create external tasks or execute work. This is still a local workspace
without authenticated reviewer identities; history labels that limitation.

`tests/test_review.py` covers persistence, provenance, promotion/reopening,
invalid edits, stale revisions, cancellation handling and inference/review races.
`scripts.seed_review_smoke` and `frontend/scripts/smoke-review-ui.cjs` exercise
the real API/browser with deterministic synthetic proposals in a dedicated test
DB, without requiring model weights in CI. The real local NLP browser smoke also
approves an extracted action and checks persistence and unchanged evidence.
