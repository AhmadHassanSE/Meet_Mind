"""Deterministic transcript preparation with reversible source references.

Offsets are Python character offsets into source_segments[*].text, not bytes.
Timed children inherit their parent's complete time range; no word timing is inferred.
"""
import json
import re
from pathlib import Path

from .ingestion import clean, timestamp, IngestionError

VERSION = '1.1'
TIME = re.compile(r'\[(\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d+)?)\s*-\s*(\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d+)?)\]\s*')
POINT_SPEAKER = re.compile(r'^\[(\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d+)?)\s*[-–]\s*([^\]\r\n]{1,60})\]:[ \t]*')
SPEAKER = re.compile(r"^([^:\r\n]{1,60}):[ \t]*(?!//)")
ABBREVIATIONS = {'mr', 'mrs', 'ms', 'dr', 'prof', 'sr', 'jr', 'vs', 'etc', 'e.g', 'i.e', 'a.m', 'p.m'}


def text_sources(text):
    """Read line turns and report-style timed turns, retaining document offsets."""
    result = []
    for line in re.finditer(r'[^\r\n]+', text):
        times = list(TIME.finditer(line[0]))
        spans = [(m.end(), times[i + 1].start() if i + 1 < len(times) else len(line[0]), m)
                 for i, m in enumerate(times)] if times else [(0, len(line[0]), None)]
        if times and line[0][:times[0].start()].strip():
            spans.insert(0, (0, times[0].start(), None))
        for a, b, timing in spans:
            raw = line[0][a:b]
            leading = len(raw) - len(raw.lstrip())
            raw = raw.strip()
            if not raw:
                continue
            point = POINT_SPEAKER.match(raw)
            name = None if point else SPEAKER.match(raw)
            body_start = a + leading + (point.end() if point else name.end() if name else 0)
            body = line[0][body_start:b].rstrip()
            if not body:
                continue
            start, end = (timestamp(timing[1]), timestamp(timing[2])) if timing else (None, None)
            if point:
                start = end = timestamp(point[1])  # Point timing: never invent an end.
            if start is not None and end < start:
                raise IngestionError('Transcript timestamp end precedes its start')
            result.append({'id': len(result) + 1, 'speaker': point[2].strip() if point else name[1] if name else None,
                           'text': body, 'source': raw, 'start': start, 'end': end,
                           'document_start': line.start() + body_start,
                           'document_end': line.start() + body_start + len(body)})
    return result


def report_sources(original):
    """Recognize our transcription report wrapper, never general document headings."""
    warnings = []
    heading = re.search(r'(?m)^\s*FULL TRANSCRIPTION\s*$', original)
    signature = 'MEETING TRANSCRIPTION REPORT' in original[:300]
    if not signature or not heading or not re.search(r'[=\-]{10,}', original[:500]):
        return text_sources(original), {'report_detected': False, 'duplicate_section_removed': False}, warnings
    structured = re.search(r'(?m)^\s*TIMESTAMPED SEGMENTS\s*$', original[heading.end():])
    split = heading.end() + structured.start() if structured else len(original)
    structured_start = heading.end() + structured.end() if structured else len(original)

    def section(a, b):
        # Replace decoration with whitespace to retain original character positions.
        body = re.sub(r'(?m)^[ \t]*[=\-]{10,}[ \t]*$', lambda m: ' ' * len(m[0]), original[a:b])
        items = text_sources(body)
        for item in items:
            item['document_start'] += a
            item['document_end'] += a
        return items

    full, turns = section(heading.end(), split), section(structured_start, len(original))
    names = {item['speaker'] for item in turns if item['speaker']}
    def canonical(items):
        value = ' '.join(item['text'] for item in items)
        for name in sorted(names, key=len, reverse=True):
            value = re.sub(r'(?<!\w)' + re.escape(name) + r':\s*', '', value)
        return clean(value)
    duplicate = bool(full and turns and canonical(full) == canonical(turns))
    if full and turns and not duplicate:
        warnings.append('Report sections differ: both versions retained for review.')
    parents = turns if duplicate else full + turns
    for i, parent in enumerate(parents, 1):
        parent['id'] = i
    return parents, {'report_detected': True, 'duplicate_section_removed': duplicate}, warnings


def token_policy():
    """Use the deployed local tokenizer, with room for target + previous turns."""
    from .bert import model_path
    try:
        from tokenizers import Tokenizer
        path = model_path()
        metadata = json.loads((path / 'meetmind_model.json').read_text(encoding='utf-8'))
        tokenizer = Tokenizer.from_file(str(path / 'tokenizer.json'))
        tokenizer.no_padding()
        tokenizer.no_truncation()
        context = int(metadata['context_turns'])
        marker = max(len(tokenizer.encode(s, add_special_tokens=False).ids)
                     for s in ('same speaker: ', 'other speaker: '))
        budget = (int(metadata['max_length']) - 3 - context * marker) // (context + 1)
        if budget < 8:
            raise ValueError('Unsupported context budget')
        return tokenizer, budget
    except (ImportError, OSError, ValueError, KeyError):
        return None, 40


def sentence_ranges(text):
    start = 0
    for match in re.finditer(r'''(?:[.!?]+["')\]]*(?=\s|$)|[۔؟]+["')\]]*)''', text):
        prefix = text[max(0, match.start() - 100):match.start()]
        word = re.search(r'([\w.]+)$', prefix)
        if match[0].startswith('.') and word:
            token = word[1].lower()
            if token in ABBREVIATIONS or len(token) == 1 or re.fullmatch(r'(?:[a-z]\.)+[a-z]', token):
                continue
        yield start, match.end()
        start = match.end()
    if text[start:].strip():
        yield start, len(text)


def prepare(original, parents=None):
    if parents is None:
        parents, details, warnings = report_sources(original)
    else:
        parents = [dict(p) for p in parents]
        details, warnings = {'report_detected': False, 'duplicate_section_removed': False}, []
    tokenizer, budget = token_policy()
    if tokenizer is None:
        warnings.append('Local tokenizer unavailable: heuristic size limits applied; BERT may still truncate.')
    segments = []
    for parent in parents:
        text = parent['text']
        for a, b in sentence_ranges(text):
            while a < b:
                while a < b and text[a].isspace():
                    a += 1
                if a == b:
                    break
                remaining = text[a:min(b, a + 4096)]
                if tokenizer:
                    encoding = tokenizer.encode(remaining, add_special_tokens=False)
                    cut = encoding.offsets[budget - 1][1] if len(encoding.ids) > budget else len(remaining)
                else:
                    words = list(re.finditer(r'\S+', remaining))
                    cut = min(240, words[budget - 1].end() if len(words) > budget else len(remaining))
                if tokenizer:
                    # NFKC cleaning can expand compatibility characters. Budget
                    # the actual model text while keeping offsets in the original.
                    while cut > 1 and len(tokenizer.encode(clean(remaining[:cut]), add_special_tokens=False).ids) > budget:
                        cut = max(1, cut // 2)
                forced = False
                if cut < b - a:
                    # Prefer a complete word, preserving conjunctions/negation verbatim.
                    boundary = max(remaining.rfind(' ', 0, cut + 1), remaining.rfind('\t', 0, cut + 1))
                    if boundary > 0:
                        cut = boundary
                    else:
                        forced = True
                end = a + max(1, cut)
                raw = text[a:end].rstrip()
                if raw:
                    segments.append({'id': len(segments) + 1, 'speaker': parent.get('speaker'),
                                     'text': clean(raw), 'source': raw,
                                     'start': parent.get('start'), 'end': parent.get('end'),
                                     'parent_source_id': parent['id'], 'source_start': a, 'source_end': a + len(raw),
                                     'timing_scope': 'source_segment' if parent.get('start') is not None else None,
                                     'preprocessing_review': ['split_inside_word'] if forced else []})
                a = end
    if not segments:
        raise IngestionError('No transcript utterances found')
    if any(s['preprocessing_review'] for s in segments):
        warnings.append('Some long unbroken strings were split inside a word; review their source turns.')
    return {'segments': segments, 'source_segments': parents, 'original_transcript': original,
            'transcript': '\n'.join(s['text'] for s in segments),
            'preprocessing': {'version': VERSION, 'source_count': len(parents), 'utterance_count': len(segments),
                              'token_budget': budget if tokenizer else None, 'warnings': warnings, **details}}
