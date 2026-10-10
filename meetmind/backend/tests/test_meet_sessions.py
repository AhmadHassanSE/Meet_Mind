import time

import pytest
from fastapi.testclient import TestClient
from app import main
from app.connectors import meet
from app.ingestion import IngestionError

START = 1_700_000_000_000


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB_PATH', tmp_path / 'test.db')
    monkeypatch.setattr(meet, 'ffmpeg_path', lambda: 'ffmpeg')
    meet.sessions.clear()
    with TestClient(main.app) as client:
        yield client
    meet.sessions.clear()


def start(client, **extra):
    body = {'title': 'Weekly sync', 'meeting_code': 'abc-defg-hij', 'self_name': 'Ali', 'started_at_ms': START, **extra}
    response = client.post('/api/meet/sessions', json=body)
    assert response.status_code == 201
    return response.json()['id']


def await_job(client, job_id):
    for _ in range(100):
        job = client.get(f'/api/ingestion/jobs/{job_id}').json()
        if job['status'] in {'completed', 'failed'}:
            return job
        time.sleep(.02)
    pytest.fail('Job did not finish')


def fake_transcribe(monkeypatch, seen=None):
    def transcribe(path, update):
        if seen is not None:
            seen.append(path.read_bytes())
        update('transcribing', 50, 'Working')
        return [{'id': 1, 'speaker': None, 'text': 'I will send the report by Friday.', 'source': 'I will send the report by Friday.', 'start': 1.0, 'end': 4.0},
                {'id': 2, 'speaker': None, 'text': 'Please review it.', 'source': 'Please review it.', 'start': 5.0, 'end': 7.0},
                {'id': 3, 'speaker': None, 'text': 'Okay.', 'source': 'Okay.', 'start': 30.0, 'end': 31.0}], {'duration': 31, 'speaker_labels': 'unavailable'}
    monkeypatch.setattr(meet, 'transcribe_media', transcribe)


def test_full_session_produces_speaker_labelled_meeting_and_cleans_up(client, monkeypatch):
    seen = []
    fake_transcribe(monkeypatch, seen)
    session_id = start(client)
    directory = meet.sessions[session_id]['dir']
    assert client.post(f'/api/meet/sessions/{session_id}/audio?seq=0', content=b'aaa').json() == {'received': 1, 'duplicate': False}
    assert client.post(f'/api/meet/sessions/{session_id}/audio?seq=1', content=b'bbb').status_code == 200
    events = [{'t': START + 500, 'speaker': 'You', 'active': True}, {'t': START + 4500, 'speaker': 'You', 'active': False},
              {'t': START + 4800, 'speaker': 'Sara', 'active': True}, {'t': START + 7500, 'speaker': 'Sara', 'active': False}]
    assert client.post(f'/api/meet/sessions/{session_id}/hints', json={'events': events}).json() == {'accepted': 4}
    response = client.post(f'/api/meet/sessions/{session_id}/finish')
    assert response.status_code == 202
    job = await_job(client, response.json()['id'])
    assert job['status'] == 'completed'
    assert seen == [b'aaabbb']
    meeting = client.get('/api/meetings/' + job['meeting_id']).json()
    assert meeting['source_type'] == 'google_meet' and meeting['meeting_code'] == 'abc-defg-hij'
    assert meeting['speaker_labels'] == 'dom_hints'
    speakers = [s['speaker'] for s in meeting['segments']]
    assert speakers[0] == 'Ali' and 'Sara' in speakers and speakers[-1] is None
    assert meeting['unattributed_segments'] == 1
    assert session_id not in meet.sessions and not directory.exists()


def test_session_without_hints_is_unlabelled_but_succeeds(client, monkeypatch):
    fake_transcribe(monkeypatch)
    session_id = start(client)
    client.post(f'/api/meet/sessions/{session_id}/audio?seq=0', content=b'a')
    job = await_job(client, client.post(f'/api/meet/sessions/{session_id}/finish').json()['id'])
    meeting = client.get('/api/meetings/' + job['meeting_id']).json()
    assert meeting['speaker_labels'] == 'unavailable'
    assert all(s['speaker'] is None for s in meeting['segments'])


def test_chunks_must_arrive_in_order_and_retries_are_idempotent(client):
    session_id = start(client)
    url = f'/api/meet/sessions/{session_id}/audio'
    assert client.post(url + '?seq=1', content=b'x').status_code == 409
    assert client.post(url + '?seq=0', content=b'one').status_code == 200
    assert client.post(url + '?seq=0', content=b'one').json()['duplicate'] is True
    assert client.post(url + '?seq=1', content=b'two').status_code == 200
    assert (meet.sessions[session_id]['dir'] / 'audio.webm').read_bytes() == b'onetwo'
    assert client.post(url + '?seq=2', content=b'').status_code == 422


def test_limits(client, monkeypatch):
    session_id = start(client)
    monkeypatch.setattr(meet, 'MAX_CHUNK_BYTES', 4)
    assert client.post(f'/api/meet/sessions/{session_id}/audio?seq=0', content=b'12345').status_code == 413
    monkeypatch.setattr(meet, 'MAX_MEDIA_BYTES', 3)
    assert client.post(f'/api/meet/sessions/{session_id}/audio?seq=0', content=b'1234').status_code == 413
    monkeypatch.setattr(meet, 'MAX_HINT_BYTES', 10)
    assert client.post(f'/api/meet/sessions/{session_id}/hints', json={'events': [{'t': 1, 'speaker': 'Sara'}]}).status_code == 413
    assert client.post(f'/api/meet/sessions/{session_id}/hints', json={'events': [{}] * 2001}).status_code == 422


def test_validation_and_unknown_sessions(client, monkeypatch):
    assert client.post('/api/meet/sessions', json={'title': '  ', 'started_at_ms': START}).status_code == 422
    assert client.post('/api/meet/sessions', json={'title': 'x', 'started_at_ms': 0}).status_code == 422
    assert client.post('/api/meet/sessions/nope/audio?seq=0', content=b'a').status_code == 404
    assert client.post('/api/meet/sessions/nope/finish').status_code == 404
    session_id = start(client)
    assert client.post(f'/api/meet/sessions/{session_id}/finish').status_code == 422  # no audio yet
    monkeypatch.setattr(meet, 'ffmpeg_path', lambda: None)
    assert client.post('/api/meet/sessions', json={'title': 'x', 'started_at_ms': START}).status_code == 503


def test_session_cap_and_cancel_cleanup(client):
    ids = [start(client) for _ in range(meet.MAX_SESSIONS)]
    assert client.post('/api/meet/sessions', json={'title': 'x', 'started_at_ms': START}).status_code == 429
    directory = meet.sessions[ids[0]]['dir']
    assert client.delete(f'/api/meet/sessions/{ids[0]}').status_code == 204
    assert not directory.exists()
    assert client.delete(f'/api/meet/sessions/{ids[0]}').status_code == 404
    start(client)


def test_failed_transcription_reports_error_and_cleans_up(client, monkeypatch):
    def broken(path, update):
        raise IngestionError('No speech detected.')
    monkeypatch.setattr(meet, 'transcribe_media', broken)
    session_id = start(client)
    directory = meet.sessions[session_id]['dir']
    client.post(f'/api/meet/sessions/{session_id}/audio?seq=0', content=b'a')
    job = await_job(client, client.post(f'/api/meet/sessions/{session_id}/finish').json()['id'])
    assert job['status'] == 'failed' and job['message'] == 'No speech detected.'
    assert not directory.exists()


def test_finishing_session_rejects_more_data_and_double_finish(client, monkeypatch):
    gate = []
    def slow(path, update):
        while not gate:
            time.sleep(.01)
        return [{'id': 1, 'speaker': None, 'text': 'Hello.', 'source': 'Hello.', 'start': 0, 'end': 1}], {'duration': 1}
    monkeypatch.setattr(meet, 'transcribe_media', slow)
    session_id = start(client)
    client.post(f'/api/meet/sessions/{session_id}/audio?seq=0', content=b'a')
    job_id = client.post(f'/api/meet/sessions/{session_id}/finish').json()['id']
    assert client.post(f'/api/meet/sessions/{session_id}/finish').status_code == 409
    assert client.post(f'/api/meet/sessions/{session_id}/audio?seq=1', content=b'b').status_code == 409
    assert client.post(f'/api/meet/sessions/{session_id}/hints', json={'events': []}).status_code == 409
    gate.append(1)
    assert await_job(client, job_id)['status'] == 'completed'


def test_full_queue_returns_429_and_session_can_retry(client, monkeypatch):
    fake_transcribe(monkeypatch)
    session_id = start(client)
    client.post(f'/api/meet/sessions/{session_id}/audio?seq=0', content=b'a')
    with monkeypatch.context() as full:
        full.setattr(main, 'slots', type('Full', (), {'acquire': lambda self, blocking=True: False})())
        assert client.post(f'/api/meet/sessions/{session_id}/finish').status_code == 429
    assert not meet.sessions[session_id]['finishing']
    assert await_job(client, client.post(f'/api/meet/sessions/{session_id}/finish').json()['id'])['status'] == 'completed'
