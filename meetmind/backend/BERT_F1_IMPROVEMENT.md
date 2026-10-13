# BERT-base macro F1 improvement: Colab handoff

Branch: `feat/bert-base-f1-improvement`, based on the latest non-Meet core
`a769929`. Google Meet work remains separate. The existing serving weights
and their reported metrics remain unchanged until a new result is verified.

**Baseline:** 0.5292777 validation macro F1, 0.6321866 weighted F1, 0.6313544
accuracy. The earlier tiny pilot's 0.5724 was accuracy, not BERT-base macro F1.
**Target:** at least 0.73 macro F1 across the same 15 AMI classes and 13,593
validation utterances. Achieving it is an empirical question; no guarantee or
completed GPU improvement is claimed.

## What was prepared

Three fixed BERT-base candidates test added preceding context and alternative
imbalance objectives. All retain the original split, labels and full 82,294
training examples. Optimization includes layer LR decay, a faster task head,
zero bias/LayerNorm weight decay, configurable warm-up and longer early stopping.
Target-first tokenization and recent-first context are shared by training,
evaluation and serving and recorded in checkpoint metadata. Old checkpoints keep
their legacy format. No future utterances or gold labels enter context.

The real input audit found no original validation truncation. Large class
confusions and low rare-class F1 motivate these experiments; added context and
loss changes are candidates, not proven gains. See
[the recorded audit](reports/bert-f1-improvement-v2/README.md).

## Run in Google Colab

1. Open `notebooks/bert_base_f1_improvement_colab.ipynb` in Colab.
2. Select a GPU runtime (T4 or another CUDA GPU), then run cells in order.
3. Upload the prepared `runs/bert-f1-training-inputs-v2.zip` when prompted.
   It contains only public train/validation data and the existing baseline
   checkpoint (~400 MiB). The notebook verifies exact names and hashes.
4. Grant Drive mounting. The default experiment is
   `MyDrive/MeetMind-BERT/bert-f1-improvement-v2`. Keep this name, source revision
   and input bundle unchanged when resuming.
5. Allow the smoke and three candidate runs to complete. Each full candidate can
   take several hours. Completed epochs can resume after a disconnect. Storage
   is needed for best models and two optimizer checkpoints per candidate.
6. Inspect `comparison/goal.json` and `comparison/comparison.md` in Drive.
   `achieved: true` is written only when the verified selected macro F1 reaches
   the target. If it is false, the target has not been reached.
7. Download `trained-bert-f1-v2-results.zip` and its checksum from the experiment
   folder, and place them in the workspace for local verification and import.

The baseline is re-evaluated on GPU so comparison has complete per-row predictions
instead of relying only on compact old summaries. Metrics are recomputed from
predictions on identical validation IDs/gold labels. The final-test rows are
absent. No application model is replaced by the notebook.

If a command fails, the full subprocess traceback is displayed and saved in the
experiment's `logs/` directory. A generic notebook subprocess exception alone
does not diagnose the cause. If the source revision changes, return to the saved
commit or choose a new experiment name; do not mix sources in one run.

## Recreate the input ZIP locally

From `meetmind/backend` with the tested NLP Python environment:

```powershell
python -m scripts.export_bert_improvement_inputs
```

The default baseline is `models/dialogue-bert-base-v1`. No final-test data,
recordings, browser profiles or credentials are included. The generated ZIP is
ignored by Git; model weights are distributed through the local Colab handoff.

## Evaluation boundaries

Some validation classes have only 3 or 7 examples. Macro F1 is sensitive to these
small supports. Repeated candidate/epoch selection makes validation optimistic;
the unchanged final test is reserved for final reporting after the model is
frozen. Do not change the split, merge rare classes or substitute weighted F1,
accuracy, action-only F1 or a sampled validation score to claim 0.73.

These are dialogue-act results on English AMI, not commitment, owner/deadline or
Urdu quality scores. Local tests verify implementation behavior with synthetic
tiny models; only the GPU study can measure the new full BERT-base scores.
