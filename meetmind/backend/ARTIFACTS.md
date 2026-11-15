# Follow-up drafts, approval and execution

The workflow below runs inside the meeting workflow ([WORKFLOW.md](WORKFLOW.md)) or
by hand from **Follow-up drafts**.

## Implemented workflow

1. In a saved meeting, the organizer reviews and approves an extracted commitment
   and links its owner account.
2. Create a follow-up. An **email** needs recipient addresses entered or confirmed
   by a person. A **Jira ticket** is assigned to the linked owner's Jira account
   ([JIRA.md](JIRA.md)).
3. A LangGraph graph calls local Ollama to draft the subject/body (or summary and
   description) and validates the structured response. The model cannot choose
   recipients or assignees, approve, or send.
4. Inspect the draft and its source evidence. Edit and save as needed.
5. The item owner (or the organizer when no owner is linked, or as the policy
   says) explicitly approves or rejects the exact saved draft. Any change to the
   draft, its source commitment or owner, or the policy invalidates approval.
6. An approved draft is executed **at most once**: an email from the approver's
   Gmail ([GMAIL.md](GMAIL.md)) or a Jira issue. Delivery state and every decision
   are kept in the draft history and the audit log.

### How drafts are written and checked

The drafting graph is `draft → validate → check_facts`. The model sees only reviewed facts: meeting title and date, task, owner, deadline wording, resolved deadline date, priority, sender name and the evidence quotes with speakers. It never sees recipients. Emails follow a fixed shape: greeting, the meeting, the action in plain words, the deadline, the quoted evidence, and a sign-off. After the model writes the draft:
- the "As discussed:" line is replaced with the exact transcript quote;
- a Jira description is built entirely from the reviewed facts (the model writes only the summary line);
- `check_facts` warns the reviewer, and never rewrites the text, when the draft:
  - mentions a date that is not a reviewed date;
  - uses the meeting date as a deadline;
  - implies a deadline when none was agreed;
  - misquotes the evidence;
  - leaves out or invents urgency;
  - contains placeholders such as `[Your Name]`.

Warnings are recalculated after every edit and shown above the draft.

Approval of a commitment and approval of its follow-up are separate decisions.
Normalized PostgreSQL storage, Slack, Calendar and automatic escalation remain
later work.

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

## Policy rules engine

The server reads `policies/followup.policy` (override with
`MEETMIND_ARTIFACT_POLICY`). There is one rule per line, and `#` starts a comment.
Every rule below is evaluated for each draft (`app/artifact_policy.py`):

| Rule | Effect |
|---|---|
| `allow channel email` / `allow channel jira` | Channels drafts may use; at least one is required |
| `require approved_commitment` | The draft's source must still be the approved, unchanged commitment |
| `require explicit_recipients` | Email drafts need people-chosen recipients; the model never chooses them |
| `require human_approval` | A person must approve the exact content (these three are mandatory) |
| `allow domain company.example` | If any are listed, every recipient must be in an allowed domain |
| `deny domain rival.example` | Recipients in a denied domain are always blocked |
| `internal domain company.example` | Domains (and their subdomains) inside the organization |
| `max recipients 5` | Upper bound on recipients per draft (1–50) |
| `require approver owner` / `require approver organizer` | Who decides: the item owner (default; the organizer when no owner is linked), or always the meeting organizer |
| `require sender approver` | Execution must use the approver's own connected account (used by connectors) |
| `require second_approver for external_domain` | A recipient outside the internal domains needs two different people to approve. The first approval is kept as partial; the organizer or owner completes it. Editing clears partial approvals. |

Unknown or malformed rules, a missing mandatory rule, or a second-approver rule
without an internal domain all fail closed, with the line number in the error.
There is no `eval`, no Python execution and no model-supplied policy. An approval
records the policy hash, so changing the policy invalidates earlier approvals
until they are reviewed again under the new rules. If the policy file is missing
or invalid, drafts stay visible but every approval is blocked, with the reason
shown. Tests: `tests/test_policy.py`.

Audit events record the signed-in user who acted (see `AUTH.md`). Bind to
loopback for local use. Model drafts still need human checks for facts, dates,
tone and intended recipients; schema validation is not semantic accuracy.

## Verification

The current backend suite count is recorded per checkpoint in `docs/development-evidence.md`
(320 on 14 Nov 2026). Draft-related tests (`test_artifacts.py`, `test_policy.py`,
`test_gmail.py`, `test_jira.py`, `test_workflow.py`) cover source eligibility,
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
