"""Actual local Ollama + LangGraph draft/review in an isolated database; never sends."""
import json
from pathlib import Path
import tempfile
from fastapi.testclient import TestClient
from app import main


def run():
    previous=main.DB_PATH
    try:
        with tempfile.TemporaryDirectory(prefix='meetmind-artifacts-') as folder:
            main.DB_PATH=Path(folder)/'smoke.db'
            with TestClient(main.app) as client:
                meeting=client.post('/api/meetings',json={'title':'Follow-up smoke fixture',
                    'transcript':'Sara: I will send the project report by Friday.','input_language':'en'}).json()
                meeting['actions']=[{'id':'smoke-action','revision':0,'task':'Send the project report',
                    'owner':'Sara','deadline':'Friday','kind':'commitment','source_id':1,'needs_review':True,
                    'evidence':[{'quote':'I will send the project report by Friday.','source_ids':[1]}]}]
                main.save(meeting)
                reviewed=client.post(f"/api/meetings/{meeting['id']}/commitments/smoke-action/review",json={
                    'revision':0,'task':'Send the project report','owner':'Sara','deadline':'Friday','decision':'approved'})
                assert reviewed.status_code==200,reviewed.text
                response=client.post(f"/api/meetings/{meeting['id']}/artifacts",json={
                    'commitment_id':'smoke-action','commitment_revision':1,'to':['sara@example.com'],
                    'idempotency_key':'actual-ollama-smoke'})
                assert response.status_code==201,response.text
                draft=response.json()
                assert draft['status']=='draft' and draft['graph_steps']==['draft_email','validate_email']
                approved=client.post(f"/api/artifacts/{draft['id']}/review",json={'revision':draft['revision'],'decision':'approved'}).json()
                assert approved['approval_valid']
                edited=client.patch(f"/api/artifacts/{draft['id']}",json={'revision':approved['revision'],
                    'to':approved['to'],'subject':approved['subject'],'body':approved['body']+'\nPlease confirm receipt.'}).json()
                assert edited['approval'] is None and edited['status']=='draft'
                assert client.get('/api/artifacts/'+draft['id']).json()==edited
                output={'real_local_ollama':True,'real_langgraph':True,'model':draft['model'],
                    'steps':draft['graph_steps'],'approval_valid_before_edit':True,'approval_invalidated_by_edit':True,
                    'persistence_checked':True,'external_message_sent':False,'accuracy_benchmark':False,
                    'generated_subject':draft['subject'],'generated_body':draft['body']}
                Path('runs').mkdir(exist_ok=True)
                Path('runs/artifact-smoke.json').write_text(json.dumps(output,indent=2)+'\n')
                print(json.dumps(output,indent=2),flush=True)
    finally:main.DB_PATH=previous


if __name__=='__main__':run()
