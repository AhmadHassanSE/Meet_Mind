import pytest

from app import artifact_policy as p
from test_auth import app_db, assign, draft, meeting_with_item, team  # noqa: F401  (shared fixtures/helpers)

pytestmark = pytest.mark.real_auth  # approver rules need real, distinct accounts
FLOOR = 'allow channel email\nrequire approved_commitment\nrequire explicit_recipients\nrequire human_approval\n'


def policy(extra=''):
    return {'sha256': 'x', **{k: sorted(v) if isinstance(v, set) else v for k, v in p.parse(FLOOR + extra).items()}}


def email(to, **changes):
    return {'channel': 'email', 'to': to, 'subject': 'Follow-up', 'body': 'Body', **changes}


def test_parser_accepts_every_rule_with_comments():
    parsed = p.parse(FLOOR + 'allow channel jira\nallow domain Company.Example  # case-insensitive\n'
                     'deny domain rival.example\ninternal domain company.example\nmax recipients 3\n'
                     'require approver organizer\nrequire sender approver\nrequire second_approver for external_domain\n')
    assert parsed['channels'] == {'email', 'jira'} and parsed['allowed_domains'] == {'company.example'}
    assert parsed['max_recipients'] == 3 and parsed['approver'] == 'organizer' and parsed['sender'] == 'approver'
    assert parsed['second_approver_external'] and parsed['denied_domains'] == {'rival.example'}


@pytest.mark.parametrize('text,message', [
    (FLOOR + 'allow channel sms\n', 'line 5'),
    (FLOOR + 'deny domain not_a_domain\n', 'line 5'),
    (FLOOR + 'max recipients 0\n', 'line 5'),
    (FLOOR + 'require approver robot\n', 'line 5'),
    (FLOOR + 'execute python\n', 'line 5'),
    ('allow channel email\nrequire approved_commitment\n', 'must allow a channel'),
    (FLOOR + 'require second_approver for external_domain\n', 'internal domain'),
])
def test_unknown_or_unsafe_rules_fail_closed(text, message):
    with pytest.raises(ValueError, match=message):
        p.parse(text)


def test_each_rule_is_evaluated():
    assert p.evaluate(email(['a@company.example']), True, policy())['can_approve']
    assert 'Explicit recipients are required' in p.evaluate(email([]), True, policy())['violations']
    assert not p.evaluate(email(['a@company.example']), False, policy())['can_approve']
    assert 'blocked' in p.evaluate(email(['a@rival.example']), True, policy('deny domain rival.example\n'))['violations'][0]
    assert 'not permitted' in p.evaluate(email(['a@other.example']), True, policy('allow domain company.example\n'))['violations'][0]
    assert 'at most 2' in p.evaluate(email(['a@x.example', 'b@x.example', 'c@x.example']), True, policy('max recipients 2\n'))['violations'][0]
    assert 'jira is not permitted' in p.evaluate(email([], channel='jira'), True, policy())['violations'][0]
    assert 'required' in p.evaluate(email(['a@x.example'], body=' '), True, policy())['violations'][0]


def test_external_recipients_need_two_approvers():
    rules = policy('internal domain company.example\nrequire second_approver for external_domain\n')
    assert p.evaluate(email(['a@company.example', 'b@sub.company.example']), True, rules)['approvals_required'] == 1
    assert p.evaluate(email(['a@company.example', 'c@partner.example']), True, rules)['approvals_required'] == 2


def write_policy(app_db, extra):
    (app_db / 'policy.txt').write_text(FLOOR + extra)


def test_approver_rule_can_require_the_organizer(team, app_db):
    admin, _ = team['admin']
    sara, sara_user = team['sara']
    meeting_id = meeting_with_item(admin)
    assign(admin, meeting_id, sara_user['id'])
    record = draft(admin, meeting_id).json()
    write_policy(app_db, 'require approver organizer\n')
    # The linked owner may no longer decide; the organizer must.
    assert sara.post(f"/api/artifacts/{record['id']}/review", json={'revision': 1, 'decision': 'approved'}).status_code == 403
    approved = admin.post(f"/api/artifacts/{record['id']}/review", json={'revision': 1, 'decision': 'approved'}).json()
    assert approved['approval_valid'] and approved['approval']['admin_override'] is False


def test_second_approver_for_external_recipients(team, app_db):
    admin, admin_user = team['admin']
    sara, sara_user = team['sara']
    write_policy(app_db, 'internal domain example.com\nrequire second_approver for external_domain\n')
    meeting_id = meeting_with_item(admin)
    assign(admin, meeting_id, sara_user['id'])
    record = draft(admin, meeting_id).json()  # recipient sara@example.com is internal
    assert record['policy']['approvals_required'] == 1
    edited = admin.patch(f"/api/artifacts/{record['id']}", json={'revision': 1, 'to': ['sara@example.com', 'partner@vendor.example'],
                                                                 'subject': record['subject'], 'body': record['body']}).json()
    assert edited['policy']['approvals_required'] == 2
    first = sara.post(f"/api/artifacts/{record['id']}/review", json={'revision': 2, 'decision': 'approved'}).json()
    assert first['status'] == 'draft' and not first['approval_valid'] and first['partial_approvals'][0]['by'] == sara_user['id']
    assert sara.post(f"/api/artifacts/{record['id']}/review", json={'revision': 3, 'decision': 'approved'}).status_code == 409
    second = admin.post(f"/api/artifacts/{record['id']}/review", json={'revision': 3, 'decision': 'approved'}).json()
    assert second['status'] == 'approved' and second['approval_valid']
    assert [a['by'] for a in second['approval']['approvers']] == [sara_user['id'], admin_user['id']]
    assert second['approval']['admin_override'] is False


def test_editing_clears_a_partial_approval(team, app_db):
    admin, _ = team['admin']
    sara, sara_user = team['sara']
    write_policy(app_db, 'internal domain example.com\nrequire second_approver for external_domain\n')
    meeting_id = meeting_with_item(admin)
    assign(admin, meeting_id, sara_user['id'])
    record = draft(admin, meeting_id).json()
    body = {'subject': record['subject'], 'body': record['body'], 'to': ['partner@vendor.example']}
    admin.patch(f"/api/artifacts/{record['id']}", json={'revision': 1, **body})
    sara.post(f"/api/artifacts/{record['id']}/review", json={'revision': 2, 'decision': 'approved'})
    changed = admin.patch(f"/api/artifacts/{record['id']}", json={'revision': 3, **body, 'body': 'Changed body'}).json()
    assert changed['partial_approvals'] == [] and changed['status'] == 'draft'
    # The earlier partial approval does not count: the organizer cannot complete it alone.
    assert admin.post(f"/api/artifacts/{record['id']}/review", json={'revision': 4, 'decision': 'approved'}).status_code == 422
    after = sara.post(f"/api/artifacts/{record['id']}/review", json={'revision': 4, 'decision': 'approved'}).json()
    assert after['status'] == 'draft' and len(after['partial_approvals']) == 1
