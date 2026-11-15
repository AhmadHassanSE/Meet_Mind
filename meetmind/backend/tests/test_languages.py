import asyncio
import json
import wave
from types import SimpleNamespace
from pathlib import Path

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
    response={'translations':{'7':'I will send the report tomorrow.'}}
    def handler(request):
        assert 'Roman Urdu' in json.loads(request.content)['messages'][0]['content']
        return httpx.Response(200,json={'message':{'content':json.dumps(response)}})
    monkeypatch.setattr(languages.httpx,'AsyncClient',lambda **kw:real_client(transport=httpx.MockTransport(handler),**kw))
    original=[{'id':7,'speaker':'Ali','text':'Main report kal bhej dunga.'}]
    translated=asyncio.run(languages.translate(original,'http://ollama','local'))
    assert translated[0]['id']==7 and translated[0]['speaker']=='Ali'
    assert original[0]['text']=='Main report kal bhej dunga.'
    response['translations']={'8':'Wrong source ID'}
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


def test_user_supplied_format_and_deadline_phrases():
    original=(Path(__file__).parent/'fixtures/urdu-project-review.txt').read_text(encoding='utf-8')
    meeting=prepare(original)
    parents=meeting['source_segments']
    assert len(parents)==8
    assert [p['speaker'] for p in parents]==['احمد','سارا','علی','سارا','احمد','سارا','علی','احمد']
    assert [p['start'] for p in parents]==[0,15,30,42,55,70,85,100]
    assert all(p['start']==p['end'] for p in parents)
    assert urdu.dates('ہم اسے آج شام تک ٹھیک کر لیں گے۔')[0]['text']=='آج شام تک'
    assert urdu.dates('میں دو بجے تک بلڈ دوں گی۔')[0]['text']=='دو بجے تک'
    assert urdu.dates('کل صبح تک ریویو مکمل ہوگا۔')[0]['text']=='کل صبح تک'
    assert urdu.dates('سارا دوپہر دو بجے تک بلڈ دیں گی۔')[0]['text']=='دوپہر دو بجے تک'


def test_multilingual_classifier_uses_translation_without_replacing_sources(monkeypatch):
    meeting={'segments':[{'id':1,'text':'Main kal report bhejunga.','speaker':'Ali'}],'input_language':'roman-ur'}
    async def translated(*args):return [{'id':1,'text':'I will send the report tomorrow.','speaker':'Ali'}]
    def classifier(segments):
        assert segments[0]['text']=='I will send the report tomorrow.'
        return {'predictions':[{'source_id':1,'needs_review':False,'review_reasons':[]}],'model':{}}
    monkeypatch.setattr(languages,'translate',translated)
    result=asyncio.run(languages.classify(meeting,classifier,'http://local','model'))
    assert meeting['segments'][0]['text']=='Main kal report bhejunga.'
    assert result['predictions'][0]['needs_review']
    assert result['language_processing']['validated_on_urdu'] is False


def test_unsupported_english_task_is_retained_as_original_urdu_clause():
    pytest.importorskip('spacy')
    text='میں رپورٹ کل بھیج دوں گا۔'
    meeting=prepare('علی: '+text)
    meeting['input_language']='ur'
    units=commitments.source_units(meeting,[{'source_id':s['id'],'label':'off','score':.8} for s in meeting['segments']])
    for unit in units:unit.update(doc=urdu.nlp()(unit['text']),people=[],dates=urdu.dates(unit['text']))
    proposal=commitments.Proposal(task='send report',owner=None,deadline=None,source_id=units[0]['source_id'],quote=text,kind='commitment')
    item=commitments.ground([proposal],units,urdu.nlp())['actions'][0]
    assert item['task']==text
    assert 'task_retained_as_source_clause_requires_edit' in item['review_reasons']
    assert item['deadline']=='کل'


def test_english_bypasses_translation(monkeypatch):
    async def forbidden(*args):raise AssertionError('English must not require translation')
    monkeypatch.setattr(languages,'translate',forbidden)
    segments=[{'id':1,'text':'I will send the report.','speaker':'Ali'}]
    result=asyncio.run(languages.classify({'segments':segments},lambda s:{'predictions':[]},'local','model'))
    assert result=={'predictions':[]}


@pytest.mark.parametrize('requested,expected',[('en','en'),('ur','ur'),('roman-ur','ur'),('auto',None)])
def test_speech_language_is_forwarded_without_translation(tmp_path,monkeypatch,requested,expected):
    observed={}
    def decode(command,**kwargs):
        with wave.open(command[-1],'wb') as output:
            output.setnchannels(1);output.setsampwidth(2);output.setframerate(16000)
            output.writeframes(b'\0\0'*16000)
        return SimpleNamespace(returncode=0)
    def speech(samples,**kwargs):
        observed.update(kwargs)
        return iter([SimpleNamespace(text='میں رپورٹ بھیجوں گا۔',start=0,end=1)]),SimpleNamespace(language='ur')
    monkeypatch.setattr(media,'MODEL_NAME','base')
    monkeypatch.setattr(media,'ffmpeg_path',lambda:'ffmpeg')
    monkeypatch.setattr(media.subprocess,'run',decode)
    monkeypatch.setattr(media,'_model',SimpleNamespace(transcribe=speech))
    segments,metadata=media.transcribe_media(tmp_path/'meeting.wav',lambda *args:None,language=requested)
    assert observed['language']==expected
    assert observed['task']=='transcribe'
    assert 'multilingual' not in observed and 'initial_prompt' not in observed
    assert metadata['language']=='ur'
    assert segments[0]['text']=='میں رپورٹ بھیجوں گا۔'


@pytest.mark.parametrize('source_id',[1,99])
def test_multilingual_proposals_attach_source_text_in_server(monkeypatch,source_id):
    original='میں رپورٹ کل بھیج دوں گا۔'
    unit={'source_id':1,'text':original,'speaker':'علی','language':'ur','bert_signals':[],'people':[],'dates':[]}
    real_client=httpx.AsyncClient
    def handler(request):
        body=json.loads(request.content)
        definition=body['format']['$defs']['Proposal']
        assert 'quote' not in definition['properties']
        assert definition['properties']['source_id']['enum']==[1]
        return httpx.Response(200,json={'message':{'content':json.dumps({'actions':[{
            'source_id':source_id,'task':'رپورٹ بھیج','owner':None,'deadline':'کل','kind':'commitment'}]})}})
    monkeypatch.setattr(commitments.httpx,'AsyncClient',lambda **kwargs:real_client(transport=httpx.MockTransport(handler),**kwargs))
    if source_id==99:
        with pytest.raises(commitments.InvalidExtraction):asyncio.run(commitments.propose([unit],'http://ollama','qwen3:4b'))
    else:
        proposals=asyncio.run(commitments.propose([unit],'http://ollama','qwen3:4b'))
        assert proposals[0].quote==original


@pytest.mark.parametrize('text,expected',[("I won't send the report.",'cancellation'),('Main report nhi bhejunga.','cancellation'),('We should send the report.','suggestion')])
def test_code_switched_negation_and_uncertainty(text,expected):
    assert urdu.kind(text,'commitment')[0]==expected
