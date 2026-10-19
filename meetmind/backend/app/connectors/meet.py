"""Google Meet capture sessions: audio chunks and speaker hints from the browser extension."""
import json
import logging
import os
import shutil
import tempfile
import threading
from pathlib import Path
from uuid import uuid4
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ..ingestion import IngestionError
from ..media import MAX_MEDIA_BYTES, ffmpeg_path, transcribe_media
from ..preprocessing import prepare
from ..languages import Language, profile
from . import diarize
from .alignment import build_intervals, label_from_intervals, name_clusters, normalize_events, turns_to_intervals

LAG_SECONDS = float(os.getenv("MEETMIND_MEET_LAG_MS", "500")) / 1000
MIN_CONFIDENCE = float(os.getenv("MEETMIND_MEET_MIN_CONFIDENCE", "0.4"))
FALLBACK_UNATTRIBUTED = float(os.getenv("MEETMIND_MEET_FALLBACK_UNATTRIBUTED", "0.3"))
MAX_CHUNK_BYTES = 10 * 1024 * 1024
MAX_HINT_BYTES = 5 * 1024 * 1024
MAX_EVENTS_PER_REQUEST = 2000
MAX_SESSIONS = 3
sessions = {}
lock = threading.Lock()


class SessionInput(BaseModel):
    input_language: Language = 'auto'
    capture_method: Literal['extension','browser_bot'] = 'extension'
    bot_id: str | None = Field(default=None,max_length=36)
    title: str = Field(min_length=1, max_length=200)
    meeting_code: str = Field(default="", max_length=64)
    self_name: str = Field(default="", max_length=80)
    started_at_ms: float = Field(gt=0)


class HintsInput(BaseModel):
    events: list[dict] = Field(max_length=MAX_EVENTS_PER_REQUEST)


def drop(session_id):
    with lock:
        session = sessions.pop(session_id, None)
    if session:
        shutil.rmtree(session["dir"], ignore_errors=True)


def fail_stale():
    """Sessions live in memory; a restart orphans their temp directories."""
    for path in Path(tempfile.gettempdir()).glob("meetmind-meet-*"):
        shutil.rmtree(path, ignore_errors=True)


def get_session(session_id):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(404, "Meet session not found")
    return session


def build_router(save, update_job, submit_job):
    router = APIRouter(prefix="/api/meet")

    @router.post("/sessions", status_code=201)
    def start(data: SessionInput):
        if not data.title.strip():
            raise HTTPException(422, "Meeting title cannot be blank")
        if not ffmpeg_path():
            raise HTTPException(503, "FFmpeg is unavailable. Install it or configure FFMPEG_PATH.")
        with lock:
            if len(sessions) >= MAX_SESSIONS:
                raise HTTPException(429, "Too many active Meet sessions. Finish or cancel one first.")
            session_id = str(uuid4())
            directory = Path(tempfile.mkdtemp(prefix="meetmind-meet-"))
            sessions[session_id] = {"dir": directory, "title": data.title.strip(), "meeting_code": data.meeting_code,
                                    "self_name": data.self_name, "started_at_ms": data.started_at_ms,
                                    'input_language': data.input_language,
                                    "next_seq": 0, "bytes": 0, "hint_bytes": 0, "finishing": False,
                                    'capture_method':data.capture_method,'bot_id':data.bot_id}
        return {"id": session_id}

    @router.post("/sessions/{session_id}/audio")
    async def audio(session_id: str, seq: int, request: Request):
        session = get_session(session_id)
        body = await request.body()
        if len(body) > MAX_CHUNK_BYTES:
            raise HTTPException(413, "Audio chunk is too large")
        if not body:
            raise HTTPException(422, "Audio chunk is empty")
        with lock:
            if session["finishing"]:
                raise HTTPException(409, "Session is already finishing")
            if seq == session["next_seq"] - 1:
                return {"received": session["next_seq"], "duplicate": True}  # retried chunk
            if seq != session["next_seq"]:
                raise HTTPException(409, f"Expected chunk {session['next_seq']}, got {seq}")
            if session["bytes"] + len(body) > MAX_MEDIA_BYTES:
                raise HTTPException(413, "Recording exceeds the 200 MB limit")
            with (session["dir"] / "audio.webm").open("ab") as target:
                target.write(body)
            session["bytes"] += len(body)
            session["next_seq"] += 1
            return {"received": session["next_seq"], "duplicate": False}

    @router.post("/sessions/{session_id}/hints")
    def hints(session_id: str, data: HintsInput):
        session = get_session(session_id)
        lines = "".join(json.dumps(event, ensure_ascii=False) + "\n" for event in data.events)
        with lock:
            if session["finishing"]:
                raise HTTPException(409, "Session is already finishing")
            if session["hint_bytes"] + len(lines) > MAX_HINT_BYTES:
                raise HTTPException(413, "Too many speaker hints for one session")
            with (session["dir"] / "hints.jsonl").open("a", encoding="utf-8") as target:
                target.write(lines)
            session["hint_bytes"] += len(lines)
        return {"accepted": len(data.events)}

    @router.delete("/sessions/{session_id}", status_code=204)
    def cancel(session_id: str):
        get_session(session_id)
        drop(session_id)

    def read_events(session):
        path = session["dir"] / "hints.jsonl"
        raw = []
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    raw.append(json.loads(line))
                except ValueError:
                    continue
        return normalize_events(raw, session["started_at_ms"], session["self_name"])

    def label(session, segments, events, duration, update):
        """Return ``(labelled segments, speaker_labels, diarization, note)``.

        Caption hints (who Meet shows as speaking) label segments directly. pyannote
        is a fallback, used only when hints leave too much unattributed (or there
        are none); set MEETMIND_DIARIZATION=always to run it on every meeting.
        """
        hinted = build_intervals(events, LAG_SECONDS, duration)
        direct = label_from_intervals(segments, hinted, MIN_CONFIDENCE)
        covered = bool(events) and sum(1 for s in direct if not s["speaker"]) <= FALLBACK_UNATTRIBUTED * len(direct)
        if not diarize.enabled():
            note = None
            state = "off"
        elif covered and not diarize.always():
            return direct, "dom_hints", "not_needed", None
        else:
            try:
                turns = diarize.diarize(session["dir"] / "decoded.wav", update)
                state, note = "pyannote", None
            except diarize.DiarizationUnavailable as error:
                turns, state, note = [], "unavailable", str(error)
            except Exception:
                logging.exception("Diarization failed for a Meet session")
                turns, state, note = [], "unavailable", "Diarization failed; speaker names come from caption hints only"
            if turns:
                names = name_clusters(turns, hinted)
                labelled = label_from_intervals(segments, turns_to_intervals(turns, names), MIN_CONFIDENCE)
                return labelled, "diarization_hints" if set(names.values()) & set(hinted) else "diarization", state, note
            if state == "pyannote":
                state, note = "unavailable", "Diarization found no speech turns"
        labelled = label_from_intervals(segments, hinted, MIN_CONFIDENCE)
        return labelled, "dom_hints" if events else "unavailable", state, note

    def run(job_id, session_id, session):
        try:
            audio_path = session["dir"] / "audio.webm"
            update = lambda s, p, m: update_job(job_id, s, p, m)
            language = session.get('input_language', 'auto')
            segments, metadata = (transcribe_media(audio_path, update) if language == 'auto' else
                                  transcribe_media(audio_path, update, language=language))
            update_job(job_id, "aligning", 90, "Matching speech to speakers")
            events = read_events(session)
            labelled, labels, diarization, note = label(
                session, segments, events, metadata.get("duration"), lambda s, p, m: update_job(job_id, s, p, m))
            prepared = prepare("\n".join(s["source"] for s in labelled), labelled)
            unattributed = sum(1 for s in labelled if not s["speaker"])
            meeting = {"id": str(uuid4()), "title": session["title"],
                       "transcript": "\n".join(s["source"] for s in labelled), "segments": labelled,
                       "actions": [], "status": "uploaded", "model": None, "source_type": "google_meet",
                       "filename": None, "meeting_code": session["meeting_code"], **metadata,
                       'capture_method':session.get('capture_method','extension'),'bot_id':session.get('bot_id'),
                       "speaker_labels": labels, "diarization": diarization, "diarization_note": note,
                       "unattributed_segments": unattributed, **prepared}
            meeting.update(input_language=language, language_profile=profile(meeting['segments'], language))
            save(meeting)
            update_job(job_id, "completed", 100, "Transcript ready", meeting["id"])
        except IngestionError as error:
            update_job(job_id, "failed", 0, str(error))
        except Exception:
            logging.exception("Meet session %s failed", session_id)
            update_job(job_id, "failed", 0, "Meet transcription failed. Check model availability and server logs, then retry.")
        finally:
            drop(session_id)

    @router.post("/sessions/{session_id}/finish", status_code=202)
    def finish(session_id: str):
        session = get_session(session_id)
        with lock:
            if session["finishing"]:
                raise HTTPException(409, "Session is already finishing")
            if not session["bytes"]:
                raise HTTPException(422, "No audio was received for this session")
            session["finishing"] = True
        job_id = str(uuid4())
        update_job(job_id, "queued", 0, "Waiting for local transcription")
        if not submit_job(lambda: run(job_id, session_id, session)):
            session["finishing"] = False
            update_job(job_id, "failed", 0, "Transcription queue is full. Wait for a job to finish.")
            raise HTTPException(429, "Transcription queue is full. Wait for a job to finish.")
        return {"id": job_id, "status": "queued", "progress": 0, "message": "Waiting for local transcription", "meeting_id": None}

    return router
