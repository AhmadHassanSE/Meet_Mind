"""Shared, versioned text construction and split validation for train and inference."""
import hashlib
import json
import re
from pathlib import Path

SCHEMA_VERSION = 1
ACTION_LABELS = {'off', 'sug', 'el.sug'}


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]


def write_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def session_group(meeting_id):
    # AMI scenario a/b/c/d meetings share a design team: never split them.
    return re.sub(r'(?<=\d)[a-d]$', '', meeting_id)


def build_inputs(segments, context_turns=2):
    """Sentence pair: current text first, past context second; never future turns.

    longest_first truncation keeps the target from being entirely displaced by
    context. Speaker identity is only a relative same/other marker, never a name.
    """
    inputs = []
    for index, segment in enumerate(segments):
        previous = segments[max(0, index - context_turns):index]
        context = []
        for item in previous:
            same = (item.get('speaker') is not None and
                    item.get('speaker') == segment.get('speaker'))
            context.append(('same speaker: ' if same else 'other speaker: ') + item['text'])
        inputs.append((segment['text'], ' '.join(context)))
    return inputs


def validate_splits(manifest):
    meetings, groups = set(), set()
    for name in ['train', 'validation', 'test']:
        current = set(manifest['splits'][name]['meetings'])
        current_groups = {session_group(m) for m in current}
        if not current or meetings & current or groups & current_groups:
            raise ValueError('Empty or leaking meeting/session split')
        meetings |= current
        groups |= current_groups


def load_split(directory, split):
    directory = Path(directory)
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    validate_splits(manifest)
    path = directory / f'{split}.jsonl'
    if sha256(path) != manifest['splits'][split]['sha256']:
        raise ValueError(f'{split} data changed since manifest creation')
    rows = read_jsonl(path)
    allowed = set(manifest['splits'][split]['meetings'])
    labels = set(manifest['labels'])
    ids = [r['id'] for r in rows]
    if (not rows or len(ids) != len(set(ids)) or
            any(r['meeting_id'] not in allowed or r['label'] not in labels or
                not r['text'].strip() for r in rows)):
        raise ValueError('Invalid labeled dataset rows')
    return rows, manifest


def training_sample(rows, limit, seed):
    """Stratified deterministic pilot sample; full runs use limit=0."""
    if not limit or limit >= len(rows):
        return rows
    from sklearn.model_selection import train_test_split
    indices, _ = train_test_split(range(len(rows)), train_size=limit,
                                  stratify=[r['label'] for r in rows], random_state=seed)
    return [rows[i] for i in sorted(indices)]
