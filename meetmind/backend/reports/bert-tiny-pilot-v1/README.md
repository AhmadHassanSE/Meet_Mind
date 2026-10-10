# 10 October 2026 — actual CPU pilot results

This is a completed, real fine-tuning run of Google's 2-layer, 128-hidden BERT
checkpoint, not BERT-base. All encoder and classifier parameters were trained
for five epochs on 24,000 stratified examples from official AMI manual
annotations. Checkpoint selection used validation macro F1; epoch 5 won.

Custom design-session-disjoint splits contain 82,294 training, 13,593 validation
and 14,882 test examples from 99/19/21 meetings respectively. All 15 dialogue-act
classes are retained. 7,118 nonlexical and 28 unlabeled acts were excluded by the
parser. Data and source hashes, meeting groups, class counts and model revision
are in the accompanying artifacts. The team has not independently reannotated
this corpus; these labels are the corpus authors' annotations.

| Model | Validation macro F1 | Validation accuracy |
|---|---:|---:|
| Majority | 0.0296 | 0.2851 |
| TF-IDF + balanced logistic regression | 0.2989 | 0.3892 |
| Fine-tuned small BERT | **0.4219** | **0.5724** |

Baselines and BERT use the same 24,000 training examples and all 13,593 validation
rows. These are initial baselines with stated settings, not exhaustively tuned
competitors. The test set has **not** been evaluated: reserve it for a frozen
selection after the main BERT-base experiments. This validation comparison does
not establish the best possible model or generalization to arbitrary meetings.

Training took approximately 8.5 minutes after dependencies/model preparation on
the local Intel i7 CPU; `training_summary.json` contains the exact elapsed times.
The full BERT-base candidate has configuration and a manual GPU notebook, but it
has not been trained in this implementation session.

## Error analysis and quality boundaries

- Offer F1 is 0.3497 (184 validation examples), Suggest F1 0.4528 (1,141), and
  Elicit-Offer-Or-Suggestion F1 0.2147 (95). Action-related quality still needs work.
- Be-Negative F1 is zero on just three validation examples. Macro F1 includes all
  15 classes; rare-class results are unstable and should not be hidden by accuracy.
- In the functional fixture, the report promise was classified Offer, while
  “Can you book the room?” was classified Elicit-Inform. This is a useful review
  example, not an independently annotated accuracy benchmark.
- Training uses gold dialogue-act boundaries. Uploaded speaker turns and ASR
  segments can contain multiple acts and transcription errors.
- AMI action-related acts include hypothetical/rejected actions. These results
  are not commitment precision/recall, owner/deadline accuracy or transcription WER.
- Score and margin review cutoffs are heuristic; no confidence calibration is claimed.

## Functional verification

30 backend tests passed, including session leakage, corrupted manifest checks,
NXT links, missing/incompatible checkpoints, persistence, validation-only model
selection and review safeguards. Production TypeScript/Vite build passed.

Real local model smoke verified API classification, exact source IDs, stable
repeat inference, weight provenance, SQLite persistence and no automatic task
creation. A browser run verified actual BERT inference, refresh persistence and
mobile layout alongside the existing ingestion checks. The first cold browser
run exceeded its 60-second result wait; inference subsequently completed, and a
warm rerun passed. The browser allowance was increased to three minutes for
Windows cold loading; this does not establish a latency guarantee.
After restarting the isolated backend, the browser check passed again with the
updated allowance. The cold-start issue was not reproduced on that rerun.

Model weights are local and ignored by Git:
`backend/models/dialogue-bert` and `backend/runs/bert-tiny-pilot-v1/best`.
SHA-256: `5eadcdca43bb32fea03cfaf00f84c2e969d1cc792e3fa120e0c220763a0a7b9a`.
Reproduce using backend/BERT.md; source code alone does not distribute weights.

Work was performed with Codex assistance at Rana's direction. Git commits use
Rana's configured identity; no separate member contributions are implied.
