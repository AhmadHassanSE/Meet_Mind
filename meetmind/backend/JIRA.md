# Jira tickets

An approved commitment can become a **Jira Cloud task**. It follows the same path as email: draft, approval of the exact content, then execution exactly once.

## How it works

1. **An admin connects the site** under **Admin → Jira** with:
   - the site address (`https://<team>.atlassian.net`);
   - an Atlassian account email;
   - an **API token**;
   - the default **project key**.

   MeetMind checks the token (`/rest/api/3/myself`) and the project before saving. The token is encrypted at rest and never returned.
2. **Match users by email.** Each active MeetMind user is mapped to the Jira account with the same email, but only when exactly one account matches. Unmatched users stay unassigned. A person can re-run the match at any time.
3. **Draft a ticket**, either from a follow-up in the meeting workflow (tick *Jira ticket*) or from **Follow-up drafts** (choose *Jira ticket*).
   - Ollama writes the summary and description (`draft_ticket → validate_ticket` LangGraph nodes).
   - **The project and the assignee are fixed when the draft is created.** The assignee is the Jira account of the item's human-linked owner; the model never chooses it.
   - These fields are part of the approved content hash, so changing the owner invalidates the draft.
4. **Approval** follows the policy. The policy must contain `allow channel jira`, otherwise approval is blocked. The approver is normally the item owner.
5. **Execution** happens from the workflow or with **Create issue now**:
   - MeetMind creates the issue (`POST /rest/api/3/issue`, issue type *Task*, description in Atlassian Document Format) and stores the issue key and link.
   - A repeated request returns the same issue; no second issue is created.
   - Temporary errors (429 and 5xx) are retried up to 3 times. Other errors are reported with Jira's message.
   - If the site or project changed after approval, nothing is created and the draft must be re-drafted.

## API

| Route | Who |
|---|---|
| `GET /api/integrations/jira` | Signed-in users (status and user mapping; no secrets) |
| `POST /api/integrations/jira` | Admin: `{base_url, email, api_token, project_key}` |
| `POST /api/integrations/jira/sync-users` | Admin |
| `DELETE /api/integrations/jira` | Admin |
| `POST /api/meetings/{id}/artifacts` with `"channel": "jira"` | Meeting organizer or item owner |

## Setup for a live check

1. Create a free Jira Cloud site and a project (for example key `MEET`).
2. Create an API token at <https://id.atlassian.com/manage-profile/security/api-tokens>.
3. Add `allow channel jira` to `policies/followup.policy`.
4. Connect under **Admin → Jira**, then press **Match users by email**.

## Tests

`tests/test_jira.py` simulates Jira Cloud. It covers:
- admin-only connection, site validation and a wrong token or project;
- the encrypted token;
- mapping users only when exactly one account matches;
- a ticket requiring a connected site and having no email recipients;
- an owner-approved ticket created once with the linked assignee and the right description format;
- the policy channel rule;
- a refused issue and a site that changed after approval;
- a Jira follow-up through the meeting workflow.

A live issue on a real site still has to be created and recorded once a site exists.
