"""Score the keyword rule baseline (nlp/rules.py) on validation and held-out test.

The rules are fixed in code and not fitted to any split, so evaluating them on
test does not influence model selection.
"""
import argparse
from pathlib import Path

from nlp import rules
from nlp.data import load_split, sha256, write_json
from nlp.metrics import classification_metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=Path('data/ami-da-v1'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Preserve the existing evaluation: choose a new output file')
    scores = {}
    for split in ('validation', 'test'):
        rows, manifest = load_split(args.data, split)
        labels = sorted(manifest['labels'])
        scores[split] = classification_metrics([r['label'] for r in rows], [rules.predict(r['text']) for r in rows], labels)
    write_json(args.output, {'baseline': 'keyword rules (nlp/rules.py)', 'fitted': False,
                             'rules_sha256': sha256(Path(rules.__file__)),
                             'dataset_manifest_sha256': sha256(args.data / 'manifest.json'), 'scores': scores})
    for split, score in scores.items():
        print(split, {k: round(score[k], 4) for k in ('accuracy', 'macro_f1', 'weighted_f1')}, score['examples'])


if __name__ == '__main__':
    main()
