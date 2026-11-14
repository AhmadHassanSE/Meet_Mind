"""Meeting workflow: one LangGraph run per meeting, paused for each human decision.

    extract -> await_review (pause) -> draft -> policy_check -> await_approval (pause, repeats) -> execute

The graph only calls the existing services, which keep enforcing roles, revisions,
explicit recipients and policy. It never approves anything: the organizer resumes it
after reviewing commitments (choosing recipients), and item owners decide drafts in
the approval queue. Execution uses only drafts whose approval is still valid. Graph
state is checkpointed in SQLite, so a paused or failed run survives a restart and is
retried from its last completed step.
"""
from datetime import datetime, timezone
import asyncio
import json
import logging
from typing import TypedDict

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from . import artifacts, auth, review

SCHEMA = 'CREATE TABLE IF NOT EXISTS workflows (meeting_id TEXT PRIMARY KEY, payload TEXT NOT NULL)'
STAGES = ['extract', 'await_review', 'draft', 'policy_check', 'await_approval', 'execute', 'completed']
MAX_DRAFT_ATTEMPTS = 5


def now():
    return datetime.now(timezone.utc).isoformat()


class FollowUp(artifacts.Recipients):
    commitment_id: str = Field(min_length=1, max_length=64)


class ResumeInput(BaseModel):
    """The organizer's decision after commitment review: which items get a follow-up, to whom."""
    model_config = ConfigDict(extra='forbid')
    follow_ups: list[FollowUp] = Field(default_factory=list, max_length=50)

    @field_validator('follow_ups')
    @classmethod
    def unique(cls, value):
        if len({f.commitment_id for f in value}) != len(value):
            raise ValueError('Each commitment can have one follow-up per workflow run')
        return value


class State(TypedDict, total=False):
    meeting_id: str
    actor_id: str
    follow_ups: list
    drafts: list


async def not_connected(draft):
    return {'status': 'not_configured', 'detail': f"No {draft['channel']} connector is configured; nothing was sent."}


class WorkflowService:
    def __init__(self, connect, checkpoint_path, extract, artifact_service, executors=None):
        self.connect, self.checkpoint_path = connect, checkpoint_path
        self.extract, self.artifacts = extract, artifact_service
        self.executors = executors if executors is not None else {}
        self.tasks = {}

    # UI-facing status record; graph state itself lives in the checkpointer.

    def read(self, meeting_id):
        with self.connect() as c:
            row = c.execute('SELECT payload FROM workflows WHERE meeting_id=?', (meeting_id,)).fetchone()
        return json.loads(row['payload']) if row else None

    def update(self, meeting_id, event=None, actor=None, **fields):
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT payload FROM workflows WHERE meeting_id=?', (meeting_id,)).fetchone()
            record = json.loads(row['payload']) if row else {'meeting_id': meeting_id, 'run': 0, 'history': []}
            record.update(fields, updated_at=now())
            if event:
                record['history'] = (record['history'] + [{'at': record['updated_at'], 'event': event,
                                                           'stage': record.get('stage'), **auth.actor(actor)}])[-100:]
            c.execute('INSERT OR REPLACE INTO workflows VALUES (?,?)', (meeting_id, json.dumps(record)))
            return record

    def recover(self):
        with self.connect() as c:
            ids = [row['meeting_id'] for row in c.execute('SELECT meeting_id FROM workflows')]
        for meeting_id in ids:
            if (self.read(meeting_id) or {}).get('status') == 'running':
                self.update(meeting_id, 'interrupted_by_restart', status='failed',
                            error='The backend restarted during this step. Retry to continue from the last completed step.')

    def meeting(self, meeting_id):
        with self.connect() as c:
            row = c.execute('SELECT payload FROM meetings WHERE id=?', (meeting_id,)).fetchone()
        if not row:
            raise HTTPException(404, 'Meeting was deleted')
        return json.loads(row['payload'])

    def draft_view(self, draft_id):
        with self.connect() as c:
            return self.artifacts.view(c, self.artifacts.read(c, draft_id))

    def pending(self, draft_ids):
        """Drafts still needing a valid decision; edits or policy changes put drafts back here."""
        result = []
        for draft_id in draft_ids:
            view = self.draft_view(draft_id)
            if view['status'] in {'drafting', 'draft'} or (view['status'] == 'approved' and not view['approval_valid']):
                result.append(draft_id)
        return result

    # Graph

    def build(self):
        from langgraph.graph import END, START, StateGraph
        from langgraph.types import interrupt

        async def extract(state):
            meeting_id = state['meeting_id']
            self.update(meeting_id, stage='extract')
            meeting = self.meeting(meeting_id)
            # Never overwrite reviewed decisions; a later run reuses the existing extraction.
            if review.has_reviews(meeting) or meeting.get('status') == 'extracted':
                self.update(meeting_id, 'extraction_reused')
            else:
                await self.extract(meeting_id)
                self.update(meeting_id, 'extracted')
            return {}

        def await_review(state):
            self.update(state['meeting_id'], stage='await_review')
            decision = interrupt({'waiting_for': 'commitment_review'})
            return {'follow_ups': decision['follow_ups'], 'actor_id': decision['actor_id']}

        async def draft(state):
            meeting_id = state['meeting_id']
            self.update(meeting_id, stage='draft')
            with self.connect() as c:
                user = auth.load_user(c, state['actor_id'])
            if user is None:
                raise HTTPException(409, 'The organizer who requested the drafts is no longer active')
            items = {i['id']: i for i in self.meeting(meeting_id).get('actions', [])}
            run = self.read(meeting_id)['run']
            drafts = []
            for follow_up in state['follow_ups']:
                item = items.get(follow_up['commitment_id'])
                if not item or item.get('review_status') != 'approved':
                    self.update(meeting_id, 'draft_skipped_unapproved_commitment')
                    continue
                # Retries reuse earlier drafts through their idempotency key; a failed
                # generation moves on to a fresh key instead of returning the failure.
                for attempt in range(MAX_DRAFT_ATTEMPTS):
                    data = artifacts.CreateInput(commitment_id=item['id'], commitment_revision=item.get('revision', 0),
                                                 to=follow_up['to'], idempotency_key=f"wf-{meeting_id}-{run}-{item['id']}-{attempt}")
                    record = await self.artifacts.create(meeting_id, data, Response(), user)
                    if record['status'] != 'failed':
                        break
                drafts.append(record['id'])
            self.update(meeting_id, 'drafts_created', drafts=drafts)
            return {'drafts': drafts}

        def policy_check(state):
            meeting_id = state['meeting_id']
            self.update(meeting_id, stage='policy_check')
            policy = {draft_id: self.draft_view(draft_id)['policy']['violations'] for draft_id in state['drafts']}
            self.update(meeting_id, 'policy_checked', policy=policy)
            return {}

        def await_approval(state):
            self.update(state['meeting_id'], stage='await_approval')
            pending = self.pending(state['drafts'])
            if pending:
                interrupt({'waiting_for': 'draft_approval', 'pending': pending})
            return {}

        async def execute(state):
            meeting_id = state['meeting_id']
            self.update(meeting_id, stage='execute')
            deliveries = {}
            for draft_id in state['drafts']:
                view = self.draft_view(draft_id)
                if (view.get('delivery') or {}).get('status') == 'sent':
                    deliveries[draft_id] = view['delivery']  # never send twice
                    continue
                if view['status'] != 'approved' or not view['approval_valid']:
                    deliveries[draft_id] = {'status': 'skipped', 'detail': f"Draft is {view['status']}; nothing was sent."}
                    continue
                delivery = await self.executors.get(view['channel'], not_connected)(view)
                self.artifacts.record_delivery(draft_id, delivery)
                deliveries[draft_id] = delivery
            self.update(meeting_id, 'executed', deliveries=deliveries)
            return {}

        graph = StateGraph(State)
        for name, node in [('extract', extract), ('await_review', await_review), ('draft', draft),
                           ('policy_check', policy_check), ('await_approval', await_approval), ('execute', execute)]:
            graph.add_node(name, node)
        graph.add_edge(START, 'extract')
        graph.add_edge('extract', 'await_review')
        graph.add_conditional_edges('await_review', lambda s: 'draft' if s.get('follow_ups') else END, ['draft', END])
        graph.add_edge('draft', 'policy_check')
        graph.add_edge('policy_check', 'await_approval')
        graph.add_conditional_edges('await_approval', lambda s: 'await_approval' if self.pending(s['drafts']) else 'execute',
                                    ['await_approval', 'execute'])
        graph.add_edge('execute', END)
        return graph

    # Running

    async def run(self, meeting_id, value):
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        config = {'configurable': {'thread_id': f"{meeting_id}:{self.read(meeting_id)['run']}"}}
        try:
            async with AsyncSqliteSaver.from_conn_string(str(self.checkpoint_path())) as saver:
                result = await self.build().compile(checkpointer=saver).ainvoke(value, config)
        except Exception as error:
            logging.exception('Workflow for meeting %s failed', meeting_id)
            detail = error.detail if isinstance(error, HTTPException) else 'Unexpected error; check the server log, then retry.'
            if (self.read(meeting_id) or {}).get('status') is not None:
                self.update(meeting_id, 'failed', status='failed', error=str(detail))
            return
        finally:
            self.tasks.pop(meeting_id, None)
        if result.get('__interrupt__'):
            waiting = result['__interrupt__'][0].value
            self.update(meeting_id, 'waiting_for_' + waiting['waiting_for'], status='waiting', waiting_for=waiting, error=None)
        else:
            self.update(meeting_id, 'completed', status='completed', stage='completed', waiting_for=None, error=None)

    def launch(self, meeting_id, value, event, actor=None):
        if meeting_id in self.tasks:
            raise HTTPException(409, 'The workflow is already running for this meeting')
        self.update(meeting_id, event, actor, status='running', waiting_for=None, error=None)
        self.tasks[meeting_id] = asyncio.create_task(self.run(meeting_id, value), name='meetmind-workflow-' + meeting_id)

    def start(self, meeting_id, user):
        record = self.read(meeting_id)
        if record and record.get('status') in {'running', 'waiting'}:
            raise HTTPException(409, 'A workflow is already in progress for this meeting')
        run = (record or {}).get('run', 0) + 1
        self.update(meeting_id, run=run, stage='extract', drafts=[], deliveries={}, policy={}, started_by=user.id, started_at=now())
        self.launch(meeting_id, {'meeting_id': meeting_id, 'follow_ups': [], 'drafts': []}, 'started', user)

    def resume(self, meeting_id, data, user):
        from langgraph.types import Command
        record = self.read(meeting_id)
        if not record or record.get('status') != 'waiting' or record['waiting_for']['waiting_for'] != 'commitment_review':
            raise HTTPException(409, 'The workflow is not waiting for commitment review')
        approved = {i['id'] for i in self.meeting(meeting_id).get('actions', [])
                    if i.get('review_status') == 'approved' and i.get('kind') != 'cancellation'}
        unknown = [f.commitment_id for f in data.follow_ups if f.commitment_id not in approved]
        if unknown:
            raise HTTPException(409, 'Approve these commitments before requesting follow-ups: ' + ', '.join(unknown))
        payload = {'follow_ups': [f.model_dump() for f in data.follow_ups], 'actor_id': user.id}
        self.launch(meeting_id, Command(resume=payload),
                    'review_completed' if data.follow_ups else 'review_completed_without_follow_ups', user)

    def retry(self, meeting_id, user):
        record = self.read(meeting_id)
        if not record or record.get('status') != 'failed':
            raise HTTPException(409, 'Only a failed workflow can be retried')
        self.launch(meeting_id, None, 'retried', user)

    async def check(self, meeting_id, user=None):
        """Re-evaluate the approval pause; called after every draft decision."""
        from langgraph.types import Command
        record = self.read(meeting_id)
        if (record and record.get('status') == 'waiting' and meeting_id not in self.tasks
                and record['waiting_for']['waiting_for'] == 'draft_approval'):
            self.launch(meeting_id, Command(resume=True), 'approval_checked', user)

    def view(self, meeting_id, user):
        with self.connect() as c:
            access = auth.require_view(c, meeting_id, user)
        record = self.read(meeting_id) or {'meeting_id': meeting_id, 'status': 'not_started', 'history': []}
        drafts = []
        for draft_id in record.get('drafts', []):
            try:
                view = self.draft_view(draft_id)
            except HTTPException:
                continue
            drafts.append({key: view.get(key) for key in ('id', 'status', 'subject', 'to', 'approval_valid', 'delivery')}
                          | {'task': view['source']['task']})
        return {**record, 'stages': STAGES, 'drafts': drafts, 'can_control': access['can_organize']}


def build_router(service):
    router = APIRouter(prefix='/api/meetings/{meeting_id}/workflow')

    def organize(meeting_id, user):
        with service.connect() as c:
            auth.require_organize(c, meeting_id, user)

    @router.get('')
    def status(meeting_id: str, user: auth.User = Depends(auth.current_user)):
        return service.view(meeting_id, user)

    @router.post('', status_code=202)
    async def start(meeting_id: str, user: auth.User = Depends(auth.current_user)):
        organize(meeting_id, user)
        service.start(meeting_id, user)
        return service.view(meeting_id, user)

    @router.post('/resume', status_code=202)
    async def resume(meeting_id: str, data: ResumeInput, user: auth.User = Depends(auth.current_user)):
        organize(meeting_id, user)
        service.resume(meeting_id, data, user)
        return service.view(meeting_id, user)

    @router.post('/retry', status_code=202)
    async def retry(meeting_id: str, user: auth.User = Depends(auth.current_user)):
        organize(meeting_id, user)
        service.retry(meeting_id, user)
        return service.view(meeting_id, user)

    @router.post('/check', status_code=202)
    async def check(meeting_id: str, user: auth.User = Depends(auth.current_user)):
        organize(meeting_id, user)
        await service.check(meeting_id, user)
        return service.view(meeting_id, user)

    return router
