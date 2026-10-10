"""Exercise real full-meeting uploads and BERT analysis without touching final test data."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import tempfile
import time

from fastapi.testclient import TestClient
from app import main
from app.bert import DialogueClassifier, model_path
from nlp.data import load_split, session_group, sha256, write_json
from nlp.metrics import classification_metrics


def audit(output, workspace_files):
    output = Path(output)
    if output.exists():
        raise ValueError('Choose a new output directory to preserve audit evidence')
    output.mkdir(parents=True)
    rows, manifest = load_split('data/ami-da-v1', 'validation')
    by_meeting = defaultdict(list)
    for row in rows:
        by_meeting[row['meeting_id']].append(row)
    # Deterministic first meeting from each independent validation session.
    seen, selected = set(), []
    for meeting in sorted(by_meeting):
        group = session_group(meeting)
        if group not in seen:
            selected.append(meeting); seen.add(group)
    selected = selected[:5]
    cases = []
    for meeting in selected:
        items = by_meeting[meeting]
        text = '\n'.join(r['speaker'] + ': ' + r['text'] for r in items)
        cases.append({'name': f'AMI {meeting}', 'text': text, 'gold_rows': items,
                      'source': 'AMI validation; official annotations; full meeting'})
    for path in workspace_files:
        cases.append({'name': path.name, 'text': path.read_text(encoding='utf-8-sig'),
                      'gold_rows': None, 'source': 'workspace transcript report; no verified gold labels'})
    tokenizer = DialogueClassifier(model_path()).tokenizer
    results, all_gold, all_predicted = [], [], []
    fixture_manifest = []
    previous_db = main.DB_PATH
    started = time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix='meetmind-real-meetings-') as directory:
            main.DB_PATH = Path(directory) / 'audit.db'
            with TestClient(main.app) as client:
                for index, case in enumerate(cases):
                    fixture = output / 'fixtures' / f'case-{index+1}.txt'
                    fixture.parent.mkdir(parents=True, exist_ok=True)
                    fixture.write_text(case['text'], encoding='utf-8')
                    uploaded = client.post('/api/ingestion/transcript',
                        data={'title': case['name']}, files={'file': (fixture.name, fixture.read_bytes(), 'text/plain')})
                    assert uploaded.status_code == 201, uploaded.text
                    meeting = uploaded.json()
                    original_segments = meeting['segments']
                    before = time.monotonic()
                    response = client.post(f'/api/meetings/{meeting["id"]}/classify')
                    duration = time.monotonic() - before
                    assert response.status_code == 200, response.text
                    analyzed = response.json()
                    predictions = analyzed['dialogue_analysis']['predictions']
                    assert [p['source_id'] for p in predictions] == [s['id'] for s in original_segments]
                    assert analyzed['segments'] == original_segments
                    assert analyzed['actions'] == []
                    assert client.get(f'/api/meetings/{meeting["id"]}').json() == analyzed
                    assert all(not p['possible_action'] or p['needs_review'] for p in predictions)
                    assert all(not p.get('input_truncated') or p['needs_review'] for p in predictions)
                    json_export = client.get(f'/api/meetings/{meeting["id"]}/transcript?format=json')
                    assert json_export.status_code == 200
                    assert json_export.json()['segments'] == original_segments
                    counts = Counter(p['label'] for p in predictions)
                    target_lengths = tokenizer([s['text'] for s in original_segments],
                        add_special_tokens=False, truncation=False, return_length=True, verbose=False)['length']
                    metadata = json.loads((model_path() / 'meetmind_model.json').read_text(encoding='utf-8'))
                    long_ids = [s['id'] for s, length in zip(original_segments, target_lengths)
                                if length + 3 > metadata['max_length']]
                    result = {'name': case['name'], 'source': case['source'],
                              'segments': len(predictions), 'characters': len(case['text']),
                              'analysis_seconds': duration, 'labels': dict(counts),
                              'needs_review': sum(p['needs_review'] for p in predictions),
                              'possible_actions': sum(p['possible_action'] for p in predictions),
                              'target_exceeds_token_budget': len(long_ids),
                              'reported_input_truncated': sum(p.get('input_truncated', False) for p in predictions),
                              'reported_target_truncated': sum(p.get('target_text_truncated', False) for p in predictions),
                              'long_source_ids': long_ids, 'max_target_tokens': max(target_lengths),
                              'source_sha256': sha256(fixture),
                              'functional_checks': 'pass: upload, analysis, source IDs/text, persistence, export, review guards'}
                    if case['gold_rows'] is not None:
                        gold_rows = case['gold_rows']
                        assert len(gold_rows) == len(predictions)
                        gold = [r['label'] for r in gold_rows]
                        predicted = [p['label'] for p in predictions]
                        result['metrics'] = classification_metrics(gold, predicted, sorted(manifest['labels']))
                        result['errors'] = [{'annotation_id': r['id'], 'source_id': p['source_id'],
                                             'gold': r['label'], 'predicted': p['label'],
                                             'score': p['score'], 'needs_review': p['needs_review']}
                                            for r, p in zip(gold_rows, predictions) if r['label'] != p['label']]
                        result['high_score_errors'] = sum(e['score'] >= .7 for e in result['errors'])
                        result['errors_without_review'] = sum(not e['needs_review'] for e in result['errors'])
                        all_gold.extend(gold); all_predicted.extend(predicted)
                    results.append(result)
                    fixture_manifest.append({'name': case['name'], 'file': str(fixture.resolve()),
                                             'segments': len(predictions)})
                    print(json.dumps({k: v for k, v in result.items() if k not in ['metrics','errors','long_source_ids']}, ensure_ascii=True), flush=True)
    finally:
        main.DB_PATH = previous_db
    report = {'checkpoint_sha256': sha256(model_path() / 'model.safetensors'),
              'selection': 'first chronological meeting ID per validation session; no outcome selection',
              'test_set_used': False, 'dataset_manifest_sha256': sha256('data/ami-da-v1/manifest.json'),
              'cases': results, 'annotated_ami_metrics': classification_metrics(all_gold, all_predicted, sorted(manifest['labels'])),
              'elapsed_seconds': time.monotonic() - started,
              'limitations': ['Validation cases are a subset of the already evaluated validation split, not new independent test evidence.',
                             'Workspace report provenance is unverified and no accuracy is claimed for those files.',
                             'Gold AMI act boundaries differ from unsegmented real reports.',
                             'Latency is a local observation, not a service guarantee.']}
    write_json(output / 'audit.json', report)
    write_json(output / 'fixtures.json', fixture_manifest)
    print('Report:', output / 'audit.json')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workspace-files', type=Path, nargs='*', default=[])
    args = parser.parse_args()
    audit(args.output, args.workspace_files)
