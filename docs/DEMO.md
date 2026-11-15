# Mid-1 demo script (8–10 minutes)

The demo is live. Recordings are a backup only, so rehearse on the demo machine and on a second machine following the README.

## Before the demo (checklist)

- [ ] `git switch main && git pull`. Note the tag shown (`mid1-demo`) and the green CI run.
- [ ] Ollama is running with `llama3.2:latest` (and `qwen3:4b` if showing Urdu): `ollama list`.
- [ ] Backend on a **fresh demo database**:

  ```powershell
  $env:MEETMIND_DB='D:\FYP_MeetMind\demo\demo.db'
  $env:BERT_MODEL_PATH='D:\FYP_MeetMind\Meet_Mind\meetmind\backend\models\dialogue-bert-base-v1'
  $env:MEETMIND_SECRET_KEY='<fernet key>'
  $env:MEETMIND_GOOGLE_CLIENT_ID='…'; $env:MEETMIND_GOOGLE_CLIENT_SECRET='…'
  uv run --frozen --no-sync uvicorn app.main:app --host 127.0.0.1 --port 8000
  ```

  `calibration.json` from `reports/bert-base-calibration-v1` must be copied into the model folder.
- [ ] Policy file contains `allow channel jira`.
- [ ] Frontend: `npm.cmd run dev` → http://127.0.0.1:5173.
- [ ] Accounts:
  - **Ayesha** is the admin and organizer (first sign-up).
  - **Sara** is a member, signed in in a private window.
  - Ayesha has connected Gmail (Account) and Jira (Admin → Jira), and pressed *Match users by email*.
- [ ] The demo transcript file is ready (below). Sara's address is a team inbox that the audience can see.

### Demo transcript (paste or upload as TXT)

```
Ayesha: Okay, let's plan the release.
Sara: I will send the test report by Friday, don't worry.
Ali: We should book the demo room for Monday or Tuesday.
Ayesha: Sara, can you also update the Jira board tomorrow? It's urgent.
Sara: Sure.
Ali: Actually, cancel the budget review.
```

## Walkthrough

| Time | Presenter | Show | Point to make |
|---|---|---|---|
| 0:00 | Rana | Problem and the five-stage flow (poster) | "Conversation to execution, with people deciding at every gate" |
| 0:45 | Azfaar | Sign in as Ayesha; Admin page (organizer request, audit log) | Roles: Admin oversees, Organizer runs meetings, the Owner approves their own items |
| 1:30 | Azfaar | Upload the transcript, then **Start workflow** | One LangGraph workflow with saved checkpoints; the stage strip moves |
| 2:30 | Sameer | BERT labels, calibrated scores, review flags; commitments with evidence quotes | Test macro F1 0.527 (target 0.73 not met: explained); "don't worry" is **not** a cancellation; "Monday or Tuesday" stays unresolved; "tomorrow" becomes a date; "urgent" makes it high priority |
| 4:00 | Rana | Review: approve Sara's report, link owner = Sara; reject or keep the suggestion; show the cancellation cannot be approved | The model never approves or chooses an owner |
| 5:00 | Rana | Workflow review step: tick Email (recipient pre-filled, confirm) and Jira ticket → Create drafts | Recipients and assignees come from people |
| 6:00 | Sameer | Switch to Sara's window → My approvals → approve both | Owner-only approval; the approval is bound to the exact content and policy |
| 6:45 | Sameer | Workflow completes: the email arrives in the inbox (show it); the Jira issue opens (show it) | Executed exactly once; delivery state and audit trail |
| 7:30 | Azfaar | Edit an approved draft → approval becomes outdated; Send is blocked | Invalidation on change |
| 8:00 | All | Tests: CI run, 320+ backend tests, browser smoke checks; the remaining plan | Honest status: what is live, what is pending |

## If something fails live

- **Ollama slow or down:** the workflow shows "Drafting unavailable" with **Retry from this step**. This demonstrates failure handling. Continue with a pre-drafted meeting from the backup database.
- **Gmail or Jira network issue:** the delivery shows `failed` with the reason and nothing is duplicated. Show the backup recording of a successful send.
- Keep `D:\FYP_MeetMind\demo\backup.db` (a completed run) and the screen recording ready.

## Likely questions

- *Why not 0.73 macro F1?* There are 15 imbalanced classes, with be.neg at 69 training examples. The test result 0.527 is measured once on held-out data and is close to validation, so selection did not overfit. BERT gives hints only; a person reviews every item.
- *Is the confidence calibrated?* BERT probabilities are temperature-scaled on validation, with calibration error reported on test. The commitment review score is a documented heuristic, not a probability.
- *What stops the model from sending email?* Three things: the model has no recipients, the policy requires human approval bound to a content hash, and delivery reserves the draft and runs at most once.
- *Which code is AI-assisted?* Disclosed in the report §8.7 and in commit trailers. Each owner explains and runs their module.
