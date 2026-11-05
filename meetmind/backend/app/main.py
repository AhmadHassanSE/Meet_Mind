"""Local-only meeting ingestion and Ollama extraction foundation."""
import json
import html
import os
import sqlite3
import logging
import shutil
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from contextlib import contextmanager
from pathlib import Path
from typing import Literal
from uuid import uuid4

import httpx
from fastapi import Depends, FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from .ingestion import IngestionError, parse_text, parse_transcript, docx_text, MAX_TEXT_BYTES
from .preprocessing import prepare
from .media import AUDIO_FORMATS, VIDEO_FORMATS, MAX_MEDIA_BYTES, MODEL_NAME, ffmpeg_path, transcribe_media
from . import auth, bert, commitments, review, languages, artifacts
from .auth import User
from .connectors import meet, bot

DB_PATH = Path(os.getenv("MEETMIND_DB", str(Path(__file__).parents[1] / "meetmind.db")))
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:latest")
MULTILINGUAL_MODEL = os.getenv('OLLAMA_MULTILINGUAL_MODEL', 'qwen3:4b')
executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="meetmind-transcription")
slots = threading.BoundedSemaphore(3)


@asynccontextmanager
async def lifespan(application):
    with connect() as connection:
        connection.execute("UPDATE ingestion_jobs SET status='failed', message='Server restarted. Upload the recording again.' WHERE status NOT IN ('completed', 'failed')")
        admin = connection.execute('SELECT id FROM users WHERE is_admin=1 AND active=1 ORDER BY created_at LIMIT 1').fetchone()
        if admin:
            auth.claim_orphans(connection, admin['id'])
    meet.fail_stale()
    bot_manager.recover()
    artifact_service.recover()
    yield
    await bot_manager.shutdown()


app = FastAPI(title="MeetMind", version="0.2.0", lifespan=lifespan)


migrated = set()


@contextmanager
def connect():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    if DB_PATH not in migrated:
        connection.execute("CREATE TABLE IF NOT EXISTS meetings (id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
        connection.execute("CREATE TABLE IF NOT EXISTS ingestion_jobs (id TEXT PRIMARY KEY, status TEXT, progress INTEGER, message TEXT, meeting_id TEXT)")
        if 'user_id' not in {row['name'] for row in connection.execute('PRAGMA table_info(ingestion_jobs)')}:
            connection.execute('ALTER TABLE ingestion_jobs ADD COLUMN user_id TEXT')
        artifacts.schema(connection)
        auth.schema(connection)
        connection.commit()
        migrated.add(DB_PATH)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


class MeetingInput(BaseModel):
    input_language: languages.Language = 'auto'
    title: str = Field(min_length=1, max_length=200)
    transcript: str = Field(min_length=1, max_length=500_000)


def segments_from_text(text):
    if text.lstrip().startswith("WEBVTT"):
        return parse_transcript(text.encode(), ".vtt")
    return parse_text(text)


auth.connect = connect


def save(meeting):
    with connect() as connection:
        connection.execute("INSERT OR REPLACE INTO meetings VALUES (?, ?)",
                           (meeting["id"], json.dumps(meeting)))
        if meeting.get('created_by'):
            auth.add_organizer(connection, meeting['id'], meeting['created_by'])


def authorize(meeting_id, user, organize=False):
    """Raise 404 for invisible meetings and 403 for view-only access."""
    with connect() as connection:
        result = (auth.require_organize if organize else auth.require_view)(connection, meeting_id, user)
        if result['role'] == 'admin':
            auth.audit(connection, user, 'admin_viewed_meeting', meeting_id)
    return result


def present(meeting, user):
    """Attach the caller's rights; not persisted."""
    with connect() as connection:
        return {**meeting, 'access': auth.access(connection, meeting['id'], user)}


def get_meeting(meeting_id):
    with connect() as connection:
        connection.execute('BEGIN IMMEDIATE')
        row = connection.execute("SELECT payload FROM meetings WHERE id = ?", (meeting_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Meeting not found")
        meeting = json.loads(row['payload'])
        review.initialize(meeting)
        if json.dumps(meeting) != row['payload']:
            connection.execute('UPDATE meetings SET payload = ? WHERE id = ?', (json.dumps(meeting), meeting_id))
    return meeting


@app.post('/api/meetings/{meeting_id}/commitments/{item_id}/review')
def review_commitment(meeting_id: str, item_id: str, data: review.ReviewInput, user: User = Depends(auth.current_user)):
    with connect() as connection:
        connection.execute('BEGIN IMMEDIATE')
        auth.require_organize(connection, meeting_id, user)
        row = connection.execute('SELECT payload FROM meetings WHERE id = ?', (meeting_id,)).fetchone()
        if not row:
            raise HTTPException(404, 'Meeting not found')
        meeting = json.loads(row['payload'])
        review.initialize(meeting)
        try:
            review.apply(meeting, item_id, data, user)
        except LookupError as error:
            raise HTTPException(404, str(error)) from error
        except RuntimeError as error:
            raise HTTPException(409, str(error)) from error
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        connection.execute('UPDATE meetings SET payload = ? WHERE id = ?', (json.dumps(meeting), meeting_id))
        artifacts.invalidate(connection,meeting_id,item_id)
    return present(meeting, user)


@app.get("/api/health")
async def health():
    ingestion = {"ffmpeg": bool(ffmpeg_path()), "speech_model": MODEL_NAME, "bert": bert.status(), 'spacy': commitments.status(),
                 'languages': {'supported': ['en','ur','roman-ur'], 'multilingual_model': MULTILINGUAL_MODEL,
                               'speech_multilingual': not MODEL_NAME.endswith('.en'), 'urdu_accuracy_validated': False}}
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            response = await client.get(f"{OLLAMA_URL}/api/tags")
            response.raise_for_status()
        names = [model["name"] for model in response.json().get("models", [])]
        ingestion['languages']['model_status'] = 'ready' if MULTILINGUAL_MODEL in names else 'model missing'
        return {"ollama": "ready" if OLLAMA_MODEL in names else "model missing", "model": OLLAMA_MODEL, **ingestion}
    except (httpx.HTTPError, ValueError):
        ingestion['languages']['model_status'] = 'offline'
        return {"ollama": "offline", "model": OLLAMA_MODEL, **ingestion}


@app.get("/api/meetings")
def meetings(user: User = Depends(auth.current_user)):
    with connect() as connection:
        visible = auth.visible_meeting_ids(connection, user)
        rows = connection.execute("SELECT id, payload FROM meetings ORDER BY rowid DESC").fetchall()
        return [{**json.loads(row["payload"]), 'access': auth.access(connection, row['id'], user)}
                for row in rows if visible is None or row['id'] in visible]


@app.post("/api/meetings", status_code=201)
def create_meeting(data: MeetingInput, user: User = Depends(auth.organizer_user)):
    if not data.title.strip() or not data.transcript.strip():
        raise HTTPException(422, "Title and transcript cannot be blank")
    try:
        prepared = prepare(data.transcript, segments_from_text(data.transcript) if data.transcript.lstrip().startswith('WEBVTT') else None)
        segments = prepared['segments']
    except IngestionError as error:
        raise HTTPException(422, str(error)) from error
    if not segments:
        raise HTTPException(422, "No transcript utterances found")
    meeting = {"id": str(uuid4()), "title": data.title.strip(), "transcript": data.transcript,
               "segments": segments, "actions": [], "status": "uploaded", "model": None,
               "source_type": "text", "filename": None, **prepared,
               'input_language': data.input_language, 'language_profile': languages.profile(segments, data.input_language),
               'created_by': user.id}
    save(meeting)
    return present(meeting, user)


@app.post("/api/ingestion/transcript", status_code=201)
async def upload_transcript(title: str = Form(..., min_length=1, max_length=200), file: UploadFile = File(...), input_language: languages.Language = Form('auto'),
                            user: User = Depends(auth.organizer_user)):
    try:
        if not title.strip():
            raise IngestionError("Meeting title cannot be blank")
        suffix = Path(file.filename or "").suffix.lower()
        data = await file.read(MAX_TEXT_BYTES + 1)
        segments = parse_transcript(data, suffix)
        original = docx_text(data) if suffix == '.docx' else data.decode('utf-8-sig')
        prepared = prepare(original, segments if suffix in {'.vtt', '.srt'} else None)
        meeting = {"id": str(uuid4()), "title": title.strip(),
                   "transcript": "\n".join(item["source"] for item in segments),
                   "segments": segments, "actions": [], "status": "uploaded", "model": None,
                   "source_type": suffix.lstrip("."), "filename": Path(file.filename or "").name, **prepared,
                   'input_language': input_language, 'language_profile': languages.profile(prepared['segments'], input_language),
                   'created_by': user.id}
        save(meeting)
        return present(meeting, user)
    except IngestionError as error:
        raise HTTPException(422, str(error)) from error
    finally:
        await file.close()


def update_job(job_id, status, progress, message, meeting_id=None, user_id=None):
    # The creating user is recorded once and preserved by later progress updates.
    with connect() as connection:
        connection.execute("INSERT INTO ingestion_jobs (id, status, progress, message, meeting_id, user_id) VALUES (?, ?, ?, ?, ?, ?) "
                           "ON CONFLICT(id) DO UPDATE SET status=excluded.status, progress=excluded.progress, "
                           "message=excluded.message, meeting_id=excluded.meeting_id",
                           (job_id, status, progress, message, meeting_id, user_id))


def submit_job(run):
    if not slots.acquire(blocking=False):
        return False

    def guarded():
        try:
            run()
        finally:
            slots.release()
    executor.submit(guarded)
    return True


app.include_router(meet.build_router(save, update_job, submit_job))
bot_manager = bot.BotManager(connect, app)
app.include_router(bot.build_router(bot_manager))
artifact_service = artifacts.Service(connect,OLLAMA_URL,
    lambda meeting: MULTILINGUAL_MODEL if languages.needs_translation(meeting) else OLLAMA_MODEL)
app.include_router(artifacts.build_router(artifact_service))
app.include_router(auth.build_router())


class AssigneeInput(BaseModel):
    revision: int = Field(ge=0)
    user_id: str | None = Field(default=None, max_length=64)


class MemberInput(BaseModel):
    user_id: str = Field(min_length=1, max_length=64)
    role: Literal['organizer', 'viewer'] = 'viewer'


class OrganizerInput(BaseModel):
    user_id: str = Field(min_length=1, max_length=64)


def active_user(connection, user_id):
    row = connection.execute('SELECT * FROM users WHERE id=? AND active=1', (user_id,)).fetchone()
    if not row:
        raise HTTPException(422, 'Choose an active MeetMind user')
    return row


@app.put('/api/meetings/{meeting_id}/commitments/{item_id}/assignee')
def assign_owner(meeting_id: str, item_id: str, data: AssigneeInput, user: User = Depends(auth.current_user)):
    """Link an item to a registered owner. The spoken ``owner`` text is kept as evidence."""
    with connect() as connection:
        connection.execute('BEGIN IMMEDIATE')
        auth.require_organize(connection, meeting_id, user)
        meeting = json.loads(connection.execute('SELECT payload FROM meetings WHERE id = ?', (meeting_id,)).fetchone()['payload'])
        review.initialize(meeting)
        item = next((i for i in meeting.get('actions', []) + meeting.get('action_candidates', []) if i['id'] == item_id), None)
        if item is None:
            raise HTTPException(404, 'Commitment not found')
        if item['revision'] != data.revision:
            raise HTTPException(409, 'This item changed. Reload the meeting before assigning it.')
        if item.get('kind') == 'cancellation':
            raise HTTPException(422, 'A cancellation statement cannot have an owner')
        target = active_user(connection, data.user_id) if data.user_id else None
        before = item.get('assignee')
        item['assignee'] = {'id': target['id'], 'name': target['name'], 'email': target['email']} if target else None
        item['revision'] += 1
        item.setdefault('review_history', []).append({
            'revision': item['revision'], 'at': auth.stamp(), 'decision': 'assigned' if target else 'unassigned',
            'note': f"Owner account: {target['name']} <{target['email']}>" if target else 'Owner account removed',
            'before': {'assignee': before}, 'after': {'assignee': item['assignee']},
            'reviewer': user.label, 'reviewer_id': user.id})
        meeting['commitment_revision'] = meeting.get('commitment_revision', 0) + 1
        if target:
            connection.execute('INSERT OR REPLACE INTO assignments VALUES (?,?,?,?,?)',
                               (meeting_id, item_id, target['id'], user.id, auth.stamp()))
        else:
            connection.execute('DELETE FROM assignments WHERE meeting_id=? AND item_id=?', (meeting_id, item_id))
        connection.execute('UPDATE meetings SET payload = ? WHERE id = ?', (json.dumps(meeting), meeting_id))
        # A different owner means a different approver: earlier approvals no longer apply.
        artifacts.invalidate(connection, meeting_id, item_id)
    return present(meeting, user)


@app.get('/api/meetings/{meeting_id}/members')
def members(meeting_id: str, user: User = Depends(auth.current_user)):
    with connect() as connection:
        auth.require_view(connection, meeting_id, user)
        rows = connection.execute(
            "SELECT u.id, u.name, u.email, m.role AS role FROM meeting_members m JOIN users u ON u.id=m.user_id WHERE m.meeting_id=? "
            "UNION SELECT u.id, u.name, u.email, 'owner' FROM assignments a JOIN users u ON u.id=a.user_id "
            'WHERE a.meeting_id=? AND a.user_id NOT IN (SELECT user_id FROM meeting_members WHERE meeting_id=?) '
            'ORDER BY role, name COLLATE NOCASE',
            (meeting_id, meeting_id, meeting_id)).fetchall()
    return [dict(row) for row in rows]


@app.post('/api/meetings/{meeting_id}/members', status_code=201)
def add_member(meeting_id: str, data: MemberInput, user: User = Depends(auth.current_user)):
    with connect() as connection:
        connection.execute('BEGIN IMMEDIATE')
        auth.require_organize(connection, meeting_id, user)
        target = active_user(connection, data.user_id)
        if data.role == 'organizer' and target['role'] != 'organizer':
            raise HTTPException(422, 'Only users with the organizer role can co-organize a meeting')
        connection.execute('INSERT OR REPLACE INTO meeting_members VALUES (?,?,?,?,?)',
                           (meeting_id, target['id'], data.role, user.id, auth.stamp()))
        auth.audit(connection, user, 'meeting_member_added', meeting_id, {'user_id': target['id'], 'role': data.role})
    return members(meeting_id, user)


@app.delete('/api/meetings/{meeting_id}/members/{user_id}', status_code=204)
def remove_member(meeting_id: str, user_id: str, user: User = Depends(auth.current_user)):
    with connect() as connection:
        connection.execute('BEGIN IMMEDIATE')
        auth.require_organize(connection, meeting_id, user)
        organizers = {row[0] for row in connection.execute(
            "SELECT user_id FROM meeting_members WHERE meeting_id=? AND role='organizer'", (meeting_id,))}
        if organizers == {user_id}:
            raise HTTPException(409, 'A meeting needs at least one organizer')
        if not connection.execute('DELETE FROM meeting_members WHERE meeting_id=? AND user_id=?', (meeting_id, user_id)).rowcount:
            raise HTTPException(404, 'Member not found')
        auth.audit(connection, user, 'meeting_member_removed', meeting_id, {'user_id': user_id})


@app.delete('/api/meetings/{meeting_id}', status_code=204)
def delete_meeting(meeting_id: str, user: User = Depends(auth.current_user)):
    """Remove the meeting with its drafts, members and assignments (scope 2.3)."""
    with connect() as connection:
        connection.execute('BEGIN IMMEDIATE')
        auth.require_organize(connection, meeting_id, user)
        for table in ('artifacts', 'meeting_members', 'assignments'):
            connection.execute(f'DELETE FROM {table} WHERE meeting_id=?', (meeting_id,))
        connection.execute('DELETE FROM meetings WHERE id=?', (meeting_id,))
        auth.audit(connection, user, 'meeting_deleted', meeting_id)


@app.post('/api/admin/meetings/{meeting_id}/organizer')
def reassign_organizer(meeting_id: str, data: OrganizerInput, admin: User = Depends(auth.admin_user)):
    """Hand a meeting to another organizer, e.g. after a role is revoked."""
    with connect() as connection:
        connection.execute('BEGIN IMMEDIATE')
        if not connection.execute('SELECT 1 FROM meetings WHERE id=?', (meeting_id,)).fetchone():
            raise HTTPException(404, 'Meeting not found')
        target = active_user(connection, data.user_id)
        if target['role'] != 'organizer':
            raise HTTPException(422, 'Grant the organizer role first')
        connection.execute("DELETE FROM meeting_members WHERE meeting_id=? AND role='organizer'", (meeting_id,))
        connection.execute('INSERT OR REPLACE INTO meeting_members VALUES (?,?,?,?,?)',
                           (meeting_id, target['id'], 'organizer', admin.id, auth.stamp()))
        auth.audit(connection, admin, 'meeting_organizer_reassigned', meeting_id, {'user_id': target['id']})
    return {'meeting_id': meeting_id, 'organizer_id': target['id']}


def run_media_job(job_id, title, filename, path, input_language='auto', user_id=None):
    try:
        update = lambda status, progress, message: update_job(job_id, status, progress, message)
        segments, metadata = transcribe_media(path, update) if input_language=='auto' else transcribe_media(path, update, language=input_language)
        prepared = prepare('\n'.join(s['source'] for s in segments), segments)
        update_job(job_id, "saving", 96, "Saving transcript and evidence segments")
        meeting = {"id": str(uuid4()), "title": title, "transcript": "\n".join(s["source"] for s in segments),
                   "segments": segments, "actions": [], "status": "uploaded", "model": None,
                   "source_type": "video" if path.suffix in VIDEO_FORMATS else "audio",
                   "filename": filename, **metadata, **prepared, 'input_language': input_language,
                   'language_profile': languages.profile(prepared['segments'], input_language), 'created_by': user_id}
        save(meeting)
        update_job(job_id, "completed", 100, "Transcript ready", meeting["id"])
    except IngestionError as error:
        update_job(job_id, "failed", 0, str(error))
    except Exception:
        logging.exception("Media ingestion job %s failed", job_id)
        update_job(job_id, "failed", 0, "Local transcription failed. Check model availability and server logs, then retry.")
    finally:
        try:
            shutil.rmtree(path.parent)
        finally:
            slots.release()


@app.post("/api/ingestion/media", status_code=202)
async def upload_media(title: str = Form(..., min_length=1, max_length=200), file: UploadFile = File(...), input_language: languages.Language = Form('auto'),
                       user: User = Depends(auth.organizer_user)):
    directory = None
    acquired = False
    submitted = False
    try:
        suffix = Path(file.filename or "").suffix.lower()
        if not title.strip():
            raise HTTPException(422, "Meeting title cannot be blank")
        if suffix not in AUDIO_FORMATS | VIDEO_FORMATS:
            raise HTTPException(422, "Unsupported audio/video format")
        if not ffmpeg_path():
            raise HTTPException(503, "FFmpeg is unavailable. Install it or configure FFMPEG_PATH.")
        acquired = slots.acquire(blocking=False)
        if not acquired:
            raise HTTPException(429, "Transcription queue is full. Wait for a job to finish.")
        directory = Path(tempfile.mkdtemp(prefix="meetmind-media-"))
        path = directory / f"input{suffix}"
        total = 0
        with path.open("wb") as target:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > MAX_MEDIA_BYTES:
                    raise HTTPException(413, "Recording exceeds the 200 MB limit")
                target.write(chunk)
        if not total:
            raise HTTPException(422, "Recording is empty")
        job_id = str(uuid4())
        update_job(job_id, "queued", 0, "Waiting for local transcription", user_id=user.id)
        executor.submit(run_media_job, job_id, title.strip(), Path(file.filename or "recording").name, path, input_language, user.id)
        submitted = True
        return {"id": job_id, "status": "queued", "progress": 0, "message": "Waiting for local transcription", "meeting_id": None}
    finally:
        await file.close()
        if not submitted:
            if directory:
                shutil.rmtree(directory)
            if acquired:
                slots.release()


@app.get("/api/ingestion/jobs/{job_id}")
def ingestion_job(job_id: str, user: User = Depends(auth.principal)):
    # Capture tokens may poll their own transcription jobs.
    with connect() as connection:
        row = connection.execute("SELECT * FROM ingestion_jobs WHERE id=?", (job_id,)).fetchone()
    if not row or (row['user_id'] != user.id and not user.is_admin):
        raise HTTPException(404, "Ingestion job not found")
    return dict(row)


@app.get("/api/meetings/{meeting_id}")
def detail(meeting_id: str, user: User = Depends(auth.current_user)):
    authorize(meeting_id, user)
    return present(get_meeting(meeting_id), user)


def caption_time(seconds):
    milliseconds = round(seconds * 1000)
    return f"{milliseconds // 3600000:02}:{milliseconds // 60000 % 60:02}:{milliseconds // 1000 % 60:02}.{milliseconds % 1000:03}"


@app.get("/api/meetings/{meeting_id}/transcript")
def download_transcript(meeting_id: str, format: str = "txt", user: User = Depends(auth.current_user)):
    authorize(meeting_id, user)
    meeting = get_meeting(meeting_id)
    if format == "json":
        body, content_type = json.dumps({key: meeting[key] for key in ('title', 'segments', 'source_segments', 'original_transcript', 'preprocessing') if key in meeting}, ensure_ascii=False), "application/json"
    elif format == 'original':
        body, content_type = meeting.get('original_transcript', meeting['transcript']), 'text/plain'
    elif format == "txt":
        body, content_type = "\n".join((f"{s['speaker']}: " if s.get('speaker') else '') + s['text'] for s in meeting["segments"]), "text/plain"
    elif format == "vtt":
        if not all(s.get("start") is not None and s.get("end") is not None for s in meeting["segments"]):
            raise HTTPException(422, "VTT export requires timestamps for every segment")
        if any(s['end'] <= s['start'] for s in meeting['segments']):
            raise HTTPException(422, 'VTT requires positive time ranges. Use JSON to preserve point timestamps.')
        cues = []
        for s in meeting["segments"]:
            speaker = f"<v {html.escape(s['speaker'])}>" if s.get("speaker") else ""
            cues.append(f"{s['id']}\n{caption_time(s['start'])} --> {caption_time(s['end'])}\n{speaker}{html.escape(s['text'])}")
        body, content_type = "WEBVTT\n\n" + "\n\n".join(cues) + "\n", "text/vtt"
    else:
        raise HTTPException(422, "Choose txt, json, original or vtt")
    return Response(body, media_type=content_type, headers={"Content-Disposition": f'attachment; filename="transcript.{format}"'})


def extraction_batches(segments):
    batches, current, size = [], [], 0
    for segment in segments:
        length = len(json.dumps(segment, ensure_ascii=False))
        if length > 12000:
            raise HTTPException(422, "An utterance is too long for extraction. Split long paragraphs into speaker turns.")
        if current and size + length > 12000:
            batches.append(current)
            current, size = [], 0
        current.append(segment)
        size += length
    if current:
        batches.append(current)
    return batches


@app.post("/api/meetings/{meeting_id}/classify")
async def classify_dialogue(meeting_id: str, user: User = Depends(auth.current_user)):
    authorize(meeting_id, user, organize=True)
    meeting = get_meeting(meeting_id)
    try:
        result = await languages.classify(meeting, bert.classify, OLLAMA_URL, MULTILINGUAL_MODEL)
    except bert.BertUnavailable as error:
        raise HTTPException(503, str(error)) from error
    except httpx.HTTPError as error:
        raise HTTPException(503, 'Local translation failed. Check Ollama and OLLAMA_MULTILINGUAL_MODEL.') from error
    except (ValueError, KeyError, TypeError) as error:
        raise HTTPException(502, 'Invalid local translation; stored analysis was preserved. Retry or select the correct input language.') from error
    # Separate from commitments: suggest/offer labels are not approved tasks.
    # Merge only analysis into the current payload, preserving concurrent reviews.
    with connect() as connection:
        connection.execute('BEGIN IMMEDIATE')
        row = connection.execute('SELECT payload FROM meetings WHERE id = ?', (meeting_id,)).fetchone()
        meeting = json.loads(row['payload'])
        meeting['dialogue_analysis'] = result
        connection.execute('UPDATE meetings SET payload = ? WHERE id = ?', (json.dumps(meeting), meeting_id))
    return present(meeting, user)


@app.post("/api/meetings/{meeting_id}/extract")
async def extract(meeting_id: str, user: User = Depends(auth.current_user)):
    authorize(meeting_id, user, organize=True)
    meeting = get_meeting(meeting_id)
    if review.has_reviews(meeting):
        raise HTTPException(409, 'This meeting has reviewed items. Upload a new copy to run extraction again without losing decisions.')
    previous_revision = meeting.get('commitment_revision', 0)
    try:
        # Work on a detached payload: failures preserve previously saved results.
        analysis = await languages.classify(meeting, bert.classify, OLLAMA_URL, MULTILINGUAL_MODEL)
        units = commitments.source_units(meeting, analysis['predictions'])
        nlp = await run_in_threadpool(commitments.annotate, units)
        extraction_model = MULTILINGUAL_MODEL if languages.needs_translation(meeting) else OLLAMA_MODEL
        proposals = await commitments.propose(units, OLLAMA_URL, extraction_model)
        result = await run_in_threadpool(commitments.ground, proposals, units, nlp)
    except (bert.BertUnavailable, commitments.NLPUnavailable) as error:
        raise HTTPException(503, str(error)) from error
    except httpx.HTTPError as error:
        raise HTTPException(503, "Ollama request failed. Check the local service and installed model.") from error
    except (ValueError, KeyError, TypeError) as error:
        raise HTTPException(502, "Model output was invalid; stored meeting was preserved. Retry extraction.") from error
    meeting.update(result, dialogue_analysis=analysis)
    meeting.update(status="extracted", model=extraction_model)
    review.initialize(meeting)
    meeting['commitment_revision'] = previous_revision + 1
    with connect() as connection:
        connection.execute('BEGIN IMMEDIATE')
        row = connection.execute('SELECT payload FROM meetings WHERE id = ?', (meeting_id,)).fetchone()
        current = json.loads(row['payload'])
        if current.get('commitment_revision', 0) != previous_revision or review.has_reviews(current):
            raise HTTPException(409, 'Meeting changed during extraction. Reload to keep the latest results and reviews.')
        connection.execute('UPDATE meetings SET payload = ? WHERE id = ?', (json.dumps(meeting), meeting_id))
    return present(meeting, user)
