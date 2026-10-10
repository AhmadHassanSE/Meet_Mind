"""Human review preserves extraction evidence and records every decision."""
from datetime import datetime, timezone
from copy import deepcopy
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class ReviewInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    revision: int = Field(ge=0)
    task: str = Field(min_length=1, max_length=1000)
    owner: str | None = Field(max_length=200)
    deadline: str | None = Field(max_length=200)
    decision: Literal['pending', 'approved', 'rejected']
    note: str = Field(default='', max_length=2000)


def initialize(meeting):
    for item in meeting.get('actions', []) + meeting.get('action_candidates', []):
        item.setdefault('id', str(uuid4()))
        item.setdefault('revision', 0)
        item.setdefault('review_status', 'pending')


def has_reviews(meeting):
    return any(item.get('review_history') for item in
               meeting.get('actions', []) + meeting.get('action_candidates', []))


def apply(meeting, item_id, data):
    for collection in ('actions', 'action_candidates'):
        item = next((item for item in meeting.get(collection, []) if item['id'] == item_id), None)
        if item is not None:
            break
    else:
        raise LookupError('Commitment not found')
    if item['revision'] != data.revision:
        raise RuntimeError('This item changed. Reload the meeting before reviewing it again.')
    if data.decision == 'approved' and item.get('kind') == 'cancellation':
        raise ValueError('A cancellation cannot be approved as a task. Review the affected commitment instead.')
    if data.decision == 'approved' and (
            item.get('original', item).get('status') == 'possible_cancellation') and not data.note:
        raise ValueError('Add a review note explaining the cancellation evidence before approving this task.')
    before = {key: deepcopy(item.get(key)) for key in
              ('task', 'owner', 'deadline', 'owner_method', 'status', 'review_status', 'needs_review')}
    if 'original' not in item:
        item['original'] = deepcopy(item)
    item.update(task=data.task, owner=data.owner or None, deadline=data.deadline or None,
                deadline_normalized=None, review_status=data.decision,
                needs_review=data.decision == 'pending', revision=item['revision'] + 1)
    item['owner_method'] = ('human_review' if item['owner'] != item['original'].get('owner')
                            else item['original'].get('owner_method', 'unresolved'))
    item['status'] = data.decision if data.decision != 'pending' else item['original'].get('status', 'proposed')
    after = {key: deepcopy(item.get(key)) for key in before}
    item.setdefault('review_history', []).append({
        'revision': item['revision'], 'at': datetime.now(timezone.utc).isoformat(),
        'decision': data.decision, 'note': data.note, 'before': before, 'after': after,
        'reviewer': 'local workspace user (identity not authenticated)'})
    if data.decision == 'approved' and collection == 'action_candidates':
        meeting[collection].remove(item)
        meeting.setdefault('actions', []).append(item)
    elif data.decision != 'approved' and collection == 'actions' and item.get('kind') in {'suggestion', 'request', 'cancellation'}:
        meeting[collection].remove(item)
        meeting.setdefault('action_candidates', []).append(item)
    meeting['commitment_revision'] = meeting.get('commitment_revision', 0) + 1
