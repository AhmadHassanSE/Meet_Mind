"""Regressions for defects found in the 14 Nov 2026 audit, using its example sentences."""
import json

import pytest
from fastapi.testclient import TestClient

from app import commitments as c, main, urdu
from app.connectors import meet
from app.ingestion import segment
from app.preprocessing import prepare
from conftest import TEST_USER
from test_commitments import nlp, proposal, units_for  # noqa: F401  (shared fixtures/helpers)


def grounded(text, **changes):
    _, units = units_for(text)
    result = c.ground([proposal(units[0], **changes)], units, nlp_model())
    return result, (result['actions'] + result['action_candidates'])[0]


def nlp_model():
    return c.load_nlp()[0]


@pytest.mark.parametrize('text', ["I will send the report by Friday, don't worry.",
                                  'I will not forget to send the report.'])
def test_incidental_negation_keeps_the_commitment(nlp, text):
    result, item = grounded('Sara: ' + text)
    assert item['kind'] == 'commitment' and result['actions']
    assert 'negation_present_check_meaning' in item['review_reasons']


@pytest.mark.parametrize('text', ['I will not send the report.', 'Do not send the report.'])
def test_negated_action_is_still_a_cancellation(nlp, text):
    _, item = grounded('Sara: ' + text)
    assert item['kind'] == 'cancellation'


@pytest.mark.parametrize('text,expected', [
    ('Main nai report kal bhej dunga.', 'commitment'),       # nai = new
    ('Main report bhej dunga, fikar na karo.', 'commitment'),
    ('میں رپورٹ بھیج دوں گا، فکر نہ کریں۔', 'commitment'),
    ('Report mat bhejna.', 'cancellation'),
    ('Main report nahi bhejunga.', 'cancellation'),
])
def test_urdu_negation_ignores_new_and_reassurance(text, expected):
    assert urdu.kind(text, 'commitment')[0] == expected


@pytest.mark.parametrize('opening', ['Okay', 'Sure', 'So'])
def test_discourse_words_are_not_owners(nlp, opening):
    _, item = grounded(f'Ali: {opening}, can you book the room?', task='Book the room', kind='request')
    assert item['owner'] is None


def test_model_proposed_discourse_owner_is_rejected(nlp):
    _, item = grounded('Ali: Okay, please book the room.', task='Book the room', kind='request', owner='Okay')
    assert item['owner'] is None


def test_vocative_name_is_checked_against_speakers(nlp):
    _, units = units_for('Sara: Ali, can you book the room?\nAli: Sure.')
    item = c.ground([proposal(units[0], task='Book the room', kind='request')], units, nlp)['action_candidates'][0]
    assert item['owner'] == 'Ali' and 'vocative_name_not_a_known_speaker' not in item['review_reasons']
    _, units = units_for('Sara: Zubair, can you book the room?')
    item = c.ground([proposal(units[0], task='Book the room', kind='request')], units, nlp)['action_candidates'][0]
    assert item['owner'] == 'Zubair' and 'vocative_name_not_a_known_speaker' in item['review_reasons']


@pytest.mark.parametrize('line', ['Note: I will send the report.', 'Agenda: budget and hiring',
                                  'Action items: send the report', 'Meeting at 10:30 tomorrow'])
def test_headings_and_clock_times_are_not_speakers(line):
    assert segment(line, 1)['speaker'] is None
    assert prepare(line)['segments'][0]['speaker'] is None


def test_real_speakers_still_parse():
    assert segment('Sara: I will send it.', 1)['speaker'] == 'Sara'
    assert prepare('Dr. Bilal: Please review the draft.')['segments'][0]['speaker'] == 'Dr. Bilal'


def test_separate_dates_keep_the_supported_deadline(nlp):
    _, item = grounded('Sara: I will send the report on Friday and the slides next week.', deadline='Friday')
    assert item['deadline'] == 'Friday'
    assert 'multiple_date_expressions' in item['review_reasons']


def test_unrelated_later_negation_is_not_a_cancellation(nlp):
    _, units = units_for('Sara: I will send the report by Friday.\nAli: The report is not ready yet.')
    action = c.ground([proposal(units[0])], units, nlp)['actions'][0]
    assert action['status'] != 'possible_cancellation'


def test_later_negation_of_the_same_action_is_flagged(nlp):
    _, units = units_for("Sara: I will send the report by Friday.\nAli: We won't send the report after all.")
    action = c.ground([proposal(units[0])], units, nlp)['actions'][0]
    assert action['status'] == 'possible_cancellation'


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB_PATH', tmp_path / 'audit.db')
    monkeypatch.setattr(meet, 'ffmpeg_path', lambda: 'ffmpeg')
    meet.sessions.clear()
    with TestClient(main.app) as client:
        yield client
    meet.sessions.clear()


def start_session(client):
    response = client.post('/api/meet/sessions', json={'title': 'Sync', 'started_at_ms': 1_700_000_000_000})
    assert response.status_code == 201, response.text
    return response.json()['id']


def test_abandoned_meet_sessions_expire(client, monkeypatch):
    for _ in range(meet.MAX_SESSIONS):
        start_session(client)
    assert client.post('/api/meet/sessions', json={'title': 'x', 'started_at_ms': 1}).status_code == 429
    monkeypatch.setattr(meet, 'IDLE_SECONDS', -1)  # every existing session is now idle
    start_session(client)
    assert len(meet.sessions) == 1


def test_cancel_is_refused_while_transcribing(client):
    session_id = start_session(client)
    meet.sessions[session_id]['finishing'] = True
    directory = meet.sessions[session_id]['dir']
    assert client.delete(f'/api/meet/sessions/{session_id}').status_code == 409
    assert directory.exists()
    meet.sessions[session_id]['finishing'] = False


def test_oversized_audio_is_rejected_while_streaming(client, monkeypatch):
    session_id = start_session(client)
    monkeypatch.setattr(meet, 'MAX_CHUNK_BYTES', 8)
    chunks = (b'1234' for _ in range(4))
    assert client.post(f'/api/meet/sessions/{session_id}/audio?seq=0', content=chunks).status_code == 413


def test_meeting_deleted_during_analysis_returns_404(client, monkeypatch):
    meeting = client.post('/api/meetings', json={'title': 'Gone', 'transcript': 'Sara: I will send it.'}).json()

    async def classify_then_delete(*args):
        with main.connect() as connection:
            connection.execute('DELETE FROM meetings WHERE id=?', (meeting['id'],))
        return {'predictions': [], 'model': {}}
    monkeypatch.setattr(main.languages, 'classify', classify_then_delete)
    assert client.post(f"/api/meetings/{meeting['id']}/classify").status_code == 404


def test_users_see_their_own_bots_beyond_the_latest_thirty(client):
    with main.connect() as connection:
        main.bot_manager.database(connection)
        connection.execute('INSERT INTO meeting_bots VALUES (?,?)', ('mine', json.dumps(
            {'id': 'mine', 'state': 'completed', 'user_id': TEST_USER.id, 'events': [], 'message': ''})))
        for index in range(35):
            connection.execute('INSERT INTO meeting_bots VALUES (?,?)', (f'other-{index}', json.dumps(
                {'id': f'other-{index}', 'state': 'completed', 'user_id': 'someone-else', 'events': [], 'message': ''})))
    member = TEST_USER.__class__('test-user', 'tester@example.com', 'Tester', 'organizer', False)
    assert [bot['id'] for bot in main.bot_manager.list(member)] == ['mine']
