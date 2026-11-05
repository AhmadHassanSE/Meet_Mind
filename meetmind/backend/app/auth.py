"""Local accounts, sessions, capture tokens and role-based meeting access.

Account roles: ``member`` (default) or ``organizer`` (granted by an admin).
``is_admin`` is separate, so an admin may also be an organizer. Per-meeting
rights come from ``meeting_members`` (organizer/viewer) and ``assignments``
(the owner of an action item). Admins can view everything but act on other
people's records only through an audited override.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

COOKIE = 'meetmind_session'
CSRF_HEADER = 'x-requested-with'
SESSION_DAYS = 7
TOKEN_DAYS = 90
MAX_FAILURES = 5
LOCK_MINUTES = 5
SCRYPT = dict(n=2 ** 14, r=8, p=1)
connect = None  # set by main.py; returns a SQLite connection context manager


def now():
    return datetime.now(timezone.utc)


def stamp(value=None):
    return (value or now()).isoformat()


def schema(connection):
    connection.executescript('''
        CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, email TEXT UNIQUE NOT NULL COLLATE NOCASE,
            name TEXT NOT NULL, password_hash TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'member',
            is_admin INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL,
            failed_logins INTEGER NOT NULL DEFAULT 0, locked_until TEXT);
        CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL,
            created_at TEXT NOT NULL, expires_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS api_tokens (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, name TEXT NOT NULL,
            token_hash TEXT UNIQUE NOT NULL, scope TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL,
            last_used_at TEXT, revoked INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS role_requests (id TEXT PRIMARY KEY, user_id TEXT NOT NULL, reason TEXT NOT NULL,
            status TEXT NOT NULL, created_at TEXT NOT NULL, decided_by TEXT, decided_at TEXT, note TEXT);
        CREATE TABLE IF NOT EXISTS meeting_members (meeting_id TEXT NOT NULL, user_id TEXT NOT NULL,
            role TEXT NOT NULL, added_by TEXT, added_at TEXT NOT NULL, PRIMARY KEY (meeting_id, user_id));
        CREATE TABLE IF NOT EXISTS assignments (meeting_id TEXT NOT NULL, item_id TEXT NOT NULL, user_id TEXT NOT NULL,
            assigned_by TEXT, assigned_at TEXT NOT NULL, PRIMARY KEY (meeting_id, item_id));
        CREATE TABLE IF NOT EXISTS audit_log (id TEXT PRIMARY KEY, at TEXT NOT NULL, actor_id TEXT, action TEXT NOT NULL,
            target TEXT, detail TEXT);
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS members_by_user ON meeting_members(user_id);
        CREATE INDEX IF NOT EXISTS assignments_by_user ON assignments(user_id);
    ''')


@dataclass(frozen=True)
class User:
    id: str
    email: str
    name: str
    role: str
    is_admin: bool
    token_scope: str | None = None

    @property
    def organizer(self):
        return self.role == 'organizer'

    @property
    def label(self):
        return f'{self.name} <{self.email}>'

    def public(self):
        return {'id': self.id, 'email': self.email, 'name': self.name, 'role': self.role, 'is_admin': self.is_admin}


def actor(user):
    """Audit identity for history entries; never an unverified placeholder."""
    return {'actor_id': user.id, 'actor': user.label} if user else {'actor_id': None, 'actor': 'system (local workflow)'}


def to_user(row, scope=None):
    return User(row['id'], row['email'], row['name'], row['role'], bool(row['is_admin']), scope)


def audit(connection, user, action, target=None, detail=None):
    connection.execute('INSERT INTO audit_log VALUES (?,?,?,?,?,?)', (str(uuid4()), stamp(), user.id if user else None,
                       action, target, json.dumps(detail, ensure_ascii=False) if detail is not None else None))


# Passwords and tokens

def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, dklen=32, **SCRYPT)
    return 'scrypt${n}${r}${p}$'.format(**SCRYPT) + base64.b64encode(salt).decode() + '$' + base64.b64encode(digest).decode()


def check_password(password, stored):
    try:
        _, n, r, p, salt, expected = stored.split('$')
        digest = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), dklen=32, n=int(n), r=int(r), p=int(p))
        return hmac.compare_digest(digest, base64.b64decode(expected))
    except (ValueError, TypeError):
        return False


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def issue_token(connection, user_id, name, scope='capture', ttl=timedelta(days=TOKEN_DAYS)):
    """Return a new raw token; only its hash is stored."""
    token = 'mmt_' + secrets.token_urlsafe(32)
    connection.execute('INSERT INTO api_tokens (id,user_id,name,token_hash,scope,created_at,expires_at) VALUES (?,?,?,?,?,?,?)',
                       (str(uuid4()), user_id, name, token_hash(token), scope, stamp(), stamp(now() + ttl)))
    return token


def revoke_token(connection, token):
    connection.execute('UPDATE api_tokens SET revoked=1 WHERE token_hash=?', (token_hash(token),))


def setting(connection, key, default):
    row = connection.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
    return json.loads(row['value']) if row else default


# Request authentication

def principal(request: Request):
    header = request.headers.get('authorization', '')
    with connect() as connection:
        if header.lower().startswith('bearer '):
            row = connection.execute(
                'SELECT u.*, t.scope, t.id AS token_id FROM api_tokens t JOIN users u ON u.id=t.user_id '
                'WHERE t.token_hash=? AND t.revoked=0 AND t.expires_at>? AND u.active=1',
                (token_hash(header[7:].strip()), stamp())).fetchone()
            if not row:
                raise HTTPException(401, 'Access token is invalid, expired or revoked')
            connection.execute('UPDATE api_tokens SET last_used_at=? WHERE id=?', (stamp(), row['token_id']))
            return to_user(row, row['scope'])
        token = request.cookies.get(COOKIE)
        row = token and connection.execute(
            'SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires_at>? AND u.active=1',
            (token_hash(token), stamp())).fetchone()
    if not row:
        raise HTTPException(401, 'Sign in to continue')
    # Cookie sessions need a header that cross-site forms cannot send without CORS approval.
    if request.method not in {'GET', 'HEAD', 'OPTIONS'} and request.headers.get(CSRF_HEADER) != 'meetmind':
        raise HTTPException(403, 'Missing X-Requested-With: meetmind header')
    return to_user(row)


def current_user(user: User = Depends(principal)):
    """Interactive users only; capture tokens cannot read or approve records."""
    if user.token_scope:
        raise HTTPException(403, 'This access token can only upload Meet captures')
    return user


def capture_user(user: User = Depends(principal)):
    if user.token_scope not in {None, 'capture'}:
        raise HTTPException(403, 'This access token cannot upload Meet captures')
    if not user.organizer:
        raise HTTPException(403, 'Only organizers can capture meetings. Request organizer access from an admin.')
    return user


def organizer_user(user: User = Depends(current_user)):
    if not user.organizer:
        raise HTTPException(403, 'Only organizers can create meetings. Request organizer access from an admin.')
    return user


def admin_user(user: User = Depends(current_user)):
    if not user.is_admin:
        raise HTTPException(403, 'Admin access required')
    return user


# Meeting access

def membership(connection, meeting_id, user_id):
    row = connection.execute('SELECT role FROM meeting_members WHERE meeting_id=? AND user_id=?', (meeting_id, user_id)).fetchone()
    return row['role'] if row else None


def assigned_items(connection, meeting_id, user_id):
    return {row['item_id'] for row in connection.execute(
        'SELECT item_id FROM assignments WHERE meeting_id=? AND user_id=?', (meeting_id, user_id))}


def assignee(connection, meeting_id, item_id):
    row = connection.execute('SELECT user_id FROM assignments WHERE meeting_id=? AND item_id=?', (meeting_id, item_id)).fetchone()
    return row['user_id'] if row else None


def access(connection, meeting_id, user):
    """Describe what ``user`` may do on a meeting; ``None`` means no visibility."""
    if not connection.execute('SELECT 1 FROM meetings WHERE id=?', (meeting_id,)).fetchone():
        return None
    role = membership(connection, meeting_id, user.id)
    owned = assigned_items(connection, meeting_id, user.id)
    organize = role == 'organizer' and user.organizer
    if not (role or owned or user.is_admin):
        return None
    return {'role': 'organizer' if role == 'organizer' else 'owner' if owned else role or 'admin',
            'can_organize': organize, 'owned_items': sorted(owned), 'admin_override': user.is_admin and not organize}


def require_view(connection, meeting_id, user):
    result = access(connection, meeting_id, user)
    if result is None:
        raise HTTPException(404, 'Meeting not found')
    return result


def require_organize(connection, meeting_id, user):
    result = require_view(connection, meeting_id, user)
    if not result['can_organize']:
        raise HTTPException(403, 'Only this meeting\'s organizer can do this')
    return result


def visible_meeting_ids(connection, user):
    """``None`` means all meetings (admin)."""
    if user.is_admin:
        return None
    return {row[0] for row in connection.execute(
        'SELECT meeting_id FROM meeting_members WHERE user_id=? UNION SELECT meeting_id FROM assignments WHERE user_id=?',
        (user.id, user.id))}


def add_organizer(connection, meeting_id, user_id, added_by=None):
    connection.execute('INSERT OR IGNORE INTO meeting_members VALUES (?,?,?,?,?)',
                       (meeting_id, user_id, 'organizer', added_by, stamp()))


def claim_orphans(connection, admin_id):
    """Meetings saved before accounts existed become the first admin's."""
    for row in connection.execute('SELECT id FROM meetings WHERE id NOT IN (SELECT meeting_id FROM meeting_members '
                                  "WHERE role='organizer')").fetchall():
        add_organizer(connection, row['id'], admin_id)


# Request models

Email = Field(min_length=3, max_length=254)


def plain_email(value):
    value = value.strip()
    if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', value):
        raise ValueError('Enter a valid email address')
    return value.lower()


class Credentials(BaseModel):
    model_config = ConfigDict(extra='forbid')
    email: str = Email
    password: str = Field(min_length=1, max_length=256)

    @field_validator('email')
    @classmethod
    def normalized(cls, value):
        return plain_email(value)


class SignupInput(Credentials):
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=10, max_length=256)


class ProfileInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str | None = Field(default=None, min_length=1, max_length=100)
    current_password: str | None = Field(default=None, max_length=256)
    new_password: str | None = Field(default=None, min_length=10, max_length=256)


class RoleRequestInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    reason: str = Field(min_length=5, max_length=1000)


class TokenInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=80)


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    role: Literal['member', 'organizer'] | None = None
    is_admin: bool | None = None
    active: bool | None = None


class PasswordReset(BaseModel):
    model_config = ConfigDict(extra='forbid')
    password: str = Field(min_length=10, max_length=256)


class Decision(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    decision: Literal['approved', 'rejected']
    note: str = Field(default='', max_length=1000)


class SettingsInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    signup_open: bool


def start_session(connection, response, user_id):
    token = secrets.token_urlsafe(32)
    connection.execute('DELETE FROM sessions WHERE expires_at<=?', (stamp(),))
    connection.execute('INSERT INTO sessions VALUES (?,?,?,?)',
                       (token_hash(token), user_id, stamp(), stamp(now() + timedelta(days=SESSION_DAYS))))
    response.set_cookie(COOKIE, token, max_age=SESSION_DAYS * 86400, httponly=True, samesite='strict',
                        secure=os.getenv('MEETMIND_COOKIE_SECURE', '0') == '1', path='/')


def user_row(connection, user_id):
    row = connection.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
    if not row:
        raise HTTPException(404, 'User not found')
    return row


def public_row(row):
    return {'id': row['id'], 'email': row['email'], 'name': row['name'], 'role': row['role'],
            'is_admin': bool(row['is_admin']), 'active': bool(row['active']), 'created_at': row['created_at']}


def active_admins(connection):
    return connection.execute('SELECT COUNT(*) FROM users WHERE is_admin=1 AND active=1').fetchone()[0]


def build_router():
    router = APIRouter(prefix='/api')

    @router.get('/auth/config')
    def config():
        with connect() as connection:
            has_users = connection.execute('SELECT EXISTS(SELECT 1 FROM users)').fetchone()[0]
            return {'has_users': bool(has_users), 'signup_open': not has_users or setting(connection, 'signup_open', True)}

    @router.post('/auth/signup', status_code=201)
    def signup(data: SignupInput, response: Response):
        with connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            first = not connection.execute('SELECT EXISTS(SELECT 1 FROM users)').fetchone()[0]
            if not first and not setting(connection, 'signup_open', True):
                raise HTTPException(403, 'Sign-up is closed. Ask an admin to create your account.')
            if connection.execute('SELECT 1 FROM users WHERE email=?', (data.email,)).fetchone():
                raise HTTPException(409, 'An account with this email already exists')
            # The first account bootstraps the workspace: admin and organizer.
            user_id = str(uuid4())
            connection.execute('INSERT INTO users (id,email,name,password_hash,role,is_admin,created_at) VALUES (?,?,?,?,?,?,?)',
                               (user_id, data.email, data.name.strip(), hash_password(data.password),
                                'organizer' if first else 'member', int(first), stamp()))
            user = to_user(user_row(connection, user_id))
            audit(connection, user, 'account_created', user_id, {'bootstrap_admin': first})
            if first:
                claim_orphans(connection, user_id)
            start_session(connection, response, user_id)
            return user.public()

    @router.post('/auth/login')
    def login(data: Credentials, response: Response):
        with connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            row = connection.execute('SELECT * FROM users WHERE email=?', (data.email,)).fetchone()
            if row and row['locked_until'] and row['locked_until'] > stamp():
                raise HTTPException(429, 'Too many failed sign-in attempts. Try again in a few minutes.')
            if not row or not row['active'] or not check_password(data.password, row['password_hash']):
                if row:
                    failures = row['failed_logins'] + 1
                    locked = stamp(now() + timedelta(minutes=LOCK_MINUTES)) if failures >= MAX_FAILURES else None
                    connection.execute('UPDATE users SET failed_logins=?, locked_until=? WHERE id=?',
                                       (0 if locked else failures, locked, row['id']))
                    connection.commit()
                raise HTTPException(401, 'Invalid email or password')
            connection.execute('UPDATE users SET failed_logins=0, locked_until=NULL WHERE id=?', (row['id'],))
            start_session(connection, response, row['id'])
            return to_user(row).public()

    @router.post('/auth/logout', status_code=204)
    def logout(request: Request, response: Response, user: User = Depends(current_user)):
        with connect() as connection:
            connection.execute('DELETE FROM sessions WHERE token_hash=?', (token_hash(request.cookies.get(COOKIE, '')),))
        response.delete_cookie(COOKIE, path='/')

    @router.get('/auth/me')
    def me(user: User = Depends(principal)):
        with connect() as connection:
            pending = connection.execute("SELECT id, reason, status, created_at, note FROM role_requests WHERE user_id=? "
                                         'ORDER BY created_at DESC LIMIT 1', (user.id,)).fetchone()
        return {**user.public(), 'token_scope': user.token_scope, 'organizer_request': dict(pending) if pending else None}

    @router.patch('/auth/me')
    def update_me(data: ProfileInput, request: Request, user: User = Depends(current_user)):
        with connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            row = user_row(connection, user.id)
            if data.new_password:
                if not check_password(data.current_password or '', row['password_hash']):
                    raise HTTPException(403, 'Current password is incorrect')
                connection.execute('UPDATE users SET password_hash=? WHERE id=?', (hash_password(data.new_password), user.id))
                # Keep this browser signed in; end every other session.
                connection.execute('DELETE FROM sessions WHERE user_id=? AND token_hash!=?',
                                   (user.id, token_hash(request.cookies.get(COOKIE, ''))))
                audit(connection, user, 'password_changed', user.id)
            if data.name:
                connection.execute('UPDATE users SET name=? WHERE id=?', (data.name, user.id))
            return public_row(user_row(connection, user.id))

    @router.post('/auth/organizer-request', status_code=201)
    def request_organizer(data: RoleRequestInput, user: User = Depends(current_user)):
        if user.organizer:
            raise HTTPException(409, 'You are already an organizer')
        with connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            if connection.execute("SELECT 1 FROM role_requests WHERE user_id=? AND status='pending'", (user.id,)).fetchone():
                raise HTTPException(409, 'You already have a pending organizer request')
            request_id = str(uuid4())
            connection.execute('INSERT INTO role_requests (id,user_id,reason,status,created_at) VALUES (?,?,?,?,?)',
                               (request_id, user.id, data.reason, 'pending', stamp()))
            audit(connection, user, 'organizer_requested', request_id, {'reason': data.reason})
            return dict(connection.execute('SELECT * FROM role_requests WHERE id=?', (request_id,)).fetchone())

    @router.get('/auth/tokens')
    def tokens(user: User = Depends(current_user)):
        with connect() as connection:
            return [dict(row) for row in connection.execute(
                'SELECT id, name, scope, created_at, expires_at, last_used_at, revoked FROM api_tokens '
                "WHERE user_id=? AND scope='capture' AND name NOT LIKE 'meet-bot:%' ORDER BY created_at DESC", (user.id,))]

    @router.post('/auth/tokens', status_code=201)
    def create_token(data: TokenInput, user: User = Depends(current_user)):
        if not user.organizer:
            raise HTTPException(403, 'Only organizers can create capture tokens')
        with connect() as connection:
            token = issue_token(connection, user.id, data.name)
            audit(connection, user, 'capture_token_created', None, {'name': data.name})
        return {'token': token, 'name': data.name, 'scope': 'capture',
                'note': 'Copy this token into the MeetMind extension now; it is not shown again.'}

    @router.delete('/auth/tokens/{token_id}', status_code=204)
    def delete_token(token_id: str, user: User = Depends(current_user)):
        with connect() as connection:
            changed = connection.execute('UPDATE api_tokens SET revoked=1 WHERE id=? AND user_id=?', (token_id, user.id)).rowcount
            if not changed:
                raise HTTPException(404, 'Token not found')
            audit(connection, user, 'capture_token_revoked', token_id)

    @router.get('/users/directory')
    def directory(user: User = Depends(current_user)):
        """Active accounts that an organizer can assign as owners or viewers."""
        with connect() as connection:
            return [{'id': row['id'], 'name': row['name'], 'email': row['email'], 'role': row['role']} for row in
                    connection.execute('SELECT id, name, email, role FROM users WHERE active=1 ORDER BY name COLLATE NOCASE')]

    @router.get('/admin/users')
    def users(admin: User = Depends(admin_user)):
        with connect() as connection:
            return [public_row(row) for row in connection.execute('SELECT * FROM users ORDER BY created_at')]

    @router.patch('/admin/users/{user_id}')
    def update_user(user_id: str, data: UserUpdate, admin: User = Depends(admin_user)):
        with connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            row = user_row(connection, user_id)
            changes = data.model_dump(exclude_none=True)
            removes_admin = row['is_admin'] and row['active'] and (changes.get('is_admin') is False or changes.get('active') is False)
            if removes_admin and active_admins(connection) <= 1:
                raise HTTPException(409, 'Keep at least one active admin')
            for key, value in changes.items():
                connection.execute(f'UPDATE users SET {key}=? WHERE id=?', (int(value) if isinstance(value, bool) else value, user_id))
            if changes.get('active') is False:
                connection.execute('DELETE FROM sessions WHERE user_id=?', (user_id,))
                connection.execute('UPDATE api_tokens SET revoked=1 WHERE user_id=?', (user_id,))
            if changes.get('role') == 'organizer':
                connection.execute("UPDATE role_requests SET status='approved', decided_by=?, decided_at=?, note=? "
                                   "WHERE user_id=? AND status='pending'", (admin.id, stamp(), 'Granted directly by admin', user_id))
            audit(connection, admin, 'user_updated', user_id, changes)
            return public_row(user_row(connection, user_id))

    @router.post('/admin/users/{user_id}/password', status_code=204)
    def reset_password(user_id: str, data: PasswordReset, admin: User = Depends(admin_user)):
        with connect() as connection:
            user_row(connection, user_id)
            connection.execute('UPDATE users SET password_hash=?, failed_logins=0, locked_until=NULL WHERE id=?',
                               (hash_password(data.password), user_id))
            connection.execute('DELETE FROM sessions WHERE user_id=?', (user_id,))
            audit(connection, admin, 'password_reset', user_id)

    @router.get('/admin/organizer-requests')
    def role_requests(status: str = 'pending', admin: User = Depends(admin_user)):
        with connect() as connection:
            return [dict(row) for row in connection.execute(
                'SELECT r.*, u.name, u.email FROM role_requests r JOIN users u ON u.id=r.user_id '
                'WHERE r.status=? OR ?=\'all\' ORDER BY r.created_at DESC', (status, status))]

    @router.post('/admin/organizer-requests/{request_id}')
    def decide(request_id: str, data: Decision, admin: User = Depends(admin_user)):
        with connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            row = connection.execute('SELECT * FROM role_requests WHERE id=?', (request_id,)).fetchone()
            if not row:
                raise HTTPException(404, 'Request not found')
            if row['status'] != 'pending':
                raise HTTPException(409, 'This request was already decided')
            connection.execute('UPDATE role_requests SET status=?, decided_by=?, decided_at=?, note=? WHERE id=?',
                               (data.decision, admin.id, stamp(), data.note, request_id))
            if data.decision == 'approved':
                connection.execute("UPDATE users SET role='organizer' WHERE id=?", (row['user_id'],))
            audit(connection, admin, 'organizer_request_' + data.decision, row['user_id'], {'request': request_id, 'note': data.note})
            return dict(connection.execute('SELECT * FROM role_requests WHERE id=?', (request_id,)).fetchone())

    @router.get('/admin/audit')
    def audit_log(limit: int = 200, admin: User = Depends(admin_user)):
        with connect() as connection:
            return [{**dict(row), 'detail': json.loads(row['detail']) if row['detail'] else None} for row in connection.execute(
                'SELECT a.*, u.email AS actor_email FROM audit_log a LEFT JOIN users u ON u.id=a.actor_id '
                'ORDER BY a.at DESC LIMIT ?', (min(max(limit, 1), 1000),))]

    @router.get('/admin/settings')
    def settings(admin: User = Depends(admin_user)):
        with connect() as connection:
            return {'signup_open': setting(connection, 'signup_open', True)}

    @router.patch('/admin/settings')
    def update_settings(data: SettingsInput, admin: User = Depends(admin_user)):
        with connect() as connection:
            connection.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', ('signup_open', json.dumps(data.signup_open)))
            audit(connection, admin, 'settings_updated', None, data.model_dump())
        return data.model_dump()

    return router
