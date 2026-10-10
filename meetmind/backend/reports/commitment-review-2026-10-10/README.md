# Commitment review verification

Implemented task/owner/deadline corrections, explicit approval/rejection,
candidate promotion, reopening and persistent decision history. Source evidence
and original extraction remain unchanged. Cancellation candidates cannot become
tasks; possible-cancellation actions require an approval note. Reviewed meetings
cannot be re-extracted in place. Atomic review transactions and revision checks
prevent lost edits; classification and in-flight extraction preserve reviews.

Validation on 10 October 2026:

- 74 backend tests passed, including seven dedicated review tests.
- The frontend TypeScript check and production build passed.
- Headless Chrome exercised the real API using synthetic proposal fixtures:
  edit, approve, reject, promote a suggestion, reject a cancellation, refresh
  persistence, original extraction/history display and mobile layout.
- The existing ingestion browser smoke passed with the updated meeting-opening
  flow: captions, timestamps, persistence, media tabs, validation and mobile.
- Two end-to-end browser cases used the actual local BERT-base, spaCy and Ollama
  extraction pipeline, then approved a returned commitment and verified its
  unchanged evidence and approval after refresh. Cases include a promise with a
  deadline and a promise followed by cancellation and suggestion evidence.
- CI now runs the synthetic review browser check without private model weights.

`verification.json` contains compact results and real pipeline timings. These
checks demonstrate functionality, not action-extraction precision/recall.
Reviewer attribution is explicitly local and unauthenticated. No task execution,
external task synchronization, calendar-date normalization or authentication
was introduced. See `COMMITMENTS.md` for the review API and user flow.
