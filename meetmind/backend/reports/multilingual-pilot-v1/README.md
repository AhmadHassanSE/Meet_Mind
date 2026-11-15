# Multilingual implementation pilot

Base: `feat/commitment-review` at `0ee75bf`, the latest remote non-Meet branch
when work began. Implementation: `feat/urdu-roman-urdu`.

## Recorded functional evidence

- 103 backend tests passed in the NLP environment; the existing Starlette/httpx
  deprecation warning remains. No tests failed or were skipped in that run.
- TypeScript/Vite production build passed.
- Headless Chrome checked language selection/submission, original Urdu text,
  translation review, RTL direction and 390px mobile layout. This check mocks API
  responses and starts no servers; it is not an inference test.
- Actual local Ollama/BERT/spaCy/rule extraction checks completed for English,
  Roman Urdu, Urdu script, mixed input and the user-provided project review.
  Each checked exact source offsets and persisted an approval in a temporary DB.
  `functional_checks.json` records observed counts, not accuracy scores.
- Multilingual Whisper `base` was cached and passed the existing real 20-second
  English recording ingestion/export check with language forced to English.
  The short clip's automatic-language run produced poor mixed-script text; this
  is why explicit speech-language selection and transcript review are documented.
  No real Urdu audio sample was available, so Urdu ASR accuracy is unmeasured.

The synthetic short checks and user fixture are smoke tests, not a gold-labelled
benchmark. The successful user fixture produced two proposed commitments. Sara's
build action retained owner `سارا` and deadline `دو بجے تک`. The final-review item
kept owner/deadline unresolved because its complete supporting turn contained
several assignments/date expressions. The API repair promise and several requests
were omitted by the model. The final mixed short check produced one action from
two promises. These are recall limitations, not evidence of complete extraction.

Initial real runs exposed inadequate Urdu output from Llama 3.2, duplicated
translation IDs, altered quote text and unsupported translated task summaries.
Fixes use a separate local Qwen3 multilingual model, a keyed translation schema,
allowed source IDs with server-attached verbatim turn evidence, and flagged
original-clause task fallback. Unsupported deadline extensions are rejected.
The English extractor keeps its original exact-substring quote contract.

The selected BERT weights remain the English AMI fine-tune. Machine translation
introduces a new error source; the English AMI validation F1 does not establish
Urdu or Roman Urdu performance. Urdu task extraction uses conservative source
rules, not an Urdu-trained spaCy NER/parser. All extracted items require review.

## Reproduce

Follow [multilingual setup](../../MULTILINGUAL.md), then from backend:

```powershell
python -m pytest -q
python -m scripts.smoke_languages
python -m scripts.smoke_languages --fixture "User-provided Urdu"
```

The full smoke uses four synthetic examples plus the checked-in user-provided
transcript. CPU duration varies substantially with memory pressure, model loading
and paused execution; no latency benchmark is claimed. Full local JSON output is
ignored under `runs/`; compact functional evidence is tracked here. Before calling
this production-ready, annotate representative Urdu/Roman Urdu/code-switched
meetings and score task recall, precision, owner/date accuracy and Urdu ASR WER.

No Google Meet branches were merged. Additional development server startup was
rejected by automatic approval during verification. The existing Meet servers
were left unchanged; subsequent UI verification used a serverless mocked browser.
AI-assisted implementation and checks require team review and ownership.
