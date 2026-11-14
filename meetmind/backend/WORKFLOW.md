# Meeting workflow (LangGraph orchestrator)

Each meeting can run one LangGraph workflow (`app/workflow.py`). It joins the existing steps into a single process that **stops at every human decision**. The graph only calls the existing services, so roles, revision checks, explicit recipients and the approval policy are enforced in the same place as before. The graph never approves anything itself.

```
extract ─▶ await_review ⏸ ─▶ draft ─▶ policy_check ─▶ await_approval ⏸ ─▶ execute ─▶ done
                 │ (no follow-ups chosen)                     ▲    │
                 └──────────────────────────────▶ done        └────┘ repeats until every draft is decided
```

| Stage | What happens | Who acts |
|---|---|---|
| extract | BERT + spaCy + Ollama extraction, the same code as **Extract commitments**. A meeting that already has an extraction or reviewed items is reused, never overwritten. | System |
| await_review ⏸ | The run pauses. The organizer approves or rejects commitments and links owners as usual, then chooses which approved items get a follow-up and **types or confirms the recipients**. The form is pre-filled from the linked owner account. | Meeting organizer |
| draft | One email draft per chosen item, through the existing drafting graph (Ollama + schema check). Retries reuse drafts through idempotency keys. | System |
| policy_check | Records the policy violations for each draft. | System |
| await_approval ⏸ | Pauses until every draft is approved or rejected, and approved drafts are still valid. A decision in **My approvals** wakes the check. Editing a draft or changing the policy puts it back into pending. | Item owner (or organizer if no owner) |
| execute | Runs only drafts whose approval is still valid. Each draft runs at most once: a `sent` delivery is never repeated. Until a connector is configured, the result is recorded as `not_configured` ("nothing was sent"). | System |

## Persistence, failure and retry

- Graph state is checkpointed with `langgraph-checkpoint-sqlite` in `<database>.workflow.db` next to the main database. Each run is a separate thread, `meeting_id:run`.
- A paused run survives a backend restart and resumes from its checkpoint without repeating finished steps (tested).
- A failing step (for example Ollama offline) marks the run `failed` with the reason and keeps all meeting data. **Retry from this step** continues from the last completed step (tested).
- A step that was running when the backend stopped is marked failed at startup and can be retried.
- The status shown in the UI (stage, history with actors, drafts, policy results, deliveries) is stored in the `workflows` table. Deleting a meeting deletes it too.

## API

| Route | Who | Purpose |
|---|---|---|
| `GET /api/meetings/{id}/workflow` | Anyone who can view the meeting | Status, stage, what it is waiting for, drafts, deliveries, history |
| `POST /api/meetings/{id}/workflow` | Meeting organizer | Start a new run (409 while one is running or waiting) |
| `POST …/workflow/resume` | Meeting organizer | Finish the review pause: `{"follow_ups": [{"commitment_id", "to": [...]}]}`. An empty list finishes without follow-ups. Commitments must already be approved. |
| `POST …/workflow/retry` | Meeting organizer | Continue a failed run from its last completed step |
| `POST …/workflow/check` | Meeting organizer | Re-check the approval pause (also triggered automatically after each draft decision) |

## Tests

`tests/test_workflow.py` uses real accounts and roles, with a fake extraction step and a fake model. It covers:
- the full run;
- an owner-only approval;
- no execution before approval;
- resume after a restart;
- failure and retry;
- finishing without follow-ups;
- a second run that reuses existing reviews;
- a single execution per approval;
- rejected drafts never executing;
- the permission checks.

`frontend/scripts/smoke-workflow-ui.cjs` drives the panel in a real browser against a real backend.

## Limits

- Email is the only drafting channel. Gmail sending (WP5) and Jira (WP6) plug into the `executors` map and the drafting step.
- Automatic 24-hour escalation is not implemented.
- The orchestrator is one graph with specialised nodes, not six independent agents.
