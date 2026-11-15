# BERT-base improvement study: prepared, not GPU-trained

The existing selected model scores validation macro F1 **0.5292777** and weighted
F1 **0.6321866** on the frozen 15-class AMI split. The requested **0.73 macro F1**
is a target, not a recorded result. No serving weights or historical scores changed.

`input-audit.json` diagnoses the existing confusion matrix and tokenization on
all 13,593 validation rows. There was **no input truncation** at the original
two-turn/128-token setting; truncation is not the measured cause of the baseline
errors. The new settings add more preceding discourse context. Target-preserving
encoding also protects long deployment inputs; it is not claimed as an observed
AMI validation repair. The eight-turn setting truncated one context, no targets.

The largest confusion is Assess → Backchannel (637 examples), followed by
Assess → Inform (478) and Inform → Suggest (473). Lowest class F1 values include
Be-Negative (0.1818; only 3 validation examples), Comment-About-Understanding
(0.2539) and Elicit-Offer-Or-Suggestion (0.3982). These support counts make macro
F1 sensitive to small changes. No labels, class definitions or split boundaries
were changed to increase a score.

The three predeclared candidates keep BERT-base and all training/validation rows:

1. Four previous turns, recent-first ordering, 192 tokens, unweighted CE.
2. Same input/optimizer settings with capped square-root inverse-frequency CE.
3. Eight previous turns, 256 tokens, effective-number weighting and focal loss.

All use layer learning-rate decay, a faster classification head, zero bias/norm
weight decay, configurable warm-up, eight maximum epochs and patience three.
Effective batch size stays 32. Training, validation and serving share the same
encoding implementation. Default/old checkpoints retain their original format.

The same existing baseline weights are exported for GPU re-evaluation with full
predictions. New comparisons recompute metrics from predictions on identical
validation IDs/gold labels. Only train/validation data are uploaded; final test
rows, private meetings and credentials are excluded. Completed epoch resume and
input/source hashes protect experiment provenance. The study may fail to reach
0.73; `goal.json` must report the actual outcome. Validation selection remains
distinct from an independent final-test estimate.

Local functional tests use a tiny synthetic BERT to exercise training, exact
resume, optimizer groups and serving parity. They do not establish an AMI score.
Run the Colab notebook and return the result archive before model promotion.

Method references (used as candidate ideas, not evidence of gains on MeetMind):
- [Class-balanced loss, Cui et al., CVPR 2019](https://openaccess.thecvf.com/content_CVPR_2019/papers/Cui_Class-Balanced_Loss_Based_on_Effective_Number_of_Samples_CVPR_2019_paper.pdf)
- [Original BERT optimizer: bias/LayerNorm decay exclusions](https://github.com/google-research/bert/blob/master/optimization.py)
