# Fine-tuned BERT for MeetMind

Decision confirmed by the user on 10 October 2026: use fine-tuned BERT for the
Iteration 1 dialogue-act classifier. Ollama remains an optional separate
commitment-extraction experiment. BERT classification does not require Ollama.

## What this model predicts

The first supervised task uses all 15 lexical dialogue-act classes in the
official AMI manual annotation ontology: backchannel, stall, fragment, inform,
elicit-inform, suggest, offer, elicit-offer-or-suggestion, assess,
elicit-assessment, comment-about-understanding,
elicit-comment-understanding, be-positive, be-negative and other.

`off`, `sug` and `el.sug` highlight **possible actions**, not confirmed task
commitments. AMI intentionally includes rejected and hypothetical actions in
these classes. Do not rename these labels to “approved action item”. A separate
annotated commitment/owner/deadline task is still needed for end-to-end action
extraction quality. spaCy and owner/deadline rules are not implemented here.

Sources and attribution:

- [AMI corpus](https://groups.inf.ed.ac.uk/ami/corpus/), manual annotations
  v1.6.2, released under CC BY 4.0. Cite the AMI corpus in the final report.
- [Official download](https://groups.inf.ed.ac.uk/ami/download/).
- [Dialogue-act annotation manual](https://groups.inf.ed.ac.uk/ami/corpus/Guidelines/dialogue_acts_manual_1.0.pdf).
- [BERT base model card](https://huggingface.co/google-bert/bert-base-uncased),
  Apache 2.0. Cite Devlin et al., *BERT: Pre-training of Deep Bidirectional
  Transformers for Language Understanding* (2019).
- [Small BERT checkpoint](https://huggingface.co/google/bert_uncased_L-2_H-128_A-2),
  for a bounded CPU pilot, not a claim that tiny BERT is the strongest model.

## Environment (PowerShell, from this backend directory)

An existing server locked the reference environment's tokenizers DLL during
setup, so NLP uses an isolated `.venv-nlp`. Leave existing servers running only
if they are not being replaced; use another port for a parallel demo.

```powershell
cd D:\FYP_MeetMind\Meet_Mind\meetmind\backend
$env:UV_PROJECT_ENVIRONMENT = '.venv-nlp'
uv sync --extra nlp --group dev
```

Keep the `UV_PROJECT_ENVIRONMENT` setting in each terminal where you use these
commands. Alternatively run `.\.venv-nlp\Scripts\python.exe` directly. The
checked-in uv configuration uses CPU PyTorch for this Intel laptop. Downloads
require internet; serving a saved checkpoint is local-only.

## Prepare data once

```powershell
uv run --extra nlp python -m scripts.prepare_ami
```

The script downloads the official ZIP, reads NXT word-range links without
extracting the archive, resolves labels from `ontologies/da-types.xml`, excludes
unlabeled/nonlexical acts with recorded counts, and writes versioned JSONL data.
Unknown labels and broken word links fail explicitly.

Split seed 42 creates a custom 70/15/15 split of design-session groups. All a/b/c/d
meetings from the same scenario session remain together, keeping meetings and
related teams out of multiple splits. This is **not** a published standard AMI
split. Meeting IDs, class counts, source/archive hashes and split-file hashes are
recorded in `data/ami-da-v1/manifest.json`; modified files are rejected.

Current text is the first BERT sentence; up to two prior chronological turns
form the second sentence. Context uses same/other speaker markers, never speaker
names or gold labels. No future context is included. The same input builder is
used in serving. Long inputs are truncated; training/evaluation uses gold AMI
act boundaries while uploads contain speaker turns/ASR segments. This boundary
and transcription mismatch limits real-upload generalization.

## Train and choose candidates

```powershell
# Practical local pilot: 24,000 stratified training examples, all 15 classes.
uv run --extra nlp python -u -m scripts.train_bert --config configs/bert-tiny-pilot.json

# Main candidate: BERT-base, full training split. Much slower on this laptop.
uv run --extra nlp python -u -m scripts.train_bert --config configs/bert-base.json
```

All encoder and classification-head parameters are fine-tuned. Training records
resolved upstream revision, dataset hash, selected training-ID hash, class
counts, seed, dependency versions, hardware device, loss, runtime and per-epoch
validation metrics. Dynamic padding, gradient accumulation, warmup, weight
decay, gradient clipping, square-root inverse class weighting and early stopping
are configured explicitly. Checkpoints are chosen by **validation macro F1**.
The test JSONL is never loaded by training. Saved weights use safetensors.

For stronger results, run BERT-base on suitable GPU compute using a fresh
environment with GPU PyTorch, `transformers>=4.48,<5` and scikit-learn installed.
The scripts are portable; retain the exact dataset/versioned split. Cloud
training is optional and has not been performed or authorized to upload private
meeting data. The checked-in uv CPU source does not install CUDA PyTorch.

Compare learning rates 2e-5, 3e-5 and 5e-5 with independent output directories;
use additional seeds to assess stability. Keep architecture, data budget and
configuration in each run record. Only validation may guide these decisions.

An unexecuted [GPU notebook](notebooks/bert_gpu_training.ipynb) prepares the same
public dataset, trains two BERT-base learning-rate candidates, selects on
validation only, evaluates the frozen winner and exports model/evidence. It is
provided for manual execution; no remote training or private-data upload has
been performed by this implementation.
The provided defaults are starting configurations, not a guarantee of optimal
hyperparameters. Pilot and full-data runs must be labeled separately.

```powershell
uv run --extra nlp python -m scripts.select_bert --runs runs/bert-tiny-pilot-v1 runs/bert-base-v1 --output models/dialogue-bert-v2
```

Only list runs that actually completed. Selection copies the strongest
validation candidate, preserves metadata and records a weights hash. It does
not claim superiority over models that were never trained. Existing run/model
directories are never silently overwritten.

## Evaluate a frozen checkpoint

```powershell
uv run --extra nlp python -m scripts.evaluate_bert --checkpoint runs/bert-tiny-pilot-v1/best --split validation --output runs/bert-tiny-pilot-v1/validation.json
# After final validation-only selection, evaluate test once for reporting:
uv run --extra nlp python -m scripts.evaluate_bert --checkpoint runs/bert-tiny-pilot-v1/best --split test --output runs/bert-tiny-pilot-v1/test.json
```

Reports compare majority, TF-IDF/bigram logistic regression, and BERT on identical
evaluation rows, with baselines fit on the same selected training examples.
They contain accuracy, macro/weighted F1, per-class precision/recall/support,
confusion matrices, prediction IDs and model/data hashes. Report these as
dialogue-act results, not owner/deadline accuracy or transcription WER. Rare
classes have small denominators; inspect support and errors instead of reporting
accuracy alone. If a baseline wins, report it honestly and improve using
validation; do not tune against the held-out test. A later test-guided change
requires a fresh final evaluation set.

## Serve and use the UI

```powershell
# One completed run can be selected on its own for a pilot demonstration.
uv run --extra nlp python -m scripts.select_bert --runs runs/bert-tiny-pilot-v1 --output models/dialogue-bert
uv run --extra nlp uvicorn app.main:app --host 127.0.0.1 --port 8000
```

`BERT_MODEL_PATH` overrides the default `backend/models/dialogue-bert` directory.
For example, point it at `runs/bert-base-v1/best` after that training finishes.
Restart the backend when switching checkpoint versions. The UI's **Analyze with
BERT** button calls `POST /api/meetings/{id}/classify` and persists labels, source
IDs, scores, alternatives, review reasons and model provenance separately from
Ollama-extracted actions. It does not execute tasks. Health reports checkpoint
availability; actual load/weight validation happens on the first classification.

Loading is local-only and refuses missing, incompatible or incompletely loaded
weights. No automatic pretrained or Ollama fallback is disguised as fine-tuned
BERT. Missing checkpoint/dependencies return 503 without altering the meeting.
Scores are uncalibrated softmax outputs. The initial .7 score and .15 margin
review cutoffs are heuristic defaults, not validated confidence calibration.
Every possible-action prediction requires human review regardless of score.
Serving also measures original and retained input/target token lengths. Shortened
target text or context is explicitly marked for review, even at high scores.
This warns about lost coverage; it does not replace evaluated turn segmentation.

```powershell
uv run --extra nlp pytest -q
uv run --extra nlp python -m scripts.smoke_bert
```

Observed pilot results and error analysis are in
[reports/bert-tiny-pilot-v1/README.md](reports/bert-tiny-pilot-v1/README.md).
The seven-file real-meeting API/browser audit and resulting fixes are in
[reports/real-meeting-audit-2026-10-10/README.md](reports/real-meeting-audit-2026-10-10/README.md).
Real browser inference can be checked with the frontend smoke script by setting
`MEETMIND_BERT_SMOKE=1`, against a dedicated test database and running servers.
The first request can take time to load Windows dependencies/weights; rehearse
and warm the model before evaluation. The UI waits for the actual result.

Raw data, model weights and run directories are ignored by Git. Commit compact
manifest/result summaries and reproducible code, not private recordings or huge
checkpoints. GitHub source code alone does not include a deployable trained
model; retrain or transfer a checkpoint separately with provenance and hash.
