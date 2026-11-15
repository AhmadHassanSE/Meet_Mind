"""Score two completed annotation sheets: agreement with each other and with AMI gold.

Reports raw agreement, Cohen's kappa, each annotator against the AMI labels (accuracy and
macro F1 over the labels used), and writes a disagreement log for the adjudication meeting.
"""
import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from sklearn.metrics import cohen_kappa_score, f1_score

LABELS = ['ass', 'bck', 'be.neg', 'be.pos', 'el.ass', 'el.inf', 'el.sug', 'el.und', 'fra', 'inf', 'off', 'oth', 'stl', 'sug', 'und']


def read(path, column):
    with Path(path).open(encoding='utf-8') as handle:
        return {row['id']: row for row in csv.DictReader(handle) if row.get(column, '').strip()}


def score(sheet_a, sheet_b, key):
    a, b, gold = read(sheet_a, 'label'), read(sheet_b, 'label'), read(key, 'ami_label')
    unknown = {r['label'].strip() for r in list(a.values()) + list(b.values())} - set(LABELS)
    if unknown:
        raise ValueError(f'Unknown labels in sheets: {sorted(unknown)}')
    shared = sorted(set(a) & set(b) & set(gold))
    if not shared:
        raise ValueError('The sheets have no completed items in common')
    la, lb = [a[i]['label'].strip() for i in shared], [b[i]['label'].strip() for i in shared]
    lg = [gold[i]['ami_label'] for i in shared]
    used = sorted(set(la) | set(lb) | set(lg))
    disagreements = [{'id': i, 'text': a[i]['text'], 'annotator_a': x, 'annotator_b': y, 'ami': g,
                      'unsure_a': a[i].get('unsure', ''), 'unsure_b': b[i].get('unsure', '')}
                     for i, x, y, g in zip(shared, la, lb, lg) if x != y]
    return {'items': len(shared),
            'agreement': sum(x == y for x, y in zip(la, lb)) / len(shared),
            'cohen_kappa': cohen_kappa_score(la, lb, labels=used),
            'annotator_a_vs_ami': {'accuracy': sum(x == g for x, g in zip(la, lg)) / len(shared),
                                   'macro_f1': f1_score(lg, la, labels=used, average='macro', zero_division=0)},
            'annotator_b_vs_ami': {'accuracy': sum(x == g for x, g in zip(lb, lg)) / len(shared),
                                   'macro_f1': f1_score(lg, lb, labels=used, average='macro', zero_division=0)},
            'most_common_disagreements': Counter((d['annotator_a'], d['annotator_b']) for d in disagreements).most_common(10),
            'disagreements': disagreements}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sheet_a', type=Path)
    parser.add_argument('sheet_b', type=Path)
    parser.add_argument('key', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = score(args.sheet_a, args.sheet_b, args.key)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    with args.output.with_suffix('.disagreements.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, ['id', 'text', 'annotator_a', 'annotator_b', 'ami', 'unsure_a', 'unsure_b', 'resolved_label'])
        writer.writeheader()
        writer.writerows(result['disagreements'])
    print({k: v for k, v in result.items() if k not in {'disagreements', 'most_common_disagreements'}})


if __name__ == '__main__':
    main()
