import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from app import commitments, languages, main, media, urdu
from app.preprocessing import prepare


@pytest.mark.parametrize('text,expected',[
    ('I will send the main report tomorrow.','en'),
    ('Main report kal bhej dunga.','roman-ur'),
    ('میں رپورٹ کل بھیج دوں گا۔','ur'),
    ('Report nahi bhejna.','roman-ur'),
])
def test_language_routing(text,expected):
    assert languages.detect(text)==expected


def test_urdu_speakers_punctuation_and_source_offsets():
    meeting=prepare('علی: میں رپورٹ بھیجوں گا۔ کیا آپ دیکھیں گے؟\nsara: Main kal review karungi.')
    assert [s['speaker'] for s in meeting['source_segments']]==['علی','sara']
    assert len(meeting['segments'])==3
    for segment in meeting['segments']:
        parent=next(p for p in meeting['source_segments'] if p['id']==segment['parent_source_id'])
        assert parent['text'][segment['source_start']:segment['source_end']]==segment['source']


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(main,'DB_PATH',tmp_path/'language.db')
    with TestClient(main.app) as client:yield client


def test_upload_language_override_and_unicode_roundtrip(client):
    original='علی: میں رپورٹ کل بھیج دوں گا۔'
    meeting=client.post('/api/meetings',json={'title':'اردو ملاقات','transcript':original,'input_language':'ur'}).json()
    assert meeting['language_profile']['effective']=='ur'
    assert client.get(f"/api/meetings/{meeting['id']}/transcript?format=original").text==original
    upload=client.post('/api/ingestion/transcript',data={'title':'Roman','input_language':'roman-ur'},files={'file':('meeting.txt',b'Ali: Kal bhej dunga.','text/plain')})
    assert upload.status_code==201
    assert upload.json()['language_profile']['effective']=='roman-ur'
    assert client.post('/api/meetings',json={'title':'X','transcript':'hello','input_language':'invalid'}).status_code==422


def test_translation_preserves_identity_and_rejects_missing_ids(monkeypatch):
    real_client=httpx.AsyncClient
    response={'translations':[{'source_id':7,'english':'I will send the report tomorrow.'}]}
    def handler(request):
        assert 'Roman Urdu' in json.loads(request.content)['messages'][0]['content']
        return httpx.Response(200,json={'message':{'content':json.dumps(response)}})
    monkeypatch.setattr(languages.httpx,'AsyncClient',lambda **kw:real_client(transport=httpx.MockTransport(handler),**kw))
    original=[{'id':7,'speaker':'Ali','text':'Main report kal bhej dunga.'}]
    translated=asyncio.run(languages.translate(original,'http://ollama','local'))
    assert translated[0]['id']==7 and translated[0]['speaker']=='Ali'
    assert original[0]['text']=='Main report kal bhej dunga.'
    response['translations'][0]['source_id']=8
    with pytest.raises(ValueError,match='IDs'):asyncio.run(languages.translate(original,'http://ollama','local'))


def test_translation_failure_preserves_saved_analysis(client,monkeypatch):
    meeting=client.post('/api/meetings',json={'title':'Urdu','transcript':'Ali: Main kal bhej dunga.','input_language':'roman-ur'}).json()
    meeting['dialogue_analysis']={'previous':'retained'}
    main.save(meeting)
    async def bad(*args):raise ValueError('Invalid translation')
    monkeypatch.setattr(languages,'translate',bad)
    assert client.post(f"/api/meetings/{meeting['id']}/classify").status_code==502
    assert client.get(f"/api/meetings/{meeting['id']}").json()['dialogue_analysis']=={'previous':'retained'}


@pytest.mark.parametrize('text,task,kind,owner,deadline',[
    ('Main report kal bhej dunga.','report bhej','commitment','Ali','kal'),
    ('میں رپورٹ کل بھیج دوں گا۔','رپورٹ بھیج','commitment','Ali','کل'),
    ('Main report nahi bhejunga.','report bhej','cancellation',None,None),
    ('رپورٹ مت بھیجنا۔','رپورٹ بھیجنا','cancellation',None,None),
    ('Shayad hum report bhej dein.','report bhej','suggestion',None,None),
    ('کیا آپ رپورٹ بھیج سکتے ہیں؟','رپورٹ بھیج','request',None,None),
])
def test_multilingual_grounding(text,task,kind,owner,deadline):
    pytest.importorskip('spacy')
    prepared=prepare('Ali: '+text)
    prepared['input_language']='ur' if languages.URDU.search(text) else 'roman-ur'
    predictions=[{'source_id':s['id'],'label':'off','score':.8} for s in prepared['segments']]
    units=commitments.source_units(prepared,predictions)
    for unit in units:
        unit.update(doc=urdu.nlp()(unit['text']),people=[],dates=urdu.dates(unit['text']))
    proposal=commitments.Proposal(source_id=units[0]['source_id'],quote=text,task=task,owner='Invented',deadline=None,kind='commitment' if kind not in {'request','suggestion'} else kind)
    result=commitments.ground([proposal],units,urdu.nlp())
    item=(result['actions']+result['action_candidates'])[0]
    assert item['kind']==kind
    assert item['owner']==owner
    assert item['deadline']==deadline
    assert item['evidence'][0]['quote']==text
    assert item['needs_review']


def test_english_only_audio_model_cannot_silently_process_urdu(tmp_path,monkeypatch):
    monkeypatch.setattr(media,'MODEL_NAME','base.en')
    with pytest.raises(ValueError,match='English-only'):
        media.transcribe_media(tmp_path/'meeting.wav',lambda *args:None,language='ur')
