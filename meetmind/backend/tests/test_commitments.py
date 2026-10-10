import json
import httpx
import pytest
from fastapi.testclient import TestClient
from app import commitments as c, main
from app.preprocessing import prepare


@pytest.fixture(scope='module')
def nlp():
    pytest.importorskip('spacy')
    try:
        return c.load_nlp()[0]
    except c.NLPUnavailable:
        pytest.skip('Install nlp extra to exercise real spaCy parsing')


def units_for(text):
    meeting = prepare(text)
    predictions = [{'source_id': s['id'], 'label': 'inf', 'score': .8} for s in meeting['segments']]
    units = c.source_units(meeting, predictions)
    c.annotate(units)
    return meeting, units


def proposal(unit, **changes):
    return c.Proposal(**({'source_id': unit['source_id'], 'quote': unit['text'], 'task': 'Send the report',
                         'owner': None, 'deadline': None, 'kind': 'commitment'} | changes))


def test_first_person_and_deadline_are_grounded_with_real_spacy(nlp):
    meeting, units = units_for('Sara: I will send the report by Friday.')
    result = c.ground([proposal(units[0], owner='Invented', deadline='2099-01-01')], units, nlp)
    action = result['actions'][0]
    assert action['owner'] == 'Sara'
    assert action['owner_method'] == 'speaker'
    assert action['deadline'] == 'by Friday'
    assert action['deadline_normalized'] is None
    assert action['needs_review'] and 'unsupported_deadline_removed' in action['review_reasons']
    ev = action['evidence'][0]
    parent = meeting['source_segments'][0]
    assert parent['text'][ev['source_start']:ev['source_end']] == ev['quote']


@pytest.mark.parametrize('text,kind', [
    ('Could we send the report?', 'request'),
    ('We should send the report.', 'suggestion'),
    ('We discussed the report yesterday.', 'suggestion'),
    ('I will not send the report.', 'cancellation'),
    ("I won't send the report.", 'cancellation'),
])
def test_non_commitments_are_separate_even_if_model_calls_them_commitments(nlp, text, kind):
    _, units = units_for('Sara: ' + text)
    result = c.ground([proposal(units[0])], units, nlp)
    assert result['actions'] == []
    assert result['action_candidates'][0]['kind'] == kind


def test_explicit_and_ambiguous_owners(nlp):
    for text, suggested, expected in [
        ('Sara will send the report.', 'Sara', 'Sara'),
        ('We will send the report.', 'Sara', None),
        ('I will send the report to Ali.', 'Ali', 'Chair'),
        ('The report will be sent.', 'Ali', None),
        ('I think Sara will send the report.', 'Sara', 'Sara'),
    ]:
        _, units = units_for('Chair: ' + text)
        result = c.ground([proposal(units[0], owner=suggested)], units, nlp)
        assert result['actions'][0]['owner'] == expected


def test_explicit_addressee_resolves_request_owner(nlp):
    _, units = units_for('Chair: Ali, can you book the room?')
    result = c.ground([proposal(units[0], task='Book the room', kind='request')], units, nlp)
    assert result['action_candidates'][0]['owner'] == 'Ali'


@pytest.mark.parametrize('invalid', ['quote', 'source', 'schema', 'limit'])
def test_ollama_response_validation(monkeypatch, invalid):
    import asyncio
    unit = {'source_id': 1, 'text': 'I will send the report.', 'speaker': 'Sara',
            'bert_signals': [], 'people': [], 'dates': []}
    item = proposal(unit).model_dump()
    payload = {'message': {'content': json.dumps({'actions': [item]})}}
    if invalid == 'quote':
        item['quote'] = 'I will buy a yacht.'
    elif invalid == 'source':
        item['source_id'] = 99
    elif invalid == 'schema':
        item['kind'] = 'approved'
    else:
        payload['done_reason'] = 'length'
    payload['message']['content'] = json.dumps({'actions': [item]})
    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, **kwargs):
            assert kwargs['json']['format']['properties']['actions']
            return httpx.Response(200, json=payload, request=httpx.Request('POST', url))
    monkeypatch.setattr(c.httpx, 'AsyncClient', Client)
    with pytest.raises(ValueError):
        asyncio.run(c.propose([unit], 'http://127.0.0.1:11434', 'fixture'))


def test_later_cancellation_crosses_batch_and_requires_review(nlp):
    _, units = units_for('Sara: I will send the report.\nAli: Cancel the report.\nAli: I will book the room.')
    result = c.ground([proposal(units[0]), proposal(units[2], task='Book the room')], units, nlp)
    assert result['actions'][0]['status'] == 'possible_cancellation'
    assert len(result['actions'][0]['evidence']) == 2
    assert result['actions'][1]['status'] == 'proposed'
    _, units = units_for('Sara: I will send the report.\nAli: Do not cancel the report.')
    result = c.ground([proposal(units[0])], units, nlp)
    assert result['actions'][0]['status'] == 'proposed'


def test_cancellation_within_same_source_turn(nlp):
    _, units = units_for('Sara: I will send the report. Actually, cancel the report.')
    item = proposal(units[0], quote='I will send the report.')
    action = c.ground([item], units, nlp)['actions'][0]
    assert action['status'] == 'possible_cancellation'
    assert action['evidence'][1]['quote'] == 'Actually, cancel the report.'


def test_unsupported_task_invalid_quote_and_duplicate_proposals(nlp):
    _, units = units_for('Sara: I will send the report.')
    item = proposal(units[0])
    assert len(c.ground([item, item], units, nlp)['actions']) == 1
    result = c.ground([proposal(units[0], task='Buy a yacht')], units, nlp)
    assert not result['actions'] and result['extraction']['discarded']
    with pytest.raises(c.InvalidExtraction):
        c.ground([proposal(units[0], quote='Invented statement')], units, nlp)


def test_split_parent_is_rejoined_and_evidence_spans_children(nlp):
    text = 'Sara: I will send the report ' + 'after reviewing the complete design carefully ' * 15 + 'by Friday.'
    meeting, units = units_for(text)
    assert len(meeting['segments']) > 1 and len(units) == 1
    action = c.ground([proposal(units[0])], units, nlp)['actions'][0]
    assert len(action['source_ids']) == len(meeting['segments'])
    assert action['deadline'] == 'by Friday'


def test_multiple_dates_are_not_silently_resolved(nlp):
    _, units = units_for('Sara: I will send the report Monday or Friday.')
    action = c.ground([proposal(units[0], deadline='Friday')], units, nlp)['actions'][0]
    assert action['deadline'] is None
    assert 'multiple_date_expressions' in action['review_reasons']


def test_plain_object_is_not_accepted_as_deadline(nlp):
    _, units = units_for('Sara: I will send the report.')
    action = c.ground([proposal(units[0], deadline='report')], units, nlp)['actions'][0]
    assert action['deadline'] is None
    assert 'unsupported_deadline_removed' in action['review_reasons']


def test_api_success_and_failure_preserve_stored_meeting(tmp_path, monkeypatch, nlp):
    monkeypatch.setattr(main, 'DB_PATH', tmp_path / 'test.db')
    monkeypatch.setattr(main.bert, 'classify', lambda segments: {
        'predictions': [{'source_id': s['id'], 'label': 'inf', 'score': .8} for s in segments],
        'model': {'model_name': 'test', 'checkpoint_stage': 'fixture'}})
    async def valid(units, *args):
        return [proposal(units[0])]
    monkeypatch.setattr(c, 'propose', valid)
    client = TestClient(main.app)
    meeting = client.post('/api/meetings', json={'title': 'Fixture', 'transcript': 'Sara: I will send the report by Friday.'}).json()
    url = f'/api/meetings/{meeting["id"]}'
    response = client.post(url + '/extract')
    assert response.status_code == 200, response.text
    extracted = response.json()
    assert extracted['actions'][0]['owner'] == 'Sara'
    assert client.get(url).json() == extracted
    async def invalid(*args):
        raise c.InvalidExtraction('Invalid model output')
    monkeypatch.setattr(c, 'propose', invalid)
    assert client.post(url + '/extract').status_code == 502
    assert client.get(url).json() == extracted
    async def offline(*args):
        raise httpx.ConnectError('Offline')
    monkeypatch.setattr(c, 'propose', offline)
    assert client.post(url + '/extract').status_code == 503
    assert client.get(url).json() == extracted


def test_missing_spacy_or_bert_is_explicit_without_partial_save(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB_PATH', tmp_path / 'test.db')
    def unavailable(*args):
        raise main.bert.BertUnavailable('Missing BERT')
    monkeypatch.setattr(main.bert, 'classify', unavailable)
    client = TestClient(main.app)
    meeting = client.post('/api/meetings', json={'title': 'Fixture', 'transcript': 'Sara: I will send the report.'}).json()
    url = f'/api/meetings/{meeting["id"]}'
    assert client.post(url + '/extract').status_code == 503
    assert client.get(url).json() == meeting
