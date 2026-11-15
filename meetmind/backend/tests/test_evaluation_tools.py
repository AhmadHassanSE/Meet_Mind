import csv
import json

import pytest

from scripts import annotation_sample, annotation_score, score_extraction as e2e


def write(path, rows, fields):
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fields)
        writer.writeheader()
        writer.writerows(rows)


def test_kappa_agreement_and_disagreement_log(tmp_path):
    ids = [f'u{i}' for i in range(6)]
    a = ['inf', 'sug', 'off', 'bck', 'inf', 'ass']
    b = ['inf', 'sug', 'sug', 'bck', 'inf', 'inf']
    gold = ['inf', 'sug', 'off', 'bck', 'ass', 'ass']
    for name, labels in (('a', a), ('b', b)):
        write(tmp_path / f'{name}.csv', [{'id': i, 'text': f'text {i}', 'label': l, 'unsure': ''} for i, l in zip(ids, labels)],
              ['id', 'text', 'label', 'unsure'])
    write(tmp_path / 'key.csv', [{'id': i, 'ami_label': g} for i, g in zip(ids, gold)], ['id', 'ami_label'])
    result = annotation_score.score(tmp_path / 'a.csv', tmp_path / 'b.csv', tmp_path / 'key.csv')
    assert result['items'] == 6 and result['agreement'] == pytest.approx(4 / 6)
    assert 0 < result['cohen_kappa'] < 1
    assert result['annotator_a_vs_ami']['accuracy'] == pytest.approx(5 / 6)
    assert [(d['annotator_a'], d['annotator_b']) for d in result['disagreements']] == [('off', 'sug'), ('ass', 'inf')]


def test_unknown_labels_are_rejected(tmp_path):
    write(tmp_path / 'a.csv', [{'id': 'u1', 'text': 't', 'label': 'promise'}], ['id', 'text', 'label'])
    write(tmp_path / 'b.csv', [{'id': 'u1', 'text': 't', 'label': 'off'}], ['id', 'text', 'label'])
    write(tmp_path / 'key.csv', [{'id': 'u1', 'ami_label': 'off'}], ['id', 'ami_label'])
    with pytest.raises(ValueError, match='Unknown labels'):
        annotation_score.score(tmp_path / 'a.csv', tmp_path / 'b.csv', tmp_path / 'key.csv')


def test_stratified_sample_covers_rare_labels():
    rows = [{'id': f'r{i}', 'label': 'inf'} for i in range(500)] + [{'id': f'o{i}', 'label': 'off'} for i in range(3)]
    picked = annotation_sample.sample(rows, 20, 5, 42)
    assert len(picked) == 20 and sum(r['label'] == 'off' for r in picked) == 3
    assert picked == annotation_sample.sample(rows, 20, 5, 42)  # deterministic for a seed


def test_end_to_end_scoring_rules():
    gold = [{'kind': 'commitment', 'owner': 'Sara', 'deadline_date': '2026-11-13', 'quote': 'I will send the report by Friday.'},
            {'kind': 'commitment', 'owner': None, 'deadline_date': None, 'quote': 'Someone needs to fix the build.'},
            {'kind': 'suggestion', 'owner': None, 'deadline_date': None, 'quote': 'We should book the room.'}]
    predicted = [{'kind': 'commitment', 'owner': 'sara', 'deadline_date': '2026-11-13', 'quote': 'I will send the report by Friday'},
                 {'kind': 'suggestion', 'owner': None, 'deadline_date': None, 'quote': 'We should book the room'},
                 {'kind': 'commitment', 'owner': 'Ali', 'deadline_date': None, 'quote': 'Ali will order lunch.'}]
    result = e2e.score([('case-1', gold, predicted)])
    assert result['totals']['true_positive_commitments'] == 1
    assert result['commitment_precision'] == 0.5 and result['commitment_recall'] == 0.5
    assert result['owner_accuracy'] == 1.0 and result['deadline_accuracy'] == 1.0 and result['kind_accuracy'] == 1.0


def test_example_gold_file_is_valid():
    from pathlib import Path
    for path in Path('evaluation/e2e').glob('*.json'):
        case = json.loads(path.read_text(encoding='utf-8'))
        assert case['meeting_date'] and case['transcript'] and isinstance(case['gold'], list)
        for item in case['gold']:
            assert item['kind'] in {'commitment', 'suggestion', 'request', 'cancellation'}
            assert item['quote'] in case['transcript']
