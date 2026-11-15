import io
import zipfile
import pytest
from fastapi.testclient import TestClient
from app import main
from app.ingestion import parse_transcript, IngestionError


def test_vtt_preserves_timing_voice_and_multiline():
    result = parse_transcript(b'WEBVTT\n\nNOTE ignore this\n\ncue-1\n00:01.000 --> 00:03.500 align:start\n<v Sara>I will send\nthe report.</v>\n', '.vtt')
    assert result == [{"id": 1, "speaker": "Sara", "text": "I will send the report.",
                       "source": "I will send the report.", "start": 1.0, "end": 3.5}]


def test_srt_and_plain_numeric_lines():
    result = parse_transcript(b'1\n00:00:01,000 --> 00:00:02,000\nAhmed: Book a room.\n', '.srt')
    assert result[0]['speaker'] == 'Ahmed'
    assert result[0]['end'] == 2
    assert parse_transcript(b'2026\nA deadline: discuss it', '.txt')[0]['text'] == '2026'


def test_vtt_header_metadata_and_multiple_voices():
    result = parse_transcript(b'WEBVTT meeting\nKind: captions\nLanguage: en\n\n00:01.000 --> 00:03.000\n<v Sara>Send report.</v><v Ahmed>Book room.</v>\n', '.vtt')
    assert [(s['speaker'], s['text']) for s in result] == [('Sara', 'Send report.'), ('Ahmed', 'Book room.')]
    assert [s['id'] for s in result] == [1, 2]


def test_docx_paragraphs():
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        archive.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Sara: Send </w:t></w:r><w:r><w:t>the report.</w:t></w:r></w:p></w:body></w:document>')
    assert parse_transcript(stream.getvalue(), '.docx')[0]['text'] == 'Send the report.'


@pytest.mark.parametrize('data,suffix', [(b'', '.txt'), (b'bad', '.docx'), (b'bad', '.pdf'),
    (b'WEBVTT\n\n00:03.000 --> 00:01.000\nwrong', '.vtt'), (b'not captions', '.srt'), (b'\xff', '.txt')])
def test_reject_invalid_input(data, suffix):
    with pytest.raises(IngestionError):
        parse_transcript(data, suffix)


def test_upload_api_preserves_source_and_rejects_without_saving(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB_PATH', tmp_path / 'test.db')
    client = TestClient(main.app)
    response = client.post('/api/ingestion/transcript', data={'title': 'Review'}, files={'file': ('notes.md', b'Sara: Send report.', 'text/plain')})
    assert response.status_code == 201
    assert response.json()['source_type'] == 'md'
    assert response.json()['segments'][0]['speaker'] == 'Sara'
    assert client.post('/api/ingestion/transcript', data={'title': 'Bad'}, files={'file': ('bad.docx', b'bad')}).status_code == 422
    assert len(client.get('/api/meetings').json()) == 1


def test_transcript_downloads_and_timestamp_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB_PATH', tmp_path / 'test.db')
    client = TestClient(main.app)
    original = b'WEBVTT\n\n00:01.000 --> 00:02.500\n<v Sara>Send the report.</v>\n'
    meeting = client.post('/api/ingestion/transcript', data={'title': 'Captions'}, files={'file': ('meeting.vtt', original)}).json()
    base = f'/api/meetings/{meeting["id"]}/transcript'
    assert client.get(base + '?format=json').json()['segments'] == meeting['segments']
    exported = client.get(base + '?format=vtt')
    assert exported.status_code == 200
    assert parse_transcript(exported.content, '.vtt') == [
        {key: s[key] for key in ('id', 'speaker', 'text', 'source', 'start', 'end')} for s in meeting['segments']]
    assert 'attachment' in exported.headers['content-disposition']
    assert client.get(base + '?format=exe').status_code == 422
    plain = client.post('/api/meetings', json={'title': 'Text', 'transcript': 'Hello'}).json()
    assert client.get(f'/api/meetings/{plain["id"]}/transcript?format=vtt').status_code == 422


def test_extraction_batches_preserve_all_ids_and_reject_oversized_turn():
    from fastapi import HTTPException
    segments = [{'id': i, 'text': 'a' * 6000} for i in range(1, 6)]
    batches = main.extraction_batches(segments)
    assert len(batches) == 5
    assert [s['id'] for batch in batches for s in batch] == list(range(1, 6))
    with pytest.raises(HTTPException):
        main.extraction_batches([{'id': 1, 'text': 'a' * 13000}])
