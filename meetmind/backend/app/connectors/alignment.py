"""Label Whisper segments with speaker hints captured from the Google Meet page.

Hints are timestamped events ``{"t": seconds, "speaker": name, "active": bool}``
meaning a participant started or stopped speaking. They are only hints: when
they are missing or ambiguous a segment stays unattributed instead of guessed.
"""
from collections import defaultdict

MAX_NAME_LENGTH = 80
SELF_ALIASES = {"you", "you (presenting)"}


def normalize_events(raw, started_at_ms, self_name=None):
    """Convert raw extension events (epoch milliseconds) to sorted second-based events."""
    events = []
    for item in raw or []:
        try:
            seconds = (float(item["t"]) - float(started_at_ms)) / 1000
            speaker = str(item["speaker"]).strip()[:MAX_NAME_LENGTH]
            active = bool(item.get("active", True))
        except (KeyError, TypeError, ValueError):
            continue
        if not speaker or seconds < 0:
            continue
        if self_name and speaker.lower() in SELF_ALIASES:
            speaker = self_name.strip()
        events.append({"t": seconds, "speaker": speaker, "active": active})
    return sorted(events, key=lambda event: event["t"])


def build_intervals(events, lag=0.0, end=None):
    """Return ``{speaker: [(start, end), ...]}``; hints appear ``lag`` seconds after speech starts."""
    open_since = {}
    intervals = defaultdict(list)
    for event in events:
        moment = max(0.0, event["t"] - lag)
        speaker = event["speaker"]
        if event["active"]:
            open_since.setdefault(speaker, moment)
        elif speaker in open_since:
            start = open_since.pop(speaker)
            if moment > start:
                intervals[speaker].append((start, moment))
    for speaker, start in open_since.items():
        stop = end if end is not None else float("inf")
        if stop > start:
            intervals[speaker].append((start, stop))
    return intervals


def overlap(a_start, a_end, b_start, b_end):
    return max(0.0, min(a_end, b_end) - max(a_start, b_start))


def label_segments(segments, events, lag=0.0, min_confidence=0.4, end=None):
    """Return copies of ``segments`` with ``speaker`` and ``speaker_confidence`` set.

    Confidence is the gap between the best and runner-up speaker overlap as a
    fraction of the segment length, so simultaneous speakers lower confidence.
    Below ``min_confidence`` the speaker is ``None``.
    """
    intervals = build_intervals(events, lag, end)
    labelled = []
    for segment in segments:
        start, stop = segment["start"], segment["end"]
        duration = stop - start
        totals = sorted(
            ((sum(overlap(start, stop, a, b) for a, b in spans), -spans[0][0], name)
             for name, spans in intervals.items()),
            reverse=True)
        totals = [item for item in totals if item[0] > 0]
        speaker, confidence = None, 0.0
        if totals and duration > 0:
            runner_up = totals[1][0] if len(totals) > 1 else 0.0
            confidence = max(0.0, (totals[0][0] - runner_up) / duration)
            if confidence >= min_confidence:
                speaker = totals[0][2]
        labelled.append({**segment, "speaker": speaker, "speaker_confidence": round(min(confidence, 1.0), 2)})
    return labelled
