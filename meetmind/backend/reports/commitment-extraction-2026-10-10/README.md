# Local pipeline functional verification

On 10 October 2026, four synthetic meetings passed actual API extraction using
the saved fine-tuned BERT CPU pilot, spaCy 3.8.16 / en_core_web_sm 3.8.0, and
local Ollama llama3.2:latest. `local-pipeline.json` records results and model
provenance. No hosted inference service was used.

Two real Chrome checks passed upload/paste, extraction, quoted evidence, review
details, cancellation/candidate separation, reload persistence, and 390px layout.
Results are in `browser.json`. Browser checks used dedicated ports 8015/5185
and an ignored test database. Regular user services were left untouched.

58 backend tests and the frontend production build passed. Tests cover invalid
Ollama sources/quotes/schema/output limits, rollback on failure, lexical task
support, deadline grounding, pronoun ambiguity, explicit addressees, task-specific
subjects, and cancellation within/across source turns.

These hand-written functional examples are not an independently labelled
evaluation dataset. No extraction precision/recall or accuracy improvement is
claimed. No AMI final test data was evaluated, and BERT weights were unchanged.
General coreference, accepted cross-turn assignments and semantic grounding
still need evaluation and human review.
