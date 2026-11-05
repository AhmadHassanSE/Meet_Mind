# Accounts and roles

MeetMind is still a local, single-workspace service, but every API route except
`/api/health`, `/api/auth/config`, `/api/auth/signup` and `/api/auth/login` now
requires a signed-in user. `tests/test_auth.py` checks this for every route in
the OpenAPI schema.

## Roles

| Role | Scope | How it is granted |
|---|---|---|
| Admin | Workspace | First account created; later by another admin (`is_admin`) |
| Organizer | Account | A member requests it; an admin approves. An admin can also grant it directly |
| Member | Account | Default for every new account |
| Owner | One action item | An organizer links the item to a registered user (`assignments`) |

An admin can also be an organizer. The first account is both, so a single-user
demo works without extra setup.

| Action | Admin | Meeting organizer | Item owner | Member |
|---|---|---|---|---|
| View all meetings and drafts | Yes (each meeting view is audited) | Own meetings | Meetings with their items | Meetings they were added to as viewer |
| Create, upload or capture meetings (extension, bot) | Only with organizer role | Yes | No | No |
| Classify, extract, review commitments, assign owners, add members, delete meeting | No | Yes | No | No |
| Draft or edit a follow-up | No | Yes | Own items | No |
| Approve or reject a follow-up | Override with a required note (audited) | Only when the item has no owner | Own items | No |
| Manage users, organizer requests, settings, audit log | Yes | No | No | No |

The spoken `owner` text from the transcript stays as evidence. The linked owner
account is stored separately as `assignee`, chosen by a person. Extraction never
sets it. Changing the assignee changes who approves, so existing drafts for that
item lose their approval (`source_changed`).

Approvals record `approved_by`, and every history entry records `actor_id` and
`actor` (name and email). Model and system steps are labelled
`system (local workflow)`.

## Sessions and tokens

- Passwords: scrypt with a per-user salt, minimum 10 characters. Five failed
  sign-ins lock the account for five minutes.
- Browser sessions: a random token in an HttpOnly, SameSite=Strict cookie; only
  its SHA-256 hash is stored. Sessions last 7 days. Logout, deactivation and
  password resets delete them. Set `MEETMIND_COOKIE_SECURE=1` when serving over
  HTTPS.
- Requests that change data with a cookie session must send
  `X-Requested-With: meetmind`. Cross-site pages cannot add this header without
  CORS approval, which the backend never grants.
- Capture tokens (`mmt_…`): created under **Account**, scope `capture`, valid
  for 90 days and stored hashed. They can only use `/api/meet/sessions/*`, poll
  their own ingestion jobs and read `/api/auth/me`.
- The browser bot gets a capture token owned by the user who started it. The
  token expires 60 minutes after the bot's maximum duration and is revoked when
  the bot finishes.

## Setup and migration

1. Start the backend and open the UI. The first sign-up becomes admin and
   organizer.
2. Meetings created before accounts existed are assigned to the first admin as
   organizer, at sign-up and at every startup.
3. **Admin → Settings** can close open sign-up. New accounts are members until
   an admin approves their organizer request.

## API

| Route | Who |
|---|---|
| `POST /api/auth/signup`, `POST /api/auth/login`, `POST /api/auth/logout`, `GET/PATCH /api/auth/me` | Public / self |
| `POST /api/auth/organizer-request` | Member |
| `GET/POST/DELETE /api/auth/tokens` | Organizer (own tokens) |
| `GET /api/users/directory` | Any signed-in user (for owner pickers) |
| `PUT /api/meetings/{id}/commitments/{item}/assignee` | Meeting organizer |
| `GET/POST/DELETE /api/meetings/{id}/members` | View / meeting organizer |
| `DELETE /api/meetings/{id}` | Meeting organizer |
| `GET /api/artifacts?awaiting_me=true` | Drafts the caller must decide |
| `/api/admin/users`, `/api/admin/organizer-requests`, `/api/admin/audit`, `/api/admin/settings`, `POST /api/admin/meetings/{id}/organizer` | Admin |

## Not included yet

Single sign-on, email verification and email-based password reset (an admin
resets passwords), automatic 24-hour escalation, confidential meetings, and
multiple organizations per installation.
