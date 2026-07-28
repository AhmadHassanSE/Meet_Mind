import argparse
import whisper
import os
import sys
import wave
from pathlib import Path

from ingestion_service import IngestionService

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
DEFAULT_AUDIO_PATH = "recordings\\meeting_clip2.wav"
#DEFAULT_AUDIO_PATH = "amicorpus\\EN2001a\\audio\\EN2001a.Mix-Headset.wav"
DEFAULT_DIARIZATION_MODEL = "pyannote/speaker-diarization-community-1"

class MeetingTranscriptionAgent:
    def __init__(
        self,
        model_size="small",
        language="en",
        diarization_model=DEFAULT_DIARIZATION_MODEL,
        hf_token=None,
        device=None,
    ):
        """
        Initialize the agent with a Whisper model.
        model_size options: tiny, base, small, medium, large
        language options: "en" for English, "auto" for Whisper detection, or any Whisper language code
        """
        self.model_size = model_size
        self.language = language
        self.diarization_model = diarization_model
        self.hf_token = hf_token
        self.device = device
        self.diarization_pipeline = None
        self.ingestion_service = IngestionService()
        print(f"Loading Whisper model: {model_size}...")
        self.model = whisper.load_model(model_size)
        print("Model loaded.")

    def transcribe(self, audio_path):
        """
        Takes an audio file path and returns the full transcription.
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        print(f"Transcribing: {audio_path}")

        transcribe_options = {
            "task": "transcribe",
            "fp16": False,
            "verbose": False,
            "temperature": 0,
            "beam_size": 5,
            "best_of": 5,
            "condition_on_previous_text": True,
        }

        if self.language and self.language != "auto":
            transcribe_options["language"] = self.language

        # Whisper transcribes and returns structured result
        result = self.model.transcribe(audio_path, **transcribe_options)
        
        return {
            "text": result["text"],
            "segments": result["segments"],
            "language": result.get("language", "unknown")
        }

    def load_diarization_pipeline(self):
        """
        Load the pyannote speaker diarization pipeline.
        Requires a Hugging Face token for gated pyannote models.
        """
        if self.diarization_pipeline is not None:
            return self.diarization_pipeline

        try:
            from pyannote.audio import Pipeline
        except ImportError as exc:
            raise ImportError(
                "Speaker diarization needs pyannote.audio. "
                "Install it with: pip install -r requirements.txt"
            ) from exc

        token = self._resolve_hf_token()
        if not token:
            raise ValueError(
                "Speaker diarization needs a Hugging Face token. "
                "Set HF_TOKEN, pass --hf-token, or run `huggingface-cli login` after accepting the pyannote model conditions on Hugging Face."
            )

        print(f"Loading diarization model: {self.diarization_model}...")
        try:
            pipeline = Pipeline.from_pretrained(self.diarization_model, token=token)
        except TypeError:
            pipeline = Pipeline.from_pretrained(self.diarization_model, use_auth_token=token)

        if self.device:
            import torch

            pipeline.to(torch.device(self.device))

        self.diarization_pipeline = pipeline
        print("Diarization model loaded.")
        return pipeline

    def diarize(self, audio_path, num_speakers=None, min_speakers=None, max_speakers=None):
        """
        Return pyannote diarization output for an audio file.
        """
        pipeline = self.load_diarization_pipeline()
        options = {}
        if num_speakers is not None:
            options["num_speakers"] = num_speakers
        if min_speakers is not None:
            options["min_speakers"] = min_speakers
        if max_speakers is not None:
            options["max_speakers"] = max_speakers

        print(f"Diarizing: {audio_path}")
        waveform_input = self._load_audio_for_diarization(audio_path)
        return pipeline(waveform_input, preload=False, **options)

    def transcribe_with_speakers(
        self,
        audio_path,
        num_speakers=None,
        min_speakers=None,
        max_speakers=None,
    ):
        """
        Transcribe audio with Whisper and assign a speaker label to each segment
        using maximum overlap with pyannote diarization turns.
        """
        transcript = self.transcribe(audio_path)
        diarization = self.diarize(
            audio_path,
            num_speakers=num_speakers,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
        )
        speaker_turns = self._speaker_turns(diarization)

        for segment in transcript["segments"]:
            segment["speaker"] = self._speaker_for_segment(
                segment["start"],
                segment["end"],
                speaker_turns,
            )

        transcript["diarization"] = diarization
        transcript["speaker_turns"] = speaker_turns
        return transcript

    def build_report(self, audio_file, result):
        report_lines = [
            "=" * 60,
            "MEETING TRANSCRIPTION REPORT",
            "=" * 60,
            f"Input file : {audio_file}",
            f"Model      : {self.model_size}",
            f"Source     : {result.get('source_type', 'audio')}",
            f"Diarizer   : {self.diarization_model if result.get('diarization') else 'disabled'}",
            f"Language   : {result.get('language', 'unknown')}",
            "",
            "FULL TRANSCRIPTION",
            "-" * 60,
            result["text"].strip(),
            "",
            "TIMESTAMPED SEGMENTS",
            "-" * 60,
            self.ingestion_service.format_segments(result),
        ]
        return "\n".join(report_lines)

    @staticmethod
    def save_rttm(diarization, output_file):
        with open(output_file, "w", encoding="utf-8") as rttm:
            MeetingTranscriptionAgent._diarization_annotation(diarization).write_rttm(rttm)

    @staticmethod
    def _speaker_turns(diarization):
        diarization = MeetingTranscriptionAgent._diarization_annotation(diarization)
        turns = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            turns.append(
                {
                    "start": float(turn.start),
                    "end": float(turn.end),
                    "speaker": speaker,
                }
            )
        return turns

    @staticmethod
    def _speaker_for_segment(start, end, speaker_turns):
        scores = {}
        for turn in speaker_turns:
            overlap = max(0.0, min(end, turn["end"]) - max(start, turn["start"]))
            if overlap > 0:
                scores[turn["speaker"]] = scores.get(turn["speaker"], 0.0) + overlap
        if not scores:
            return "UNKNOWN"
        return max(scores, key=scores.get)

    @staticmethod
    def _diarization_annotation(diarization):
        if hasattr(diarization, "speaker_diarization"):
            return diarization.speaker_diarization
        if hasattr(diarization, "annotation"):
            return diarization.annotation
        return diarization

    def _resolve_hf_token(self):
        token = self.hf_token or os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")
        if token:
            return token

        try:
            from huggingface_hub import get_token
        except ImportError:
            return None

        return get_token()

    @staticmethod
    def _load_audio_for_diarization(audio_path):
        """
        Load audio before passing it to pyannote so Windows does not depend on
        torchcodec/FFmpeg DLL discovery for simple WAV files.
        """
        import torch
        import numpy as np

        path = Path(audio_path)
        if path.suffix.lower() not in {".wav", ".wave"}:
            raise ValueError(
                "Diarization audio loading currently supports WAV files without torchcodec. "
                "Use a .wav file or install a compatible audio backend for other formats."
            )

        with wave.open(str(path), "rb") as wav_file:
            sample_rate = wav_file.getframerate()
            num_channels = wav_file.getnchannels()
            sample_width = wav_file.getsampwidth()
            frame_count = wav_file.getnframes()
            raw_audio = wav_file.readframes(frame_count)

        if sample_width == 1:
            audio = np.frombuffer(raw_audio, dtype=np.uint8).astype(np.float32)
            audio = (audio - 128.0) / 128.0
        elif sample_width == 2:
            audio = np.frombuffer(raw_audio, dtype=np.int16).astype(np.float32)
            audio /= 32768.0
        elif sample_width == 4:
            audio = np.frombuffer(raw_audio, dtype=np.int32).astype(np.float32)
            audio /= 2147483648.0
        else:
            raise ValueError(
                f"Unsupported WAV sample width: {sample_width} bytes."
            )

        if num_channels > 1:
            audio = audio.reshape(-1, num_channels).T
        else:
            audio = audio.reshape(1, -1)

        waveform = torch.from_numpy(audio.copy())
        return {"waveform": waveform, "sample_rate": sample_rate}


def main():
    parser = argparse.ArgumentParser(description="Ingest meeting audio or transcript files with optional speaker diarization.")
    parser.add_argument("--input", "--audio", dest="input_path", default=DEFAULT_AUDIO_PATH, help="Path to a .wav/.mp3/.m4a audio file, .vtt transcript, .docx transcript, or plain text file.")
    parser.add_argument("--model-size", default="small", help="Whisper model size: tiny, base, small, medium, large.")
    parser.add_argument("--language", default="en", help='Whisper language code, or "auto".')
    parser.add_argument("--diarize", action="store_true", help="Enable speaker diarization.")
    parser.add_argument("--diarization-model", default=DEFAULT_DIARIZATION_MODEL)
    parser.add_argument("--hf-token", default=None, help="Hugging Face token. Prefer HF_TOKEN env var.")
    parser.add_argument("--device", default=None, help='Optional torch device, for example "cuda" or "cpu".')
    parser.add_argument("--num-speakers", type=int, default=None, help="Known number of speakers.")
    parser.add_argument("--min-speakers", type=int, default=None, help="Minimum speaker count.")
    parser.add_argument("--max-speakers", type=int, default=None, help="Maximum speaker count.")
    parser.add_argument("--output", default=str(Path("recordings") / "transcription.txt"))
    parser.add_argument("--rttm-output", default=None, help="Optional path for diarization RTTM output.")
    args = parser.parse_args()

    agent = MeetingTranscriptionAgent(
        model_size=args.model_size,
        language=args.language,
        diarization_model=args.diarization_model,
        hf_token=args.hf_token,
        device=args.device,
    )

    input_file = args.input_path

    try:
        result = agent.ingestion_service.ingest(
            input_file,
            transcribe_audio=agent.transcribe,
            transcribe_audio_with_speakers=agent.transcribe_with_speakers,
            diarize=args.diarize,
            num_speakers=args.num_speakers,
            min_speakers=args.min_speakers,
            max_speakers=args.max_speakers,
        )

        report = agent.build_report(input_file, result)
        print("\n" + report)

        output_file = Path(args.output)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(report)
        print(f"\nSaved to: {output_file}")

        if args.rttm_output and result.get("diarization"):
            rttm_output = Path(args.rttm_output)
            rttm_output.parent.mkdir(parents=True, exist_ok=True)
            agent.save_rttm(result["diarization"], rttm_output)
            print(f"Saved RTTM to: {rttm_output}")

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
