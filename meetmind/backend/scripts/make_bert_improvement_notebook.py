"""Generate the portable Colab notebook; never execute GPU training locally."""
import json
from pathlib import Path
import textwrap


def cell(kind,source):
    result={'cell_type':kind,'metadata':{},'source':textwrap.dedent(source).strip().splitlines(keepends=True)}
    if kind=='code':result.update(execution_count=None,outputs=[])
    return result


cells=[cell('markdown',r'''
# MeetMind BERT-base: macro F1 improvement study v2

Select **Runtime → Change runtime type → GPU**, then run in order.
The measured baseline is macro F1 0.5292777; **0.73 is a target, not a promise**.
Three predefined candidates keep the 15 classes and frozen session-disjoint
train/validation rows. The notebook never uploads or evaluates final-test rows.
It does not replace your application model automatically.

Upload `bert-f1-training-inputs-v2.zip`, prepared locally. It contains public AMI
train/validation and the existing BERT-base baseline weights (~400 MiB).
Google Drive retains completed epochs. Each full candidate can take several
hours; runtime speed, early stopping and Drive I/O affect duration. If your GPU
session expires, reconnect and rerun with the same experiment name/source/ZIP.
'''),cell('code',r'''
import sys, subprocess, pathlib, os, json, hashlib, zipfile, io, time
import torch
assert torch.cuda.is_available(), 'Enable a Colab GPU runtime.'
print('GPU:', torch.cuda.get_device_name(0), 'PyTorch:',torch.__version__)
# Retain Colab's CUDA PyTorch; the local uv environment uses a CPU wheel.
subprocess.check_call([sys.executable,'-m','pip','install',
                       'transformers==4.57.6','scikit-learn==1.9.1','safetensors'])
repo=pathlib.Path('/content/MeetMind-F1-v2')
BRANCH='feat/bert-base-f1-improvement'
if not repo.exists():
    subprocess.check_call(['git','clone','--branch',BRANCH,
                           'https://github.com/AhmadHassanSE/Meet_Mind.git',str(repo)])
assert subprocess.check_output(['git','-C',str(repo),'branch','--show-current'],text=True).strip()==BRANCH
backend=repo/'meetmind/backend'
os.chdir(backend)
source_revision=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
print('Training source:',source_revision)
'''),cell('code',r'''
from google.colab import drive,files
drive.mount('/content/drive')
EXPERIMENT_NAME='bert-f1-improvement-v2'
experiment=pathlib.Path('/content/drive/MyDrive/MeetMind-BERT')/EXPERIMENT_NAME
experiment.mkdir(parents=True,exist_ok=True)
source_file=experiment/'source-revision.txt'
if source_file.exists():
    assert source_file.read_text().strip()==source_revision, 'Source changed. Check out the saved revision or use a NEW experiment name.'
else:source_file.write_text(source_revision+'\n')
uploaded=files.upload()
assert len(uploaded)==1, 'Choose only bert-f1-training-inputs-v2.zip.'
from scripts.export_bert_improvement_inputs import MODEL_FILES
expected={'data/ami-da-v1/'+n for n in ('manifest.json','train.jsonl','validation.jsonl')}
expected|={'reference/bert-base-v1/best/'+n for n in MODEL_FILES}
expected|={'reference/bert-base-v1/run_config.json'}
with zipfile.ZipFile(io.BytesIO(next(iter(uploaded.values())))) as archive:
    assert len(archive.namelist())==len(expected)+1
    assert set(archive.namelist())==expected|{'input-manifest.json'}, 'Unexpected ZIP contents.'
    inputs=json.loads(archive.read('input-manifest.json'))
    assert inputs['test_data_included'] is False and inputs['private_meetings_included'] is False
    assert set(inputs['files'])==expected
    for name in sorted(expected):
        assert archive.getinfo(name).file_size < 600*1024**2
        content=archive.read(name)
        assert hashlib.sha256(content).hexdigest()==inputs['files'][name], name
        target=backend/name
        target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():assert target.read_bytes()==content, 'Existing input differs; use a fresh runtime.'
        else:target.write_bytes(content)
del uploaded
assert not pathlib.Path('data/ami-da-v1/test.jsonl').exists()
input_file=experiment/'input-manifest.json'
if input_file.exists():assert json.loads(input_file.read_text())==inputs, 'Input bundle changed.'
else:input_file.write_text(json.dumps(inputs,indent=2))
from nlp.data import load_split
for split in ('train','validation'):load_split('data/ami-da-v1',split)
print('Frozen train/validation and existing baseline verified. Final test is absent.')
'''),cell('code',r'''
def run_module(module,*args):
    logs=experiment/'logs';logs.mkdir(exist_ok=True)
    log=logs/(module.replace('.','_')+'-'+str(time.time_ns())+'.log')
    command=[sys.executable,'-u','-m',module,*map(str,args)]
    with log.open('w') as stream:
        with subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                               text=True,bufsize=1) as process:
            for line in process.stdout:
                print(line,end='',flush=True);stream.write(line);stream.flush()
            status=process.wait()
    if status:raise RuntimeError(f'{module} failed ({status}). Full traceback is above and in {log}')

candidate_names=['context4-ce','context4-balanced','context8-focal']
configs=[]
for name in candidate_names:
    cfg=json.loads(pathlib.Path(f'configs/bert-f1-v2-{name}.json').read_text())
    cfg['output']=str(experiment/f'bert-f1-v2-{name}')
    path=experiment/(name+'.json')
    if path.exists():assert json.loads(path.read_text())==cfg, 'Config changed; choose a new experiment name.'
    else:path.write_text(json.dumps(cfg,indent=2))
    configs.append(path)
print('Fixed candidates:',candidate_names)
'''),cell('code',r'''
# Short REAL BERT-base GPU check. Its score is never eligible for selection.
smoke_output=experiment/'smoke'
smoke_status=smoke_output/'status.json'
if smoke_status.exists() and json.loads(smoke_status.read_text())['status']=='completed':
    print('Completed smoke retained.')
else:
    if smoke_output.exists():smoke_output=experiment/('smoke-retry-'+str(time.time_ns()))
    smoke=json.loads(configs[0].read_text())
    smoke.update(output=str(smoke_output),stage='smoke-test',max_train_examples=256,
                 max_validation_examples=128,epochs=1,save_epoch_state=False)
    smoke_config=experiment/('smoke-config-'+str(time.time_ns())+'.json')
    smoke_config.write_text(json.dumps(smoke,indent=2))
    run_module('scripts.train_bert','--config',smoke_config)
'''),cell('code',r'''
comparison_dir=experiment/'comparison'
run_module('scripts.run_bert_improvement','--configs',*configs,
           '--reference-run','reference/bert-base-v1','--output',comparison_dir,'--target','0.73')
print((comparison_dir/'comparison.md').read_text())
goal=json.loads((comparison_dir/'goal.json').read_text())
print('TARGET REACHED:',goal['achieved'])
print('Measured validation macro F1:',goal['measured_macro_f1'])
print('Gain over re-evaluated baseline:',goal['gain_over_reference'])
'''),cell('code',r'''
# Export actual predictions, compact evidence and ONLY the winning checkpoint.
# Keep the current serving model until local import/verification approves it.
summary=json.loads((comparison_dir/'comparison.json').read_text())
winner=pathlib.Path(summary['selected_report']).parent
for config in configs:
    cfg=json.loads(config.read_text());run=pathlib.Path(cfg['output'])
    evidence=experiment/'reports'/run.name
    if not evidence.exists():run_module('scripts.summarize_bert','--run',run,'--output',evidence)
export_path=experiment/'trained-bert-f1-v2-results.zip'
if not export_path.exists():
    with zipfile.ZipFile(export_path,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for directory in [comparison_dir,experiment/'reports']:
            for path in directory.rglob('*'):
                if path.is_file():archive.write(path,path.relative_to(experiment))
        for config in configs:
            run=pathlib.Path(json.loads(config.read_text())['output'])
            for name in ('validation.json','run_config.json','history.json','status.json'):
                archive.write(run/name,'runs/'+run.name+'/'+name)
        for name in sorted(MODEL_FILES):archive.write(winner/'best'/name,'winner/best/'+name)
        archive.write(winner/'run_config.json','winner/run_config.json')
        archive.write(backend/'reference/bert-base-v1/validation.json','reference/validation.json')
        archive.write(source_file,'source-revision.txt')
        archive.write(input_file,'input-manifest.json')
    digest=hashlib.sha256()
    with export_path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):digest.update(block)
    export_path.with_suffix('.zip.sha256').write_text(digest.hexdigest()+'  '+export_path.name+'\n')
print('Result ZIP:',export_path)
print('Download from Drive and return the ZIP with comparison/goal.json. No score is assumed.')
'''),cell('markdown',r'''
## Interpreting results and resuming

`comparison/goal.json` records whether **actual 15-class validation macro F1**
reached 0.73. Accuracy, weighted F1, action-only F1 and validation-subset scores
cannot substitute for it. The baseline may remain the winner. No new score
should be reported until this notebook completes.

Resume from the latest **completed epoch**, not the interrupted batch. Keep the
same source commit, input bundle and experiment name. Different GPU/software
versions may prevent bit-exact reproducibility. If smoke alone was interrupted,
its retry is preserved separately and remains ineligible for selection.

The selected epoch and candidate use validation data. Repeated selection makes
validation optimistic; reserve the unchanged final test for final reporting.
The two extremely rare classes have only 3 and 7 validation examples. If the
target is not reached, inspect per-class errors and plan another explicit study;
do not relabel, exclude classes, change splits or report a different metric.
''')]

if __name__=='__main__':
    notebook={'cells':cells,'metadata':{'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},
              'language_info':{'name':'python'},'accelerator':'GPU'},'nbformat':4,'nbformat_minor':5}
    for i,c in enumerate(cells):c['id']=f'bert-f1-v2-{i}'
    output=Path(__file__).resolve().parents[1]/'notebooks/bert_base_f1_improvement_colab.ipynb'
    output.write_text(json.dumps(notebook,indent=2)+'\n',encoding='utf-8')
    print(output)
