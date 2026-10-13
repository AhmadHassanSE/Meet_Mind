"""Real Chrome/WebRTC/MediaRecorder -> shared API -> real Whisper, local fixture.

No Google call is joined. Supply a short local speech recording. Uses a temporary
profile/database; fake meeting DOM, real incoming peer audio, real media/model.
"""
import argparse
import asyncio
import base64
import json
from pathlib import Path
import subprocess
import tempfile
import time

import httpx
from app import main
from app.connectors.bot_browser import BrowserBot

HTML='''<!doctype html><html><body><label>Your name<input aria-label="Your name"></label>
<button id="join">Ask to join</button><script>
document.querySelector('#join').onclick=()=>{
 document.querySelector('#join').remove(); document.querySelector('input').remove();
 setTimeout(()=>{
  const leave=document.createElement('button'); leave.setAttribute('aria-label','Leave call');
  leave.textContent='Leave call'; document.body.appendChild(leave); window.fixtureAudio();
 },300);
};
</script></body></html>'''
PEER_AUDIO='''async (encoded) => {
  const context=new AudioContext();await context.resume();
  const bytes=Uint8Array.from(atob(encoded),c=>c.charCodeAt(0));
  const audio=await context.decodeAudioData(bytes.buffer);
  window.fixtureAudio=async()=>{
    const destination=context.createMediaStreamDestination();
    const source=context.createBufferSource();source.buffer=audio;source.loop=true;source.connect(destination);
    const sender=new RTCPeerConnection(),receiver=new RTCPeerConnection();
    receiver.addEventListener('track',event=>{
      const audio=document.createElement('audio');audio.srcObject=new MediaStream([event.track]);
      audio.autoplay=true;document.body.appendChild(audio);audio.play();
    });
    sender.onicecandidate=e=>{if(e.candidate)receiver.addIceCandidate(e.candidate)};
    receiver.onicecandidate=e=>{if(e.candidate)sender.addIceCandidate(e.candidate)};
    for(const track of destination.stream.getTracks())sender.addTrack(track,destination.stream);
    await sender.setLocalDescription(await sender.createOffer());
    await receiver.setRemoteDescription(sender.localDescription);
    await receiver.setLocalDescription(await receiver.createAnswer());
    await sender.setRemoteDescription(receiver.localDescription);
    source.start();window.fixturePeers=[sender,receiver,source,context];
  };
}'''


async def run(path,seconds):
    with tempfile.TemporaryDirectory(prefix='meetmind-bot-smoke-') as directory:
        root=Path(directory)
        wave=root/'speech.wav'
        subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y','-i',str(path),
                        '-t','20','-ac','1','-ar','16000',str(wave)],check=True)
        encoded=base64.b64encode(wave.read_bytes()).decode()
        class FixtureBrowser(BrowserBot):
            def __init__(self,profile):super().__init__(root/'profile',headless=True)
            async def open(self,url,on_chunk):
                await super().open('about:blank',on_chunk)
                await self.page.route('http://meetmind.fixture/',lambda route:route.fulfill(body=HTML,content_type='text/html'))
                await self.page.goto('http://meetmind.fixture/')
                await self.page.evaluate(PEER_AUDIO,encoded)
        main.DB_PATH=root/'bot.db'
        main.bot_manager.driver_factory=FixtureBrowser
        async with main.lifespan(main.app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='http://local') as api:
                response=await api.post('/api/meet/bots',json={'title':'Real local WebRTC bot fixture',
                    'meeting_url':'https://meet.google.com/abc-defg-hij','consent_confirmed':True})
                response.raise_for_status();bot_id=response.json()['id']
                recorded=None;last=None
                deadline=time.monotonic()+180
                while time.monotonic()<deadline:
                    response=await api.get('/api/meet/bots/'+bot_id);response.raise_for_status();record=response.json()
                    if record['state']!=last:print(record['state'],record['message'],flush=True);last=record['state']
                    if record['state']=='recording':
                        if recorded is None:recorded=time.monotonic()
                        if time.monotonic()-recorded>=seconds:
                            (await api.post('/api/meet/bots/'+bot_id+'/stop')).raise_for_status()
                    if record['state']=='completed':
                        meeting=(await api.get('/api/meetings/'+record['meeting_id'])).json()
                        assert meeting['capture_method']=='browser_bot' and meeting['source_type']=='google_meet'
                        assert meeting['segments'] and record['capture_stats']['remote_tracks']>0
                        assert record['capture_stats']['peak']>0
                        assert record['recorded_bytes']>0
                        output={'live_google_meet':False,'real_chrome':True,'real_webrtc_audio':True,
                            'real_whisper':True,'segments':len(meeting['segments']),'state':record['state'],
                            'capture_stats':record['capture_stats'],'capture_method':meeting['capture_method']}
                        Path('runs').mkdir(exist_ok=True)
                        Path('runs/bot-browser-smoke.json').write_text(json.dumps(output,indent=2))
                        print(json.dumps(output,indent=2),flush=True)
                        return
                    if record['state'] in {'failed','cancelled'}:
                        print(json.dumps(record.get('capture_stats',{})),flush=True)
                        raise RuntimeError(record['message'])
                    await asyncio.sleep(.5)
                raise TimeoutError('Browser fixture did not finish')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('recording',type=Path)
    parser.add_argument('--seconds',type=int,default=8)
    args=parser.parse_args()
    asyncio.run(run(args.recording,args.seconds))
