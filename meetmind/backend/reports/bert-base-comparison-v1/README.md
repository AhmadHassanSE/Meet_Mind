# Completed full BERT-base experiment

GPU execution was performed by the user in Colab on a Tesla T4, using source
revision `b1c787d20bc4135e2f840d2f03fc0d4a04d59386`. The returned results were
imported on 10 October 2026. Both candidates fine-tuned all 109,493,775
parameters on 82,294 AMI examples; selection used all 13,593 validation examples.

| Candidate | Best epoch | Validation macro F1 | Accuracy |
|---|---:|---:|---:|
| BERT-base, learning rate 3e-5 | 3 | 0.5292777 | 0.6313544 |
| BERT-base, learning rate 2e-5 | 5 | 0.5235926 | 0.6381226 |
| Tiny BERT pilot, 24,000 training examples | 5 | 0.4219068 | 0.5723534 |

The 3e-5 candidate wins on the prespecified macro F1 criterion despite the
2e-5 candidate's higher accuracy. Its gain over the pilot is 0.1073709 macro
F1 (10.74 percentage points). Both runs completed five epochs in roughly two
hours each. The 3e-5 run retained epoch 3 after two epochs without improvement.

The original reports, training histories, dataset manifests, configs and model
metadata are preserved in this directory. Dataset manifest SHA256:
`f6cf4e2856ec3fd3fd29cd86b6678f60ce727cde9b4d067caa52f22e8844e9d1`.
Imported model weight hashes match the evaluation reports and comparison:

- 3e-5: `5a70014dec35d58aa1c4661fc2d93cda5986d20e49b0eb317968f8bf78f472eb`
- 2e-5: `373bcd3b0f6c42d4162786ee4a7c547c4cd0156ccebc49b644d760670ab4d105`
- Returned ZIP: `9611815da5377da59eebd054a7b37c77bc8e4a335f310bec20c920b2cae167a5`

Both checkpoint architectures were checked as 12-layer BERT with hidden size
768 and 15 labels. Reported macro F1 agrees with the mean of the per-class F1
values; support sums to 13,593. Best-epoch metadata agrees with training history.
Full prediction arrays are not included in the returned ZIP, so these checks
do not independently reproduce the Colab evaluation. A local full-validation
attempt stopped while Windows reported insufficient paging memory during
concurrent checks; no locally recomputed full-validation score is claimed.

The selected checkpoint is installed locally in `models/dialogue-bert-base-v1`,
now the app default. The previous pilot is preserved in `models/dialogue-bert`.
Weights and raw datasets remain outside Git; see `BERT_BASE_COMPARISON.md` for
team installation and an explicit pilot override.

Local validation: all 67 backend tests pass, including interrupted/resumed
training and preprocessing using the selected model's 128-token budget. Real
saved-checkpoint API inference, repeat inference and SQLite persistence pass.
Chrome checks pass for two AMI validation excerpts (23 and 22 prepared segments),
covering upload, BERT analysis, source display, refresh persistence, and mobile
layout. These are functional checks, not a real-meeting accuracy benchmark.
All four synthetic BERT + spaCy + local Ollama checks also pass on a sequential
retry: promise, suggestion/negation, later cancellation, and ambiguous owner.
The initial concurrent check failed on the Ollama request. Compact timings and
the actual serving weight hash are recorded in `local_verification.json`.

Limitations: training budget and input length differ from the pilot, so this
does not isolate architecture effects. Rare-class estimates are unstable
(negative assessments have only three validation examples). Confidence remains
uncalibrated. These are dialogue-act metrics, not commitment extraction scores.
The final test split has not been evaluated or used for selection.
