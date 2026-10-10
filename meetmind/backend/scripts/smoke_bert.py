"""Exercise a real saved BERT checkpoint through API/persistence in an isolated DB."""
import json
from pathlib import Path
import tempfile

from fastapi.testclient import TestClient
from app import main


def main_check():
    old_path = main.DB_PATH
    try:
        with tempfile.TemporaryDirectory(prefix='meetmind-bert-check-') as directory:
            main.DB_PATH = Path(directory) / 'smoke.db'
            with TestClient(main.app) as client:
                response = client.post('/api/meetings', json={
                    'title': 'BERT verification fixture',
                    'transcript': 'Sara: I will send the project report by Friday.\nAhmed: Can you book the room?\nSara: Yes.'})
                assert response.status_code == 201, response.text
                meeting_id = response.json()['id']
                result = client.post(f'/api/meetings/{meeting_id}/classify')
                assert result.status_code == 200, result.text
                meeting = result.json()
                analysis = meeting['dialogue_analysis']
                assert [p['source_id'] for p in analysis['predictions']] == [1, 2, 3]
                assert all(0 <= p['score'] <= 1 for p in analysis['predictions'])
                assert analysis['model']['confidence_calibrated'] is False
                assert len(analysis['model']['model_weights_sha256']) == 64
                assert meeting['actions'] == [], 'Dialogue-act analysis must not create confirmed commitments'
                assert client.get(f'/api/meetings/{meeting_id}').json() == meeting
                assert client.post(f'/api/meetings/{meeting_id}/classify').json() == meeting
                print(json.dumps(analysis, indent=2))
                print('Real local checkpoint, API inference, stable repeat inference and persistence verified.')
    finally:
        main.DB_PATH = old_path


if __name__ == '__main__':
    main_check()
