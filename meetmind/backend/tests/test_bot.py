import asyncio
import base64
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from app import main
from app.connectors import bot, meet


class FakeBrowser:
    instances=[]
    wait_login=False
    tracks=1
    peak=40
    fail=False
    def __init__(self,profile):
        self.closed=False
        self.instances.append(self)
    async def open(self,url,on_chunk):
        self.on_chunk=on_chunk
        if self.fail:raise RuntimeError('Browser launch failed')
    async def join(self,name,control,update,timeout):
        if self.wait_login:
            update('needs_login','Manual sign-in needed')
            while not control.resume.is_set():
                if control.cancel.is_set() or control.stop.is_set():raise bot.BotCancelled()
                await asyncio.sleep(.01)
        update('waiting_for_admission','Waiting for host')
    async def start_capture(self):pass
    async def ended(self):return False
    async def tick(self):return {'stats':{'remote_tracks':self.tracks,'peak':self.peak},'hints':[]}
    async def stop_capture(self):
        await self.on_chunk(base64.b64encode(b'fake-webm').decode())
        return {'remote_tracks':self.tracks,'bytes':9,'chunks':1,'peak':self.peak},[]
    async def close(self):self.closed=True


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(main,'DB_PATH',tmp_path/'bot.db')
    monkeypatch.setattr(main.bot_manager,'driver_factory',FakeBrowser)
    monkeypatch.setattr(main.bot_manager,'capabilities',lambda:{'playwright_installed':True})
    monkeypatch.setattr(bot,'ffmpeg_path',lambda:'ffmpeg')
    monkeypatch.setattr(meet,'ffmpeg_path',lambda:'ffmpeg')
    FakeBrowser.instances=[];FakeBrowser.wait_login=False;FakeBrowser.tracks=1;FakeBrowser.fail=False
    FakeBrowser.peak=40
    def transcribe(path,update):
        return [{'id':1,'speaker':None,'text':'I will send the report.','source':'I will send the report.','start':0,'end':2}],{'duration':2}
    monkeypatch.setattr(meet,'transcribe_media',transcribe)
    monkeypatch.setattr(meet.diarize,'enabled',lambda:False)
    with TestClient(main.app) as client:yield client


def input_data(**changes):
    return {'title':'Bot fixture','meeting_url':'https://meet.google.com/abc-defg-hij','consent_confirmed':True,**changes}


def await_state(client,bot_id,states):
    for attempt in range(200):
        record=client.get('/api/meet/bots/'+bot_id).json()
        if record['state'] in states:return record
        time.sleep(.02)
    pytest.fail('Bot did not reach '+str(states)+': '+str(record))


@pytest.mark.parametrize('url',['http://meet.google.com/abc-defg-hij','https://evil.example/abc-defg-hij',
    'https://meet.google.com.evil.example/abc-defg-hij','https://meet.google.com/abc-defg-hij?redirect=https://evil.example',
    'https://meet.google.com:444/abc-defg-hij','file:///secret','https://meet.google.com/../../../secret'])
def test_only_meet_links_are_accepted(client,url):
    assert client.post('/api/meet/bots',json=input_data(meeting_url=url)).status_code==422


def test_recording_requires_confirmation_and_bounded_duration(client):
    assert client.post('/api/meet/bots',json=input_data(consent_confirmed=False)).status_code==422
    assert client.post('/api/meet/bots',json=input_data(max_duration_minutes=121)).status_code==422
    assert client.post('/api/meet/bots',json=input_data(title=' ')).status_code==422


def test_complete_capture_uses_shared_transcription_and_provenance(client):
    result=client.post('/api/meet/bots',json=input_data())
    assert result.status_code==201
    bot_id=result.json()['id']
    await_state(client,bot_id,{'recording'})
    assert client.post('/api/meet/bots',json=input_data()).status_code==429
    assert client.post('/api/meet/bots/'+bot_id+'/stop').status_code==200
    record=await_state(client,bot_id,{'completed'})
    assert record['uploaded_chunks']==1
    meeting=client.get('/api/meetings/'+record['meeting_id']).json()
    assert meeting['source_type']=='google_meet' and meeting['capture_method']=='browser_bot'
    assert meeting['bot_id']==bot_id
    assert FakeBrowser.instances[0].closed
    assert client.post('/api/meet/bots/'+bot_id+'/stop').status_code==409


def test_manual_login_cancel_and_cleanup(client):
    FakeBrowser.wait_login=True
    bot_id=client.post('/api/meet/bots',json=input_data()).json()['id']
    await_state(client,bot_id,{'needs_login'})
    assert client.post('/api/meet/bots/'+bot_id+'/cancel').status_code==200
    await_state(client,bot_id,{'cancelled'})
    assert FakeBrowser.instances[0].closed
    assert client.get('/api/meetings').json()==[]


def test_resume_after_manual_login(client):
    FakeBrowser.wait_login=True
    bot_id=client.post('/api/meet/bots',json=input_data()).json()['id']
    await_state(client,bot_id,{'needs_login'})
    client.post('/api/meet/bots/'+bot_id+'/resume')
    await_state(client,bot_id,{'recording'})
    assert client.post('/api/meet/bots/'+bot_id+'/resume').status_code==409
    client.post('/api/meet/bots/'+bot_id+'/cancel')
    await_state(client,bot_id,{'cancelled'})


def test_capture_without_remote_tracks_fails_instead_of_fake_success(client):
    FakeBrowser.tracks=0
    bot_id=client.post('/api/meet/bots',json=input_data()).json()['id']
    await_state(client,bot_id,{'recording'})
    client.post('/api/meet/bots/'+bot_id+'/stop')
    record=await_state(client,bot_id,{'failed'})
    assert 'No incoming' in record['message']
    assert client.get('/api/meetings').json()==[]
    assert not meet.sessions


def test_silent_tracks_report_diagnosis_and_never_queue_transcription(client):
    FakeBrowser.peak=0
    bot_id=client.post('/api/meet/bots',json=input_data()).json()['id']
    for _ in range(200):
        record=client.get('/api/meet/bots/'+bot_id).json()
        if record.get('capture_stats',{}).get('peak')==0:break
        time.sleep(.01)
    assert record['capture_stats']['peak']==0
    client.post('/api/meet/bots/'+bot_id+'/stop')
    record=await_state(client,bot_id,{'failed'})
    assert 'silent audio throughout' in record['message']
    assert not record.get('job_id')
    assert not meet.sessions
    assert client.get('/api/meetings').json()==[]


def test_launch_failure_and_missing_runtime(client,monkeypatch):
    FakeBrowser.fail=True
    bot_id=client.post('/api/meet/bots',json=input_data()).json()['id']
    await_state(client,bot_id,{'failed'})
    monkeypatch.setattr(main.bot_manager,'capabilities',lambda:{'playwright_installed':False})
    assert client.post('/api/meet/bots',json=input_data()).status_code==503


def test_restart_retains_terminal_results_and_fails_orphaned_browser(client):
    bot_id=client.post('/api/meet/bots',json=input_data()).json()['id']
    await_state(client,bot_id,{'recording'})
    client.post('/api/meet/bots/'+bot_id+'/cancel')
    await_state(client,bot_id,{'cancelled'})
    main.bot_manager.update(bot_id,'recording','Orphaned browser fixture')
    main.bot_manager.recover()
    record=client.get('/api/meet/bots/'+bot_id).json()
    assert record['state']=='failed' and 'restarted' in record['message']
    assert client.get('/api/meet/bots/not-a-bot').status_code==404
