# BERT-base confidence calibration: 15 November 2026

The softmax scores of the selected BERT-base model (weights `5a70014d…`) were over-confident. **Temperature scaling** divides the logits by one learned number, T, before softmax. That makes the scores better match how often the model is actually right, without changing any predicted label.

- T was fitted on the **validation split only**, by minimising negative log-likelihood: **T = 1.2281**.
- The held-out **test split was used only to report** the effect. It did not influence T or the model. This is the second use of test, after the one-time evaluation in `../bert-base-test-v1`, and it is disclosed here.
- Command: `python -m scripts.calibrate_bert --checkpoint <run>/bert-base-gpu-lr3e5/best --data data/ami-da-v1 --output reports/bert-base-calibration-v1`. This was a CPU run; it was paused while the laptop slept, so its wall time is not meaningful.

## Results (15-bin expected calibration error, ECE)

| Split | Utterances | ECE before | ECE after | NLL before | NLL after | Accuracy |
|---|---:|---:|---:|---:|---:|---:|
| Validation (fit) | 13,593 | 0.1036 | 0.0419 | 1.0595 | 1.0309 | 0.6314 |
| **Test (held-out)** | 14,882 | **0.1063** | **0.0433** | 1.0003 | 0.9660 | 0.6632 |

Accuracy is unchanged because the label ranking does not change. It also matches the earlier evaluations (0.6314 validation, 0.6632 test), which confirms that the same inputs were used. On held-out data the calibration error falls by about 59%: a predicted confidence of, say, 0.8 is now right about 80% of the time, within roughly 4 percentage points on average. The reliability diagram is `reliability.svg`; the per-bin values are in `calibration_metrics.json`.

## How MeetMind uses it

- `calibration.json` (temperature plus the model weights hash) is copied into the model folder. `app/bert.py` applies it **only if the weights hash matches**, then reports `confidence_calibrated: true` and the temperature with every analysis. The review thresholds (`MEETMIND_REVIEW_THRESHOLD`, `MEETMIND_REVIEW_MARGIN`) now act on calibrated probabilities.
- The commitment **review score** (`app/deadlines.py`) uses the calibrated action-act probability, multiplied by penalties for a missing owner or date. That product is a documented heuristic for ordering review, **not** a calibrated probability.

## Limits

- Calibration was measured on AMI gold dialogue-act segments. It may not hold for ASR transcripts, other meeting styles, or Urdu text translated before classification.
- A single temperature cannot fix per-class miscalibration in rare classes (be.neg, el.und).
