import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app import artifact_graph, auth, main

pytestmark = pytest.mark.real_auth
PUBLIC = {('GET', '/api/health'), ('GET', '/api/auth/config'), ('POST', '/api/auth/signup'), ('POST', '/api/auth/login')}
CSRF = {'X-Requested-With': 'meetmind'}


@pytest.fixture
def app_db(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB_PATH', tmp_path / 'auth.db')
    policy = tmp_path / 'policy.txt'
    policy.write_text('allow channel email\nrequire approved_commitment\nrequire explicit_recipients\nrequire human_approval\n')
    monkeypatch.setenv('MEETMIND_ARTIFACT_POLICY', str(policy))

    async def fake(context, url, model):
        return json.dumps({'subject': 'Report follow-up', 'body': 'Please send the report by Friday.'})
    monkeypatch.setattr(artifact_graph, 'ollama_draft', fake)
    return tmp_path


def account(email, name=None, password='correct horse battery'):
    client = TestClient(main.app, headers=CSRF)
    response = client.post('/api/auth/signup', json={'email': email, 'name': name or email.split('@')[0], 'password': password})
    assert response.status_code == 201, response.text
    return client, response.json()


@pytest.fixture
def team(app_db):
    admin, admin_user = account('admin@example.com', 'Ayesha Admin')
    member, member_user = account('sara@example.com', 'Sara')
    other, other_user = account('bilal@example.com', 'Bilal')
    return {'admin': (admin, admin_user), 'sara': (member, member_user), 'bilal': (other, other_user)}


def meeting_with_item(client):
    meeting = client.post('/api/meetings', json={'title': 'Sync', 'transcript': 'Sara: I will send the report by Friday.'}).json()
    stored = main.get_meeting(meeting['id'])
    stored['actions'] = [{'id': 'item-1', 'revision': 0, 'task': 'Send the report', 'owner': 'Sara', 'deadline': 'Friday',
                          'kind': 'commitment', 'status': 'proposed', 'needs_review': True, 'source_id': 1,
                          'evidence': [{'quote': 'I will send the report by Friday.', 'source_ids': [1]}]}]
    main.save(stored)
    item = client.get('/api/meetings/' + meeting['id']).json()['actions'][0]
    approved = client.post(f"/api/meetings/{meeting['id']}/commitments/item-1/review", json={
        'revision': item['revision'], 'task': item['task'], 'owner': 'Sara', 'deadline': 'Friday', 'decision': 'approved', 'note': ''})
    assert approved.status_code == 200, approved.text
    return meeting['id']


def assign(client, meeting_id, user_id):
    item = client.get('/api/meetings/' + meeting_id).json()['actions'][0]
    return client.put(f'/api/meetings/{meeting_id}/commitments/item-1/assignee', json={'revision': item['revision'], 'user_id': user_id})


def draft(client, meeting_id):
    item = client.get('/api/meetings/' + meeting_id).json()['actions'][0]
    return client.post(f'/api/meetings/{meeting_id}/artifacts', json={
        'commitment_id': 'item-1', 'commitment_revision': item['revision'], 'to': ['sara@example.com'], 'idempotency_key': str(uuid4())})


def test_every_api_route_requires_authentication(app_db):
    anonymous = TestClient(main.app)
    checked = 0
    # The OpenAPI schema lists routes from included routers too.
    for route_path, operations in main.app.openapi()['paths'].items():
        for method in operations:
            if (method.upper(), route_path) in PUBLIC:
                continue
            path = route_path.replace('{', '').replace('}', '')
            response = anonymous.request(method.upper(), path)
            assert response.status_code == 401, (method, route_path, response.status_code)
            checked += 1
    assert checked > 40


def test_first_account_bootstraps_admin_and_later_accounts_are_members(team):
    admin, admin_user = team['admin']
    assert admin_user['is_admin'] and admin_user['role'] == 'organizer'
    assert team['sara'][1]['role'] == 'member' and not team['sara'][1]['is_admin']
    assert admin.get('/api/auth/me').json()['email'] == 'admin@example.com'
    assert TestClient(main.app).post('/api/auth/signup', json={
        'email': 'ADMIN@example.com', 'name': 'Dup', 'password': 'another long password'}).status_code == 409
    assert admin.patch('/api/admin/settings', json={'signup_open': False}).status_code == 200
    assert TestClient(main.app).post('/api/auth/signup', json={
        'email': 'late@example.com', 'name': 'Late', 'password': 'another long password'}).status_code == 403
    assert TestClient(main.app).get('/api/auth/config').json() == {'has_users': True, 'signup_open': False}


def test_login_logout_lockout_and_csrf_header(team):
    anonymous = TestClient(main.app)
    for _ in range(auth.MAX_FAILURES):
        assert anonymous.post('/api/auth/login', json={'email': 'sara@example.com', 'password': 'wrong'}).status_code == 401
    assert anonymous.post('/api/auth/login', json={'email': 'sara@example.com', 'password': 'correct horse battery'}).status_code == 429
    bilal = TestClient(main.app)
    assert bilal.post('/api/auth/login', json={'email': 'Bilal@Example.com', 'password': 'correct horse battery'}).status_code == 200
    # A cookie alone is not enough for state changes.
    assert bilal.post('/api/auth/organizer-request', json={'reason': 'I run team syncs'}).status_code == 403
    assert bilal.post('/api/auth/organizer-request', json={'reason': 'I run team syncs'}, headers=CSRF).status_code == 201
    assert bilal.post('/api/auth/logout', headers=CSRF).status_code == 204
    assert bilal.get('/api/auth/me').status_code == 401


def test_member_needs_admin_approved_organizer_role_to_create_meetings(team):
    admin, _ = team['admin']
    sara, sara_user = team['sara']
    body = {'title': 'Plan', 'transcript': 'Sara: I will draft the plan.'}
    assert sara.post('/api/meetings', json=body).status_code == 403
    request = sara.post('/api/auth/organizer-request', json={'reason': 'I organize weekly planning'}).json()
    assert sara.post('/api/auth/organizer-request', json={'reason': 'Second request'}).status_code == 409
    assert sara.post(f"/api/admin/organizer-requests/{request['id']}", json={'decision': 'approved'}).status_code == 403
    pending = admin.get('/api/admin/organizer-requests').json()
    assert [r['email'] for r in pending] == ['sara@example.com']
    assert admin.post(f"/api/admin/organizer-requests/{request['id']}", json={'decision': 'approved', 'note': 'ok'}).status_code == 200
    assert admin.post(f"/api/admin/organizer-requests/{request['id']}", json={'decision': 'rejected'}).status_code == 409
    assert sara.get('/api/auth/me').json()['role'] == 'organizer'
    created = sara.post('/api/meetings', json=body)
    assert created.status_code == 201 and created.json()['access']['role'] == 'organizer'
    actions = [entry['action'] for entry in admin.get('/api/admin/audit').json()]
    assert 'organizer_requested' in actions and 'organizer_request_approved' in actions


def test_visibility_owner_rights_and_admin_audit(team):
    admin, _ = team['admin']
    sara, sara_user = team['sara']
    bilal, _ = team['bilal']
    meeting_id = meeting_with_item(admin)
    for client in (sara, bilal):
        assert client.get('/api/meetings').json() == []
        assert client.get('/api/meetings/' + meeting_id).status_code == 404
    assert assign(admin, meeting_id, sara_user['id']).status_code == 200
    # The owner sees the meeting but cannot run organizer actions.
    assert [m['id'] for m in sara.get('/api/meetings').json()] == [meeting_id]
    seen = sara.get('/api/meetings/' + meeting_id).json()
    assert seen['access'] == {'role': 'owner', 'can_organize': False, 'owned_items': ['item-1'], 'admin_override': False}
    assert seen['actions'][0]['assignee']['email'] == 'sara@example.com' and seen['actions'][0]['owner'] == 'Sara'
    assert sara.post(f'/api/meetings/{meeting_id}/extract').status_code == 403
    assert sara.delete('/api/meetings/' + meeting_id).status_code == 403
    assert bilal.get('/api/meetings/' + meeting_id).status_code == 404
    assert [m['role'] for m in admin.get(f'/api/meetings/{meeting_id}/members').json()] == ['organizer', 'owner']


def test_owner_decides_the_draft_and_admin_override_needs_a_reason(team):
    admin, _ = team['admin']
    sara, sara_user = team['sara']
    bilal, bilal_user = team['bilal']
    meeting_id = meeting_with_item(admin)
    assign(admin, meeting_id, sara_user['id'])
    created = draft(sara, meeting_id)
    assert created.status_code == 201, created.text
    record = created.json()
    assert record['rights'] == {'can_edit': True, 'can_decide': True, 'assignee_id': sara_user['id'], 'can_override': False}
    assert [d['id'] for d in sara.get('/api/artifacts?awaiting_me=true').json()] == [record['id']]
    assert admin.get('/api/artifacts?awaiting_me=true').json() == []
    assert bilal.get('/api/artifacts/' + record['id']).status_code == 404
    # The organizer (here also admin) may only override, with a reason.
    assert admin.post(f"/api/artifacts/{record['id']}/review", json={'revision': 1, 'decision': 'approved'}).status_code == 422
    approved = sara.post(f"/api/artifacts/{record['id']}/review", json={'revision': 1, 'decision': 'approved'}).json()
    assert approved['approval_valid'] and approved['approval']['approved_by'] == sara_user['id']
    assert approved['history'][-1]['actor'] == 'Sara <sara@example.com>' and not approved['approval']['admin_override']
    # Reassigning the owner changes the approver, so the approval is invalidated.
    assert assign(admin, meeting_id, bilal_user['id']).status_code == 200
    changed = admin.get('/api/artifacts/' + record['id']).json()
    assert changed['status'] == 'source_changed' and not changed['approval_valid']


def test_admin_override_is_recorded(team):
    admin, _ = team['admin']
    sara, sara_user = team['sara']
    admin.patch(f"/api/admin/users/{sara_user['id']}", json={'role': 'organizer'})
    meeting_id = meeting_with_item(sara)
    record = draft(sara, meeting_id).json()
    assert admin.get('/api/meetings/' + meeting_id).status_code == 200
    decided = admin.post(f"/api/artifacts/{record['id']}/review", json={'revision': 1, 'decision': 'rejected', 'note': 'Wrong recipient'})
    assert decided.status_code == 200 and decided.json()['history'][-1]['admin_override'] is True
    actions = [entry['action'] for entry in admin.get('/api/admin/audit').json()]
    assert 'admin_viewed_meeting' in actions and 'admin_override_rejected' in actions


def test_capture_token_is_limited_to_meet_uploads(team, monkeypatch):
    admin, _ = team['admin']
    sara, _ = team['sara']
    monkeypatch.setattr(main.meet, 'ffmpeg_path', lambda: 'ffmpeg')
    assert sara.post('/api/auth/tokens', json={'name': 'Laptop'}).status_code == 403
    token = admin.post('/api/auth/tokens', json={'name': 'Laptop'}).json()['token']
    extension = TestClient(main.app, headers={'Authorization': 'Bearer ' + token})
    session = extension.post('/api/meet/sessions', json={'title': 'Standup', 'started_at_ms': 1})
    assert session.status_code == 201, session.text
    assert extension.get('/api/meetings').status_code == 403
    assert extension.get('/api/auth/me').json()['token_scope'] == 'capture'
    # Members cannot capture; another organizer sees the session as missing.
    assert sara.delete(f"/api/meet/sessions/{session.json()['id']}").status_code == 403
    admin.patch(f"/api/admin/users/{team['sara'][1]['id']}", json={'role': 'organizer'})
    assert sara.delete(f"/api/meet/sessions/{session.json()['id']}").status_code == 404
    token_id = admin.get('/api/auth/tokens').json()[0]['id']
    assert admin.delete('/api/auth/tokens/' + token_id).status_code == 204
    assert extension.post('/api/meet/sessions', json={'title': 'Again', 'started_at_ms': 1}).status_code == 401
    assert admin.delete(f"/api/meet/sessions/{session.json()['id']}").status_code == 204


def test_admin_safeguards_and_deactivation(team):
    admin, admin_user = team['admin']
    sara, sara_user = team['sara']
    assert admin.patch(f"/api/admin/users/{admin_user['id']}", json={'is_admin': False}).status_code == 409
    assert admin.patch(f"/api/admin/users/{sara_user['id']}", json={'active': False}).json()['active'] is False
    assert sara.get('/api/auth/me').status_code == 401
    assert TestClient(main.app).post('/api/auth/login', json={'email': 'sara@example.com', 'password': 'correct horse battery'}).status_code == 401
    assert admin.post(f"/api/admin/users/{sara_user['id']}/password", json={'password': 'a brand new password'}).status_code == 204
    assert sara.get('/api/admin/users').status_code == 401


def test_organizer_deletes_meeting_and_members(team):
    admin, _ = team['admin']
    sara, sara_user = team['sara']
    meeting_id = meeting_with_item(admin)
    assert admin.post(f'/api/meetings/{meeting_id}/members', json={'user_id': sara_user['id'], 'role': 'organizer'}).status_code == 422
    assert admin.post(f'/api/meetings/{meeting_id}/members', json={'user_id': sara_user['id']}).status_code == 201
    assert sara.get('/api/meetings/' + meeting_id).json()['access']['role'] == 'viewer'
    assert admin.delete(f"/api/meetings/{meeting_id}/members/{admin.get('/api/auth/me').json()['id']}").status_code == 409
    draft(admin, meeting_id)
    assert admin.delete('/api/meetings/' + meeting_id).status_code == 204
    assert admin.get('/api/meetings/' + meeting_id).status_code == 404
    assert admin.get('/api/artifacts').json() == []
    assert sara.get('/api/meetings').json() == []


def test_existing_meetings_are_claimed_by_the_first_admin(app_db):
    legacy = {'id': 'legacy', 'title': 'Before accounts', 'segments': [], 'actions': [], 'status': 'uploaded'}
    main.save(legacy)
    admin, _ = account('first@example.com')
    assert [m['id'] for m in admin.get('/api/meetings').json()] == ['legacy']
    assert admin.get('/api/meetings/legacy').json()['access']['can_organize']
