"""Deadline normalisation and priority cues; deterministic rules, never model guesses.

A deadline phrase from the transcript ("by Friday", "kal", "15 November") is resolved
to a calendar date relative to the meeting date. Anything ambiguous or unrecognised
stays ``None`` with a reason, and a person can enter the date during review. The
original wording is always kept as evidence.
"""
from datetime import date, datetime, timedelta, timezone
import calendar
import os
import re

WEEKDAYS = {'monday': 0, 'mon': 0, 'tuesday': 1, 'tue': 1, 'tues': 1, 'wednesday': 2, 'wed': 2, 'thursday': 3, 'thu': 3,
            'thurs': 3, 'friday': 4, 'fri': 4, 'saturday': 5, 'sat': 5, 'sunday': 6, 'sun': 6,
            'peer': 0, 'pir': 0, 'mangal': 1, 'budh': 2, 'jumerat': 3, 'jumeraat': 3, 'jumma': 4, 'juma': 4, 'jumah': 4,
            'hafta': 5, 'itwar': 6, 'پیر': 0, 'منگل': 1, 'بدھ': 2, 'جمعرات': 3, 'جمعہ': 4, 'ہفتہ': 5, 'ہفتے': 5, 'اتوار': 6}
MONTHS = {name.lower(): number for number, name in enumerate(calendar.month_name) if name}
MONTHS.update({name.lower(): number for number, name in enumerate(calendar.month_abbr) if name})
MONTHS['sept'] = 9
HIGH = re.compile(r"\b(?:urgent(?:ly)?|asap|as soon as possible|immediately|right away|top priority|high priority|critical|"
                  r"end of (?:the )?day|eod|zaroori|zaruri|fori|foran|jaldi)\b|فوری|ضروری|جلدی", re.I)
LOW = re.compile(r"\b(?:no rush|whenever|low priority|not urgent|eventually|when you (?:get|have) (?:a )?(?:chance|time)|"
                 r"aaram se|araam se)\b", re.I)


def meeting_reference(meeting):
    """The meeting's local date; falls back to today (flagged) for meetings without one."""
    offset = timezone(timedelta(hours=float(os.getenv('MEETMIND_UTC_OFFSET_HOURS', '5'))))
    for key in ('meeting_date', 'created_at'):
        if meeting.get(key):
            return datetime.fromisoformat(meeting[key]).astimezone(offset).date(), key
    return datetime.now(offset).date(), 'assumed_today'


def result(value, method, reason=None):
    return {'date': value.isoformat() if value else None, 'method': method, 'reason': reason}


def upcoming(reference, weekday, strictly_after=False):
    days = (weekday - reference.weekday()) % 7
    if days == 0 and strictly_after:
        days = 7
    return reference + timedelta(days=days)


def normalize(text, reference):
    """Resolve one deadline phrase. Returns ``{'date', 'method', 'reason'}``."""
    if not text:
        return result(None, 'none', 'no_deadline')
    t = re.sub(r'\s+', ' ', text.strip().lower())
    if match := re.search(r'\b(\d{4})-(\d{2})-(\d{2})\b', t):
        return result(safe_date(int(match[1]), int(match[2]), int(match[3])), 'iso_date')
    if match := re.search(r'\b(\d{1,2})[/.](\d{1,2})(?:[/.](\d{2,4}))?\b', t):
        year = int(match[3]) + (2000 if match[3] and len(match[3]) == 2 else 0) if match[3] else reference.year
        value = safe_date(year, int(match[2]), int(match[1]))  # day first, as written in Pakistan
        return result(value, 'numeric_date', 'day_first_assumed' if value else 'invalid_date')
    month_words = '|'.join(sorted(MONTHS, key=len, reverse=True))
    if (match := re.search(rf'\b(\d{{1,2}})(?:st|nd|rd|th)? (?:of )?({month_words})\b(?: (\d{{4}}))?', t)) or \
            (match := re.search(rf'\b({month_words}) (\d{{1,2}})(?:st|nd|rd|th)?\b(?:,? (\d{{4}}))?', t)):
        day, month = (match[1], match[2]) if match[1].isdigit() else (match[2], match[1])
        value = safe_date(int(match[3]) if match[3] else reference.year, MONTHS[month], int(day))
        if value and not match[3] and value < reference:
            value = safe_date(reference.year + 1, MONTHS[month], int(day))
        return result(value, 'calendar_date', None if value else 'invalid_date')
    if re.search(r'\bday after tomorrow\b|\bparso[n]?\b|پرسوں', t):
        return result(reference + timedelta(days=2), 'relative_day')
    if re.search(r'\btomorrow\b|\bkal\b|(?<!\S)کل(?!\S)', t):
        return result(reference + timedelta(days=1), 'relative_day', 'kal_read_as_tomorrow' if re.search(r'\bkal\b|کل', t) else None)
    if re.search(r'\btoday\b|\btonight\b|\baaj\b|آج|end of (?:the )?day|\beod\b', t):
        return result(reference, 'relative_day')
    if match := re.search(r'\bin (\d{1,3}|a|one|two|three|four) (day|week)s?\b', t):
        count = {'a': 1, 'one': 1, 'two': 2, 'three': 3, 'four': 4}.get(match[1]) or int(match[1])
        return result(reference + timedelta(days=count * (7 if match[2] == 'week' else 1)), 'relative_offset')
    if re.search(r'\bend of (?:the |this )?month\b|\bthis month\b', t):
        return result(reference.replace(day=calendar.monthrange(reference.year, reference.month)[1]), 'end_of_period')
    if re.search(r'\bnext month\b', t):
        year, month = (reference.year + 1, 1) if reference.month == 12 else (reference.year, reference.month + 1)
        return result(date(year, month, calendar.monthrange(year, month)[1]), 'end_of_period', 'period_end_assumed')
    if re.search(r'\bend of (?:the |this )?week\b|\bthis week\b', t):
        return result(max(reference, upcoming(reference, 4)), 'end_of_period', 'working_week_ends_friday')
    if re.search(r'\bnext week\b|\baglay hafte\b|\bagle hafte\b|اگلے ہفتے', t):
        return result(upcoming(reference, 4) + timedelta(days=7), 'end_of_period', 'period_end_assumed')
    for word, weekday in sorted(WEEKDAYS.items(), key=lambda item: -len(item[0])):
        if re.search(rf'(?<!\w){re.escape(word)}(?!\w)', t):
            if re.search(rf'\bnext {re.escape(word)}\b', t):
                # "next Friday" said early in a week usually means the following week's Friday.
                return result(upcoming(reference, weekday, True) + timedelta(days=7 if weekday > reference.weekday() else 0),
                              'weekday', 'next_weekday_interpretation')
            return result(upcoming(reference, weekday), 'weekday')
    if re.search(r'\b\d{1,2}(?::\d{2})? ?(?:am|pm)\b|\bo\'?clock\b|\bbaj[ae]y?\b|بجے', t):
        return result(reference, 'time_only', 'time_without_date_assumed_same_day')
    return result(None, 'unrecognized', 'phrase_not_a_calendar_date')


def safe_date(year, month, day):
    try:
        return date(year, month, day)
    except ValueError:
        return None


def priority(text):
    """'high' or 'low' from explicit urgency words in the evidence; otherwise 'normal'."""
    if match := HIGH.search(text or ''):
        return 'high', match[0]
    if match := LOW.search(text or ''):
        return 'low', match[0]
    return 'normal', None


def annotate(meeting, items):
    """Add normalised deadlines, priority and a review score to extracted items (in place)."""
    reference, source = meeting_reference(meeting)
    threshold = float(os.getenv('MEETMIND_COMMITMENT_REVIEW_THRESHOLD', '0.5'))
    for item in items:
        resolved = normalize(item.get('deadline'), reference)
        item['deadline_normalized'] = resolved['date']
        item['deadline_resolution'] = {**resolved, 'reference_date': reference.isoformat(), 'reference': source}
        quote = ' '.join(e.get('quote', '') for e in item.get('evidence', [])[:1])
        item['priority'], item['priority_cue'] = priority(quote + ' ' + (item.get('deadline') or ''))
        item['confidence'] = score(item)
        reasons = item.setdefault('review_reasons', [])
        if source == 'assumed_today' and resolved['date']:
            reasons.append('deadline_reference_date_assumed')
        if item['deadline'] and not resolved['date']:
            reasons.append('deadline_not_normalized')
        if item['confidence']['score'] < threshold:
            reasons.append('low_confidence_score')
    return items


def score(item):
    """Heuristic review score in [0, 1]; a prioritisation aid, not a calibrated probability.

    It multiplies BERT's (temperature-calibrated, when available) probability that the
    source is an action-related dialogue act with penalties for a missing owner or date.
    """
    signals = [s.get('action_probability') for s in item.get('bert_signals', []) if s.get('action_probability') is not None]
    action = max(signals) if signals else None
    owner = 1.0 if item.get('owner') else 0.8
    deadline = 1.0 if item.get('deadline_normalized') else 0.9
    value = (action if action is not None else 0.5) * owner * deadline
    return {'score': round(value, 4), 'action_probability': None if action is None else round(action, 4),
            'owner_factor': owner, 'deadline_factor': deadline, 'kind': 'heuristic_review_score'}
