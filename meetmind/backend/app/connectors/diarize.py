"""Optional speaker diarization with pyannote.audio (local, CPU).

Install with the ``diarization`` extra. The default model is gated on Hugging
Face: accept its conditions on the model page, then provide a token through
``HF_TOKEN`` or ``hf auth login``. Everything here degrades to
``DiarizationUnavailable`` so Meet sessions still finish with caption hints only.
"""
import gc
import logging
import os
import threading
import wave

MODEL = os.getenv("MEETMIND_DIARIZATION_MODEL", "pyannote/speaker-diarization-community-1")
MODE = os.getenv("MEETMIND_DIARIZATION", "auto").strip().lower()
MAX_SPEAKERS = int(os.getenv("MEETMIND_MAX_SPEAKERS", "0")) or None
_lock = threading.Lock()


class DiarizationUnavailable(Exception):
    """Diarization cannot run; the message is safe to show to the user."""


def enabled():
    return MODE != "off"


def always():
    return MODE == "always"


def hf_token():
    token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_TOKEN")
    if token:
        return token
    try:
        from huggingface_hub import get_token
        return get_token()
    except Exception:
        return None


def _load_waveform(path):
    import numpy as np
    import torch
    with wave.open(str(path), "rb") as audio:
        rate = audio.getframerate()
        samples = np.frombuffer(audio.readframes(audio.getnframes()), dtype="<i2").astype(np.float32) / 32768.0
    return {"waveform": torch.from_numpy(samples).unsqueeze(0), "sample_rate": rate}


def diarize(wav_path, update=None):
    """Return ``[(start, end, cluster_label), ...]`` for a mono WAV file."""
    try:
        import torch
        from pyannote.audio import Pipeline
    except ImportError as error:
        raise DiarizationUnavailable("pyannote.audio is not installed (install the 'diarization' extra)") from error
    token = hf_token()
    if not token:
        raise DiarizationUnavailable("No Hugging Face token found (set HF_TOKEN or run 'hf auth login')")
    with _lock:
        pipeline = None
        try:
            if update:
                update("diarizing", 90, "Loading speaker model")
            try:
                pipeline = Pipeline.from_pretrained(MODEL, token=token)
            except Exception as error:
                logging.warning("Diarization model %s could not be loaded: %s", MODEL, error)
                raise DiarizationUnavailable(
                    "Diarization model could not be loaded. Check the Hugging Face token and that its "
                    "access conditions were accepted on the model page.") from error
            if pipeline is None:
                raise DiarizationUnavailable("Diarization model could not be loaded (access not granted)")
            torch.set_num_threads(max(1, min(4, os.cpu_count() or 1)))
            if update:
                update("diarizing", 92, "Separating speakers")
            options = {"max_speakers": MAX_SPEAKERS} if MAX_SPEAKERS else {}
            output = pipeline(_load_waveform(wav_path), **options)
            # pyannote 4 returns an object; "exclusive" turns never overlap, which suits transcripts.
            annotation = getattr(output, "exclusive_speaker_diarization", None) \
                or getattr(output, "speaker_diarization", output)
            return [(float(turn.start), float(turn.end), str(label))
                    for turn, _, label in annotation.itertracks(yield_label=True)]
        finally:
            del pipeline
            gc.collect()
