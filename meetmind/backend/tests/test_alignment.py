from app.connectors.alignment import build_intervals, label_segments, normalize_events


def seg(start, end, text='Send the report.'):
    return {'id': 1, 'speaker': None, 'text': text, 'source': text, 'start': start, 'end': end}


def on(t, speaker):
    return {'t': t, 'speaker': speaker, 'active': True}


def off(t, speaker):
    return {'t': t, 'speaker': speaker, 'active': False}


def test_normalize_converts_epoch_maps_self_and_drops_bad_events():
    raw = [{'t': 12_000, 'speaker': 'Sara', 'active': False}, {'t': 11_000, 'speaker': 'You'},
           {'t': 9_999, 'speaker': 'Early'}, {'t': 'x', 'speaker': 'Bad'}, {'t': 11_500, 'speaker': ' '}, {'speaker': 'NoTime'}]
    assert normalize_events(raw, 10_000, self_name='Ali') == [
        {'t': 1.0, 'speaker': 'Ali', 'active': True}, {'t': 2.0, 'speaker': 'Sara', 'active': False}]


def test_normalize_keeps_you_without_self_name():
    assert normalize_events([{'t': 1000, 'speaker': 'You'}], 0)[0]['speaker'] == 'You'


def test_labels_segment_by_overlap():
    events = [on(0, 'Ali'), off(5, 'Ali'), on(5, 'Sara'), off(10, 'Sara')]
    labelled = label_segments([seg(0.5, 4.5), seg(5.5, 9)], events)
    assert [s['speaker'] for s in labelled] == ['Ali', 'Sara']
    assert all(s['speaker_confidence'] == 1.0 for s in labelled)


def test_lag_shifts_hints_earlier():
    events = [on(2.5, 'Ali'), off(7.5, 'Ali'), on(7.5, 'Sara'), off(12, 'Sara')]
    assert label_segments([seg(5.2, 6)], events)[0]['speaker'] == 'Ali'
    assert label_segments([seg(5.2, 6)], events, lag=1.0)[0]['speaker'] == 'Ali'
    assert label_segments([seg(2.0, 2.4)], events)[0]['speaker'] is None
    assert label_segments([seg(2.0, 2.4)], events, lag=1.0)[0]['speaker'] == 'Ali'


def test_silence_without_hints_stays_unattributed():
    labelled = label_segments([seg(20, 22)], [on(0, 'Ali'), off(5, 'Ali')])
    assert labelled[0]['speaker'] is None and labelled[0]['speaker_confidence'] == 0.0
    assert label_segments([seg(0, 2)], [])[0]['speaker'] is None


def test_simultaneous_speakers_are_ambiguous():
    events = [on(0, 'Ali'), on(0, 'Sara'), off(4, 'Ali'), off(4, 'Sara')]
    labelled = label_segments([seg(0, 4)], events)[0]
    assert labelled['speaker'] is None and labelled['speaker_confidence'] == 0.0


def test_dominant_speaker_wins_over_brief_interjection():
    events = [on(0, 'Ali'), off(10, 'Ali'), on(4, 'Sara'), off(5, 'Sara')]
    labelled = label_segments([seg(0, 10)], events)[0]
    assert labelled['speaker'] == 'Ali' and labelled['speaker_confidence'] == 0.9


def test_open_interval_runs_to_session_end_and_inputs_are_not_mutated():
    segments = [seg(8, 9)]
    assert build_intervals([on(2, 'Ali')], end=10)['Ali'] == [(2, 10)]
    assert label_segments(segments, [on(2, 'Ali')], end=10)[0]['speaker'] == 'Ali'
    assert segments[0]['speaker'] is None and 'speaker_confidence' not in segments[0]


def test_zero_length_segment_is_unattributed():
    assert label_segments([seg(3, 3)], [on(0, 'Ali'), off(5, 'Ali')])[0]['speaker'] is None
