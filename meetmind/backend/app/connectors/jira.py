"""Jira Cloud connector: workspace site connection, user mapping and issue creation.

An admin connects one Jira Cloud site with an API token (encrypted at rest) and a
default project. MeetMind users are mapped to Jira accounts by email. A ticket draft
fixes its project and assignee when it is created; the assignee is the human-linked
owner's Jira account, never chosen by the model. Issues are created only through
``artifacts.Service.deliver``, so an approved ticket is created at most once.
"""
import asyncio
import base64
from datetime import datetime, timezone
import json
import re

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .. import auth, vault

SCHEMA = ['CREATE TABLE IF NOT EXISTS jira_users (user_id TEXT PRIMARY KEY, account_id TEXT NOT NULL, '
          'display_name TEXT, synced_at TEXT NOT NULL)']
WORKSPACE = 'workspace'
ATTEMPTS = 3


class SiteInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    base_url: str = Field(max_length=200)
    email: str = Field(min_length=3, max_length=254)
    api_token: str = Field(min_length=8, max_length=500)
    project_key: str = Field(min_length=1, max_length=20)

    @field_validator('base_url')
    @classmethod
    def cloud_site(cls, value):
        match = re.fullmatch(r'https://([a-z0-9][a-z0-9-]{0,62})\.atlassian\.net/?', value.lower())
        if not match:
            raise ValueError('Use your Jira Cloud address, like https://your-team.atlassian.net')
        return f'https://{match[1]}.atlassian.net'

    @field_validator('project_key')
    @classmethod
    def key(cls, value):
        if not re.fullmatch(r'[A-Z][A-Z0-9_]{0,19}', value.upper()):
            raise ValueError('Project key is letters and digits, like MEET')
        return value.upper()


def document(text):
    """Jira's description format (Atlassian Document Format), one paragraph per block of text."""
    blocks = [b.strip() for b in text.split('\n\n') if b.strip()]
    return {'type': 'doc', 'version': 1, 'content': [
        {'type': 'paragraph', 'content': [{'type': 'text', 'text': b}]} for b in blocks]}


class Jira:
    def __init__(self, connect, key_path, transport=None):
        self.connect, self.key_path, self.transport = connect, key_path, transport
        self.backoff = 1.0

    def client(self, site):
        token = base64.b64encode(f"{site['email']}:{site['api_token']}".encode()).decode()
        return httpx.AsyncClient(base_url=site['base_url'], timeout=30, transport=self.transport,
                                 headers={'Authorization': 'Basic ' + token, 'Accept': 'application/json'})

    def site(self, connection=None):
        def read(c):
            return c.execute("SELECT * FROM integrations WHERE user_id=? AND provider='jira'", (WORKSPACE,)).fetchone()
        row = read(connection) if connection is not None else None
        if connection is None:
            with self.connect() as c:
                row = read(c)
        return {**vault.unseal(row['secret'], self.key_path), 'account': row['account']} if row else None

    def status(self):
        site = self.site()
        with self.connect() as c:
            mapped = [dict(r) for r in c.execute(
                'SELECT j.user_id, j.account_id, j.display_name, u.email, u.name FROM jira_users j '
                'JOIN users u ON u.id=j.user_id ORDER BY u.name')]
        return {'connected': bool(site), 'base_url': site and site['base_url'], 'project_key': site and site['project_key'],
                'account': site and site['account'], 'mapped_users': mapped}

    async def connect_site(self, data, admin):
        site = data.model_dump()
        async with self.client(site) as client:
            me = await client.get('/rest/api/3/myself')
            if me.status_code in {401, 403}:
                raise HTTPException(422, 'Jira rejected the email or API token')
            me.raise_for_status()
            project = await client.get(f"/rest/api/3/project/{data.project_key}")
            if project.status_code == 404:
                raise HTTPException(422, f'Project {data.project_key} was not found or is not visible to this account')
            project.raise_for_status()
        account = me.json().get('displayName') or data.email
        with self.connect() as c:
            c.execute('INSERT OR REPLACE INTO integrations VALUES (?,?,?,?,?)',
                      (WORKSPACE, 'jira', account, vault.seal(site, self.key_path), datetime.now(timezone.utc).isoformat()))
            auth.audit(c, admin, 'jira_connected', WORKSPACE, {'site': data.base_url, 'project': data.project_key})
        return self.status()

    async def sync_users(self, admin):
        """Match each active MeetMind user to exactly one Jira account with the same email."""
        site = self.site()
        if not site:
            raise HTTPException(409, 'Connect Jira first')
        with self.connect() as c:
            users = [dict(r) for r in c.execute('SELECT id, email FROM users WHERE active=1')]
        found = {}
        async with self.client(site) as client:
            for user in users:
                response = await client.get('/rest/api/3/user/search', params={'query': user['email']})
                matches = [m for m in (response.json() if response.is_success else []) if m.get('accountType', 'atlassian') == 'atlassian']
                if len(matches) == 1:
                    found[user['id']] = matches[0]
        with self.connect() as c:
            c.execute('DELETE FROM jira_users')
            for user_id, match in found.items():
                c.execute('INSERT INTO jira_users VALUES (?,?,?,?)', (user_id, match['accountId'], match.get('displayName'),
                                                                       datetime.now(timezone.utc).isoformat()))
            auth.audit(c, admin, 'jira_users_synced', WORKSPACE, {'mapped': len(found), 'users': len(users)})
        return self.status()

    def disconnect(self, admin):
        with self.connect() as c:
            if not c.execute("DELETE FROM integrations WHERE user_id=? AND provider='jira'", (WORKSPACE,)).rowcount:
                raise HTTPException(404, 'Jira is not connected')
            c.execute('DELETE FROM jira_users')
            auth.audit(c, admin, 'jira_disconnected', WORKSPACE)

    def ticket_context(self, connection, meeting_id, item):
        """Fields fixed when a ticket draft is created; part of what gets approved."""
        site = self.site(connection)
        if not site:
            raise HTTPException(409, 'Jira is not connected. An admin connects it under Admin → Jira.')
        owner = auth.assignee(connection, meeting_id, item['id'])
        mapped = owner and connection.execute('SELECT j.account_id, j.display_name FROM jira_users j WHERE j.user_id=?', (owner,)).fetchone()
        return {'site': site['base_url'], 'project_key': site['project_key'], 'assignee_user_id': owner,
                'assignee_account_id': mapped['account_id'] if mapped else None,
                'assignee_name': mapped['display_name'] if mapped else None}

    async def create_issue(self, draft):
        """Executor for approved Jira drafts; returns a delivery record and never raises for Jira errors."""
        site, fixed = self.site(), draft['jira']
        if not site:
            return {'status': 'not_configured', 'detail': 'Jira is not connected; no issue was created.'}
        if site['base_url'] != fixed['site'] or site['project_key'] != fixed['project_key']:
            return {'status': 'failed', 'detail': 'The Jira site or project changed after approval; create a new draft. No issue was created.'}
        fields = {'project': {'key': fixed['project_key']}, 'summary': draft['subject'], 'issuetype': {'name': 'Task'},
                  'description': document(draft['body'])}
        if fixed.get('assignee_account_id'):
            fields['assignee'] = {'accountId': fixed['assignee_account_id']}
        if draft['source'].get('deadline_normalized'):
            fields['duedate'] = draft['source']['deadline_normalized']  # resolved or confirmed during review
        for attempt in range(ATTEMPTS):
            try:
                async with self.client(site) as client:
                    response = await client.post('/rest/api/3/issue', json={'fields': fields})
            except httpx.HTTPError:
                response = None
            if response is not None and response.is_success:
                key = response.json()['key']
                return {'status': 'sent', 'issue_key': key, 'url': f"{site['base_url']}/browse/{key}",
                        'detail': f'Created {key}', 'attempts': attempt + 1}
            if response is not None and response.status_code not in {429, 500, 502, 503, 504}:
                try:
                    reason = '; '.join(response.json().get('errorMessages', []) + list(response.json().get('errors', {}).values()))
                except (ValueError, json.JSONDecodeError):
                    reason = ''
                return {'status': 'failed', 'attempts': attempt + 1,
                        'detail': f'Jira refused the issue ({response.status_code}{": " + reason if reason else ""}); no issue was created.'}
            await asyncio.sleep(self.backoff * 2 ** attempt)
        return {'status': 'failed', 'attempts': ATTEMPTS, 'detail': 'Jira was unavailable after several attempts; no issue is known to have been created.'}


def build_router(jira):
    router = APIRouter(prefix='/api/integrations/jira')

    @router.get('')
    def status(user: auth.User = Depends(auth.current_user)):
        return jira.status()

    @router.post('')
    async def connect(data: SiteInput, admin: auth.User = Depends(auth.admin_user)):
        return await jira.connect_site(data, admin)

    @router.post('/sync-users')
    async def sync(admin: auth.User = Depends(auth.admin_user)):
        return await jira.sync_users(admin)

    @router.delete('', status_code=204)
    def disconnect(admin: auth.User = Depends(auth.admin_user)):
        jira.disconnect(admin)

    return router
