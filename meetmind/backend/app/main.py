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
from uuid import uuid4

import httpx
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from .ingestion import IngestionError, parse_text, parse_transcript, docx_text, MAX_TEXT_BYTES
from .preprocessing import prepare
from .media import AUDIO_FORMATS, VIDEO_FORMATS, MAX_MEDIA_BYTES, MODEL_NAME, ffmpeg_path, transcribe_media
from . import bert, commitments, review, languages

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
    yield


app = FastAPI(title="MeetMind", version="0.2.0", lifespan=lifespan)


@contextmanager
def connect():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("CREATE TABLE IF NOT EXISTS meetings (id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
    connection.execute("CREATE TABLE IF NOT EXISTS ingestion_jobs (id TEXT PRIMARY KEY, status TEXT, progress INTEGER, message TEXT, meeting_id TEXT)")
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


def save(meeting):
    with connect() as connection:
        connection.execute("INSERT OR REPLACE INTO meetings VALUES (?, ?)",
                           (meeting["id"], json.dumps(meeting)))


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
def review_commitment(meeting_id: str, item_id: str, data: review.ReviewInput):
    with connect() as connection:
        connection.execute('BEGIN IMMEDIATE')
        row = connection.execute('SELECT payload FROM meetings WHERE id = ?', (meeting_id,)).fetchone()
        if not row:
            raise HTTPException(404, 'Meeting not found')
        meeting = json.loads(row['payload'])
        review.initialize(meeting)
        try:
            review.apply(meeting, item_id, data)
        except LookupError as error:
            raise HTTPException(404, str(error)) from error
        except RuntimeError as error:
            raise HTTPException(409, str(error)) from error
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        connection.execute('UPDATE meetings SET payload = ? WHERE id = ?', (json.dumps(meeting), meeting_id))
    return meeting


@app.get("/api/health")
async def health():
    ingestion = {"ffmpeg": bool(ffmpeg_path()), "speech_model": MODEL_NAME, "bert": bert.status(), 'spacy': commitments.status(),
                 'languages': {'supported': ['en','ur','roman-ur','mixed'], 'multilingual_model': MULTILINGUAL_MODEL,
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
def meetings():
    with connect() as connection:
        rows = connection.execute("SELECT payload FROM meetings ORDER BY rowid DESC").fetchall()
    return [json.loads(row["payload"]) for row in rows]


@app.post("/api/meetings", status_code=201)
def create_meeting(data: MeetingInput):
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
               'input_language': data.input_language, 'language_profile': languages.profile(segments, data.input_language)}
    save(meeting)
    return meeting


@app.post("/api/ingestion/transcript", status_code=201)
async def upload_transcript(title: str = Form(..., min_length=1, max_length=200), file: UploadFile = File(...), input_language: languages.Language = Form('auto')):
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
                   'input_language': input_language, 'language_profile': languages.profile(prepared['segments'], input_language)}
        save(meeting)
        return meeting
    except IngestionError as error:
        raise HTTPException(422, str(error)) from error
    finally:
        await file.close()


def update_job(job_id, status, progress, message, meeting_id=None):
    with connect() as connection:
        connection.execute("INSERT OR REPLACE INTO ingestion_jobs VALUES (?, ?, ?, ?, ?)",
                           (job_id, status, progress, message, meeting_id))


def run_media_job(job_id, title, filename, path, input_language='auto'):
    try:
        update = lambda status, progress, message: update_job(job_id, status, progress, message)
        segments, metadata = transcribe_media(path, update) if input_language=='auto' else transcribe_media(path, update, language=input_language)
        prepared = prepare('\n'.join(s['source'] for s in segments), segments)
        update_job(job_id, "saving", 96, "Saving transcript and evidence segments")
        meeting = {"id": str(uuid4()), "title": title, "transcript": "\n".join(s["source"] for s in segments),
                   "segments": segments, "actions": [], "status": "uploaded", "model": None,
                   "source_type": "video" if path.suffix in VIDEO_FORMATS else "audio",
                   "filename": filename, **metadata, **prepared, 'input_language': input_language,
                   'language_profile': languages.profile(prepared['segments'], input_language)}
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
async def upload_media(title: str = Form(..., min_length=1, max_length=200), file: UploadFile = File(...), input_language: languages.Language = Form('auto')):
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
        update_job(job_id, "queued", 0, "Waiting for local transcription")
        executor.submit(run_media_job, job_id, title.strip(), Path(file.filename or "recording").name, path, input_language)
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
def ingestion_job(job_id: str):
    with connect() as connection:
        row = connection.execute("SELECT * FROM ingestion_jobs WHERE id=?", (job_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Ingestion job not found")
    return dict(row)


@app.get("/api/meetings/{meeting_id}")
def detail(meeting_id: str):
    return get_meeting(meeting_id)


def caption_time(seconds):
    milliseconds = round(seconds * 1000)
    return f"{milliseconds // 3600000:02}:{milliseconds // 60000 % 60:02}:{milliseconds // 1000 % 60:02}.{milliseconds % 1000:03}"


@app.get("/api/meetings/{meeting_id}/transcript")
def download_transcript(meeting_id: str, format: str = "txt"):
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
async def classify_dialogue(meeting_id: str):
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
    return meeting


@app.post("/api/meetings/{meeting_id}/extract")
async def extract(meeting_id: str):
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
    return meeting
