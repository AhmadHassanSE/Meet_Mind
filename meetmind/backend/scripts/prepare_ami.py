"""Download official AMI manual annotations and create session-disjoint DA data."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import random
import re
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

from nlp.data import build_inputs, session_group, sha256, validate_splits, write_json

URL = 'https://groups.inf.ed.ac.uk/ami/AMICorpusAnnotations/ami_public_manual_1.6.2.zip'
NITE = '{http://nite.sourceforge.net/}'


def xml(data):
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise ValueError('DTD/entities are not accepted')
    return ET.fromstring(data)


def read_annotations(archive):
    """Read linked word spans in archive order (including non-word ID anchors)."""
    rows, skipped = [], Counter()
    with zipfile.ZipFile(archive) as z:
        ontology = xml(z.read('ontologies/da-types.xml'))
        labels = {e.attrib[NITE + 'id']: {'name': e.attrib['name'], 'description': e.attrib['gloss']}
                  for e in ontology.iter() if re.fullmatch(r'ami_da_\d+', e.get(NITE + 'id', ''))}
        for name in sorted(z.namelist()):
            if not name.startswith('dialogueActs/') or not name.endswith('.dialog-act.xml'):
                continue
            prefix = Path(name).name.removesuffix('.dialog-act.xml')
            meeting, speaker = prefix.rsplit('.', 1)
            word_path = f'words/{prefix}.words.xml'
            if word_path not in z.namelist():
                raise ValueError(f'Missing transcript {word_path}')
            words = list(xml(z.read(word_path)))
            positions = {w.get(NITE + 'id'): i for i, w in enumerate(words)}
            for act in xml(z.read(name)):
                pointers = [p for p in act if p.get('role') == 'da-aspect']
                if not pointers:
                    skipped['unlabeled_acts'] += 1
                    continue
                if len(pointers) != 1:
                    raise ValueError(f'Invalid dialogue act label: {name}')
                label_id = re.search(r'#id\(([^)]+)\)', pointers[0].get('href', '')).group(1)
                if label_id not in labels:
                    raise ValueError(f'Unknown ontology label {label_id}')
                selected = []
                for child in act:
                    if child.tag != NITE + 'child':
                        continue
                    target, span = child.get('href', '').split('#', 1)
                    if target != f'{prefix}.words.xml':
                        raise ValueError('Cross-speaker transcript span')
                    anchors = re.findall(r'id\(([^)]+)\)', span)
                    if not 1 <= len(anchors) <= 2:
                        raise ValueError('Invalid NXT word range')
                    first, last = positions[anchors[0]], positions[anchors[-1]]
                    if first > last:
                        raise ValueError('Reversed word range')
                    selected.extend(words[first:last + 1])
                lexical = [w for w in selected if w.tag == 'w' and w.text]
                text = ' '.join(w.text.strip() for w in lexical)
                text = re.sub(r'\s+([.,!?;:])', r'\1', text).strip()
                if not text:
                    skipped['nonlexical_acts'] += 1
                    continue
                starts = [float(w.get('starttime')) for w in selected if w.get('starttime') is not None]
                ends = [float(w.get('endtime')) for w in selected if w.get('endtime') is not None]
                rows.append({'id': act.attrib[NITE + 'id'], 'meeting_id': meeting,
                             'speaker': speaker, 'text': text, 'label': labels[label_id]['name'],
                             'annotation_label_id': label_id, 'start': min(starts) if starts else None,
                             'end': max(ends) if ends else None})
    return rows, labels, dict(skipped)


def prepare(archive, output, seed=42, context_turns=2):
    rows, ontology, skipped = read_annotations(archive)
    meetings = defaultdict(list)
    for row in rows:
        meetings[row['meeting_id']].append(row)
    for items in meetings.values():
        items.sort(key=lambda r: (r['start'] if r['start'] is not None else float('inf'), r['id']))
        for row, (text, context) in zip(items, build_inputs(items, context_turns)):
            row['context'] = context
    groups = sorted({session_group(m) for m in meetings})
    if len(groups) < 10:
        raise ValueError('At least ten independent meeting/session groups are required')
    random.Random(seed).shuffle(groups)
    a, b = int(.7 * len(groups)), int(.85 * len(groups))
    assigned = dict(zip(['train', 'validation', 'test'], [groups[:a], groups[a:b], groups[b:]]))
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError('Output directory is not empty; use a new dataset version')
    output.mkdir(parents=True, exist_ok=True)
    manifest = {'schema_version': 1, 'source_url': URL, 'archive_sha256': sha256(archive),
                'license': 'CC BY 4.0; cite AMI corpus and annotation guidelines',
                'task': 'AMI dialogue-act classification (not confirmed action-item extraction)',
                'split_policy': 'custom 70/15/15 shuffled session-group split; not published standard split',
                'seed': seed, 'context_turns': context_turns, 'skipped': skipped,
                'labels': {v['name']: v['description'] for v in ontology.values()}, 'splits': {}}
    for split, selected_groups in assigned.items():
        names = sorted(m for m in meetings if session_group(m) in selected_groups)
        selected = [r for m in names for r in meetings[m]]
        path = output / f'{split}.jsonl'
        path.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in selected), encoding='utf-8')
        manifest['splits'][split] = {'meetings': names, 'groups': sorted(selected_groups),
                                     'rows': len(selected), 'counts': dict(Counter(r['label'] for r in selected)),
                                     'sha256': sha256(path)}
    validate_splits(manifest)
    if set(manifest['labels']) != set(manifest['splits']['train']['counts']):
        raise ValueError('Training split lacks a class; inspect annotations before training')
    write_json(output / 'manifest.json', manifest)
    print(json.dumps({s: {'meetings': len(v['meetings']), 'rows': v['rows'], 'counts': v['counts']}
                      for s, v in manifest['splits'].items()}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, default=Path('data/raw/ami_public_manual_1.6.2.zip'))
    parser.add_argument('--output', type=Path, default=Path('data/ami-da-v1'))
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--context-turns', type=int, choices=range(0, 5), default=2)
    args = parser.parse_args()
    if not args.archive.exists():
        args.archive.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.archive.with_suffix('.download')
        urllib.request.urlretrieve(URL, temporary)
        temporary.replace(args.archive)
    prepare(args.archive, args.output, args.seed, args.context_turns)


if __name__ == '__main__':
    main()
