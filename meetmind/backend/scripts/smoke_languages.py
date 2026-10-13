"""Real local-model smoke; synthetic fixtures, NOT an accuracy benchmark.

Run from backend: python -m scripts.smoke_languages
Does not alter the user's meeting DB. Requires Ollama and configured BERT/spaCy.
"""
import json
from pathlib import Path
import tempfile
import time
import argparse

from fastapi.testclient import TestClient
from app import main


def main_run():
    parser=argparse.ArgumentParser()
    parser.add_argument('--fixture',help='Run one named fixture')
    args=parser.parse_args()
    fixtures=[('English','en','Ali: I will send the report by Friday.'),
              ('Roman Urdu','roman-ur','Ali: Main report kal bhej dunga.'),
              ('Urdu','ur','علی: میں رپورٹ کل بھیج دوں گا۔'),
              ('Mixed','mixed','Ali: Main report kal bhej dunga.\nSara: I will review the report by Friday.')]
    supplied=Path('tests/fixtures/urdu-project-review.txt')
    if supplied.exists():fixtures.append(('User-provided Urdu','ur',supplied.read_text(encoding='utf-8')))
    if args.fixture:fixtures=[f for f in fixtures if f[0]==args.fixture]
    errors=[]
    def trace_async(module,name):
        original=getattr(module,name)
        async def wrapped(*args,**kwargs):
            try:return await original(*args,**kwargs)
            except Exception as error:
                errors.append({'stage':name,'type':type(error).__name__,'reason':str(error)})
                print('Validation failure:',name,type(error).__name__,str(error)[:400],flush=True)
                raise
        setattr(module,name,wrapped)
    trace_async(main.languages,'translate')
    trace_async(main.commitments,'propose')
    results=[]
    with tempfile.TemporaryDirectory(prefix='meetmind-language-smoke-') as directory:
        main.DB_PATH=Path(directory)/'smoke.db'
        with TestClient(main.app) as client:
            for title,language,transcript in fixtures:
                print(f'Running {title}...',flush=True)
                start=time.monotonic()
                response=client.post('/api/meetings',json={'title':title,'transcript':transcript,'input_language':language})
                response.raise_for_status()
                meeting=response.json()
                response=client.post(f"/api/meetings/{meeting['id']}/extract")
                result={'fixture':title,'status_code':response.status_code,'elapsed_seconds':round(time.monotonic()-start,2)}
                if response.status_code==200:
                    analyzed=response.json()
                    assert analyzed['original_transcript']==transcript
                    for item in analyzed['actions']+analyzed.get('action_candidates',[]):
                        for evidence in item['evidence']:
                            parent=next(s for s in analyzed['source_segments'] if s['id']==evidence['parent_source_id'])
                            assert parent['text'][evidence['source_start']:evidence['source_end']]==evidence['quote']
                    result.update(actions=analyzed['actions'],candidates=analyzed.get('action_candidates',[]),
                                  dialogue_analysis=analyzed['dialogue_analysis'],extraction=analyzed['extraction'])
                    result['explicit_promise_found']=bool(analyzed['actions'])
                    if analyzed['actions']:
                        item=analyzed['actions'][0]
                        review=client.post(f"/api/meetings/{meeting['id']}/commitments/{item['id']}/review",json={
                            'revision':item['revision'],'task':item['task'],'owner':item['owner'],
                            'deadline':item['deadline'],'decision':'approved','note':'Synthetic multilingual smoke review'})
                        review.raise_for_status()
                        assert client.get(f"/api/meetings/{meeting['id']}").json()['actions'][0]['review_status']=='approved'
                        result['review_persistence']=True
                else:result['error']=response.json()
                result['validation_errors']=errors[:];errors.clear()
                results.append(result)
                print(f"{title}: HTTP {response.status_code}, {result['elapsed_seconds']}s; promise found={result.get('explicit_promise_found')}",flush=True)
    filename='language-smoke-'+args.fixture.lower().replace(' ','-')+'.json' if args.fixture else 'language-smoke.json'
    output=Path('runs')/filename;output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps({'synthetic_fixtures':True,'accuracy_benchmark':False,'model':main.MULTILINGUAL_MODEL,'results':results},ensure_ascii=False,indent=2),encoding='utf-8')
    print('Saved',output,flush=True)
    if any(r['status_code']!=200 or not r.get('explicit_promise_found') for r in results):raise SystemExit(1)


if __name__=='__main__':main_run()
