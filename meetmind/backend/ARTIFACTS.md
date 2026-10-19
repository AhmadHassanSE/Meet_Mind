# Iteration 2 checkpoint: follow-up drafting and approval

Branch: `feat/iteration2-agent-framework`. The new isolated checkout is
`D:\FYP_MeetMind\Meet_Mind_iteration2`. It merges the latest multilingual speech
update, the BERT experiment tooling, commitment review, the participant extension
and the browser bot. It does not replace the existing BERT weights or claim a
new F1 score. Original feature branches remain available.

## Implemented workflow

1. In a saved meeting, review and approve an extracted commitment.
2. Choose **Draft follow-up**. Enter actual recipient addresses explicitly.
3. A LangGraph workflow calls local Ollama to draft a subject/body and validates
   the structured response. The model cannot choose recipients or send messages.
4. Inspect the email and its source evidence in **Follow-up drafts**. Edit and
   save recipients, subject or body as needed.
5. Explicitly approve or reject the exact saved draft. Changes to any draft
   field invalidate approval. Re-reviewing the source commitment invalidates all
   its drafts, including approval, in the same database transaction.
6. Reopen drafts to inspect their saved state and history.

Approval of a commitment and approval of its follow-up are separate decisions.
**No email is sent at this checkpoint.** There is no delivery endpoint, Gmail
OAuth, Jira/Slack connector or execution worker yet. The next vertical slice is
authenticated Gmail connection and an explicitly authorized, idempotent send.
Accounts/RBAC, normalized PostgreSQL storage and full agent orchestration are
also remaining Iteration 2 work.

## Run in the integrated checkout

Use one backend process and stop old capture sessions before changing checkouts.
Do not run the CLI and backend concurrently against the same capture storage.

```powershell
cd D:\FYP_MeetMind\Meet_Mind_iteration2\meetmind\backend
$env:UV_PROJECT_ENVIRONMENT='.venv-nlp'
uv sync --frozen --extra nlp --extra agents --extra bot --group dev
$env:BERT_MODEL_PATH='D:\FYP_MeetMind\Meet_Mind\meetmind\backend\models\dialogue-bert-base-v1'
uv run --frozen --no-sync uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Run Ollama separately with `llama3.2:latest` installed. Non-English meetings use
`qwen3:4b` (override with `OLLAMA_MULTILINGUAL_MODEL`). Downloads are separate
from Git. Drafting calls the configured local `/api/chat` with a strict subject/
body JSON schema; no hosted model credentials are required.

In another terminal:

```powershell
cd D:\FYP_MeetMind\Meet_Mind_iteration2\meetmind\frontend
npm.cmd ci
npm.cmd run dev
```

This checkout uses a separate local database. Existing meetings and the dedicated
bot profile are not copied or merged automatically. To reuse a dedicated bot
profile, set `MEETMIND_BOT_PROFILE` to its existing path only after its Chrome
window and old bot process are closed. Otherwise prepare the new profile with
`python -m scripts.setup_bot_profile`. Credentials/profiles stay outside Git.

Whisper now defaults to `small`, preserving the teammate's latest speech update.
Select English or Urdu explicitly for short known-language recordings. Roman
Urdu speech selection means Urdu ASR, not guaranteed Romanized output. The bot
passes the selection through the shared capture/session path. Original-language
source text is retained for the multilingual NLP and review pipeline.

## Persistence and API

`artifacts(id, meeting_id, request_key, payload)` stores immutable source snapshots,
generated originals, editable fields, revisions, approvals, workflow steps and
history. Source IDs/revisions and fingerprints link to the existing meeting
payload. There is no claimed SQL foreign key. Approval binds the exact content
hash and current policy hash. Pending generation becomes failed after restart;
it is not silently regenerated or sent.

| Endpoint | Behavior |
|---|---|
| `POST /api/meetings/{id}/artifacts` | Explicit commitment ID/revision, recipient list and idempotency key; generate email |
| `GET /api/artifacts?meeting_id=...` | Global or meeting-scoped saved drafts, policy result and approval validity |
| `GET /api/artifacts/{id}` | Current draft and history |
| `PATCH /api/artifacts/{id}` | Revision-checked edit; clears prior approval |
| `POST /api/artifacts/{id}/review` | Revision-checked `approved`/`rejected` decision |

Repeated creation with the same key/inputs returns the existing record. Reusing
a key for different inputs returns 409. Stale source/draft revisions return 409.
Schema/header/recipient failures return 422. Missing local runtime/model returns
503; invalid model output returns 502 with a retained failed draft and unchanged
source. A new request key is required to intentionally retry a failed generation.

## Policy subset

The server reads `policies/followup.policy` (override with
`MEETMIND_ARTIFACT_POLICY`). Supported declarative statements:

```text
allow channel email
require approved_commitment
require explicit_recipients
require human_approval
# Optional destination restriction:
# allow domain company.example
```

All three requirements are mandatory in this checkpoint. Unknown rules fail
closed; there is no `eval`, Python execution or arbitrary model-supplied policy.
Changing policy invalidates the validity of previous approvals until reviewed
under the current policy. This is a deliberately small DSL subset, not a general
organizational policy language or a completed external execution engine.

The service is a local single-user prototype. Audit events explicitly identify
an unauthenticated local workspace user, not a verified organizational identity.
Bind to loopback. Authentication/authorization must precede any shared deployment
or connected account execution. Model drafts still need human checks for facts,
dates, tone and intended recipients; schema validation is not semantic accuracy.

## Verification

179 combined backend tests passed locally. The new tests cover source eligibility,
real LangGraph nodes with mocked Ollama responses, idempotency, stale edits,
approval invalidation, concurrent source change, policy updates, invalid recipients,
restart recovery and Urdu capture metadata. Browser checks cover the built UI
with explicitly mocked APIs, including mobile layout and refresh persistence.
The real WebRTC regression still checks audio capture independently of Meet's
page playback.

`python -m scripts.smoke_artifacts` uses a real local Ollama and LangGraph in a
temporary database with a synthetic pre-reviewed commitment. It checks drafting,
approval, edit invalidation and persistence; it does not run extraction or send
an email. One English run passed with `llama3.2:latest`. No semantic quality score,
new live Meet run, multilingual drafting benchmark or external delivery is claimed.

References:
- [LangGraph StateGraph](https://reference.langchain.com/python/langgraph/graph/state/StateGraph)
- [Ollama structured output](https://ollama.com/blog/structured-outputs)
