"""Declarative follow-up policy: parsed rules, never executable code.

One rule per line; ``#`` starts a comment. Unknown or malformed rules fail closed.

    allow channel email|jira          channels drafts may use (at least one)
    require approved_commitment       } mandatory floor: these three must always be present
    require explicit_recipients       }
    require human_approval            }
    allow domain example.com          recipients must be in an allowed domain (if any are listed)
    deny domain example.org           recipients in a denied domain are always blocked
    internal domain example.com       domains treated as inside the organization
    max recipients 5                  upper bound on recipients per draft
    require approver owner|organizer  who decides: the item owner (default; organizer when no
                                      owner is linked) or always the meeting organizer
    require sender approver           execution must use the approver's own connected account
    require second_approver for external_domain
                                      a recipient outside the internal domains needs two
                                      different people to approve
"""
import hashlib
import os
import re
from pathlib import Path

DEFAULT = Path(__file__).parents[1]/'policies/followup.policy'
REQUIRED = {'approved_commitment', 'explicit_recipients', 'human_approval'}
CHANNELS = {'email', 'jira'}
DOMAIN = re.compile(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+')


def parse(text):
    policy = {'channels': set(), 'requirements': set(), 'allowed_domains': set(), 'denied_domains': set(),
              'internal_domains': set(), 'max_recipients': None, 'approver': 'owner', 'sender': 'any',
              'second_approver_external': False}
    for number, line in enumerate(text.splitlines(), 1):
        parts = line.split('#', 1)[0].strip().lower().split()
        if not parts:
            continue
        rule = ' '.join(parts)
        if len(parts) == 3 and parts[:2] == ['allow', 'channel'] and parts[2] in CHANNELS:
            policy['channels'].add(parts[2])
        elif len(parts) == 2 and parts[0] == 'require' and parts[1] in REQUIRED:
            policy['requirements'].add(parts[1])
        elif len(parts) == 3 and parts[1] == 'domain' and parts[0] in {'allow', 'deny', 'internal'} and DOMAIN.fullmatch(parts[2]):
            policy[{'allow': 'allowed_domains', 'deny': 'denied_domains', 'internal': 'internal_domains'}[parts[0]]].add(parts[2])
        elif len(parts) == 3 and parts[:2] == ['max', 'recipients'] and parts[2].isdigit() and 1 <= int(parts[2]) <= 50:
            policy['max_recipients'] = int(parts[2])
        elif len(parts) == 3 and parts[:2] == ['require', 'approver'] and parts[2] in {'owner', 'organizer'}:
            policy['approver'] = parts[2]
        elif rule == 'require sender approver':
            policy['sender'] = 'approver'
        elif rule == 'require second_approver for external_domain':
            policy['second_approver_external'] = True
        else:
            raise ValueError(f'Unknown follow-up policy rule on line {number}: {rule}')
    if not policy['channels'] or policy['requirements'] != REQUIRED:
        raise ValueError('Policy must allow a channel and require approved_commitment, explicit_recipients and human_approval')
    if policy['second_approver_external'] and not policy['internal_domains']:
        raise ValueError('A second approver for external recipients needs at least one "internal domain" rule')
    return policy


def load():
    text = Path(os.getenv('MEETMIND_ARTIFACT_POLICY', str(DEFAULT))).read_text(encoding='utf-8')
    policy = parse(text)
    return {'sha256': hashlib.sha256(text.encode()).hexdigest(),
            **{k: sorted(v) if isinstance(v, set) else v for k, v in policy.items()}}


def domain(address):
    return address.rsplit('@', 1)[-1].lower()


def external(address, policy):
    return not any(domain(address) == d or domain(address).endswith('.' + d) for d in policy['internal_domains'])


def evaluate(artifact, source_current, policy):
    """Every rule is checked here; ``can_approve`` is false while any violation remains."""
    reasons = []
    recipients = artifact.get('to', [])
    if artifact['channel'] not in policy['channels']:
        reasons.append(f"Channel {artifact['channel']} is not permitted by policy")
    # approved_commitment: the draft's source must still be the approved, unchanged commitment.
    if not source_current:
        reasons.append('Source commitment changed or is no longer approved; create a new draft')
    # explicit_recipients: people chose them; the model never does.
    if artifact['channel'] == 'email' and not recipients:
        reasons.append('Explicit recipients are required')
    allowed, denied = set(policy['allowed_domains']), set(policy['denied_domains'])
    if allowed and any(domain(a) not in allowed for a in recipients):
        reasons.append('Recipient domain is not permitted by policy')
    if any(domain(a) in denied for a in recipients):
        reasons.append('A recipient domain is blocked by policy')
    if policy['max_recipients'] and len(recipients) > policy['max_recipients']:
        reasons.append(f"Policy allows at most {policy['max_recipients']} recipients")
    if not artifact.get('subject', '').strip() or not artifact.get('body', '').strip():
        reasons.append('Subject and message body are required')
    needs_two = policy['second_approver_external'] and any(external(a, policy) for a in recipients)
    return {'sha256': policy['sha256'], 'can_approve': not reasons, 'requires_human_approval': True,
            'violations': reasons, 'approvals_required': 2 if needs_two else 1,
            'approver': policy['approver'], 'sender': policy['sender']}


def invalid(error):
    """Result used when the policy file cannot be read: nothing can be approved, but drafts stay visible."""
    return {'sha256': None, 'can_approve': False, 'requires_human_approval': True, 'approvals_required': 1,
            'approver': 'owner', 'sender': 'any', 'violations': [f'Follow-up policy is missing or invalid: {error}']}
