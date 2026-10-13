"""Export public train/validation and the existing baseline weights; no final test."""
import argparse
import json
from pathlib import Path
import zipfile
from nlp.data import load_split, sha256

MODEL_FILES = {'config.json','meetmind_model.json','model.safetensors','special_tokens_map.json',
               'tokenizer.json','tokenizer_config.json','vocab.txt'}


def export(data, checkpoint, run_config, output):
    data,checkpoint,output = Path(data),Path(checkpoint),Path(output)
    if output.exists():raise ValueError('Preserve the existing input bundle; choose a new output')
    for split in ('train','validation'):load_split(data,split)
    metadata = json.loads((checkpoint/'meetmind_model.json').read_text())
    if metadata['dataset_manifest_sha256'] != sha256(data/'manifest.json'):
        raise ValueError('Baseline and dataset do not match')
    if metadata['model_name'] != 'google-bert/bert-base-uncased' or metadata['test_used_for_selection']:
        raise ValueError('Expected the existing validation-selected BERT-base checkpoint')
    entries = {f'data/ami-da-v1/{name}':data/name for name in ('manifest.json','train.jsonl','validation.jsonl')}
    entries.update({f'reference/bert-base-v1/best/{name}':checkpoint/name for name in MODEL_FILES})
    entries['reference/bert-base-v1/run_config.json'] = Path(run_config)
    for path in entries.values():
        if not path.is_file():raise ValueError(f'Missing required public artifact: {path.name}')
    hashes = {name:sha256(path) for name,path in entries.items()}
    manifest = {'schema_version':1,'study':'bert-base-f1-improvement-v2','test_data_included':False,
                'private_meetings_included':False,'files':hashes,'target_macro_f1':.73,
                'baseline_macro_f1':metadata['validation_macro_f1'],
                'dataset_manifest_sha256':metadata['dataset_manifest_sha256']}
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,path in sorted(entries.items()):archive.write(path,name)
        archive.writestr('input-manifest.json',json.dumps(manifest,indent=2))
    output.with_suffix('.zip.sha256').write_text(sha256(output)+'  '+output.name+'\n')
    print(f'Prepared {output}: {output.stat().st_size/1024**2:.1f} MiB; final test excluded')


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',type=Path,default=Path('data/ami-da-v1'))
    parser.add_argument('--checkpoint',type=Path,default=Path('models/dialogue-bert-base-v1'))
    parser.add_argument('--run-config',type=Path,default=Path('reports/bert-base-comparison-v1/bert-base-gpu-lr3e5/run_config.json'))
    parser.add_argument('--output',type=Path,default=Path('runs/bert-f1-training-inputs-v2.zip'))
    args=parser.parse_args();export(args.data,args.checkpoint,args.run_config,args.output)
