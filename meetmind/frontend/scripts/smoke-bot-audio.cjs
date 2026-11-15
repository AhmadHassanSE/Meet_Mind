// Regression: received WebRTC must be recorded even without Meet's own audio player.
const { chromium } = require('playwright');
const path = require('node:path');
const assert = require('node:assert/strict');
(async () => {
  const browser = await chromium.launch({channel:'chrome',headless:true,
    args:['--autoplay-policy=no-user-gesture-required']});
  try {
    const page = await browser.newPage();
    let bytes = 0;
    await page.exposeFunction('__meetmindAudioChunk', data => {bytes += Buffer.from(data,'base64').length;});
    await page.addInitScript({path:path.resolve(__dirname,'../../backend/app/connectors/bot_audio.js')});
    await page.route('http://bot-audio.test/', route => route.fulfill({body:'<!doctype html><body></body>',contentType:'text/html'}));
    await page.goto('http://bot-audio.test/');
    await page.evaluate(async () => {
      await __meetmindBotAudio.start();
      const ctx = new AudioContext();await ctx.resume();
      const tone = ctx.createOscillator(),gain = ctx.createGain(),out = ctx.createMediaStreamDestination();
      gain.gain.value=.2;tone.connect(gain);gain.connect(out);tone.start();
      const sender = new RTCPeerConnection(),receiver = new RTCPeerConnection();
      sender.onicecandidate=e=>{if(e.candidate)receiver.addIceCandidate(e.candidate)};
      receiver.onicecandidate=e=>{if(e.candidate)sender.addIceCandidate(e.candidate)};
      for(const track of out.stream.getTracks())sender.addTrack(track,out.stream);
      // Deliberately no page-created audio element or playback handler.
      await sender.setLocalDescription(await sender.createOffer());
      await receiver.setRemoteDescription(sender.localDescription);
      await receiver.setLocalDescription(await receiver.createAnswer());
      await sender.setRemoteDescription(receiver.localDescription);
      window.fixture={ctx,tone,sender,receiver};
    });
    await page.waitForFunction(()=>__meetmindBotAudio.stats().peak>5,{},{timeout:15000});
    const before = await page.evaluate(()=>__meetmindBotAudio.stats());
    assert(before.active_tracks>0 && before.playback_errors===0);
    const after = await page.evaluate(()=>__meetmindBotAudio.stop());
    assert(after.peak>5 && after.chunks>0 && bytes>500);
    assert.equal(after.active_tracks,0);
    assert.equal(await page.locator('audio').count(),0);
    await page.evaluate(async()=>{
      fixture.sender.close();fixture.receiver.close();fixture.tone.stop();await fixture.ctx.close();
    });
    console.log('Bot audio regression passed: remote WebRTC, no page playback, audible capture and sink cleanup.');
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
