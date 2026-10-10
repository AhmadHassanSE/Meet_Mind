"""Transfer identical public train/validation bytes and pilot predictions to a GPU runtime."""
import argparse
import json
from pathlib import Path
import zipfile
from nlp.data import load_split, sha256


def export(data, reference, output):
    data, reference, output = Path(data), Path(reference), Path(output)
    if output.exists():
        raise ValueError('Choose a new export; preserve the existing input bundle')
    _, manifest = load_split(data, 'train')
    validation, _ = load_split(data, 'validation')
    report = json.loads(reference.read_text(encoding='utf-8'))
    if report['split'] != 'validation' or report['dataset_manifest_sha256'] != sha256(data / 'manifest.json'):
        raise ValueError('Pilot report must evaluate this exact validation dataset')
    expected = {(r['id'], r['label']) for r in validation}
    actual = {(r['id'], r['gold']) for r in report['predictions']}
    if expected != actual or len(report['predictions']) != len(validation):
        raise ValueError('Pilot report does not cover the complete matching validation set')
    output.parent.mkdir(parents=True, exist_ok=True)
    files = {f'data/ami-da-v1/{name}': data / name for name in ('train.jsonl', 'validation.jsonl', 'manifest.json')}
    files['reference/pilot-validation.json'] = reference
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, path in files.items():
            archive.writestr(name, path.read_bytes())
        archive.writestr('input-manifest.json', json.dumps({
            'files': {name: sha256(path) for name, path in files.items()},
            'test_data_included': False, 'source': manifest['source_url'],
            'license': manifest['license'], 'dataset_manifest_sha256': sha256(data / 'manifest.json')}, indent=2))
    output.with_suffix('.zip.sha256').write_text(f'{sha256(output)}  {output.name}\n', encoding='utf-8')
    print(f'Exported {output}; {len(validation)} matching validation examples; final test excluded')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=Path('data/ami-da-v1'))
    parser.add_argument('--reference', type=Path, default=Path('runs/bert-tiny-pilot-v1/validation.json'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    export(args.data, args.reference, args.output)
