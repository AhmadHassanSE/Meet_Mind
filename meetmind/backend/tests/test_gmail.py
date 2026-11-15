import base64
from email import message_from_bytes, policy as email_policy
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main
from test_auth import CSRF, account, app_db, assign, draft, meeting_with_item, team  # noqa: F401

pytestmark = pytest.mark.real_auth


class FakeGoogle:
    """Stands in for Google's OAuth, userinfo, revoke and Gmail send endpoints."""

    def __init__(self):
        self.sent, self.revoked, self.send_status = [], [], []
        self.grant_scope = 'openid email https://www.googleapis.com/auth/gmail.send'

    def __call__(self, request):
        url = str(request.url)
        if url.startswith('https://oauth2.googleapis.com/token'):
            form = parse_qs(request.content.decode())
            if form['grant_type'] == ['authorization_code']:
                assert form['code_verifier'] and form['code'] == ['good-code']
                return httpx.Response(200, json={'access_token': 'access-1', 'refresh_token': 'refresh-secret-123',
                                                 'scope': self.grant_scope, 'expires_in': 3600})
            assert form['refresh_token'] == ['refresh-secret-123']
            return httpx.Response(200, json={'access_token': f'access-{len(self.sent) + 2}', 'expires_in': 3600})
        if url.startswith('https://openidconnect.googleapis.com'):
            return httpx.Response(200, json={'email': 'ayesha.team@gmail.com'})
        if url.startswith('https://oauth2.googleapis.com/revoke'):
            self.revoked.append(parse_qs(request.content.decode())['token'][0])
            return httpx.Response(200)
        if url.startswith('https://gmail.googleapis.com'):
            status = self.send_status.pop(0) if self.send_status else 200
            if status == 200:
                raw = request.read().decode()
                self.sent.append(message_from_bytes(base64.urlsafe_b64decode(httpx.Response(200, content=raw).json()['raw']), policy=email_policy.default))
                return httpx.Response(200, json={'id': f'gmail-msg-{len(self.sent)}'})
            return httpx.Response(status, json={'error': 'fake'})
        raise AssertionError('Unexpected request ' + url)


@pytest.fixture
def google(team, monkeypatch):
    monkeypatch.setenv('MEETMIND_GOOGLE_CLIENT_ID', 'client-id')
    monkeypatch.setenv('MEETMIND_GOOGLE_CLIENT_SECRET', 'client-secret')
    fake = FakeGoogle()
    monkeypatch.setattr(main.gmail, 'transport', httpx.MockTransport(fake))
    monkeypatch.setattr(main.gmail, 'backoff', 0)
    main.gmail.tokens.clear()
    return fake


def connect(client):
    url = client.post('/api/integrations/gmail/connect').json()['url']
    query = parse_qs(urlparse(url).query)
    assert query['scope'] == ['openid email https://www.googleapis.com/auth/gmail.send']
    assert query['code_challenge_method'] == ['S256'] and query['access_type'] == ['offline']
    # Google redirects the browser back; the callback carries no session cookie (SameSite=Strict).
    browser = TestClient(main.app)  # no MeetMind cookies at all
    response = browser.get('/api/integrations/gmail/callback', params={'state': query['state'][0], 'code': 'good-code'},
                           follow_redirects=False)
    return query['state'][0], response


def approved_draft(team):
    admin, _ = team['admin']
    meeting_id = meeting_with_item(admin)  # no owner linked: the organizer approves
    record = draft(admin, meeting_id).json()
    approved = admin.post(f"/api/artifacts/{record['id']}/review", json={'revision': 1, 'decision': 'approved'}).json()
    assert approved['approval_valid']
    return record['id']


def test_not_configured_without_client_credentials(team):
    admin, _ = team['admin']
    assert admin.get('/api/integrations/gmail').json()['configured'] is False
    assert admin.post('/api/integrations/gmail/connect').status_code == 503


def test_connect_stores_only_an_encrypted_token(team, google):
    admin, _ = team['admin']
    state, response = connect(admin)
    assert response.status_code == 303 and response.headers['location'].endswith('/account?gmail=connected')
    status = admin.get('/api/integrations/gmail').json()
    assert status == {**status, 'configured': True, 'connected': True, 'account': 'ayesha.team@gmail.com'}
    assert 'refresh' not in str(status)
    with main.connect() as c:
        stored = c.execute('SELECT secret FROM integrations').fetchone()['secret']
    assert 'refresh-secret-123' not in stored
    # The state is single-use.
    replay = admin.get('/api/integrations/gmail/callback', params={'state': state, 'code': 'good-code'}, follow_redirects=False)
    assert replay.headers['location'].endswith('gmail=error')


def test_connection_without_send_permission_is_refused(team, google):
    admin, _ = team['admin']
    google.grant_scope = 'openid email'
    _, response = connect(admin)
    assert response.headers['location'].endswith('gmail=error')
    assert admin.get('/api/integrations/gmail').json()['connected'] is False


def test_approved_draft_is_sent_once_from_the_approvers_account(team, google):
    admin, _ = team['admin']
    connect(admin)
    draft_id = approved_draft(team)
    sent = admin.post(f'/api/artifacts/{draft_id}/send').json()
    assert sent['delivery']['status'] == 'sent' and sent['delivery']['message_id'] == 'gmail-msg-1'
    assert sent['delivery']['sender'] == 'ayesha.team@gmail.com' and sent['approval_valid']
    [message] = google.sent
    assert message['To'] == 'sara@example.com' and message['Subject'] == sent['subject']
    assert message.get_content().strip() == sent['body'].strip()
    again = admin.post(f'/api/artifacts/{draft_id}/send').json()
    assert again['delivery']['message_id'] == 'gmail-msg-1' and len(google.sent) == 1
    assert [h['action'] for h in again['history']][-1] == 'delivery_sent'


def test_unapproved_or_edited_drafts_cannot_be_sent(team, google):
    admin, _ = team['admin']
    connect(admin)
    meeting_id = meeting_with_item(admin)
    record = draft(admin, meeting_id).json()
    assert admin.post(f"/api/artifacts/{record['id']}/send").status_code == 409
    admin.post(f"/api/artifacts/{record['id']}/review", json={'revision': 1, 'decision': 'approved'})
    admin.patch(f"/api/artifacts/{record['id']}", json={'revision': 2, 'to': ['sara@example.com'],
                                                         'subject': 'Changed', 'body': 'Changed body'})
    assert admin.post(f"/api/artifacts/{record['id']}/send").status_code == 409
    assert google.sent == []


def test_other_users_cannot_send(team, google):
    sara, _ = team['sara']
    draft_id = approved_draft(team)
    assert sara.post(f'/api/artifacts/{draft_id}/send').status_code == 404


def test_without_a_connection_nothing_is_sent(team, google):
    admin, _ = team['admin']
    draft_id = approved_draft(team)
    result = admin.post(f'/api/artifacts/{draft_id}/send').json()
    assert result['delivery']['status'] == 'not_configured' and google.sent == []


def test_transient_errors_retry_and_permanent_errors_stop(team, google):
    admin, _ = team['admin']
    connect(admin)
    google.send_status = [503, 401, 200]  # unavailable, expired token (refresh), then success
    first = admin.post(f'/api/artifacts/{approved_draft(team)}/send').json()['delivery']
    assert first['status'] == 'sent' and first['attempts'] == 3
    google.send_status = [400]
    second = admin.post(f'/api/artifacts/{approved_draft(team)}/send').json()['delivery']
    assert second['status'] == 'failed' and '400' in second['detail'] and len(google.sent) == 1


def test_disconnect_revokes_the_token(team, google):
    admin, _ = team['admin']
    connect(admin)
    assert admin.delete('/api/integrations/gmail').status_code == 204
    assert google.revoked == ['refresh-secret-123']
    assert admin.get('/api/integrations/gmail').json()['connected'] is False
    actions = [entry['action'] for entry in admin.get('/api/admin/audit').json()]
    assert 'gmail_connected' in actions and 'gmail_disconnected' in actions


def test_interrupted_send_is_reported_not_repeated(team, google):
    admin, _ = team['admin']
    draft_id = approved_draft(team)
    main.artifact_service.begin_delivery(draft_id)  # simulate a crash after reserving the send
    main.artifact_service.recover()
    record = admin.get(f'/api/artifacts/{draft_id}').json()
    assert record['delivery']['status'] == 'failed' and 'Sent folder' in record['delivery']['detail']
    assert google.sent == []
