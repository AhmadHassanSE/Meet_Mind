# BERT-base held-out test evaluation: 14 November 2026

This is the one-time evaluation of the frozen, selected dialogue-act model on the **held-out AMI test split**. The split was never used for training, epoch choice, learning-rate choice or model selection; all of those used validation only (`reports/bert-base-comparison-v1`). It closes the Iteration 1 milestone "baseline F1 results, BERT fine-tuned".

## What was evaluated

| Item | Value |
|---|---|
| Model | `google-bert/bert-base-uncased`, fully fine-tuned, learning rate 3e-5, best epoch by validation macro F1 |
| Weights | `model.safetensors` SHA-256 `5a70014dec35d58aa1c4661fc2d93cda5986d20e49b0eb317968f8bf78f472eb`. This is the same file as `models/dialogue-bert-base-v1` and `runs/bert-base-colab-v1/bert-base-gpu-lr3e5/best`. |
| Data | AMI v1.6.2 manual dialogue acts, 15 labels, session-disjoint split. Manifest SHA-256 `f6cf4e2856ec…`. **Test: 14,882 utterances from 21 meetings.** |
| Baselines | Majority class; TF-IDF (1–2-grams) + class-balanced logistic regression fit on all 82,294 training rows; keyword rules (`nlp/rules.py`, written before looking at test and not fitted to any data) |
| Machine | Windows laptop CPU, 4 threads; evaluation took 18 minutes |

Commands, run from `meetmind/backend`:

```powershell
python -m scripts.evaluate_bert --checkpoint <run>/bert-base-gpu-lr3e5/best --data data/ami-da-v1 --split test --device cpu --output reports/bert-base-test-v1/test_metrics.json
python -m scripts.rule_baseline --data data/ami-da-v1 --output reports/bert-base-test-v1/rule_baseline_metrics.json
```

## Results: held-out test (14,882 utterances)

| Model | Accuracy | Macro F1 | Weighted F1 |
|---|---:|---:|---:|
| Majority class (`inf`) | 0.3289 | 0.0330 | 0.1628 |
| Keyword rules | 0.4884 | 0.2608 | 0.4167 |
| TF-IDF + logistic regression | 0.4553 | 0.3264 | 0.4660 |
| **Fine-tuned BERT-base** | **0.6632** | **0.5271** | **0.6623** |

The selected model had validation macro F1 0.5293. Test macro F1 0.5271 is close to that, so the validation-based selection did not overfit noticeably. The weighted F1 is higher on test (0.6623 versus 0.6322) because the class mix differs between splits.

### Per-class F1 on test

| Label | Meaning | Support | Rules | TF-IDF | BERT |
|---|---|---:|---:|---:|---:|
| inf | Inform | 4,895 | 0.635 | 0.557 | **0.767** |
| ass | Assess | 2,595 | 0.123 | 0.363 | **0.510** |
| bck | Backchannel | 1,465 | 0.613 | 0.618 | **0.695** |
| sug | Suggest | 1,393 | 0.224 | 0.440 | **0.614** |
| fra | Fragment | 1,246 | 0.394 | 0.427 | **0.789** |
| stl | Stall | 1,168 | 0.455 | 0.550 | **0.758** |
| el.inf | Elicit-inform | 572 | 0.565 | 0.297 | **0.632** |
| und | Comment-about-understanding | 319 | 0.000 | 0.245 | **0.372** |
| be.pos | Be-positive | 300 | 0.273 | 0.425 | **0.490** |
| el.ass | Elicit-assessment | 293 | 0.118 | 0.211 | **0.493** |
| oth | Other | 269 | 0.000 | 0.216 | **0.323** |
| off | Offer | 217 | 0.458 | 0.279 | **0.589** |
| el.sug | Elicit-offer-or-suggestion | 90 | 0.019 | 0.150 | **0.371** |
| el.und | Elicit-comment-understanding | 34 | 0.000 | 0.119 | **0.384** |
| be.neg | Be-negative | 26 | 0.036 | 0.000 | **0.121** |

BERT has the best F1 on all 15 classes. The confusion matrices for all three learned and rule models are in the two JSON files. `test_metrics.json` also contains every prediction with its id, meeting and score, for error analysis.

### Main BERT errors (gold → predicted)

| Count | Confusion | Likely cause |
|---:|---|---|
| 676 | Assess → Backchannel | Short evaluative replies ("yeah, good") look like acknowledgements |
| 503 | Inform → Suggest | Statements about the design read as proposals ("it would have a…") |
| 481 | Inform → Assess | Opinionated statements; the boundary is subjective in the AMI guidelines |
| 241 | Suggest → Inform | The reverse of the above |
| 227 | Assess → Inform | The reverse of the above |
| 162 | Assess → Stall | Short hedged replies |

For MeetMind the action-related acts matter most: offer F1 0.589, suggest 0.614, elicit-offer-or-suggestion 0.371. BERT labels are therefore used only as **hints** for commitment extraction. Every extracted item still needs human review.

## Target and limitations

- **The macro F1 ≥ 0.73 target is not achieved** (measured 0.5271). Macro F1 weighs the rare classes heavily: be.neg has 69 training and 26 test examples; el.und has 152 and 34. Published 15-class AMI dialogue-act work reports accuracy of roughly 0.65–0.75. This model's accuracy of 0.663 is in that range, but because this split is custom and session-disjoint, the numbers are not directly comparable.
- **The test split has now been used once.** Any further model change must be selected on validation. If a new model is reported against test, that second use must be disclosed.
- These are dialogue-act classification metrics on gold AMI segments. They are **not** commitment, owner or deadline extraction accuracy, and not performance on ASR transcripts.
- One training seed; fp16 GPU training is not bit-reproducible. Scores are uncalibrated softmax outputs.
- Weights and data are gitignored. They can be rebuilt with `scripts/prepare_ami.py` and the recorded configuration, and checked against the hashes above.
