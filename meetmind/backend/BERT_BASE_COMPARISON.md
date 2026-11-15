# Full BERT-base GPU training and comparison

Full GPU training was completed on 10 October 2026 and the returned checkpoints
were imported locally. The 3e-5 candidate (best epoch 3) won by validation macro
F1: **0.5292777**, accuracy **0.6313544**, versus 2e-5's **0.5235926** and the
tiny pilot's **0.4219068**. This is a gain of **0.1073709** macro F1. Final-test
evaluation remains reserved. Compact evidence is in
`reports/bert-base-comparison-v1/`.

The app defaults to `models/dialogue-bert-base-v1`. The selected weights SHA256
is `5a70014dec35d58aa1c4661fc2d93cda5986d20e49b0eb317968f8bf78f472eb`.
Weights and the results ZIP stay outside Git. For another team member, obtain
the results ZIP from the team, extract it into a fresh local folder, and copy
`bert-base-gpu-lr3e5/best/` to `models/dialogue-bert-base-v1/`. Compare the weight
hash above before serving. Restart the backend to load the new default. To
explicitly use the preserved pilot in PowerShell, set
`$env:BERT_MODEL_PATH = (Resolve-Path models/dialogue-bert).Path` before starting
the backend. Remove that override to use the new default.

The following sections document the reproducible training workflow. The local laptop
has Intel Iris Xe graphics and CPU PyTorch; it has no CUDA GPU. Full BERT-base
training must execute in the user's Colab/Kaggle GPU runtime. A prepared notebook
or a passing unit test is not a completed full-model experiment.

## Checkpoint 1: trainer and honest comparison

The new branch is `feat/bert-base-comparison`. Two configurations use the exact
same full AMI training split, seed 42, a pinned `google-bert/bert-base-uncased`
revision, 128-token pairs, effective batch size 32, five maximum epochs,
validation macro F1 selection, and early stopping. Learning rates are 2e-5 and
3e-5. FP16 and activation checkpointing reduce CUDA memory use. An explicit
CUDA requirement prevents accidentally starting a long CPU run.

The trainer saves model, optimizer, scheduler, gradient-scaler and RNG state at
completed epochs. The latest two completed states are retained. An interrupted
epoch is replayed from the preceding completed epoch. Resume checks the original
configuration and dataset hash. Completed runs and existing serving models are
not silently overwritten. Exact restart equivalence is tested on a small local
BERT fixture; cross-GPU/software reproducibility is not guaranteed.

`scripts.compare_bert` accepts only validation reports with the same dataset
hash, unique example IDs, gold labels and ontology. It recomputes F1/accuracy from
predictions before ranking. Smoke experiments and test reports are rejected.
The old tiny pilot used 24,000 training examples and length 96, so comparing it
against full-data BERT-base also changes data budget and sequence length. This
is not a controlled architecture-only ablation. Final-test evaluation remains
reserved until model selection is frozen.

## Checkpoint 2: run on Colab

The byte-exact input package is generated locally as follows (backend directory):

```powershell
.\.venv-nlp\Scripts\python.exe -m scripts.export_training_inputs --output export/bert-base-training-inputs.zip
```

It includes only public AMI train/validation files, their manifest and the
existing pilot's complete validation predictions. It excludes final-test data,
private uploaded meetings and model weights. Original file bytes preserve the
Windows-generated dataset hashes; re-generating the corpus on Linux would change
line endings/hashes and invalidate a direct hash-matched comparison.

Open [the Colab notebook](notebooks/bert_base_comparison_colab.ipynb), or open its
GitHub URL in Colab after the branch is pushed. Choose **Runtime > Change runtime
type > GPU**, then run the cells in order. Authorize Drive storage when Colab
requests it and upload the input ZIP. The notebook keeps the runtime's CUDA
PyTorch instead of installing this laptop's CPU-only uv source.

The notebook first runs a small, explicitly labelled real BERT-base GPU smoke
experiment, then both full-data candidates and complete validation evaluation.
It stores completed epoch states in Drive. To resume, reconnect a GPU runtime
and use the same experiment name, source revision, configs and input ZIP.
Storage includes two recent full optimizer checkpoints per candidate plus best
weights; allow several GB. Runtime depends on the assigned GPU and session
limits; no fixed completion time or improved F1 is promised.

If using a Kaggle GPU notebook instead, install the same Transformers/sklearn
versions shown in the Colab notebook, upload/extract the verified input package,
and run from `meetmind/backend` with CUDA PyTorch:

```bash
python -u -m scripts.run_bert_comparison \
  --configs configs/bert-base-gpu-lr2e5.json configs/bert-base-gpu-lr3e5.json \
  --reference reference/pilot-validation.json \
  --output runs/bert-base-comparison --resume
```

Use persistent output paths appropriate to the Kaggle environment and preserve
the configuration when resuming. Evaluation automatically uses CUDA when
available; `--device cpu` can force CPU evaluation.

## Checkpoint 3: actual results and integration

Once GPU execution finishes, retain `comparison.json`, `comparison.md`, compact
per-run evidence and the trained `best/` checkpoint directories. The Colab
notebook creates a results ZIP in Drive. It does not automatically replace the
pilot. Review the validation results first; a larger model may underperform.
Only a completed, stronger candidate should be considered for serving, followed
by the existing real API/browser model checks. Final test scores must never guide
learning-rate or model selection.

Notebook outputs and trained weights are ignored by Git. Commit compact verified
experiment evidence, not fabricated metrics or a claim that an unexecuted
notebook completed training. The requested friend's commit identity is supplied
by the user; GitHub push authentication is separate and requires that account's
device authorization. No shared password is used or stored by this workflow.
