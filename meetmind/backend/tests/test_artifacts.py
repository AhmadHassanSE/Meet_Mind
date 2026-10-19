import json
from pathlib import Path
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from app import main,artifact_graph,artifact_policy,review


@pytest.fixture
def setup(tmp_path,monkeypatch):
    monkeypatch.setattr(main,'DB_PATH',tmp_path/'test.db')
    policy=tmp_path/'policy.txt'
    policy.write_text('allow channel email\nrequire approved_commitment\nrequire explicit_recipients\nrequire human_approval\n')
    monkeypatch.setenv('MEETMIND_ARTIFACT_POLICY',str(policy))
    calls=[]
    async def fake(context,url,model):
        calls.append(context)
        return json.dumps({'subject':'Project report follow-up','body':'Please send the project report by Friday.'})
    monkeypatch.setattr(artifact_graph,'ollama_draft',fake)
    with TestClient(main.app) as client:
        meeting=client.post('/api/meetings',json={'title':'Project sync','transcript':'Sara: I will send the project report by Friday.'}).json()
        meeting['actions']=[{'id':'commitment-1','revision':0,'task':'Send the project report','owner':'Sara',
            'deadline':'Friday','kind':'commitment','status':'proposed','needs_review':True,'source_id':1,
            'evidence':[{'quote':'I will send the project report by Friday.','source_ids':[1]}]}]
        main.save(meeting)
        yield client,meeting,calls,policy


def approve(client,meeting,**changes):
    item=client.get('/api/meetings/'+meeting['id']).json()['actions'][0]
    value=dict(revision=item['revision'],task=item['task'],owner=item['owner'],deadline=item['deadline'],decision='approved',note='')
    value.update(changes)
    result=client.post(f"/api/meetings/{meeting['id']}/commitments/commitment-1/review",json=value)
    assert result.status_code==200,result.text
    return result.json()['actions'][0]


def create(client,meeting,**changes):
    data={'commitment_id':'commitment-1','commitment_revision':1,'to':['sara@example.com'],'idempotency_key':str(uuid4())}
    data.update(changes)
    return client.post(f"/api/meetings/{meeting['id']}/artifacts",json=data)


def test_graph_draft_and_independent_approval_survive_reload(setup):
    client,meeting,calls,_=setup
    assert create(client,meeting,commitment_revision=0).status_code==409
    approve(client,meeting)
    result=create(client,meeting)
    assert result.status_code==201,result.text
    draft=result.json()
    assert draft['status']=='draft' and not draft['approval_valid']
    assert draft['graph_steps']==['draft_email','validate_email']
    assert calls[0]['task']=='Send the project report'
    assert draft['to']==['sara@example.com'] and draft['source']['evidence']
    approved=client.post(f"/api/artifacts/{draft['id']}/review",json={'revision':1,'decision':'approved'}).json()
    assert approved['approval_valid'] and approved['approval']['content_sha256']
    assert client.get('/api/artifacts/'+draft['id']).json()==approved
    assert client.get('/api/meetings/'+meeting['id']).json()['actions'][0]['revision']==1
    assert not any('sent'==e['action'] for e in approved['history'])


def test_idempotency_and_source_revision_conflicts(setup):
    client,meeting,calls,_=setup
    approve(client,meeting)
    assert create(client,meeting,commitment_revision=0).status_code==409
    key=str(uuid4())
    first=create(client,meeting,idempotency_key=key)
    second=create(client,meeting,idempotency_key=key)
    assert second.status_code==200 and first.json()['id']==second.json()['id']
    assert len(calls)==1
    assert create(client,meeting,idempotency_key=key,to=['other@example.com']).status_code==409


def test_edit_invalidates_approval_and_stale_writes_never_win(setup):
    client,meeting,_,_=setup
    approve(client,meeting)
    draft=create(client,meeting).json()
    approved=client.post(f"/api/artifacts/{draft['id']}/review",json={'revision':1,'decision':'approved'}).json()
    path='/api/artifacts/'+draft['id']
    edit={'revision':approved['revision'],'to':['new@example.com'],'subject':'Updated subject','body':'Please send the report.'}
    edited=client.patch(path,json=edit).json()
    assert edited['status']=='draft' and edited['approval'] is None and not edited['approval_valid']
    assert edited['original_generated']==draft['original_generated']
    assert client.patch(path,json=edit).status_code==409
    assert client.post(path+'/review',json={'revision':approved['revision'],'decision':'approved'}).status_code==409
    rejected=client.post(path+'/review',json={'revision':edited['revision'],'decision':'rejected'}).json()
    assert rejected['status']=='rejected' and not rejected['approval_valid']


def test_source_review_invalidates_approved_draft_in_same_transaction(setup):
    client,meeting,_,_=setup
    approve(client,meeting)
    draft=create(client,meeting).json()
    client.post(f"/api/artifacts/{draft['id']}/review",json={'revision':1,'decision':'approved'})
    approve(client,meeting,task='Send the amended report')
    updated=client.get('/api/artifacts/'+draft['id']).json()
    assert updated['status']=='source_changed' and updated['approval'] is None
    assert not updated['source_current'] and not updated['approval_valid']
    assert client.post(f"/api/artifacts/{draft['id']}/review",json={'revision':updated['revision'],'decision':'approved'}).status_code==409


def test_source_race_during_generation_does_not_save_an_approvable_draft(setup,monkeypatch):
    client,meeting,_,_=setup
    approve(client,meeting)
    async def changing(*args):
        main.review_commitment(meeting['id'],'commitment-1',review.ReviewInput(
            revision=1,task='Changed task',owner='Sara',deadline='Friday',decision='approved'))
        return json.dumps({'subject':'Old task','body':'Old draft'})
    monkeypatch.setattr(artifact_graph,'ollama_draft',changing)
    assert create(client,meeting).status_code==409
    record=client.get('/api/artifacts').json()[0]
    assert record['status']=='source_changed' and not record['approval_valid']


def test_invalid_llm_fields_fail_without_changing_source(setup,monkeypatch):
    client,meeting,_,_=setup
    approve(client,meeting)
    before=client.get('/api/meetings/'+meeting['id']).json()
    async def invalid(*args):return json.dumps({'subject':'Injected','body':'Text','to':['invented@example.com']})
    monkeypatch.setattr(artifact_graph,'ollama_draft',invalid)
    assert create(client,meeting).status_code==502
    assert client.get('/api/artifacts').json()[0]['status']=='failed'
    assert client.get('/api/meetings/'+meeting['id']).json()==before


def test_policy_change_revokes_validity_and_domain_rule_blocks_reapproval(setup):
    client,meeting,_,policy=setup
    approve(client,meeting)
    draft=create(client,meeting).json()
    client.post(f"/api/artifacts/{draft['id']}/review",json={'revision':1,'decision':'approved'})
    policy.write_text(policy.read_text()+'allow domain company.example\n')
    record=client.get('/api/artifacts/'+draft['id']).json()
    assert not record['approval_valid'] and not record['policy']['can_approve']
    assert client.post(f"/api/artifacts/{draft['id']}/review",json={'revision':2,'decision':'approved'}).status_code==409
    policy.write_text('allow channel email\nrequire approved_commitment\n')
    with pytest.raises(ValueError):artifact_policy.load()
    assert client.get('/api/artifacts').status_code==503


@pytest.mark.parametrize('to',[[],['Name <person@example.com>'],['a@example.com\r\nBcc:other@example.com'],
    ['a@example.com','A@example.com'],['a@foo..com'],['..a@example.com']])
def test_bad_recipients_rejected_before_generation(setup,to):
    client,meeting,calls,_=setup
    approve(client,meeting)
    assert create(client,meeting,to=to).status_code==422
    assert calls==[]


def test_restart_marks_incomplete_drafting_failed(setup):
    client,meeting,_,_=setup
    approve(client,meeting)
    draft=create(client,meeting).json()
    with main.connect() as c:
        draft['status']='drafting'
        c.execute('UPDATE artifacts SET payload=? WHERE id=?',(json.dumps(draft),draft['id']))
    main.artifact_service.recover()
    assert client.get('/api/artifacts/'+draft['id']).json()['status']=='failed'


def test_urdu_meet_capture_reaches_multilingual_core(setup,monkeypatch):
    from app.connectors import meet
    client,_,_,_=setup
    monkeypatch.setattr(meet,'ffmpeg_path',lambda:'ffmpeg')
    monkeypatch.setattr(meet.diarize,'enabled',lambda:False)
    seen=[]
    def transcribe(path,update,language='auto'):
        seen.append(language)
        return [{'id':1,'speaker':None,'text':'میں رپورٹ بھیج دوں گا۔','source':'میں رپورٹ بھیج دوں گا۔','start':0,'end':2}],{'duration':2}
    monkeypatch.setattr(meet,'transcribe_media',transcribe)
    session=client.post('/api/meet/sessions',json={'title':'Urdu sync','started_at_ms':1700000000000,'input_language':'ur'}).json()
    client.post('/api/meet/sessions/'+session['id']+'/audio?seq=0',content=b'fake-audio')
    job=client.post('/api/meet/sessions/'+session['id']+'/finish').json()
    import time
    for _ in range(100):
        job=client.get('/api/ingestion/jobs/'+job['id']).json()
        if job['status'] in {'completed','failed'}:break
        time.sleep(.02)
    assert job['status']=='completed'
    saved=client.get('/api/meetings/'+job['meeting_id']).json()
    assert seen==['ur'] and saved['language_profile']['effective']=='ur'
