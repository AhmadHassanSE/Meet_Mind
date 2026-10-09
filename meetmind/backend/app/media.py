"""Local media decoding and Whisper inference. Never invokes a shell."""
import os
import shutil
import subprocess
import threading
import wave
from pathlib import Path

from .ingestion import IngestionError, MAX_CHARACTERS, segment

AUDIO_FORMATS = {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".aac"}
VIDEO_FORMATS = {".mp4", ".webm", ".mov", ".mkv"}
MAX_MEDIA_BYTES = 200 * 1024 * 1024
MAX_DURATION = 2 * 60 * 60
MODEL_NAME = os.getenv("WHISPER_MODEL", "base.en")
_model = None
_lock = threading.Lock()


def ffmpeg_path():
    return shutil.which(os.getenv("FFMPEG_PATH", "ffmpeg"))


def transcribe_media(path: Path, update):
    ffmpeg = ffmpeg_path()
    if not ffmpeg:
        raise IngestionError("FFmpeg is missing. Install FFmpeg or configure FFMPEG_PATH, then retry.")
    update("decoding", 10, "Extracting and validating meeting audio")
    wav = path.with_name("decoded.wav")
    try:
        result = subprocess.run([ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(path), "-map", "0:a:0", "-vn", "-t", str(MAX_DURATION + 1),
            "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)],
            capture_output=True, timeout=300, check=False)
    except subprocess.TimeoutExpired as error:
        raise IngestionError("Audio decoding timed out. Try a smaller recording.") from error
    if result.returncode:
        raise IngestionError("Media cannot be decoded or has no audio track. Upload a playable recording with meeting audio.")
    with wave.open(str(wav), "rb") as audio:
        duration = audio.getnframes() / audio.getframerate()
    if duration <= 0:
        raise IngestionError("Recording has no audio samples")
    if duration > MAX_DURATION:
        raise IngestionError("Recordings must be at most two hours long. Split this meeting into smaller files.")
    update("loading_model", 20, "Loading local speech model; first use may download model weights")
    global _model
    with _lock:
        if _model is None:
            from faster_whisper import WhisperModel
            _model = WhisperModel(MODEL_NAME, device="cpu", compute_type="int8",
                                  cpu_threads=max(1, min(4, os.cpu_count() or 1)))
        update("transcribing", 25, "Transcribing speech locally")
        stream, info = _model.transcribe(str(wav), language="en", beam_size=5,
            vad_filter=True, condition_on_previous_text=False)
        segments = []
        characters = 0
        for item in stream:
            if not item.text.strip():
                continue
            characters += len(item.text)
            if characters > MAX_CHARACTERS:
                raise IngestionError("Transcription exceeds the supported transcript size. Split the recording.")
            segments.append(segment(item.text, len(segments) + 1, item.start, item.end))
            update("transcribing", min(94, 25 + int(69 * item.end / duration)),
                   f"Transcribed {min(item.end, duration):.0f} of {duration:.0f} seconds")
    if not segments:
        raise IngestionError("No speech detected. Check that the recording contains audible meeting speech.")
    return segments, {"duration": round(duration, 2), "language": info.language,
                      "transcription_model": MODEL_NAME, "speaker_labels": "unavailable"}
