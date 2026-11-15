from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from app import main


@pytest.fixture
def reviewed_meeting(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB_PATH', tmp_path / 'review.db')
    client = TestClient(main.app)
    meeting = client.post('/api/meetings', json={
        'title': 'Review fixture', 'transcript': 'Sara: I will send the report by Friday.'}).json()
    action = {'task': 'Send report', 'owner': 'Sara', 'deadline': 'by Friday',
              'kind': 'commitment', 'status': 'proposed', 'needs_review': True,
              'source_id': 1, 'source_ids': [1], 'review_reasons': ['human_review_required'],
              'evidence': [{'quote': 'I will send the report by Friday.', 'source_ids': [1]}]}
    candidate = {**deepcopy(action), 'task': 'Review design', 'kind': 'suggestion', 'status': 'suggestion'}
    meeting.update(actions=[action], action_candidates=[candidate], status='extracted')
    main.save(meeting)
    meeting = client.get('/api/meetings/' + meeting['id']).json()
    return client, meeting


def update(client, meeting, item, **changes):
    body = {'revision': item['revision'], 'task': item['task'], 'owner': item['owner'],
            'deadline': item['deadline'], 'decision': 'pending', 'note': '', **changes}
    return client.post(f"/api/meetings/{meeting['id']}/commitments/{item['id']}/review", json=body)


def test_edit_approve_reject_and_reopen_persist_with_original_evidence(reviewed_meeting):
    client, meeting = reviewed_meeting
    original = deepcopy(meeting['actions'][0])
    response = update(client, meeting, original, task='Send final report', owner='Ali', deadline='Monday')
    assert response.status_code == 200
    edited = response.json()['actions'][0]
    assert edited['original'] == original
    assert edited['evidence'] == original['evidence']
    assert edited['owner_method'] == 'human_review'
    assert edited['needs_review']
    for decision in ('approved', 'rejected', 'pending'):
        response = update(client, meeting, edited, decision=decision, note='Checked source')
        assert response.status_code == 200
        edited = response.json()['actions'][0]
        assert edited['review_status'] == decision
        assert edited['needs_review'] == (decision == 'pending')
    persisted = client.get('/api/meetings/' + meeting['id']).json()
    assert persisted == response.json()
    assert len(edited['review_history']) == 4
    assert edited['review_history'][0]['before']['owner'] == 'Sara'
    assert edited['review_history'][0]['after']['owner'] == 'Ali'
    assert edited['original'] == original


def test_candidate_promotion_and_return_to_candidates(reviewed_meeting):
    client, meeting = reviewed_meeting
    item = meeting['action_candidates'][0]
    promoted = update(client, meeting, item, decision='approved', owner='', deadline='').json()
    assert not promoted['action_candidates']
    item = promoted['actions'][1]
    assert item['kind'] == 'suggestion' and item['review_status'] == 'approved'
    assert item['owner'] is None and item['deadline'] is None
    reopened = update(client, meeting, item).json()
    assert len(reopened['actions']) == 1
    assert reopened['action_candidates'][0]['id'] == item['id']


def test_stale_revision_and_invalid_fields_preserve_saved_review(reviewed_meeting):
    client, meeting = reviewed_meeting
    original = meeting['actions'][0]
    saved = update(client, meeting, original, decision='approved').json()
    assert update(client, meeting, original, decision='rejected').status_code == 409
    for changes in ({'task': '  '}, {'owner': 'a' * 201}, {'evidence': []}, {'decision': 'done'}):
        assert update(client, meeting, saved['actions'][0], **changes).status_code == 422
    assert client.get('/api/meetings/' + meeting['id']).json() == saved
    missing = {**original, 'id': 'missing'}
    assert update(client, meeting, missing).status_code == 404


def test_cancellations_cannot_be_promoted_and_flagged_tasks_need_note(reviewed_meeting):
    client, meeting = reviewed_meeting
    meeting['actions'][0]['status'] = 'possible_cancellation'
    meeting['action_candidates'][0].update(kind='cancellation', status='cancellation')
    main.save(meeting)
    assert update(client, meeting, meeting['action_candidates'][0], decision='approved').status_code == 422
    assert update(client, meeting, meeting['actions'][0], decision='approved').status_code == 422
    assert update(client, meeting, meeting['actions'][0], decision='approved', note='Cancellation referred to a different report').status_code == 200


def test_reextraction_does_not_erase_edits_or_rejected_items(reviewed_meeting, monkeypatch):
    client, meeting = reviewed_meeting
    saved = update(client, meeting, meeting['actions'][0], decision='rejected').json()
    def forbidden(*args):
        pytest.fail('Reviewed meetings must be rejected before running inference')
    monkeypatch.setattr(main.bert, 'classify', forbidden)
    assert client.post(f"/api/meetings/{meeting['id']}/extract").status_code == 409
    assert client.get('/api/meetings/' + meeting['id']).json() == saved


def test_classification_merges_concurrent_review(reviewed_meeting, monkeypatch):
    client, meeting = reviewed_meeting
    def classify(segments):
        assert update(client, meeting, meeting['actions'][0], decision='approved').status_code == 200
        return {'predictions': [], 'model': {}}
    monkeypatch.setattr(main.bert, 'classify', classify)
    response = client.post(f"/api/meetings/{meeting['id']}/classify")
    assert response.status_code == 200
    assert response.json()['actions'][0]['review_status'] == 'approved'


def test_extraction_cannot_overwrite_review_made_during_inference(reviewed_meeting, monkeypatch):
    client, meeting = reviewed_meeting
    monkeypatch.setattr(main.bert, 'classify', lambda _: {'predictions': []})
    monkeypatch.setattr(main.commitments, 'source_units', lambda *_: [])
    monkeypatch.setattr(main.commitments, 'annotate', lambda _: None)
    async def propose(*args):
        assert update(client, meeting, meeting['actions'][0], decision='approved').status_code == 200
        return []
    monkeypatch.setattr(main.commitments, 'propose', propose)
    monkeypatch.setattr(main.commitments, 'ground', lambda *_: {'actions': [], 'action_candidates': []})
    assert client.post(f"/api/meetings/{meeting['id']}/extract").status_code == 409
    assert client.get('/api/meetings/' + meeting['id']).json()['actions'][0]['review_status'] == 'approved'
