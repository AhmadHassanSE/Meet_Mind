import time
from pathlib import Path
from types import SimpleNamespace
import wave

import pytest
from fastapi.testclient import TestClient
from app import main, media
from app.ingestion import IngestionError


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB_PATH', tmp_path / 'test.db')
    monkeypatch.setattr(main, 'ffmpeg_path', lambda: 'ffmpeg')
    with TestClient(main.app) as client:
        yield client


def await_job(client, job_id):
    for _ in range(100):
        job = client.get(f'/api/ingestion/jobs/{job_id}').json()
        if job['status'] in {'completed', 'failed'}:
            return job
        time.sleep(.02)
    pytest.fail('Job did not finish')


def test_job_lifecycle_persistence_and_cleanup(client, monkeypatch):
    paths = []
    def transcribe(path, update):
        paths.append(path)
        update('transcribing', 50, 'Working')
        return [{'id': 1, 'speaker': None, 'text': 'Send report.', 'source': 'Send report.', 'start': 0, 'end': 2}], {'duration': 2}
    monkeypatch.setattr(main, 'transcribe_media', transcribe)
    response = client.post('/api/ingestion/media', data={'title': 'Recording'}, files={'file': ('meeting.mp4', b'media')})
    assert response.status_code == 202
    job = await_job(client, response.json()['id'])
    assert job['status'] == 'completed'
    meeting = client.get('/api/meetings/' + job['meeting_id']).json()
    assert meeting['source_type'] == 'video'
    assert meeting['segments'][0]['start'] == 0
    for _ in range(50):
        if not paths[0].parent.exists():
            break
        time.sleep(.02)
    assert not paths[0].parent.exists()


def test_failed_job_does_not_create_meeting(client, monkeypatch):
    def fail(path, update):
        raise IngestionError('No speech detected')
    monkeypatch.setattr(main, 'transcribe_media', fail)
    response = client.post('/api/ingestion/media', data={'title': 'Silent'}, files={'file': ('silence.wav', b'silent')})
    assert await_job(client, response.json()['id'])['message'] == 'No speech detected'
    assert client.get('/api/meetings').json() == []


def test_upload_validation_and_job_not_found(client, monkeypatch):
    assert client.post('/api/ingestion/media', data={'title': 'Bad'}, files={'file': ('bad.exe', b'x')}).status_code == 422
    assert client.post('/api/ingestion/media', data={'title': 'Empty'}, files={'file': ('empty.wav', b'')}).status_code == 422
    monkeypatch.setattr(main, 'MAX_MEDIA_BYTES', 2)
    assert client.post('/api/ingestion/media', data={'title': 'Large'}, files={'file': ('large.wav', b'123')}).status_code == 413
    monkeypatch.setattr(main, 'ffmpeg_path', lambda: None)
    assert client.post('/api/ingestion/media', data={'title': 'Offline'}, files={'file': ('test.wav', b'x')}).status_code == 503
    assert client.get('/api/ingestion/jobs/missing').status_code == 404


def test_queue_full(client, monkeypatch):
    monkeypatch.setattr(main, 'slots', SimpleNamespace(acquire=lambda **kwargs: False))
    assert client.post('/api/ingestion/media', data={'title': 'Busy'}, files={'file': ('test.wav', b'x')}).status_code == 429


def test_restart_marks_unfinished_jobs_failed(client):
    main.update_job('interrupted', 'transcribing', 50, 'Working')
    with TestClient(main.app) as restarted:
        assert restarted.get('/api/ingestion/jobs/interrupted').json()['status'] == 'failed'


def test_no_audio_track_and_silent_transcription(tmp_path, monkeypatch):
    monkeypatch.setattr(media, 'ffmpeg_path', lambda: 'ffmpeg')
    monkeypatch.setattr(media.subprocess, 'run', lambda *args, **kwargs: SimpleNamespace(returncode=1))
    with pytest.raises(IngestionError, match='no audio track'):
        media.transcribe_media(tmp_path / 'video.mp4', lambda *args: None)
    def decode(*args, **kwargs):
        with wave.open(str(tmp_path / 'decoded.wav'), 'wb') as audio:
            audio.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
            audio.writeframes(b'\x00\x00' * 16000)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(media.subprocess, 'run', decode)
    monkeypatch.setattr(media, '_model', SimpleNamespace(transcribe=lambda *args, **kwargs: (iter([]), SimpleNamespace(language='en'))))
    with pytest.raises(IngestionError, match='No speech'):
        media.transcribe_media(tmp_path / 'silence.wav', lambda *args: None)
