# Transcript preparation

New pasted transcripts, TXT/MD/DOCX/caption uploads, and Whisper results are prepared before analysis. Recognized transcription reports lose wrapper metadata and decoration. The full-transcription section is removed only when its spoken content matches the structured section after speaker-label and whitespace normalization. Conflicting versions remain visible with a warning. Ordinary documents are not treated as reports solely because they contain a heading.

Plain report timestamps support multiple turns on one line. Speakers and source time ranges are preserved. English sentence boundaries protect common titles, initials, decimals and time abbreviations. Long sentences are split at word boundaries to fit the locally deployed tokenizer's target-plus-context budget. This is deterministic segmentation, not learned dialogue-act boundary detection. Short utterances may still rely on surrounding context for meaning.

For the current 96-token checkpoint and two prior context turns, each prepared utterance is limited to 29 WordPiece tokens, reserving speaker markers and pair special tokens. No model weights are loaded for preprocessing. Without the local tokenizer, character/word limits apply and the UI warns that truncation is still possible. Unbroken strings that require splitting inside a word carry a review flag.

Each meeting stores:

- `original_transcript`: original decoded text, or extracted DOCX paragraph text; for media, the original ASR transcript text.
- `source_segments`: unsplit source turns; text-source turns include Python character offsets into the original document.
- `segments`: prepared utterances with `parent_source_id` and half-open `source_start`/`source_end` offsets into the parent's `text`. `source` is that exact substring; `text` is normalized for analysis.
- `preprocessing`: version, counts, token budget, duplicate-removal status and warnings.

Caption/ASR children inherit their parent's complete time range (`timing_scope: source_segment`). No word timestamps are estimated. Original caption markup is retained in `original_transcript`; parent offsets refer to decoded cue text. Point timestamps are preserved in JSON but rejected by VTT export, which requires positive ranges.

The meeting page exposes the original transcript and expandable source turns. JSON downloads include all provenance. `GET /api/meetings/{id}/transcript?format=original` downloads the original text. Existing saved meetings remain unchanged; upload again to apply preparation and obtain fresh analysis. No model is retrained by this change.

## Verification on 10 October 2026

38 backend tests passed and the frontend production build passed. Five complete AMI validation meetings and two local report files passed actual upload/classify/persistence/export/source-coverage checks. Browser checks passed for all seven, including original text, source turns, reload persistence and 390px layout.

| Input | Source turns | Prepared utterances | BERT input truncated |
|---|---:|---:|---:|
| AMI ES2005a | 140 | 148 | 0 |
| AMI IS1005a | 263 | 286 | 0 |
| AMI IS1007a | 348 | 367 | 0 |
| AMI TS3006a | 655 | 702 | 0 |
| AMI TS3010a | 219 | 245 | 0 |
| sampleTra_report.txt | 47 | 108 | 0 |
| transcription.txt | 226 | 232 | 0 |

Both report files had matching duplicate sections removed. Before preparation the two reports produced 19 and 68 truncated BERT inputs respectively. This demonstrates removal of truncation on these examples, not improved classification accuracy. Prepared boundaries differ from AMI gold dialogue-act boundaries, so this audit deliberately omits accuracy/F1 rather than copying parent labels to children. Final test data was not used. Existing raw-boundary training and evaluation remain available independently.

Private fixture text, full outputs and browser database remain in ignored `backend/runs/preprocessing-audit-v2`. The reproducible API audit is `scripts.audit_bert_meetings`; browser audit is `frontend/scripts/audit-bert-ui.cjs`. Compact evidence is tracked in `reports/preprocessing-audit-2026-10-10`.
