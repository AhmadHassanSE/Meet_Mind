"""Small declarative follow-up policy: parsed rules, never executable code."""
import hashlib
import os
from pathlib import Path

DEFAULT = Path(__file__).parents[1]/'policies/followup.policy'
REQUIRED = {'approved_commitment','explicit_recipients','human_approval'}


def load():
    text = Path(os.getenv('MEETMIND_ARTIFACT_POLICY', str(DEFAULT))).read_text(encoding='utf-8')
    channels, requirements, domains = set(), set(), set()
    for line in text.splitlines():
        parts = line.split('#',1)[0].strip().split()
        if not parts:continue
        if parts == ['allow','channel','email']:channels.add('email')
        elif len(parts)==2 and parts[0]=='require' and parts[1] in REQUIRED:requirements.add(parts[1])
        elif len(parts)==3 and parts[:2]==['allow','domain'] and all(c.isalnum() or c in '.-' for c in parts[2]):
            domains.add(parts[2].lower())
        else:raise ValueError('Unknown follow-up policy rule: '+ ' '.join(parts))
    if not channels or requirements != REQUIRED:
        raise ValueError('Policy must permit email and require approved commitments, explicit recipients and human approval')
    return {'sha256':hashlib.sha256(text.encode()).hexdigest(), 'channels':sorted(channels),
            'requirements':sorted(requirements),'allowed_domains':sorted(domains)}


def evaluate(artifact, source_current, policy):
    reasons=[]
    if artifact['channel'] not in policy['channels']:reasons.append('Channel is not permitted')
    if not source_current:reasons.append('Source commitment changed or is no longer approved; create a new draft')
    if not artifact.get('to'):reasons.append('Explicit recipients are required')
    allowed=set(policy['allowed_domains'])
    if allowed and any(address.rsplit('@',1)[-1].lower() not in allowed for address in artifact.get('to',[])):
        reasons.append('Recipient domain is not permitted by policy')
    if not artifact.get('subject','').strip() or not artifact.get('body','').strip():
        reasons.append('Subject and message body are required')
    return {'sha256':policy['sha256'],'can_approve':not reasons,'requires_human_approval':True,
            'violations':reasons}
