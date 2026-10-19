"""Persistent bot control plane; shared extension/Whisper ingestion underneath."""
import asyncio
import base64
from dataclasses import dataclass, field
from datetime import datetime, timezone
import importlib.util
import json
import logging
import os
from pathlib import Path
import re
import time
from uuid import uuid4

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .bot_browser import BrowserBot, BotCancelled
from ..media import ffmpeg_path
from ..languages import Language

TERMINAL = {'completed','failed','cancelled'}
PROFILE = Path(os.getenv('MEETMIND_BOT_PROFILE', str(Path(__file__).parents[2]/'.bot-profile')))


def now():
    return datetime.now(timezone.utc).isoformat()


class BotInput(BaseModel):
    input_language: Language = 'auto'
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    title: str = Field(min_length=1,max_length=200)
    meeting_url: str = Field(max_length=200)
    display_name: str = Field(default='MeetMind Notetaker',min_length=1,max_length=80)
    max_duration_minutes: int = Field(default=60,ge=1,le=120)
    consent_confirmed: bool

    @field_validator('meeting_url')
    @classmethod
    def meet_only(cls,value):
        match=re.fullmatch(r'https://meet\.google\.com/([a-z]{3}-[a-z]{4}-[a-z]{3})/?',value)
        if not match: raise ValueError('Use a Google Meet link like https://meet.google.com/abc-defg-hij')
        return 'https://meet.google.com/'+match[1]

    @field_validator('consent_confirmed')
    @classmethod
    def informed_recording(cls,value):
        if value is not True: raise ValueError('Confirm that the host/participants know this bot will record audio')
        return value


@dataclass
class Control:
    stop: asyncio.Event = field(default_factory=asyncio.Event)
    cancel: asyncio.Event = field(default_factory=asyncio.Event)
    resume: asyncio.Event = field(default_factory=asyncio.Event)


class BotManager:
    def __init__(self,connect,app,driver_factory=BrowserBot):
        self.connect,self.app,self.driver_factory=connect,app,driver_factory
        self.controls={}
        self.tasks={}
        self.start_lock=asyncio.Lock()

    def database(self,connection):
        connection.execute('CREATE TABLE IF NOT EXISTS meeting_bots (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')

    def read(self,bot_id):
        with self.connect() as connection:
            self.database(connection)
            row=connection.execute('SELECT payload FROM meeting_bots WHERE id=?',(bot_id,)).fetchone()
        if not row: raise HTTPException(404,'Meeting bot not found')
        result=json.loads(row['payload'])
        if result['state']=='transcribing' and result.get('job_id'):
            with self.connect() as connection:
                job=connection.execute('SELECT * FROM ingestion_jobs WHERE id=?',(result['job_id'],)).fetchone()
            if job and job['status'] in {'completed','failed'}:
                result=self.update(bot_id,job['status'],job['message'],meeting_id=job['meeting_id'])
            elif job: result['job']=dict(job)
        return result

    def update(self,bot_id,state=None,message=None,**fields):
        with self.connect() as connection:
            self.database(connection)
            connection.execute('BEGIN IMMEDIATE')
            row=connection.execute('SELECT payload FROM meeting_bots WHERE id=?',(bot_id,)).fetchone()
            if not row: raise HTTPException(404,'Meeting bot not found')
            record=json.loads(row['payload'])
            if state and (record['state']!=state or message!=record['message']):
                record['events']=(record['events']+[{'state':state,'message':message,'at':now()}])[-80:]
            record.update(fields,updated_at=now())
            if state:record['state']=state
            if message is not None:record['message']=message
            connection.execute('UPDATE meeting_bots SET payload=? WHERE id=?',(json.dumps(record),bot_id))
        return record

    def list(self):
        with self.connect() as connection:
            self.database(connection)
            ids=[row['id'] for row in connection.execute('SELECT id FROM meeting_bots ORDER BY rowid DESC LIMIT 30')]
        return [self.read(bot_id) for bot_id in ids]

    def recover(self):
        for record in self.list():
            if record['state'] not in TERMINAL|{'transcribing'}:
                self.update(record['id'],'failed','Backend restarted; the browser session cannot be resumed. Start a new bot.')

    def capabilities(self):
        return {'playwright_installed':importlib.util.find_spec('playwright') is not None,
                'ffmpeg_available':bool(ffmpeg_path()),'browser':os.getenv('MEETMIND_BOT_BROWSER','chrome'),
                'max_active_bots':1,'capture':'incoming_webrtc_audio','live_meet_validated':True}

    async def start(self,data):
        async with self.start_lock:
            if self.tasks:raise HTTPException(429,'A browser bot is already active. Stop or cancel it first.')
            if not self.capabilities()['playwright_installed']:
                raise HTTPException(503,'Install the backend bot extra: uv sync --extra bot. Google Chrome is also required.')
            if not ffmpeg_path():raise HTTPException(503,'FFmpeg is required to transcribe bot recordings.')
            bot_id=str(uuid4())
            record={'id':bot_id,**data.model_dump(),'state':'queued','message':'Starting an isolated bot browser',
                    'created_at':now(),'updated_at':now(),'events':[],'job_id':None,'meeting_id':None,
                    'capture_method':'browser_bot','uploaded_chunks':0,'recorded_bytes':0,'remote_tracks':0}
            with self.connect() as connection:
                self.database(connection)
                connection.execute('INSERT INTO meeting_bots VALUES (?,?)',(bot_id,json.dumps(record)))
            control=Control();self.controls[bot_id]=control
            task=asyncio.create_task(self.run(bot_id,data,control),name='meetmind-bot-'+bot_id)
            self.tasks[bot_id]=task
            return record

    def command(self,bot_id,command):
        record=self.read(bot_id)
        if bot_id not in self.controls or record['state'] in TERMINAL|{'transcribing'}:
            raise HTTPException(409,'This bot is not running; transcription jobs cannot be cancelled here.')
        if command=='resume' and record['state']!='needs_login':raise HTTPException(409,'This bot is not waiting for manual sign-in')
        getattr(self.controls[bot_id],command).set()
        return self.update(bot_id,message={'stop':'Stopping and preparing transcription','cancel':'Cancelling and discarding capture','resume':'Continuing after manual sign-in'}[command])

    async def run(self,bot_id,data,control):
        browser=self.driver_factory(PROFILE)
        session_id=None
        submitted=False
        seq=0
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),base_url='http://meetmind.internal',timeout=30) as api:
            async def request(method,path,**kwargs):
                response=await api.request(method,path,**kwargs)
                if response.is_error:
                    try: detail=response.json().get('detail','Capture API error')
                    except ValueError: detail='Capture API error'
                    raise RuntimeError(str(detail))
                return response.json() if response.status_code!=204 else None

            async def chunk(encoded):
                nonlocal seq
                if not session_id:raise RuntimeError('Audio arrived before the capture session was ready')
                # Bounded before decoding to keep an unexpected browser payload small.
                if len(encoded)>14*1024*1024:raise RuntimeError('Browser audio chunk exceeded its limit')
                audio=base64.b64decode(encoded,validate=True)
                await request('POST',f'/api/meet/sessions/{session_id}/audio?seq={seq}',content=audio)
                seq+=1
                self.update(bot_id,uploaded_chunks=seq,recorded_bytes=self.read(bot_id)['recorded_bytes']+len(audio))

            try:
                self.update(bot_id,'launching','Opening the dedicated browser; microphone and camera are denied')
                await browser.open(data.meeting_url,chunk)
                await browser.join(data.display_name,control,lambda state,message:self.update(bot_id,state,message),
                                   timeout=int(os.getenv('MEETMIND_BOT_JOIN_TIMEOUT','300')))
                if control.cancel.is_set() or control.stop.is_set():raise BotCancelled()
                session=await request('POST','/api/meet/sessions',json={
                    'title':data.title,'meeting_code':data.meeting_url.rsplit('/',1)[1],
                    'self_name':data.display_name,'started_at_ms':time.time()*1000,
                    'capture_method':'browser_bot','bot_id':bot_id,'input_language':data.input_language})
                session_id=session['id']
                await browser.start_capture()
                self.update(bot_id,'recording','Bot admitted. Recording incoming meeting audio; captions provide best-effort speaker hints.',capture_session_id=session_id)
                started=time.monotonic()
                while not control.stop.is_set() and time.monotonic()-started<data.max_duration_minutes*60:
                    if control.cancel.is_set():raise BotCancelled()
                    if await browser.ended():break
                    tick=await browser.tick()
                    if tick['stats'].get('error'):raise RuntimeError(tick['stats']['error'])
                    if tick['hints']:await request('POST',f'/api/meet/sessions/{session_id}/hints',json={'events':tick['hints']})
                    self.update(bot_id,remote_tracks=tick['stats']['remote_tracks'],capture_stats=tick['stats'],
                                elapsed_seconds=round(time.monotonic()-started))
                    try:await asyncio.wait_for(control.stop.wait(),timeout=1)
                    except TimeoutError:pass
                if control.cancel.is_set():raise BotCancelled()
                self.update(bot_id,'stopping','Flushing audio and leaving the meeting')
                stats,hints=await browser.stop_capture()
                self.update(bot_id,remote_tracks=stats['remote_tracks'],capture_stats=stats)
                if hints:await request('POST',f'/api/meet/sessions/{session_id}/hints',json={'events':hints})
                if not stats['remote_tracks'] or not stats['bytes']:
                    raise RuntimeError('No incoming meeting audio was captured. Check admission and remote speech; no transcript was created.')
                if stats.get('peak') == 0:
                    raise RuntimeError('The bot received silent audio throughout the recording. Check that another participant is unmuted and audible in the bot window. No transcript was created.')
                await browser.close();browser=None
                # Queue contention is temporary; retain the completed capture while retrying.
                response=None
                for attempt in range(30):
                    response=await api.post(f'/api/meet/sessions/{session_id}/finish')
                    if response.status_code!=429:break
                    if control.cancel.is_set():raise BotCancelled()
                    await asyncio.sleep(2)
                if response.is_error:
                    raise RuntimeError(response.json().get('detail','Cannot queue transcription'))
                submitted=True
                self.update(bot_id,'transcribing','Browser closed. Local Whisper transcription queued.',job_id=response.json()['id'])
            except (BotCancelled,asyncio.CancelledError):
                self.update(bot_id,'cancelled','Bot left the meeting and its unfinished capture was discarded')
            except Exception as error:
                logging.exception('Browser bot %s failed',bot_id)
                # Avoid exposing browser profile paths/cookies or arbitrary page content.
                message=str(error)[:300] if isinstance(error,RuntimeError) else 'Browser automation failed. Check Chrome, the bot extra, and local server logs.'
                self.update(bot_id,'failed',message)
            finally:
                if browser:
                    try:await asyncio.wait_for(browser.close(),timeout=15)
                    except Exception:logging.exception('Bot browser cleanup failed')
                if session_id and not submitted:
                    try:await api.delete(f'/api/meet/sessions/{session_id}')
                    except Exception:logging.exception('Bot capture cleanup failed')
                self.tasks.pop(bot_id,None);self.controls.pop(bot_id,None)

    async def shutdown(self):
        tasks=list(self.tasks.values())
        for control in self.controls.values():control.cancel.set();control.stop.set()
        if tasks:
            done,pending=await asyncio.wait(tasks,timeout=20)
            for task in pending:task.cancel()
            if pending:await asyncio.gather(*pending,return_exceptions=True)


def build_router(manager):
    router=APIRouter(prefix='/api/meet/bots')

    @router.get('/capabilities')
    def capabilities():return manager.capabilities()

    @router.get('')
    def list_bots():return manager.list()

    @router.post('',status_code=201)
    async def start(data:BotInput):return await manager.start(data)

    @router.get('/{bot_id}')
    def detail(bot_id:str):return manager.read(bot_id)

    @router.post('/{bot_id}/stop')
    async def stop(bot_id:str):return manager.command(bot_id,'stop')

    @router.post('/{bot_id}/cancel')
    async def cancel(bot_id:str):return manager.command(bot_id,'cancel')

    @router.post('/{bot_id}/resume')
    async def resume(bot_id:str):return manager.command(bot_id,'resume')

    return router
