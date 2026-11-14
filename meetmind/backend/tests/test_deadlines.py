import json
from datetime import date

import pytest

from app import bert, deadlines as d, main
from app.review import ReviewInput, apply

WEDNESDAY = date(2026, 11, 11)  # reference meeting date


@pytest.mark.parametrize('phrase,expected,reason', [
    ('by Friday', '2026-11-13', None),
    ('on Wednesday', '2026-11-11', None),
    ('Monday', '2026-11-16', None),
    ('next Friday', '2026-11-20', 'next_weekday_interpretation'),
    ('tomorrow', '2026-11-12', None),
    ('day after tomorrow', '2026-11-13', None),
    ('today', '2026-11-11', None),
    ('end of day', '2026-11-11', None),
    ('in 3 days', '2026-11-14', None),
    ('in two weeks', '2026-11-25', None),
    ('end of the month', '2026-11-30', None),
    ('next month', '2026-12-31', 'period_end_assumed'),
    ('this week', '2026-11-13', 'working_week_ends_friday'),
    ('next week', '2026-11-20', 'period_end_assumed'),
    ('15 November', '2026-11-15', None),
    ('November 3rd', '2027-11-03', None),          # already past this year
    ('2026-12-01', '2026-12-01', None),
    ('5/12', '2026-12-05', 'day_first_assumed'),
    ('31/02', None, 'invalid_date'),
    ('by 5 pm', '2026-11-11', 'time_without_date_assumed_same_day'),
    ('kal', '2026-11-12', 'kal_read_as_tomorrow'),
    ('parson', '2026-11-13', None),
    ('jumma tak', '2026-11-13', None),
    ('aglay hafte', '2026-11-20', 'period_end_assumed'),
    ('کل', '2026-11-12', 'kal_read_as_tomorrow'),
    ('پرسوں', '2026-11-13', None),
    ('دو بجے تک', '2026-11-11', 'time_without_date_assumed_same_day'),
    ('soon', None, 'phrase_not_a_calendar_date'),
    (None, None, 'no_deadline'),
])
def test_deadline_resolution_table(phrase, expected, reason):
    result = d.normalize(phrase, WEDNESDAY)
    assert result['date'] == expected and result['reason'] == reason


@pytest.mark.parametrize('text,level', [
    ('Please send it ASAP.', 'high'), ('This is urgent', 'high'), ('report zaroori hai', 'high'),
    ('یہ فوری بھیجیں', 'high'), ('No rush, whenever you can.', 'low'), ('I will send the report.', 'normal'),
])
def test_priority_cues(text, level):
    assert d.priority(text)[0] == level


def test_annotate_uses_the_meeting_date_and_scores(monkeypatch):
    meeting = {'created_at': '2026-11-11T09:00:00+00:00'}
    items = [{'deadline': 'by Friday', 'owner': 'Sara', 'evidence': [{'quote': 'I will send it urgently by Friday.'}],
              'bert_signals': [{'action_probability': 0.9}]},
             {'deadline': 'soonish', 'owner': None, 'evidence': [{'quote': 'Someone should look at it.'}],
              'bert_signals': [{'action_probability': 0.2}]}]
    d.annotate(meeting, items)
    first, second = items
    assert first['deadline_normalized'] == '2026-11-13' and first['priority'] == 'high'
    assert first['deadline_resolution']['reference_date'] == '2026-11-11' and first['confidence']['score'] == 0.9
    assert second['deadline_normalized'] is None and second['confidence']['score'] == round(0.2 * 0.8 * 0.9, 4)
    assert 'low_confidence_score' in second['review_reasons'] and 'deadline_not_normalized' in second['review_reasons']
    monkeypatch.setenv('MEETMIND_COMMITMENT_REVIEW_THRESHOLD', '0.1')
    third = [{'deadline': None, 'owner': 'Ali', 'evidence': [], 'bert_signals': [{'action_probability': 0.2}]}]
    d.annotate(meeting, third)
    assert 'low_confidence_score' not in third[0]['review_reasons']


def test_meeting_without_a_date_is_flagged():
    items = [{'deadline': 'tomorrow', 'owner': 'Sara', 'evidence': [], 'bert_signals': []}]
    d.annotate({}, items)
    assert items[0]['deadline_resolution']['reference'] == 'assumed_today'
    assert 'deadline_reference_date_assumed' in items[0]['review_reasons']


def test_review_renormalizes_or_accepts_a_confirmed_date():
    item = {'id': 'i1', 'revision': 0, 'task': 'Send', 'owner': 'Sara', 'deadline': 'by Friday', 'kind': 'commitment',
            'status': 'proposed', 'deadline_normalized': '2026-11-13', 'priority': 'normal',
            'deadline_resolution': {'date': '2026-11-13', 'method': 'weekday', 'reason': None, 'reference_date': '2026-11-11'}}
    meeting = {'actions': [item]}
    apply(meeting, 'i1', ReviewInput(revision=0, task='Send', owner='Sara', deadline='by Monday', decision='pending'))
    assert item['deadline_normalized'] == '2026-11-16' and item['deadline_resolution']['reference_date'] == '2026-11-11'
    apply(meeting, 'i1', ReviewInput(revision=1, task='Send', owner='Sara', deadline='next sprint',
                                     deadline_date=date(2026, 11, 27), priority='high', decision='approved'))
    assert item['deadline_normalized'] == '2026-11-27' and item['deadline_resolution']['method'] == 'human_review'
    assert item['priority'] == 'high' and item['review_history'][-1]['after']['deadline_normalized'] == '2026-11-27'


def test_calibration_must_match_the_weights(tmp_path):
    classifier = bert.DialogueClassifier.__new__(bert.DialogueClassifier)
    classifier.path, classifier.metadata = tmp_path, {'model_weights_sha256': 'abc', 'review_threshold': .7, 'review_margin': .15}
    assert classifier.load_calibration() == 1.0 and classifier.metadata['confidence_calibrated'] is False
    (tmp_path / 'calibration.json').write_text(json.dumps({'method': 'temperature scaling', 'temperature': 1.7,
                                                           'fitted_on': 'validation', 'model_weights_sha256': 'abc'}))
    assert classifier.load_calibration() == 1.7 and classifier.metadata['confidence_calibrated'] is True
    (tmp_path / 'calibration.json').write_text(json.dumps({'method': 'temperature scaling', 'temperature': 1.7,
                                                           'fitted_on': 'validation', 'model_weights_sha256': 'other'}))
    with pytest.raises(ValueError):
        classifier.load_calibration()


def test_review_thresholds_can_be_configured(monkeypatch):
    classifier = bert.DialogueClassifier.__new__(bert.DialogueClassifier)
    classifier.metadata = {'review_threshold': .7, 'review_margin': .15}
    assert classifier.thresholds() == (.7, .15)
    monkeypatch.setenv('MEETMIND_REVIEW_THRESHOLD', '0.55')
    monkeypatch.setenv('MEETMIND_REVIEW_MARGIN', '0.05')
    assert classifier.thresholds() == (.55, .05)


def test_new_meetings_record_their_date(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    monkeypatch.setattr(main, 'DB_PATH', tmp_path / 'dates.db')
    meeting = TestClient(main.app).post('/api/meetings', json={'title': 'Dated', 'transcript': 'Sara: I will send it.'}).json()
    assert meeting['created_at'] and d.meeting_reference(meeting)[1] == 'created_at'
