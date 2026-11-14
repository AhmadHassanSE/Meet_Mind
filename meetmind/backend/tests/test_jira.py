import base64
import json
import time

import httpx
import pytest

from app import artifact_graph, main
from test_auth import CSRF, app_db, assign, meeting_with_item, team  # noqa: F401

pytestmark = pytest.mark.real_auth
SITE = {'base_url': 'https://meetmind-team.atlassian.net', 'email': 'admin@example.com',
        'api_token': 'jira-token-secret', 'project_key': 'meet'}


class FakeJira:
    def __init__(self):
        self.issues, self.issue_status = [], []
        self.accounts = {'sara@example.com': [{'accountId': 'acc-sara', 'displayName': 'Sara J', 'accountType': 'atlassian'}],
                         'bilal@example.com': [{'accountId': 'a1', 'accountType': 'atlassian'}, {'accountId': 'a2', 'accountType': 'atlassian'}]}

    def __call__(self, request):
        assert request.headers['Authorization'].startswith('Basic ')
        path = request.url.path
        if path == '/rest/api/3/myself':
            user, token = base64.b64decode(request.headers['Authorization'][6:]).decode().split(':', 1)
            return httpx.Response(200 if token == 'jira-token-secret' else 401, json={'displayName': 'MeetMind Bot'})
        if path == '/rest/api/3/project/MEET':
            return httpx.Response(200, json={'key': 'MEET'})
        if path.startswith('/rest/api/3/project/'):
            return httpx.Response(404, json={})
        if path == '/rest/api/3/user/search':
            return httpx.Response(200, json=self.accounts.get(request.url.params['query'], []))
        if path == '/rest/api/3/issue':
            status = self.issue_status.pop(0) if self.issue_status else 201
            if status == 201:
                self.issues.append(json.loads(request.content)['fields'])
                return httpx.Response(201, json={'key': f'MEET-{len(self.issues)}'})
            return httpx.Response(status, json={'errorMessages': ['Field assignee is invalid']})
        raise AssertionError('Unexpected request ' + str(request.url))


@pytest.fixture
def jira(team, app_db, monkeypatch):
    fake = FakeJira()
    monkeypatch.setattr(main.jira, 'transport', httpx.MockTransport(fake))
    monkeypatch.setattr(main.jira, 'backoff', 0)

    async def fake_draft(context, url, model, channel='email'):
        assert channel == 'jira'
        return json.dumps({'subject': 'Send the project report', 'body': 'Owner: Sara\n\nDue: Friday'})
    monkeypatch.setattr(artifact_graph, 'ollama_draft', fake_draft)
    (app_db / 'policy.txt').write_text('allow channel email\nallow channel jira\nrequire approved_commitment\n'
                                       'require explicit_recipients\nrequire human_approval\n')
    return fake


def connected(team):
    admin, _ = team['admin']
    response = admin.post('/api/integrations/jira', json=SITE)
    assert response.status_code == 200, response.text
    assert admin.post('/api/integrations/jira/sync-users').status_code == 200
    return admin


def ticket(admin, meeting_id, key='jira-key-0001'):
    item = admin.get('/api/meetings/' + meeting_id).json()['actions'][0]
    return admin.post(f'/api/meetings/{meeting_id}/artifacts', json={
        'commitment_id': 'item-1', 'commitment_revision': item['revision'], 'channel': 'jira', 'idempotency_key': key})


def test_site_connection_is_validated_and_admin_only(team, jira):
    admin, _ = team['admin']
    sara, _ = team['sara']
    assert sara.post('/api/integrations/jira', json=SITE).status_code == 403
    assert admin.post('/api/integrations/jira', json={**SITE, 'base_url': 'https://evil.example.com'}).status_code == 422
    assert admin.post('/api/integrations/jira', json={**SITE, 'api_token': 'wrong-token'}).status_code == 422
    assert admin.post('/api/integrations/jira', json={**SITE, 'project_key': 'NOPE'}).status_code == 422
    status = admin.post('/api/integrations/jira', json=SITE).json()
    assert status['connected'] and status['project_key'] == 'MEET' and 'jira-token-secret' not in json.dumps(status)
    with main.connect() as c:
        assert 'jira-token-secret' not in c.execute("SELECT secret FROM integrations WHERE provider='jira'").fetchone()['secret']


def test_users_map_only_to_a_single_matching_account(team, jira):
    status = connected(team).get('/api/integrations/jira').json()
    assert [(u['email'], u['account_id']) for u in status['mapped_users']] == [('sara@example.com', 'acc-sara')]


def test_ticket_needs_a_connected_site(team, jira):
    admin, _ = team['admin']
    meeting_id = meeting_with_item(admin)
    assert ticket(admin, meeting_id).status_code == 409
    item = admin.get('/api/meetings/' + meeting_id).json()['actions'][0]
    bad = admin.post(f'/api/meetings/{meeting_id}/artifacts', json={'commitment_id': 'item-1', 'commitment_revision': item['revision'],
                                                                   'channel': 'jira', 'to': ['x@example.com'], 'idempotency_key': 'jira-key-0002'})
    assert bad.status_code == 422


def test_owner_approved_ticket_is_created_once_with_the_linked_assignee(team, jira):
    admin = connected(team)
    sara, sara_user = team['sara']
    meeting_id = meeting_with_item(admin)
    assign(admin, meeting_id, sara_user['id'])
    record = ticket(admin, meeting_id).json()
    assert record['channel'] == 'jira' and record['to'] == [] and record['graph_steps'] == ['draft_ticket', 'validate_ticket']
    assert record['jira'] == {'site': SITE['base_url'], 'project_key': 'MEET', 'assignee_user_id': sara_user['id'],
                              'assignee_account_id': 'acc-sara', 'assignee_name': 'Sara J'}
    assert admin.post(f"/api/artifacts/{record['id']}/send").status_code == 409  # not approved yet
    approved = sara.post(f"/api/artifacts/{record['id']}/review", json={'revision': 1, 'decision': 'approved'}).json()
    assert approved['approval_valid']
    created = sara.post(f"/api/artifacts/{record['id']}/send").json()['delivery']
    assert created['status'] == 'sent' and created['issue_key'] == 'MEET-1'
    assert created['url'] == 'https://meetmind-team.atlassian.net/browse/MEET-1'
    [fields] = jira.issues
    assert fields['assignee'] == {'accountId': 'acc-sara'} and fields['project'] == {'key': 'MEET'}
    assert fields['summary'] == 'Send the project report'
    assert [p['content'][0]['text'] for p in fields['description']['content']] == ['Owner: Sara', 'Due: Friday']
    assert sara.post(f"/api/artifacts/{record['id']}/send").json()['delivery']['issue_key'] == 'MEET-1'
    assert len(jira.issues) == 1


def test_policy_must_allow_jira(team, jira, app_db):
    admin = connected(team)
    meeting_id = meeting_with_item(admin)
    record = ticket(admin, meeting_id).json()
    (app_db / 'policy.txt').write_text('allow channel email\nrequire approved_commitment\nrequire explicit_recipients\nrequire human_approval\n')
    blocked = admin.post(f"/api/artifacts/{record['id']}/review", json={'revision': 1, 'decision': 'approved'})
    assert blocked.status_code == 409 and 'jira is not permitted' in blocked.json()['detail']


def test_changed_site_and_refused_issue_are_reported(team, jira):
    admin = connected(team)
    meeting_id = meeting_with_item(admin)
    record = ticket(admin, meeting_id).json()
    admin.post(f"/api/artifacts/{record['id']}/review", json={'revision': 1, 'decision': 'approved'})
    jira.issue_status = [400]
    refused = admin.post(f"/api/artifacts/{record['id']}/send").json()['delivery']
    assert refused['status'] == 'failed' and 'assignee is invalid' in refused['detail']
    jira.issue_status = []
    connected_other = admin.post('/api/integrations/jira', json={**SITE, 'base_url': 'https://other-team.atlassian.net'})
    assert connected_other.status_code == 200
    moved = admin.post(f"/api/artifacts/{record['id']}/send").json()['delivery']
    assert moved['status'] == 'failed' and 'changed after approval' in moved['detail'] and jira.issues == []


def test_workflow_can_create_a_ticket_follow_up(team, jira, monkeypatch):
    admin = connected(team)
    meeting_id = meeting_with_item(admin)

    async def extracted(meeting_id):
        return None
    monkeypatch.setattr(main.workflow_service, 'extract', extracted)
    from fastapi.testclient import TestClient
    with TestClient(main.app, headers=CSRF, cookies=admin.cookies) as live:
        assert live.post(f'/api/meetings/{meeting_id}/workflow').status_code == 202
        for _ in range(300):
            state = live.get(f'/api/meetings/{meeting_id}/workflow').json()
            if state['status'] == 'waiting':
                break
            time.sleep(.02)
        assert live.post(f'/api/meetings/{meeting_id}/workflow/resume', json={'follow_ups': [
            {'commitment_id': 'item-1', 'channel': 'jira'}]}).status_code == 202
        for _ in range(300):
            state = live.get(f'/api/meetings/{meeting_id}/workflow').json()
            if state['status'] == 'waiting' and state['waiting_for']['waiting_for'] == 'draft_approval':
                break
            time.sleep(.02)
        draft_id = state['drafts'][0]['id']
        live.post(f'/api/artifacts/{draft_id}/review', json={'revision': 1, 'decision': 'approved'})
        for _ in range(300):
            state = live.get(f'/api/meetings/{meeting_id}/workflow').json()
            if state['status'] == 'completed':
                break
            time.sleep(.02)
    assert state['deliveries'][draft_id]['issue_key'] == 'MEET-1' and len(jira.issues) == 1
