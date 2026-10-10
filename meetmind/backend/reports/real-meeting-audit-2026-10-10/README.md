# Real-transcript pilot verification — 10 October 2026

Seven full text files were uploaded and analyzed through the actual BERT endpoint and the browser’s **Analyze with BERT** button. Five are official AMI validation meetings; two are existing workspace transcript reports. No model weights were retrained or tuned during this audit. The final test split was not loaded.

## Measured classification quality

| AMI meeting | Annotated utterances | Correct labels | Accuracy |
|---|---:|---:|---:|
| AMI ES2005a | 140 | 83 | 59.3% |
| AMI IS1005a | 263 | 146 | 55.5% |
| AMI IS1007a | 348 | 187 | 53.7% |
| AMI TS3006a | 655 | 365 | 55.7% |
| AMI TS3010a | 219 | 119 | 54.3% |

Pooled results: **900/1,625 correct (55.4% accuracy), macro F1 0.4070, weighted F1 0.5597**. Offer F1 0.3279 (24 examples), Suggest F1 0.4103 (151), Elicit-Offer-Or-Suggestion F1 0.2564 (17). These are dialogue-act metrics, not task/owner/deadline extraction accuracy.

Selection was deterministic: the first meeting ID from each of the five validation design sessions (ES2005, IS1005, IS1007, TS3006, TS3010). All five sessions are disjoint from training. They are a subset of the already evaluated validation data, so this is an integration/error audit, not fresh independent test evidence. Per-meeting accuracy is descriptive; the dataset and model remain unchanged.

AMI attribution: official manual annotations v1.6.2, CC BY 4.0. https://groups.inf.ed.ac.uk/ami/corpus/ and https://groups.inf.ed.ac.uk/ami/download/ . Source, dataset and model hashes are recorded in summary.json and the original pilot evidence.

## Functional checks

All seven files passed transcript upload, real BERT inference, one result per source segment, unchanged transcript evidence, SQLite persistence, JSON export and possible-action review safeguards. No confirmed action tasks were created by dialogue classification.

All seven also passed real Chrome checks: file upload, Analyze with BERT, rendered prediction count, reload persistence, visible target-truncation warnings where applicable, and 390px layout without horizontal overflow. Browser JavaScript error checks passed. Existing development servers were left separate; audit servers used ports 8013/5183 and a dedicated database.

31 backend tests and TypeScript/Vite production build passed after the fixes.

## Problems found and addressed

1. **Silent truncation.** Report paragraphs greatly exceeded the pilot’s 96-token sentence-pair budget. The two reports had maximum target lengths of 1,401 and 3,393 tokens. Classification now records original/processed target and input token counts, flags shortened target text or context, and requires review even when the model score is high. Labels and weights are unchanged. The fix exposes partial coverage; it does not recover discarded text or solve segmentation.
2. **Mobile overflow.** Long report separators overflowed the transcript column. Text wrapping and panel sizing were corrected; the complete seven-file browser audit then passed.

| Workspace report | Parsed lines | Target text shortened | Target or context shortened |
|---|---:|---:|---:|
| sampleTra_report.txt | 59 | 8 | 19 |
| transcription.txt | 78 | 43 | 68 |

The workspace files include report headers/separators and full-transcript/report formatting rather than clean gold-labeled dialogue turns. Their source provenance is unverified; no accuracy claim is made for them. One report can include duplicated text and metadata that the generic text parser treats as transcript lines. Prefer clean speaker turns, one per line, without report headers or duplicated full-text sections.

## Quality issues still open

- Of 725 incorrect AMI labels, 167 had model score at least 0.7, and 131 were not flagged by the current review rules. A high score or absence of a review badge does not establish correctness. The score/margin cutoffs are uncalibrated heuristics.
- Frequent confusions include Inform → Suggest (68), Assess → Backchannel (61), Inform → Assess (54), and Suggest → Inform (49). Some action-related utterances are missed or misidentified.
- Gold AMI act boundaries are cleaner than uploaded reports or ASR turns. A report cleaner and evaluated utterance segmentation are needed before claiming support for arbitrary long prose.
- Full BERT-base training, validation-based model comparison, confidence calibration and final frozen-test evaluation remain outstanding. No automatic external execution should depend on this pilot.

## Most useful additional data

Provide anonymized English transcripts from the meetings MeetMind is intended to handle. Prefer speaker labels, one turn per line, meeting dates and intact dialogue context. Include expected confirmed tasks, owners and deadlines where known, plus negated/cancelled tasks, suggestions without commitments and examples with no tasks. For supervised classifier improvement, map reviewed utterances to a consistent dialogue-act/commitment labeling guide. Unlabeled transcripts are still useful for error analysis and can be annotated together.

Keep each meeting/session entirely within one split. Reserve a new unseen target-domain evaluation set before training/tuning on any supplied examples. No private transcript text or screenshots were committed; only aggregate measurements and reproducible code are in Git.

## Reproduction

From meetmind/backend, use the .venv-nlp environment:

```powershell
.\.venv-nlp\Scripts\python.exe -m scripts.audit_bert_meetings --output runs/real-meeting-audit-new --workspace-files "path/to/report1.txt" "path/to/report2.txt"
```

With a dedicated backend/frontend running, from meetmind/frontend:

```powershell
$env:MEETMIND_UI_URL = 'http://127.0.0.1:5183'
node scripts/audit-bert-ui.cjs "../backend/runs/real-meeting-audit-new/fixtures.json" "browser-results.json"
```

Use a new output directory to preserve previous evidence. Full local fixtures and audit outputs are ignored under backend/runs. This work was performed with Codex assistance at Rana’s direction; it does not imply independent contributions from other members.
