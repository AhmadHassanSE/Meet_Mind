import ast
import json
from pathlib import Path
import zipfile
import pytest
from nlp.data import sha256,write_json
from scripts.export_bert_improvement_inputs import export,MODEL_FILES
from scripts.run_bert_improvement import assess_goal


def test_goal_uses_macro_f1_and_does_not_claim_an_unmet_target():
    summary={'ranked_candidates':[{'report':'actual.json','scores':{'macro_f1':.72,'weighted_f1':.9}}],
             'selected_macro_f1_gain':.19}
    result=assess_goal(summary,.73)
    assert not result['achieved'] and not result['serving_model_changed']
    summary['ranked_candidates'][0]['scores']['macro_f1']=.73
    assert assess_goal(summary,.73)['achieved']
    for target in (-1,0,1.1,float('nan')):
        with pytest.raises(ValueError):assess_goal(summary,target)


def test_export_has_byte_exact_public_inputs_and_never_reads_final_test(tmp_path):
    data=tmp_path/'data';data.mkdir()
    manifest={'context_turns':0,'labels':{'inf':'Inform'},'splits':{}}
    for split,meeting in [('train','TR0001a'),('validation','VA0001a'),('test','TE0001a')]:
        path=data/f'{split}.jsonl'
        path.write_text(json.dumps({'id':split,'meeting_id':meeting,'text':'yes','label':'inf','context':''}))
        manifest['splits'][split]={'meetings':[meeting],'sha256':sha256(path)}
    write_json(data/'manifest.json',manifest)
    (data/'test.jsonl').write_text('NEVER READ OR UPLOAD THIS FILE')
    checkpoint=tmp_path/'model';checkpoint.mkdir()
    for name in MODEL_FILES:(checkpoint/name).write_text('public placeholder')
    write_json(checkpoint/'meetmind_model.json',{'dataset_manifest_sha256':sha256(data/'manifest.json'),
        'model_name':'google-bert/bert-base-uncased','test_used_for_selection':False,'validation_macro_f1':.5293})
    cfg=tmp_path/'run.json';cfg.write_text('{}')
    output=tmp_path/'inputs.zip'
    export(data,checkpoint,cfg,output)
    with zipfile.ZipFile(output) as z:
        assert not any(name.endswith('test.jsonl') for name in z.namelist())
        assert z.read('data/ami-da-v1/train.jsonl')==(data/'train.jsonl').read_bytes()
        record=json.loads(z.read('input-manifest.json'))
        assert record['test_data_included'] is False
        assert set(z.namelist())==set(record['files'])|{'input-manifest.json'}
        for name,digest in record['files'].items():
            import hashlib
            assert hashlib.sha256(z.read(name)).hexdigest()==digest
    with pytest.raises(ValueError):export(data,checkpoint,cfg,output)


def test_colab_notebook_code_parses_and_uses_the_improvement_branch():
    backend=Path(__file__).resolve().parents[1]
    nb=json.loads((backend/'notebooks/bert_base_f1_improvement_colab.ipynb').read_text())
    code='\n'.join(''.join(c['source']) for c in nb['cells'] if c['cell_type']=='code')
    for c in nb['cells']:
        if c['cell_type']=='code':ast.parse(''.join(c['source']))
    assert "BRANCH='feat/bert-base-f1-improvement'" in code
    assert 'scripts.run_bert_improvement' in code
    assert "'--target','0.73'" in code
    assert all(not c.get('outputs') for c in nb['cells'])
