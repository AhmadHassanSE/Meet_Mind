import json
import re
from fastapi.testclient import TestClient
from app import main, preprocessing as p
from nlp.data import build_inputs


def assert_coverage(prepared):
    for parent in prepared['source_segments']:
        children = [s for s in prepared['segments'] if s['parent_source_id'] == parent['id']]
        for child in children:
            assert parent['text'][child['source_start']:child['source_end']] == child['source']
        assert re.sub(r'\s+', '', ''.join(c['source'] for c in children)) == re.sub(r'\s+', '', parent['text'])


def report(full, turns):
    return '=' * 60 + '\nMEETING TRANSCRIPTION REPORT\nInput file : sample.txt\nFULL TRANSCRIPTION\n' + '-' * 60 + '\n' + full + '\nTIMESTAMPED SEGMENTS\n' + '-' * 60 + '\n' + turns


def test_report_duplicate_and_conflicting_versions():
    prepared = p.prepare(report('Sara: Send it. Ali: Okay.', 'Sara: Send it.\nAli: Okay.'))
    assert prepared['preprocessing']['duplicate_section_removed']
    assert len(prepared['segments']) == 2
    assert_coverage(prepared)
    conflicting = p.prepare(report('Sara: Cancel it.', 'Sara: Send it.'))
    assert not conflicting['preprocessing']['duplicate_section_removed']
    assert any('both versions' in w for w in conflicting['preprocessing']['warnings'])
    assert len(conflicting['source_segments']) == 2


def test_inline_timestamps_and_original_offsets():
    text = '[00:01 - 00:04] SPEAKER_01: Dr. Sara will send it. Do not cancel it. [00:04 - 00:04] SPEAKER_02: Yes.'
    prepared = p.prepare(text)
    assert [s['speaker'] for s in prepared['segments']] == ['SPEAKER_01', 'SPEAKER_01', 'SPEAKER_02']
    assert [s['start'] for s in prepared['segments']] == [1, 1, 4]
    assert 'Do not cancel it.' == prepared['segments'][1]['text']
    for source in prepared['source_segments']:
        assert text[source['document_start']:source['document_end']] == source['text']
    assert_coverage(prepared)


def test_long_unicode_text_and_context_budget():
    text = 'Sara: ' + ('We must review café designs and cannot cancel the work ' * 60)
    prepared = p.prepare(text)
    # Segment count depends on the deployed tokenizer; a fresh clone uses the
    # documented heuristic fallback rather than ignored private model files.
    assert len(prepared['segments']) > 1
    assert_coverage(prepared)
    tokenizer, budget = p.token_policy()
    if tokenizer:
        from app.bert import model_path
        metadata = json.loads((model_path() / 'meetmind_model.json').read_text(encoding='utf-8'))
        for target, context in build_inputs(prepared['segments'], 2):
            assert len(tokenizer.encode(target, context).ids) <= metadata['max_length']


def test_fallback_and_ordinary_headings(monkeypatch):
    monkeypatch.setattr(p, 'token_policy', lambda: (None, 40))
    prepared = p.prepare('FULL TRANSCRIPTION\nhttps://example.org\n' + 'x' * 700)
    assert not prepared['preprocessing']['report_detected']
    assert prepared['segments'][1]['speaker'] is None
    assert prepared['preprocessing']['warnings']
    assert any(s['preprocessing_review'] for s in prepared['segments'])
    assert_coverage(prepared)


def test_compatibility_characters_are_budgeted_after_cleaning():
    prepared = p.prepare('Sara: ' + '\ufdfa ' * 100)
    assert_coverage(prepared)
    tokenizer, budget = p.token_policy()
    if tokenizer:
        assert all(len(tokenizer.encode(s['text'], add_special_tokens=False).ids) <= budget for s in prepared['segments'])


def test_original_export_and_persistent_lineage(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB_PATH', tmp_path / 'test.db')
    client = TestClient(main.app)
    original = report('Sara: Send it. Ali: Okay.', 'Sara: Send it.\nAli: Okay.')
    meeting = client.post('/api/meetings', json={'title': 'Report', 'transcript': original}).json()
    assert client.get(f'/api/meetings/{meeting["id"]}').json() == meeting
    assert client.get(f'/api/meetings/{meeting["id"]}/transcript?format=original').text == original
    exported = client.get(f'/api/meetings/{meeting["id"]}/transcript?format=json').json()
    assert exported['source_segments'] == meeting['source_segments']
    assert_coverage(meeting)


def test_caption_and_media_children_share_source_times():
    parents = [{'id': 1, 'text': 'Send it. Do not cancel it.', 'source': 'Send it. Do not cancel it.',
                'speaker': 'Sara', 'start': 1.0, 'end': 5.0}]
    prepared = p.prepare('original captions', parents)
    assert len(prepared['segments']) == 2
    assert all(s['start'] == 1 and s['end'] == 5 and s['timing_scope'] == 'source_segment' for s in prepared['segments'])
    assert_coverage(prepared)
