"""Create compact, text-free Git/report evidence from a completed experiment."""
import argparse
import json
from pathlib import Path

from nlp.data import write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Evidence directory already exists; preserve previous results')
    config = json.loads((args.run / 'run_config.json').read_text(encoding='utf-8'))
    metadata = json.loads((args.run / 'best' / 'meetmind_model.json').read_text(encoding='utf-8'))
    manifest = json.loads((Path(config['data']) / 'manifest.json').read_text(encoding='utf-8'))
    write_json(args.output / 'dataset_manifest.json', manifest)
    write_json(args.output / 'run_config.json', config)
    write_json(args.output / 'model_metadata.json', metadata)
    history = json.loads((args.run / 'history.json').read_text(encoding='utf-8'))
    write_json(args.output / 'training_summary.json', [{
        'epoch': row['epoch'], 'train_loss': row['train_loss'],
        'elapsed_seconds': row['elapsed_seconds'],
        'validation_macro_f1': row['validation']['macro_f1'],
        'validation_accuracy': row['validation']['accuracy']} for row in history])
    for split in ['validation', 'test']:
        path = args.run / f'{split}.json'
        if not path.exists():
            continue
        report = json.loads(path.read_text(encoding='utf-8'))
        predictions = report.pop('predictions')
        report['error_example_ids'] = [p for p in predictions if p['gold'] != p['predicted']][:30]
        write_json(args.output / f'{split}_metrics.json', report)
    print(f'Evidence saved to {args.output}')


if __name__ == '__main__':
    main()
