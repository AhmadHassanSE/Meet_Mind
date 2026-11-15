"""Draw a stratified sample of AMI test utterances for two independent team annotators.

Writes one blank sheet per annotator (``label`` and ``unsure`` columns to fill in) and a
separate key with the AMI gold labels, which annotators must not open until both are done.
Sampling is stratified by gold label (at least ``--min-per-label`` per label when available)
so rare acts such as offers are represented.
"""
import argparse
import csv
import random
from collections import defaultdict
from pathlib import Path

from nlp.data import load_split

FIELDS = ['item', 'id', 'meeting_id', 'speaker', 'context', 'text', 'label', 'unsure', 'comment']


def sample(rows, size, min_per_label, seed):
    by_label = defaultdict(list)
    for row in rows:
        by_label[row['label']].append(row)
    generator = random.Random(seed)
    chosen = []
    for label in sorted(by_label):
        chosen += generator.sample(by_label[label], min(min_per_label, len(by_label[label])))
    picked = {row['id'] for row in chosen}
    rest = [row for row in rows if row['id'] not in picked]
    chosen += generator.sample(rest, max(0, size - len(chosen)))
    generator.shuffle(chosen)
    return chosen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=Path('data/ami-da-v1'))
    parser.add_argument('--output', type=Path, default=Path('evaluation/annotation'))
    parser.add_argument('--size', type=int, default=150)
    parser.add_argument('--min-per-label', type=int, default=5)
    parser.add_argument('--annotators', nargs=2, default=['annotator_a', 'annotator_b'])
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        raise ValueError('Output folder is not empty; keep earlier sheets and choose a new folder')
    rows, _ = load_split(args.data, 'test')
    items = sample(rows, args.size, args.min_per_label, args.seed)
    args.output.mkdir(parents=True, exist_ok=True)
    for name in args.annotators:
        with (args.output / f'{name}.csv').open('w', newline='', encoding='utf-8') as handle:
            writer = csv.DictWriter(handle, FIELDS)
            writer.writeheader()
            for number, row in enumerate(items, 1):
                writer.writerow({'item': number, 'id': row['id'], 'meeting_id': row['meeting_id'], 'speaker': row['speaker'],
                                 'context': row['context'][-300:], 'text': row['text'], 'label': '', 'unsure': '', 'comment': ''})
    with (args.output / 'ami_key_DO_NOT_OPEN_UNTIL_DONE.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, ['id', 'ami_label'])
        writer.writeheader()
        writer.writerows({'id': row['id'], 'ami_label': row['label']} for row in items)
    print(f'Wrote {len(items)} items for {", ".join(args.annotators)} to {args.output}')


if __name__ == '__main__':
    main()
