"""Gmail connector: per-user OAuth and sending of human-approved follow-up emails.

Each user connects their own Google account with the ``gmail.send`` permission only;
MeetMind cannot read mail. Refresh tokens are encrypted at rest and never returned by
the API. Sending is reached only through ``artifacts.Service.deliver``, which checks
that the exact draft is approved and was never sent before.
"""
import asyncio
import base64
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
import hashlib
import json
import logging
import os
import secrets
import time
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse

from .. import auth, vault

AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth'
TOKEN_URL = 'https://oauth2.googleapis.com/token'
REVOKE_URL = 'https://oauth2.googleapis.com/revoke'
USERINFO_URL = 'https://openidconnect.googleapis.com/v1/userinfo'
SEND_URL = 'https://gmail.googleapis.com/gmail/v1/users/me/messages/send'
SEND_SCOPE = 'https://www.googleapis.com/auth/gmail.send'
SCOPES = f'openid email {SEND_SCOPE}'
SCHEMA = ['CREATE TABLE IF NOT EXISTS integrations (user_id TEXT NOT NULL, provider TEXT NOT NULL, account TEXT NOT NULL, '
          'secret TEXT NOT NULL, connected_at TEXT NOT NULL, PRIMARY KEY (user_id, provider))',
          'CREATE TABLE IF NOT EXISTS oauth_states (state TEXT PRIMARY KEY, user_id TEXT NOT NULL, provider TEXT NOT NULL, '
          'verifier TEXT NOT NULL, expires_at TEXT NOT NULL)']
ATTEMPTS = 3


def settings():
    client_id, client_secret = os.getenv('MEETMIND_GOOGLE_CLIENT_ID'), os.getenv('MEETMIND_GOOGLE_CLIENT_SECRET')
    if not client_id or not client_secret:
        return None
    return {'client_id': client_id, 'client_secret': client_secret,
            'redirect_uri': os.getenv('MEETMIND_GOOGLE_REDIRECT_URI', 'http://127.0.0.1:8000/api/integrations/gmail/callback'),
            'ui': os.getenv('MEETMIND_UI_URL', 'http://127.0.0.1:5173').rstrip('/')}


def now():
    return datetime.now(timezone.utc)


class Gmail:
    def __init__(self, connect, key_path, transport=None):
        self.connect, self.key_path, self.transport = connect, key_path, transport
        self.tokens = {}  # user_id -> (access token, monotonic expiry)
        self.backoff = 1.0

    def client(self):
        return httpx.AsyncClient(timeout=30, transport=self.transport)

    def account(self, user_id):
        with self.connect() as c:
            row = c.execute("SELECT * FROM integrations WHERE user_id=? AND provider='gmail'", (user_id,)).fetchone()
        return dict(row) if row else None

    def status(self, user):
        row = self.account(user.id)
        return {'configured': settings() is not None, 'connected': bool(row),
                'account': row['account'] if row else None, 'connected_at': row['connected_at'] if row else None,
                'scope': SEND_SCOPE}

    def begin(self, user):
        config = settings()
        if not config:
            raise HTTPException(503, 'Gmail is not configured on this server. Set MEETMIND_GOOGLE_CLIENT_ID and MEETMIND_GOOGLE_CLIENT_SECRET.')
        state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
        with self.connect() as c:
            c.execute('DELETE FROM oauth_states WHERE expires_at<=?', (now().isoformat(),))
            c.execute('INSERT INTO oauth_states VALUES (?,?,?,?,?)',
                      (state, user.id, 'gmail', verifier, (now() + timedelta(minutes=10)).isoformat()))
        return AUTH_URL + '?' + urlencode({
            'client_id': config['client_id'], 'redirect_uri': config['redirect_uri'], 'response_type': 'code',
            'scope': SCOPES, 'state': state, 'code_challenge': challenge, 'code_challenge_method': 'S256',
            'access_type': 'offline', 'prompt': 'consent'})

    async def finish(self, code, state):
        """OAuth callback. The single-use state, not a cookie, identifies the user."""
        config = settings()
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute("SELECT * FROM oauth_states WHERE state=? AND provider='gmail'", (state,)).fetchone()
            c.execute('DELETE FROM oauth_states WHERE state=?', (state,))
        if not config or not row or row['expires_at'] <= now().isoformat():
            raise ValueError('The Gmail connection request expired or is invalid. Start again from your account page.')
        async with self.client() as client:
            response = await client.post(TOKEN_URL, data={
                'code': code, 'client_id': config['client_id'], 'client_secret': config['client_secret'],
                'redirect_uri': config['redirect_uri'], 'grant_type': 'authorization_code', 'code_verifier': row['verifier']})
            if response.is_error:
                raise ValueError('Google rejected the connection request')
            tokens = response.json()
            if SEND_SCOPE not in tokens.get('scope', '').split() or not tokens.get('refresh_token'):
                raise ValueError('Google did not grant permission to send email. Connect again and allow sending.')
            profile = await client.get(USERINFO_URL, headers={'Authorization': 'Bearer ' + tokens['access_token']})
            account = profile.json().get('email') if profile.is_success else None
        if not account:
            raise ValueError('Could not read the connected Google account address')
        with self.connect() as c:
            c.execute('INSERT OR REPLACE INTO integrations VALUES (?,?,?,?,?)',
                      (row['user_id'], 'gmail', account, vault.seal({'refresh_token': tokens['refresh_token']}, self.key_path),
                       now().isoformat()))
            user = auth.load_user(c, row['user_id'])
            auth.audit(c, user, 'gmail_connected', row['user_id'], {'account': account})
        self.tokens.pop(row['user_id'], None)
        return account

    async def disconnect(self, user):
        row = self.account(user.id)
        if not row:
            raise HTTPException(404, 'Gmail is not connected')
        try:
            refresh = vault.unseal(row['secret'], self.key_path)['refresh_token']
            async with self.client() as client:
                await client.post(REVOKE_URL, data={'token': refresh})
        except (ValueError, httpx.HTTPError):
            logging.warning('Gmail token revocation failed; deleting the stored connection anyway')
        with self.connect() as c:
            c.execute("DELETE FROM integrations WHERE user_id=? AND provider='gmail'", (user.id,))
            auth.audit(c, user, 'gmail_disconnected', user.id, {'account': row['account']})
        self.tokens.pop(user.id, None)

    async def access_token(self, user_id, refresh=False):
        cached = self.tokens.get(user_id)
        if cached and not refresh and cached[1] > time.monotonic():
            return cached[0]
        row, config = self.account(user_id), settings()
        if not row or not config:
            return None
        async with self.client() as client:
            response = await client.post(TOKEN_URL, data={
                'client_id': config['client_id'], 'client_secret': config['client_secret'], 'grant_type': 'refresh_token',
                'refresh_token': vault.unseal(row['secret'], self.key_path)['refresh_token']})
        if response.is_error:
            return None
        token = response.json()
        self.tokens[user_id] = (token['access_token'], time.monotonic() + token.get('expires_in', 3600) - 60)
        return token['access_token']

    async def send(self, draft):
        """Executor for approved email drafts. Returns a delivery record; never raises for Google errors."""
        approval = draft['approval']
        senders = [approval['approved_by']]
        if approval.get('sender_rule', 'any') == 'any':
            # Without "require sender approver" the person who requested the draft may also send it.
            senders += [h['actor_id'] for h in draft['history'] if h['action'] == 'draft_requested' and h.get('actor_id')]
        sender = next((s for s in senders if self.account(s)), None)
        if sender is None:
            return {'status': 'not_configured', 'detail': 'The approver has not connected Gmail on their account page; nothing was sent.'}
        account = self.account(sender)['account']
        message = EmailMessage()
        message['To'] = ', '.join(draft['to'])
        message['Subject'] = draft['subject']
        message.set_content(draft['body'])
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        refreshed = False
        for attempt in range(ATTEMPTS):
            token = await self.access_token(sender, refresh=refreshed)
            if token is None:
                return {'status': 'failed', 'sender': account,
                        'detail': 'Google no longer accepts this Gmail connection; reconnect it on the account page. Nothing was sent.'}
            try:
                async with self.client() as client:
                    response = await client.post(SEND_URL, json={'raw': raw}, headers={'Authorization': 'Bearer ' + token})
            except httpx.HTTPError:
                response = None
            if response is not None and response.is_success:
                return {'status': 'sent', 'sender': account, 'message_id': response.json().get('id'),
                        'detail': f'Sent from {account}', 'attempts': attempt + 1}
            if response is not None and response.status_code == 401 and not refreshed:
                refreshed = True
                continue
            if response is not None and response.status_code not in {429, 500, 502, 503, 504}:
                return {'status': 'failed', 'sender': account, 'attempts': attempt + 1,
                        'detail': f'Gmail refused the message ({response.status_code}); nothing was sent.'}
            await asyncio.sleep(self.backoff * 2 ** attempt)
        return {'status': 'failed', 'sender': account, 'attempts': ATTEMPTS,
                'detail': 'Gmail was unavailable after several attempts; nothing is known to have been sent.'}


def build_router(gmail):
    router = APIRouter(prefix='/api/integrations/gmail')

    @router.get('')
    def status(user: auth.User = Depends(auth.current_user)):
        return gmail.status(user)

    @router.post('/connect')
    def connect(user: auth.User = Depends(auth.current_user)):
        return {'url': gmail.begin(user)}

    @router.get('/callback', include_in_schema=False)
    async def callback(state: str = '', code: str = '', error: str = ''):
        ui = (settings() or {}).get('ui', os.getenv('MEETMIND_UI_URL', 'http://127.0.0.1:5173').rstrip('/'))
        if error or not code:
            return RedirectResponse(ui + '/account?gmail=cancelled', status_code=303)
        try:
            await gmail.finish(code, state)
        except (ValueError, httpx.HTTPError, json.JSONDecodeError):
            logging.exception('Gmail connection failed')
            return RedirectResponse(ui + '/account?gmail=error', status_code=303)
        return RedirectResponse(ui + '/account?gmail=connected', status_code=303)

    @router.delete('', status_code=204)
    async def disconnect(user: auth.User = Depends(auth.current_user)):
        await gmail.disconnect(user)

    return router
