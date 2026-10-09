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
