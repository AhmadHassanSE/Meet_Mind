import re
import unicodedata
from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET


class IngestionService:
    AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".aac", ".ogg", ".webm", ".wma"}

    def ingest(
        self,
        input_path,
        transcribe_audio,
        transcribe_audio_with_speakers=None,
        diarize=False,
        num_speakers=None,
        min_speakers=None,
        max_speakers=None,
    ):
        path = Path(input_path)
        if not path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        suffix = path.suffix.lower()
        if suffix in self.AUDIO_EXTENSIONS:
            if diarize:
                if transcribe_audio_with_speakers is None:
                    raise ValueError("Audio diarization requires a speaker-aware transcription callback.")
                result = transcribe_audio_with_speakers(
                    str(path),
                    num_speakers=num_speakers,
                    min_speakers=min_speakers,
                    max_speakers=max_speakers,
                )
            else:
                result = transcribe_audio(str(path))
            result["source_type"] = "audio"
            return self.normalize_result(result)

        if diarize:
            raise ValueError("Speaker diarization is only available for audio inputs.")

        if suffix == ".vtt":
            result = self._ingest_vtt(path)
            result["source_type"] = "vtt"
        elif suffix == ".docx":
            result = self._ingest_docx(path)
            result["source_type"] = "docx"
        else:
            result = self._ingest_text(path)
            result["source_type"] = "text"

        return self.normalize_result(result)

    def format_segments(self, result, max_gap_seconds=1.2):
        grouped_lines = []
        current_group = []
        previous_end = None
        previous_speaker = None

        for seg in result.get("segments", []):
            text = seg["text"].strip()
            speaker = seg.get("speaker")
            start_value = seg.get("start")
            end_value = seg.get("end")

            if start_value is None or end_value is None:
                if current_group:
                    grouped_lines.append(" ".join(current_group).strip())
                    current_group = []
                if speaker:
                    grouped_lines.append(f"{speaker}: {text}")
                else:
                    grouped_lines.append(text)
                previous_end = None
                previous_speaker = speaker
                continue

            start = self._format_time(start_value)
            end = self._format_time(end_value)
            has_gap = previous_end is not None and (start_value - previous_end) > max_gap_seconds
            has_speaker_change = speaker and previous_speaker and speaker != previous_speaker
            if (has_gap or has_speaker_change) and current_group:
                grouped_lines.append(" ".join(current_group).strip())
                current_group = []

            if speaker:
                current_group.append(f"[{start} - {end}] {speaker}: {text}")
            else:
                current_group.append(f"[{start} - {end}] {text}")
            previous_end = end_value
            previous_speaker = speaker

        if current_group:
            grouped_lines.append(" ".join(current_group).strip())

        return "\n\n".join(grouped_lines)

    def normalize_result(self, result):
        result = dict(result)
        result["text"] = self.clean_text(result.get("text", ""))
        cleaned_segments = []
        for segment in result.get("segments", []):
            cleaned_segment = dict(segment)
            cleaned_segment["text"] = self.clean_text(cleaned_segment.get("text", ""))
            if cleaned_segment["text"]:
                cleaned_segments.append(cleaned_segment)
        result["segments"] = cleaned_segments
        return result

    @staticmethod
    def clean_text(text):
        text = unicodedata.normalize("NFKC", text or "")
        text = text.replace("\u00a0", " ").replace("\u200b", "")
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"\s+([,.;:!?])", r"\1", text)
        text = re.sub(r"([([{])\s+", r"\1", text)
        text = re.sub(r"\s+([)\]}])", r"\1", text)
        return text.strip()

    @staticmethod
    def _ingest_text(path):
        raw_text = path.read_text(encoding="utf-8-sig")
        paragraphs = [line.strip() for line in raw_text.splitlines() if line.strip()]
        if not paragraphs:
            paragraphs = [raw_text.strip()]
        segments = [{"text": paragraph} for paragraph in paragraphs if paragraph.strip()]
        return {"text": "\n\n".join(paragraphs), "segments": segments, "language": "unknown"}

    @staticmethod
    def _ingest_vtt(path):
        text = path.read_text(encoding="utf-8-sig")
        blocks = re.split(r"(?:\r?\n){2,}", text.strip())
        segments = []

        for block in blocks:
            lines = [line.strip() for line in block.splitlines() if line.strip()]
            if not lines or lines[0].upper() == "WEBVTT":
                continue

            timestamp_index = next((index for index, line in enumerate(lines) if "-->" in line), None)
            if timestamp_index is None:
                continue

            timestamp_line = lines[timestamp_index]
            match = re.match(r"^(?P<start>[^\s]+)\s+-->\s+(?P<end>[^\s]+)", timestamp_line)
            if not match:
                continue

            cue_text = " ".join(lines[timestamp_index + 1 :]).strip()
            if not cue_text:
                continue

            segments.append(
                {
                    "start": IngestionService._parse_timestamp(match.group("start")),
                    "end": IngestionService._parse_timestamp(match.group("end")),
                    "text": cue_text,
                }
            )

        full_text = "\n".join(segment["text"] for segment in segments)
        return {"text": full_text, "segments": segments, "language": "unknown"}

    @staticmethod
    def _ingest_docx(path):
        namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        with ZipFile(path) as archive:
            document_xml = archive.read("word/document.xml")

        root = ET.fromstring(document_xml)
        paragraphs = []

        for paragraph in root.findall(".//w:p", namespace):
            fragments = []
            for node in paragraph.iter():
                tag = node.tag.rsplit("}", 1)[-1]
                if tag == "t" and node.text:
                    fragments.append(node.text)
                elif tag == "tab":
                    fragments.append("\t")
                elif tag in {"br", "cr"}:
                    fragments.append("\n")

            paragraph_text = "".join(fragments).strip()
            if paragraph_text:
                paragraphs.append(paragraph_text)

        if not paragraphs:
            paragraphs = [""]

        segments = [{"text": paragraph} for paragraph in paragraphs if paragraph.strip()]
        return {"text": "\n\n".join(paragraphs).strip(), "segments": segments, "language": "unknown"}

    @staticmethod
    def _format_time(seconds):
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        if hours:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        return f"{minutes:02d}:{secs:02d}"

    @staticmethod
    def _parse_timestamp(value):
        parts = value.split(":")
        if len(parts) == 3:
            hours, minutes, seconds = parts
        elif len(parts) == 2:
            hours = "0"
            minutes, seconds = parts
        else:
            raise ValueError(f"Unsupported VTT timestamp: {value}")

        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)