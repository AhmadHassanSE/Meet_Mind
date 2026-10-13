# English, Urdu and Roman Urdu

Branch: `feat/urdu-roman-urdu`, based on the latest non-Meet branch
`feat/commitment-review` at `0ee75bf`. Google Meet remains separate.

## Supported inputs

The UI's **Meeting language** selector applies to paste, transcript files and
audio/video uploads. Values: `auto`, `en`, `ur`, `roman-ur`.
JSON paste requests and multipart uploads use `input_language` (default `auto`).
The meeting stores `input_language` and a `language_profile`. Short Roman Urdu
is ambiguous, so explicit selection is recommended. Detection uses script and
word heuristics; it is not a trained language identification model. Forced
English deliberately bypasses translation, so choose the correct language.

Examples:

```text
Ali: I will send the report by Friday.
Ali: Main report kal bhej dunga.
علی: میں رپورٹ کل بھیج دوں گا۔
[00:42 - سارا]: ہاں بالکل علی، میں دو بجے تک نیا بلڈ ٹیسٹ سرور پر اپ لوڈ کر دوں گی۔
```

The last format preserves a point timestamp: start equals end. No end time is
invented; VTT export consequently requires genuine positive time ranges.
Original UTF-8 text, source speakers and evidence offsets remain unchanged.
Urdu punctuation `۔` and `؟` is segmented. UI evidence/input/review fields use
automatic text direction; Urdu can display right to left alongside English UI.

## Local models and setup

English extraction still uses `OLLAMA_MODEL` (default `llama3.2:latest`).
Multilingual translation and extraction use `OLLAMA_MULTILINGUAL_MODEL`
(default **`qwen3:4b`**, approximately 2.5 GB download). Qwen's official language
list includes Urdu; that is not a MeetMind accuracy benchmark:
https://qwenlm.github.io/blog/qwen3/

```powershell
ollama pull qwen3:4b
cd meetmind/backend
$env:OLLAMA_MULTILINGUAL_MODEL='qwen3:4b'
$env:WHISPER_MODEL='small'
uv run --extra nlp uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Qwen3 thinking is disabled for bounded structured outputs. A missing model
causes an explicit error, not an English-only fallback. `/api/health` reports
the multilingual model name/status separately from the English extractor.
CPU inference on longer transcripts can take several minutes. `OLLAMA_TIMEOUT_SECONDS` configures extraction request timeout (default 600 seconds). Model inference remains local to Ollama; no hosted AI key/provider is added.
Downloads need internet. Existing Google Meet servers do not automatically pick
up this feature branch or its new configuration.

### Audio and recordings

The default speech model is now multilingual Whisper **`small`**, replacing
`base.en`. The first use downloads its weights. `en` forces English, `ur` and
`roman-ur` force Urdu speech recognition, and `auto` allows language
detection. The task is **transcribe**, not translate. Urdu speech normally yields
Urdu script; the Roman Urdu option does not promise Romanized ASR output.

Whisper language detection on short audio and English/Urdu code switching can
fail; select English/Urdu explicitly when known and review the transcript.
`base` is a small CPU model; Urdu recording accuracy has not been established.
`WHISPER_MODEL` can select another multilingual Whisper model if resources allow.
An English-only `.en` model explicitly rejects Urdu/auto audio instead of
silently treating it as English. It can still be used with `input_language=en`.

## BERT and commitment processing

1. Preserve the original source transcript and prepared segments.
2. For Urdu/Roman Urdu input, translate bounded batches locally to English.
   Require each original source ID exactly once using a constrained keyed object; reject missing, duplicate, unexpected or truncated output and restore original turn order before storing analysis.
3. Classify those translations with the existing fine-tuned English BERT.
   Translation text/model and warnings are stored under
   `dialogue_analysis.language_processing`; predictions require human review.
4. Extract proposals from **original-language turns**. Deadlines must be verbatim source text. In multilingual batches the model selects an allowed source-turn ID and the server attaches that turn verbatim as its quote; English-only batches keep the original substring quote contract. English spaCy NER/parser is used for English turns;
   Urdu/Roman turns use explicitly labelled conservative lexical rules, not
   claimed Urdu NER or parsing. Source-level owner/deadline/negation checks keep
   ambiguous fields unresolved and suggestions/requests/cancellations separate. If a multilingual task summary has no lexical support, keep the verbatim supporting clause as the task and flag it for editing; do not accept the unsupported summary.
5. Use the existing revisioned commitment review flow. Translation never replaces
   source evidence. Task lexical support is a conservative filter, not entailment.

This does **not** retrain BERT on Urdu. The recorded AMI validation macro F1
0.5292777 applies to English AMI dialogue acts only. It is not an Urdu, translation
or commitment extraction score. Urdu and Roman Urdu quality is experimental;
spelling variation, inferred references, negation scope and calendar grounding
still require evaluation and human review. Relative dates such as `kal`/`کل`
retain their original wording; no calendar date is inferred.

## Checks

```powershell
# Run from backend, with the nlp environment active:
python -m pytest -q
python -m scripts.smoke_languages
python -m scripts.smoke_media --language ur path/to/urdu.wav

# Run from frontend:
npm.cmd run build
node scripts/smoke-languages-ui.cjs
```

The language smoke exercises actual Ollama, BERT, grounding and approval
persistence in an isolated temporary DB. It uses four synthetic examples and the
user-provided project-review transcript; it is not a labelled accuracy benchmark.
The browser smoke uses the production build and mocked API responses without
starting servers. It checks language submission, source display, translation
review, RTL and mobile layout; it does not test inference. Ignored `runs/` folders
contain local results/screenshots. The user-provided transcript is tracked as a
regression fixture, not as a scored gold commitment annotation set.

AI-assisted implementation and fixtures must be reviewed and understood by the
team before evaluation. Native Urdu BERT fine-tuning, a labelled multilingual
commitment benchmark, calibrated confidence, robust code-switch ASR and Google
Meet branch reconciliation remain separate work.
