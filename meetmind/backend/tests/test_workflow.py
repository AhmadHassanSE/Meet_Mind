import json
import time

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import artifact_graph, main

pytestmark = pytest.mark.real_auth
CSRF = {'X-Requested-With': 'meetmind'}
ITEM = {'id': 'item-1', 'revision': 0, 'task': 'Send the report', 'owner': 'Sara', 'deadline': 'Friday',
        'kind': 'commitment', 'status': 'proposed', 'needs_review': True, 'source_id': 1,
        'evidence': [{'quote': 'I will send the report by Friday.', 'source_ids': [1]}]}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB_PATH', tmp_path / 'wf.db')
    policy = tmp_path / 'policy.txt'
    policy.write_text('allow channel email\nrequire approved_commitment\nrequire explicit_recipients\nrequire human_approval\n')
    monkeypatch.setenv('MEETMIND_ARTIFACT_POLICY', str(policy))

    async def fake_draft(context, url, model):
        return json.dumps({'subject': 'Report follow-up', 'body': 'Please send the report by Friday.'})
    monkeypatch.setattr(artifact_graph, 'ollama_draft', fake_draft)
    calls = {'extract': 0, 'fail': False, 'sent': []}

    async def fake_extract(meeting_id):
        calls['extract'] += 1
        if calls['fail']:
            calls['fail'] = False
            raise HTTPException(503, 'Ollama request failed. Check the local service and installed model.')
        meeting = main.get_meeting(meeting_id)
        meeting.update(status='extracted', actions=[dict(ITEM)])
        main.save(meeting)
    monkeypatch.setattr(main.workflow_service, 'extract', fake_extract)
    monkeypatch.setattr(main.artifact_service, 'executors', {})
    return calls


def account(client, email, name):
    response = client.post('/api/auth/signup', json={'email': email, 'name': name, 'password': 'correct horse battery'})
    assert response.status_code == 201, response.text
    return response.json()


def wait(client, meeting_id, predicate, what):
    for _ in range(300):
        state = client.get(f'/api/meetings/{meeting_id}/workflow').json()
        if predicate(state):
            return state
        time.sleep(.02)
    pytest.fail(f'Workflow did not reach {what}: {state}')


def waiting_for(kind):
    return lambda s: s['status'] == 'waiting' and s['waiting_for']['waiting_for'] == kind


def approve_item(client, meeting_id, assignee=None):
    item = client.get(f'/api/meetings/{meeting_id}').json()['actions'][0]
    result = client.post(f'/api/meetings/{meeting_id}/commitments/item-1/review', json={
        'revision': item['revision'], 'task': item['task'], 'owner': 'Sara', 'deadline': 'Friday', 'decision': 'approved', 'note': ''})
    assert result.status_code == 200, result.text
    if assignee:
        item = result.json()['actions'][0]
        assert client.put(f'/api/meetings/{meeting_id}/commitments/item-1/assignee',
                          json={'revision': item['revision'], 'user_id': assignee}).status_code == 200


@pytest.fixture
def team(env):
    # Clients stay open so background workflow runs keep a live event loop, as in the server.
    with TestClient(main.app, headers=CSRF) as organizer, TestClient(main.app, headers=CSRF) as owner, \
            TestClient(main.app, headers=CSRF) as outsider:
        account(organizer, 'org@example.com', 'Ayesha')
        sara = account(owner, 'sara@example.com', 'Sara')
        account(outsider, 'bilal@example.com', 'Bilal')
        meeting = organizer.post('/api/meetings', json={'title': 'Sync', 'transcript': 'Sara: I will send the report by Friday.'}).json()
        yield {'org': organizer, 'owner': owner, 'sara': sara, 'outsider': outsider, 'meeting': meeting['id'], 'calls': env}


def test_full_run_pauses_for_people_and_executes_only_after_owner_approval(team):
    org, owner, meeting_id = team['org'], team['owner'], team['meeting']
    started = org.post(f'/api/meetings/{meeting_id}/workflow')
    assert started.status_code == 202 and started.json()['status'] == 'running'
    assert org.post(f'/api/meetings/{meeting_id}/workflow').status_code == 409
    state = wait(org, meeting_id, waiting_for('commitment_review'), 'commitment review')
    assert state['stage'] == 'await_review' and state['can_control']
    follow_up = {'follow_ups': [{'commitment_id': 'item-1', 'to': ['sara@example.com']}]}
    # The graph cannot draft for a commitment no person has approved.
    assert org.post(f'/api/meetings/{meeting_id}/workflow/resume', json=follow_up).status_code == 409
    approve_item(org, meeting_id, assignee=team['sara']['id'])
    assert org.post(f'/api/meetings/{meeting_id}/workflow/resume', json=follow_up).status_code == 202
    state = wait(org, meeting_id, waiting_for('draft_approval'), 'draft approval')
    [draft] = state['drafts']
    assert draft['status'] == 'draft' and draft['to'] == ['sara@example.com'] and state['policy'] == {draft['id']: []}
    # Nothing executes while the owner has not decided, even if the organizer asks again.
    assert org.post(f'/api/meetings/{meeting_id}/workflow/check').status_code == 202
    state = wait(org, meeting_id, waiting_for('draft_approval'), 'draft approval again')
    assert 'deliveries' not in state or state['deliveries'] == {}
    assert org.post(f"/api/artifacts/{draft['id']}/review", json={'revision': 1, 'decision': 'approved'}).status_code == 422
    assert owner.post(f"/api/artifacts/{draft['id']}/review", json={'revision': 1, 'decision': 'approved'}).status_code == 200
    state = wait(org, meeting_id, lambda s: s['status'] == 'completed', 'completion')
    assert state['deliveries'][draft['id']]['status'] == 'not_configured'
    assert state['drafts'][0]['delivery']['status'] == 'not_configured'
    events = [h['event'] for h in state['history']]
    for expected in ['started', 'extracted', 'waiting_for_commitment_review', 'review_completed', 'drafts_created',
                     'policy_checked', 'waiting_for_draft_approval', 'approval_checked', 'executed', 'completed']:
        assert expected in events
    assert next(h for h in state['history'] if h['event'] == 'review_completed')['actor'] == 'Ayesha <org@example.com>'
    assert team['calls']['extract'] == 1


def test_permissions(team):
    org, owner, outsider, meeting_id = team['org'], team['owner'], team['outsider'], team['meeting']
    assert outsider.get(f'/api/meetings/{meeting_id}/workflow').status_code == 404
    assert owner.post(f'/api/meetings/{meeting_id}/workflow').status_code == 404
    org.post(f'/api/meetings/{meeting_id}/workflow')
    wait(org, meeting_id, waiting_for('commitment_review'), 'review')
    approve_item(org, meeting_id, assignee=team['sara']['id'])
    view = owner.get(f'/api/meetings/{meeting_id}/workflow')
    assert view.status_code == 200 and view.json()['can_control'] is False
    assert owner.post(f'/api/meetings/{meeting_id}/workflow/resume', json={'follow_ups': []}).status_code == 403


def test_paused_run_survives_a_restart(team):
    org, meeting_id = team['org'], team['meeting']
    org.post(f'/api/meetings/{meeting_id}/workflow')
    wait(org, meeting_id, waiting_for('commitment_review'), 'review')
    approve_item(org, meeting_id)
    with TestClient(main.app, headers=CSRF, cookies=org.cookies) as restarted:  # new lifespan, empty task table
        assert restarted.get(f'/api/meetings/{meeting_id}/workflow').json()['status'] == 'waiting'
        assert restarted.post(f'/api/meetings/{meeting_id}/workflow/resume', json={'follow_ups': [
            {'commitment_id': 'item-1', 'to': ['sara@example.com']}]}).status_code == 202
        state = wait(restarted, meeting_id, waiting_for('draft_approval'), 'draft approval')
        assert len(state['drafts']) == 1
    assert team['calls']['extract'] == 1  # resumed from the checkpoint, not re-run


def test_failure_is_retried_from_the_failed_step(team):
    org, meeting_id = team['org'], team['meeting']
    team['calls']['fail'] = True
    org.post(f'/api/meetings/{meeting_id}/workflow')
    state = wait(org, meeting_id, lambda s: s['status'] == 'failed', 'failure')
    assert 'Ollama' in state['error'] and state['stage'] == 'extract'
    assert org.post(f'/api/meetings/{meeting_id}/workflow/resume', json={'follow_ups': []}).status_code == 409
    assert org.post(f'/api/meetings/{meeting_id}/workflow/retry').status_code == 202
    wait(org, meeting_id, waiting_for('commitment_review'), 'review after retry')
    assert team['calls']['extract'] == 2


def test_finish_without_follow_ups_and_rerun_reuses_reviews(team):
    org, meeting_id = team['org'], team['meeting']
    org.post(f'/api/meetings/{meeting_id}/workflow')
    wait(org, meeting_id, waiting_for('commitment_review'), 'review')
    approve_item(org, meeting_id)
    assert org.post(f'/api/meetings/{meeting_id}/workflow/resume', json={'follow_ups': []}).status_code == 202
    state = wait(org, meeting_id, lambda s: s['status'] == 'completed', 'completion')
    assert state['drafts'] == []
    # A second run keeps the reviewed decisions instead of re-extracting over them.
    assert org.post(f'/api/meetings/{meeting_id}/workflow').status_code == 202
    state = wait(org, meeting_id, waiting_for('commitment_review'), 'second review')
    assert state['run'] == 2 and 'extraction_reused' in [h['event'] for h in state['history']]
    assert team['calls']['extract'] == 1
    assert org.get(f'/api/meetings/{meeting_id}').json()['actions'][0]['review_status'] == 'approved'


def test_executor_runs_once_for_a_valid_approval(team, monkeypatch):
    org, meeting_id, calls = team['org'], team['meeting'], team['calls']

    async def fake_send(draft):
        calls['sent'].append(draft['id'])
        return {'status': 'sent', 'detail': 'fake message id 1'}
    monkeypatch.setattr(main.artifact_service, 'executors', {'email': fake_send})
    org.post(f'/api/meetings/{meeting_id}/workflow')
    wait(org, meeting_id, waiting_for('commitment_review'), 'review')
    approve_item(org, meeting_id)  # no owner linked: the organizer decides
    org.post(f'/api/meetings/{meeting_id}/workflow/resume', json={'follow_ups': [{'commitment_id': 'item-1', 'to': ['x@example.com']}]})
    state = wait(org, meeting_id, waiting_for('draft_approval'), 'approval')
    draft_id = state['drafts'][0]['id']
    org.post(f'/api/artifacts/{draft_id}/review', json={'revision': 1, 'decision': 'approved'})
    state = wait(org, meeting_id, lambda s: s['status'] == 'completed', 'completion')
    assert calls['sent'] == [draft_id] and state['deliveries'][draft_id]['status'] == 'sent'
    history = org.get(f'/api/artifacts/{draft_id}').json()['history']
    assert history[-1]['action'] == 'delivery_sent' and org.get(f'/api/artifacts/{draft_id}').json()['approval_valid']


def test_rejected_draft_is_never_executed(team, monkeypatch):
    org, meeting_id, calls = team['org'], team['meeting'], team['calls']

    async def fake_send(draft):
        calls['sent'].append(draft['id'])
        return {'status': 'sent'}
    monkeypatch.setattr(main.artifact_service, 'executors', {'email': fake_send})
    org.post(f'/api/meetings/{meeting_id}/workflow')
    wait(org, meeting_id, waiting_for('commitment_review'), 'review')
    approve_item(org, meeting_id)
    org.post(f'/api/meetings/{meeting_id}/workflow/resume', json={'follow_ups': [{'commitment_id': 'item-1', 'to': ['x@example.com']}]})
    draft_id = wait(org, meeting_id, waiting_for('draft_approval'), 'approval')['drafts'][0]['id']
    org.post(f'/api/artifacts/{draft_id}/review', json={'revision': 1, 'decision': 'rejected'})
    state = wait(org, meeting_id, lambda s: s['status'] == 'completed', 'completion')
    assert calls['sent'] == [] and state['deliveries'][draft_id]['status'] == 'skipped'
