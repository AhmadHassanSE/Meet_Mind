"""Normalize supported transcripts into evidence-preserving segments."""
import html
import io
import re
import unicodedata
import zipfile
import xml.etree.ElementTree as ET

TEXT_FORMATS = {".txt", ".md", ".docx", ".vtt", ".srt"}
MAX_TEXT_BYTES = 2 * 1024 * 1024
MAX_CHARACTERS = 500_000


class IngestionError(ValueError):
    pass


def clean(text):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text).replace("\u200b", "")).strip()


def segment(text, index, start=None, end=None, speaker=None):
    source = clean(text)
    match = re.match(r"^([^:\n]{1,60}):\s*(.+)$", source)
    if match and speaker is None:
        speaker, text = clean(match[1]), match[2]
    else:
        text = source
    return {"id": index, "speaker": speaker, "text": clean(text), "source": source,
            "start": start, "end": end}


def parse_text(text):
    return [segment(line, i + 1) for i, line in enumerate(line for line in text.splitlines() if line.strip())]


def timestamp(value):
    parts = value.replace(",", ".").split(":")
    if len(parts) not in {2, 3}:
        raise IngestionError("Invalid caption timestamp")
    try:
        seconds = float(parts[-1])
        minutes = int(parts[-2])
        hours = int(parts[0]) if len(parts) == 3 else 0
        if hours < 0 or not 0 <= minutes < 60 or not 0 <= seconds < 60:
            raise ValueError()
        return hours * 3600 + minutes * 60 + seconds
    except ValueError as error:
        raise IngestionError("Invalid caption timestamp") from error


def parse_captions(text, suffix):
    text = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
    if suffix == ".vtt":
        if not text.startswith("WEBVTT"):
            raise IngestionError("VTT files must start with WEBVTT")
        parts = re.split(r"\n[ \t]*\n", text, maxsplit=1)
        if len(parts) != 2:
            raise IngestionError("VTT header must be followed by a blank line and caption cues")
        text = parts[1]
    result = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = block.strip().splitlines()
        if not lines or lines[0].startswith(("NOTE", "STYLE", "REGION")):
            continue
        position = next((i for i, line in enumerate(lines) if "-->" in line), None)
        if position is None:
            raise IngestionError("Caption cue is missing a timestamp range")
        match = re.fullmatch(r"\s*(\S+)\s+-->\s+(\S+)(?:\s+.*)?", lines[position])
        if not match:
            raise IngestionError("Invalid caption timestamp range")
        start, end = timestamp(match[1]), timestamp(match[2])
        if end <= start:
            raise IngestionError("Caption end time must follow its start time")
        cue = " ".join(lines[position + 1:])
        voices = list(re.finditer(r"<v(?:\.[^\s>]+)?\s+([^>]+)>(.*?)(?:</v>|(?=<v[\s.])|$)", cue))
        if voices:
            for voice in voices:
                spoken = html.unescape(re.sub(r"<[^>]*>", "", voice[2]))
                if clean(spoken):
                    result.append(segment(spoken, len(result) + 1, start, end, html.unescape(voice[1]).strip()))
        else:
            cue = html.unescape(re.sub(r"<[^>]*>", "", cue))
            if clean(cue):
                result.append(segment(cue, len(result) + 1, start, end))
    return result


def docx_text(data):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            info = archive.getinfo("word/document.xml")
            if info.file_size > 8 * 1024 * 1024:
                raise IngestionError("DOCX text content is too large")
            xml = archive.read(info)
        if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:
            raise IngestionError("Unsupported DOCX XML declarations")
        root = ET.fromstring(xml)
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        paragraphs = []
        for paragraph in root.findall(".//w:p", ns):
            paragraphs.append("".join(node.text or "" for node in paragraph.findall(".//w:t", ns)))
        return "\n".join(paragraphs)
    except (zipfile.BadZipFile, KeyError, ET.ParseError, RuntimeError) as error:
        raise IngestionError("Corrupt or unsupported DOCX document") from error


def parse_docx(data):
    return parse_text(docx_text(data))


def parse_transcript(data, suffix):
    if suffix not in TEXT_FORMATS:
        raise IngestionError("Unsupported transcript format")
    if not data or len(data) > MAX_TEXT_BYTES:
        raise IngestionError("Transcript must be non-empty and at most 2 MB")
    if suffix == ".docx":
        result = parse_docx(data)
    else:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise IngestionError("Text and caption files must use UTF-8 encoding") from error
        if "\x00" in text:
            raise IngestionError("File does not contain a supported text transcript")
        result = parse_captions(text, suffix) if suffix in {".vtt", ".srt"} else parse_text(text)
    if not result:
        raise IngestionError("No transcript utterances found")
    if sum(len(item["text"]) for item in result) > MAX_CHARACTERS:
        raise IngestionError("Transcript exceeds the 500,000 character limit")
    return result
