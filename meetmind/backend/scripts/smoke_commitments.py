"""Real local BERT + spaCy + Ollama API checks against synthetic meeting examples."""
import argparse
import json
from pathlib import Path
import tempfile
import time
from fastapi.testclient import TestClient
from app import main

CASES = [
    ('promise', 'Sara: I will send the project report by Friday.', 'Sara', 'Friday'),
    ('suggestion and negation', 'Sara: We should redesign the dashboard.\nAli: I will not send the budget report.', None, None),
    ('later cancellation', 'Sara: I will send the project report by Friday.\nAli: Cancel the project report.', 'Sara', None),
    ('ambiguous owner', 'Sara: We will book the meeting room tomorrow.', None, 'tomorrow'),
]


def smoke(output):
    previous = main.DB_PATH
    results = []
    try:
        with tempfile.TemporaryDirectory(prefix='meetmind-commitments-') as directory:
            main.DB_PATH = Path(directory) / 'smoke.db'
            with TestClient(main.app) as client:
                for name, text, owner, deadline in CASES:
                    meeting = client.post('/api/meetings', json={'title': name, 'transcript': text}).json()
                    started = time.monotonic()
                    response = client.post(f'/api/meetings/{meeting["id"]}/extract')
                    assert response.status_code == 200, response.text
                    result = response.json()
                    assert client.get(f'/api/meetings/{meeting["id"]}').json() == result
                    assert all(a['needs_review'] for a in result['actions'] + result['action_candidates'])
                    assert all(i in {s['id'] for s in result['segments']} for a in result['actions'] + result['action_candidates'] for i in a['source_ids'])
                    if name == 'suggestion and negation':
                        assert not result['actions'], result['actions']
                    else:
                        assert result['actions'], result
                        assert result['actions'][0]['owner'] == owner, result['actions']
                        if deadline:
                            assert deadline.lower() in (result['actions'][0]['deadline'] or '').lower(), result['actions']
                        if name == 'later cancellation':
                            assert result['actions'][0]['status'] == 'possible_cancellation', result['actions']
                    summary = {'case': name, 'seconds': round(time.monotonic() - started, 2),
                               'actions': result['actions'], 'candidates': result['action_candidates'],
                               'bert_model': result['dialogue_analysis']['model'], 'extraction': result['extraction']}
                    results.append(summary)
                    print(json.dumps({'case': name, 'seconds': summary['seconds'], 'actions': len(result['actions']),
                                      'candidates': len(result['action_candidates']), 'result': 'pass'}), flush=True)
    finally:
        main.DB_PATH = previous
        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps({'cases': results, 'all_passed': len(results) == len(CASES),
                                          'dataset': 'synthetic functional checks; not an accuracy benchmark'}, indent=2), encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    smoke(parser.parse_args().output)
