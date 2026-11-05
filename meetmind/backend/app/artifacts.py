"""Persistent email drafts and separate revision-bound human approval."""
import asyncio
from copy import deepcopy
from datetime import datetime,timezone
import hashlib
import json
from typing import Annotated,Literal
from uuid import uuid4

import httpx
from fastapi import APIRouter,Depends,HTTPException,Response
from pydantic import BaseModel,ConfigDict,Field,AfterValidator,field_validator
import re
from . import artifact_graph,artifact_policy,auth


def now():return datetime.now(timezone.utc).isoformat()


def address(value):
    if not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,63}",value):
        raise ValueError('Enter a plain email address, without a display name or headers')
    local,domain=value.rsplit('@',1)
    if local.startswith('.') or local.endswith('.') or '..' in local or any(
            not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?',label) for label in domain.split('.')):
        raise ValueError('Invalid email address')
    return value


Address=Annotated[str,Field(min_length=3,max_length=254),AfterValidator(address)]


class Recipients(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    to:list[Address]=Field(min_length=1,max_length=10)

    @field_validator('to')
    @classmethod
    def unique(cls,value):
        if len({v.lower() for v in value})!=len(value):raise ValueError('Duplicate recipients')
        return value


class CreateInput(Recipients):
    commitment_id:str=Field(min_length=1,max_length=64)
    commitment_revision:int=Field(ge=0)
    idempotency_key:str=Field(min_length=8,max_length=128)


class EditInput(Recipients):
    revision:int=Field(ge=0)
    subject:str=Field(min_length=1,max_length=200)
    body:str=Field(min_length=1,max_length=8000)

    @field_validator('subject')
    @classmethod
    def subject_line(cls,value):
        if '\r' in value or '\n' in value:raise ValueError('Subject must be one line')
        return value


class DecisionInput(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    revision:int=Field(ge=0)
    decision:Literal['approved','rejected']
    note:str=Field(default='',max_length=2000)


def schema(connection):
    connection.execute('CREATE TABLE IF NOT EXISTS artifacts (id TEXT PRIMARY KEY, meeting_id TEXT NOT NULL, request_key TEXT UNIQUE NOT NULL, payload TEXT NOT NULL)')


def policy():
    try:return artifact_policy.load()
    except (OSError,ValueError) as error:
        raise HTTPException(503,'Follow-up policy is missing or invalid. Check the server policy configuration.') from error


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def content_hash(record):
    return digest({k:record[k] for k in ('channel','to','subject','body','source')})


def event(record,action,note='',user=None,**extra):
    record['updated_at']=now()
    record.setdefault('history',[]).append({'at':record['updated_at'],'action':action,
        'revision':record['revision'],'note':note,'content_sha256':content_hash(record),**auth.actor(user),**extra})


def rights(c,record,user):
    """Organizer or assigned owner may draft/edit; the owner (else organizer) decides."""
    meeting_access=auth.require_view(c,record['meeting_id'],user)
    owner=auth.assignee(c,record['meeting_id'],record['source']['commitment_id'])
    edit=meeting_access['can_organize'] or owner==user.id
    decide=owner==user.id if owner else meeting_access['can_organize']
    return {'can_edit':edit,'can_decide':decide,'assignee_id':owner,
            'can_override':user.is_admin and not decide}


def write(connection,record):
    connection.execute('UPDATE artifacts SET payload=? WHERE id=?',(json.dumps(record),record['id']))


def invalidate(connection,meeting_id,commitment_id):
    for row in connection.execute('SELECT payload FROM artifacts WHERE meeting_id=?',(meeting_id,)).fetchall():
        record=json.loads(row['payload'])
        if record['source']['commitment_id']==commitment_id and record['status'] not in {'source_changed','failed'}:
            record.update(status='source_changed',approval=None,revision=record['revision']+1)
            event(record,'source_changed','Source commitment reviewed again; prior draft approval invalidated')
            write(connection,record)


class Service:
    def __init__(self,connect,url,model_for):self.connect,self.url,self.model_for=connect,url,model_for

    def source(self,connection,meeting_id,item_id,revision=None):
        row=connection.execute('SELECT payload FROM meetings WHERE id=?',(meeting_id,)).fetchone()
        if not row:raise HTTPException(404,'Meeting not found')
        meeting=json.loads(row['payload'])
        item=next((i for i in meeting.get('actions',[]) if i.get('id')==item_id),None)
        if not item or item.get('review_status')!='approved' or item.get('kind')=='cancellation':
            raise HTTPException(409,'Approve the source commitment before drafting or approving its follow-up')
        if revision is not None and item.get('revision',0)!=revision:
            raise HTTPException(409,'Source commitment changed; reload the meeting')
        return meeting,item

    def view(self,connection,record,user=None):
        try:
            _,item=self.source(connection,record['meeting_id'],record['source']['commitment_id'],record['source']['revision'])
            current=digest({k:item.get(k) for k in ('task','owner','deadline','evidence')})==record['source']['fingerprint']
        except HTTPException:current=False
        result=deepcopy(record)
        result['source_current']=current
        result['policy']=artifact_policy.evaluate(record,current,policy())
        approval=record.get('approval')
        result['approval_valid']=bool(record['status']=='approved' and approval and current and
            approval['revision']==record['revision'] and
            result['policy']['can_approve'] and approval['policy_sha256']==result['policy']['sha256'] and
            approval['content_sha256']==content_hash(record))
        if user:result['rights']=rights(connection,record,user)
        return result

    def read(self,connection,artifact_id):
        row=connection.execute('SELECT payload FROM artifacts WHERE id=?',(artifact_id,)).fetchone()
        if not row:raise HTTPException(404,'Draft not found')
        return json.loads(row['payload'])

    async def create(self,meeting_id,data,response,user):
        # Resolve policy before spending model time; no external messaging occurs.
        policy()
        request_hash=digest({'meeting_id':meeting_id,**data.model_dump(exclude={'idempotency_key'})})
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            meeting_access=auth.require_view(c,meeting_id,user)
            if not (meeting_access['can_organize'] or auth.assignee(c,meeting_id,data.commitment_id)==user.id):
                raise HTTPException(403,'Only the meeting organizer or the item owner can draft its follow-up')
            duplicate=c.execute('SELECT payload FROM artifacts WHERE request_key=?',(data.idempotency_key,)).fetchone()
            if duplicate:
                record=json.loads(duplicate['payload'])
                if record['request_hash']!=request_hash:raise HTTPException(409,'This request key was used for different draft inputs')
                response.status_code=200
                return self.view(c,record,user)
            meeting,item=self.source(c,meeting_id,data.commitment_id,data.commitment_revision)
            source={'commitment_id':item['id'],'revision':item.get('revision',0),
                    'fingerprint':digest({k:item.get(k) for k in ('task','owner','deadline','evidence')}),
                    'task':item['task'],'owner':item.get('owner'),'deadline':item.get('deadline'),
                    'evidence':deepcopy(item.get('evidence',[]))}
            record={'id':str(uuid4()),'meeting_id':meeting_id,'meeting_title':meeting['title'],
                    'channel':'email','to':data.to,'subject':'','body':'','source':source,
                    'status':'drafting','revision':0,'approval':None,'created_at':now(),
                    'request_hash':request_hash,'model':self.model_for(meeting),'history':[]}
            event(record,'draft_requested',user=user)
            c.execute('INSERT INTO artifacts VALUES (?,?,?,?)',(record['id'],meeting_id,data.idempotency_key,json.dumps(record)))
        try:
            context={'meeting_title':meeting['title'],'task':source['task'],'owner':source['owner'],
                     'deadline':source['deadline'],'evidence':[{'quote':e.get('quote','')[:2000]} for e in source['evidence'][:3]]}
            email,steps=await artifact_graph.generate(context,self.url,record['model'])
            # Revalidate even if graph is supplied by a future adapter.
            email=artifact_graph.EmailText.model_validate(email).model_dump()
            with self.connect() as c:
                c.execute('BEGIN IMMEDIATE')
                latest=self.read(c,record['id'])
                if latest['status']!='drafting':raise HTTPException(409,'Source changed while drafting; create a new draft')
                self.source(c,meeting_id,data.commitment_id,data.commitment_revision)
                latest.update(**email,status='draft',graph_steps=steps,revision=1,original_generated=deepcopy(email))
                event(latest,'draft_generated')
                write(c,latest)
                return self.view(c,latest,user)
        except (Exception,asyncio.CancelledError) as error:
            with self.connect() as c:
                c.execute('BEGIN IMMEDIATE')
                latest=self.read(c,record['id'])
                if latest['status']=='drafting':
                    latest.update(status='failed',revision=latest['revision']+1)
                    event(latest,'draft_failed','Generation did not complete; create a new draft to retry')
                    write(c,latest)
            if isinstance(error,(HTTPException,asyncio.CancelledError)):raise
            if isinstance(error,(httpx.HTTPError,RuntimeError)):
                raise HTTPException(503,'Drafting unavailable. Check the local Ollama model and install the agents extra.') from error
            raise HTTPException(502,'The model returned an invalid draft. Source commitment and existing drafts were preserved.') from error

    def mutate(self,artifact_id,data,user,decision=False):
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            record=self.read(c,artifact_id)
            allowed=rights(c,record,user)
            if decision and not allowed['can_decide']:
                if not allowed['can_override']:
                    raise HTTPException(403,'Only the item owner (or the organizer when no owner is assigned) can decide this draft')
                if not data.note:raise HTTPException(422,'Admin override requires a note explaining the reason')
            if not decision and not allowed['can_edit']:
                raise HTTPException(403,'Only the meeting organizer or the item owner can edit this draft')
            if record['revision']!=data.revision:raise HTTPException(409,'Draft changed; reload before saving')
            if record['status'] not in {'draft','approved','rejected'}:raise HTTPException(409,'This draft cannot be edited or reviewed; create a new draft')
            if decision:
                viewed=self.view(c,record)
                if data.decision=='approved' and not viewed['policy']['can_approve']:
                    raise HTTPException(409,'; '.join(viewed['policy']['violations']))
                record.update(status=data.decision,revision=record['revision']+1,approval=None)
                override=not allowed['can_decide']
                if data.decision=='approved':record['approval']={'at':now(),'revision':record['revision'],
                    'content_sha256':content_hash(record),'policy_sha256':viewed['policy']['sha256'],
                    'approved_by':user.id,'approved_by_label':user.label,'admin_override':override}
                event(record,data.decision,data.note,user,admin_override=override)
                if override:auth.audit(c,user,'admin_override_'+data.decision,record['id'],{'note':data.note})
            else:
                record.update(**data.model_dump(exclude={'revision'}),status='draft',approval=None,revision=record['revision']+1)
                event(record,'edited','Editing requires a new approval',user)
            write(c,record)
            return self.view(c,record,user)

    def recover(self):
        with self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            for row in c.execute('SELECT payload FROM artifacts').fetchall():
                record=json.loads(row['payload'])
                if record['status']=='drafting':
                    record.update(status='failed',revision=record['revision']+1)
                    event(record,'draft_failed','Server restarted during generation; create a new draft')
                    write(c,record)


def build_router(service):
    router=APIRouter()

    @router.post('/api/meetings/{meeting_id}/artifacts',status_code=201)
    async def create(meeting_id:str,data:CreateInput,response:Response,user:auth.User=Depends(auth.current_user)):
        return await service.create(meeting_id,data,response,user)

    @router.get('/api/artifacts')
    def listing(meeting_id:str|None=None,awaiting_me:bool=False,user:auth.User=Depends(auth.current_user)):
        # awaiting_me: drafts this user is the designated decider for, not yet decided.
        with service.connect() as c:
            visible=auth.visible_meeting_ids(c,user)
            rows=c.execute('SELECT payload FROM artifacts'+(' WHERE meeting_id=?' if meeting_id else '')+' ORDER BY rowid DESC',
                           (meeting_id,) if meeting_id else ()).fetchall()
            views=[service.view(c,record,user) for record in map(lambda row:json.loads(row['payload']),rows)
                   if visible is None or record['meeting_id'] in visible]
            return [v for v in views if v['status']=='draft' and v['rights']['can_decide']] if awaiting_me else views

    @router.get('/api/artifacts/{artifact_id}')
    def get(artifact_id:str,user:auth.User=Depends(auth.current_user)):
        with service.connect() as c:
            record=service.read(c,artifact_id)
            try:auth.require_view(c,record['meeting_id'],user)
            except HTTPException:raise HTTPException(404,'Draft not found') from None
            return service.view(c,record,user)

    @router.patch('/api/artifacts/{artifact_id}')
    def edit(artifact_id:str,data:EditInput,user:auth.User=Depends(auth.current_user)):
        return service.mutate(artifact_id,data,user)

    @router.post('/api/artifacts/{artifact_id}/review')
    def review(artifact_id:str,data:DecisionInput,user:auth.User=Depends(auth.current_user)):
        return service.mutate(artifact_id,data,user,decision=True)

    return router
