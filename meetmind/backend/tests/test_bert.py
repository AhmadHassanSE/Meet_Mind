import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from app import bert, main
from nlp.data import build_inputs, load_split, session_group, validate_splits
from scripts.prepare_ami import read_annotations


def test_session_split_rejects_related_meetings():
    assert session_group('ES2002a') == session_group('ES2002d')
    manifest = {'splits': {s: {'meetings': [m]} for s, m in
                          [('train', 'ES2002a'), ('validation', 'ES2002b'), ('test', 'IS1000a')]}}
    with pytest.raises(ValueError, match='leaking'):
        validate_splits(manifest)


def test_context_has_only_past_turns_and_no_speaker_names():
    rows = [{'text': 'Earlier', 'speaker': 'Sara'}, {'text': 'Current', 'speaker': 'Sara'},
            {'text': 'Future', 'speaker': 'Ahmed'}]
    inputs = build_inputs(rows, 1)
    assert inputs == [('Earlier', ''), ('Current', 'same speaker: Earlier'),
                      ('Future', 'other speaker: Current')]
    assert build_inputs(rows, 0)[1] == ('Current', '')


def test_nxt_span_handles_nonword_anchor_and_unlabeled_act(tmp_path):
    path = tmp_path / 'annotations.zip'
    namespace = 'xmlns:nite="http://nite.sourceforge.net/"'
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('ontologies/da-types.xml', f'<root {namespace}><da-type nite:id="ami_da_7" name="off" gloss="Offer"/></root>')
        z.writestr('words/ES2002a.A.words.xml', f'<root {namespace}><w nite:id="w0" starttime="1" endtime="2">I</w><vocalsound nite:id="w1"/><w nite:id="w2" starttime="2" endtime="3">will</w></root>')
        z.writestr('dialogueActs/ES2002a.A.dialog-act.xml', f'<root {namespace}><dact nite:id="act1"><nite:pointer role="da-aspect" href="da-types.xml#id(ami_da_7)"/><nite:child href="ES2002a.A.words.xml#id(w0)..id(w2)"/></dact><dact nite:id="unlabeled"/></root>')
    rows, labels, skipped = read_annotations(path)
    assert rows[0]['text'] == 'I will'
    assert rows[0]['label'] == 'off'
    assert (rows[0]['start'], rows[0]['end']) == (1, 3)
    assert skipped == {'unlabeled_acts': 1}


def test_modified_data_rejected(tmp_path):
    manifest = {'splits': {s: {'meetings': [m], 'sha256': 'wrong'} for s, m in
                          [('train', 'ES2002a'), ('validation', 'IS1000a'), ('test', 'TS3000a')]}}
    (tmp_path / 'manifest.json').write_text(json.dumps(manifest))
    (tmp_path / 'train.jsonl').write_text('{}\n')
    with pytest.raises(ValueError, match='changed'):
        load_split(tmp_path, 'train')


def test_missing_checkpoint_preserves_meeting(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB_PATH', tmp_path / 'test.db')
    monkeypatch.setenv('BERT_MODEL_PATH', str(tmp_path / 'missing'))
    client = TestClient(main.app)
    meeting = client.post('/api/meetings', json={'title': 'Review', 'transcript': 'Sara: I will send it.'}).json()
    response = client.post(f'/api/meetings/{meeting["id"]}/classify')
    assert response.status_code == 503
    assert client.get(f'/api/meetings/{meeting["id"]}').json() == meeting
    assert client.post('/api/meetings/missing/classify').status_code == 404


def test_classifications_persist_without_creating_commitments(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB_PATH', tmp_path / 'test.db')
    result = {'task': 'ami_dialogue_act', 'predictions': [{'source_id': 1, 'label': 'off'}], 'model': {'checkpoint_stage': 'test'}}
    monkeypatch.setattr(bert, 'classify', lambda segments: result)
    client = TestClient(main.app)
    meeting = client.post('/api/meetings', json={'title': 'Review', 'transcript': 'Sara: I will send it.'}).json()
    response = client.post(f'/api/meetings/{meeting["id"]}/classify')
    assert response.status_code == 200
    assert response.json()['dialogue_analysis'] == result
    assert response.json()['actions'] == []
    assert client.get(f'/api/meetings/{meeting["id"]}').json() == response.json()


def test_incompatible_metadata_rejected_before_loading(tmp_path):
    pytest.importorskip('transformers')
    (tmp_path / 'meetmind_model.json').write_text(json.dumps({'task': 'wrong', 'schema_version': 1}))
    with pytest.raises(bert.BertUnavailable, match='invalid'):
        bert.DialogueClassifier(tmp_path)


def test_action_labels_always_require_review_even_at_high_score():
    torch = pytest.importorskip('torch')
    from types import SimpleNamespace
    classifier = bert.DialogueClassifier.__new__(bert.DialogueClassifier)
    classifier.torch = torch
    classifier.labels = ['inf', 'off', 'sug']
    classifier.metadata = {'context_turns': 2, 'max_length': 96, 'review_threshold': .7,
                           'review_margin': .15, 'label_descriptions': {'inf': 'Inform', 'off': 'Offer', 'sug': 'Suggest'}}
    classifier.tokenizer = lambda *args, **kwargs: {}
    classifier.model = lambda **kwargs: SimpleNamespace(logits=torch.tensor([[0., 9., 0.], [1., 1., 1.]]))
    results = classifier.predict([{'id': 2, 'text': 'I will do it', 'speaker': 'Sara'},
                                  {'id': 8, 'text': 'Maybe', 'speaker': None}])
    assert results[0]['source_id'] == 2
    assert results[0]['score'] > .99
    assert results[0]['review_reasons'] == ['possible_action_is_not_a_confirmed_commitment']
    assert results[0]['needs_review']
    assert results[1]['source_id'] == 8
    assert 'low_model_score' in results[1]['review_reasons']
    assert 'close_alternative_label' in results[1]['review_reasons']


def test_selection_uses_validation_and_preserves_existing_model(tmp_path):
    from scripts.select_bert import select
    for name, score in [('first', .3), ('second', .5)]:
        checkpoint = tmp_path / name / 'best'
        checkpoint.mkdir(parents=True)
        (checkpoint / 'model.safetensors').write_bytes(b'test-fixture')
        (checkpoint / 'meetmind_model.json').write_text(json.dumps({
            'test_used_for_selection': False, 'validation_macro_f1': score,
            'dataset_manifest_sha256': 'same', 'checkpoint_stage': 'test'}))
    output = tmp_path / 'served'
    select([tmp_path / 'first', tmp_path / 'second'], output)
    assert json.loads((output / 'selection.json').read_text())['selected_run'].endswith('second')
    with pytest.raises(ValueError, match='already exists'):
        select([tmp_path / 'first'], output)
