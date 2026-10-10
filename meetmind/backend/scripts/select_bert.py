"""Select a trained candidate by validation macro F1 and copy it for local serving."""
import argparse
import json
from pathlib import Path
import shutil

from nlp.data import sha256, write_json


def select(runs, output):
    candidates = []
    for run in runs:
        run = Path(run)
        checkpoint = run / 'best'
        metadata = json.loads((checkpoint / 'meetmind_model.json').read_text(encoding='utf-8'))
        if metadata.get('test_used_for_selection') is not False:
            raise ValueError('Candidate must declare validation-only selection')
        if not (checkpoint / 'model.safetensors').is_file():
            raise ValueError('Candidate has no saved fine-tuned weights')
        candidates.append((metadata['validation_macro_f1'], run, metadata))
    if len({c[2]['dataset_manifest_sha256'] for c in candidates}) != 1:
        raise ValueError('Cannot compare candidates evaluated on different dataset versions')
    best = max(candidates, key=lambda candidate: candidate[0])
    output = Path(output)
    if output.exists():
        raise ValueError('Serving directory already exists. Select a new version; do not overwrite a loaded model.')
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(best[1] / 'best', output)
    summary = {'criterion': 'highest validation macro F1; test never used',
               'selected_run': str(best[1]), 'model_weights_sha256': sha256(output / 'model.safetensors'),
               'candidates': [{'run': str(run), 'validation_macro_f1': score,
                               'stage': metadata['checkpoint_stage']} for score, run, metadata in candidates]}
    write_json(output / 'selection.json', summary)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', nargs='+', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path('models/dialogue-bert'))
    args = parser.parse_args()
    select(args.runs, args.output)
