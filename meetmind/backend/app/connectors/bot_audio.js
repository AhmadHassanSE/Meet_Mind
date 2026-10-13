// Installed before navigation. Observe incoming WebRTC tracks only; never the
// local microphone, system loopback, screen, or another tab's audio.
(() => {
  if (globalThis.__meetmindBotAudio) return;
  const tracks = new Map(), connections = new Map(), peers = new Set();
  let context, destination, recorder, upload = Promise.resolve(), error = null;
  let bytes = 0, chunks = 0, timer, tracker, peak = 0, analyser;
  const connect = track => {
    if (track.kind !== 'audio' || tracks.has(track.id)) return;
    tracks.set(track.id, track);
    if (context) attach(track);
  };
  const attach = track => {
    if (connections.has(track.id) || track.readyState === 'ended') return;
    const source = context.createMediaStreamSource(new MediaStream([track]));
    source.connect(destination);
    source.connect(analyser);
    connections.set(track.id, source);
    track.addEventListener('ended', () => { source.disconnect(); connections.delete(track.id); });
  };
  const Original = globalThis.RTCPeerConnection;
  if (Original) globalThis.RTCPeerConnection = new Proxy(Original, {
    construct(target, args) {
      const peer = Reflect.construct(target, args);
      peers.add(peer);
      peer.addEventListener('track', event => connect(event.track));
      peer.addEventListener('connectionstatechange', () => {
        for (const receiver of peer.getReceivers()) if (receiver.track) connect(receiver.track);
        if (peer.connectionState === 'closed') peers.delete(peer);
      });
      return peer;
    }
  });
  const stats = () => ({ remote_tracks: tracks.size, active_tracks: connections.size,
    bytes, chunks, peak, error, recording: recorder?.state === 'recording' });
  globalThis.__meetmindBotAudio = {
    stats,
    async start() {
      if (recorder) throw new Error('Bot audio recorder already started');
      if (!MediaRecorder.isTypeSupported('audio/webm;codecs=opus')) throw new Error('WebM/Opus recording unavailable');
      context = new AudioContext(); await context.resume();
      destination = context.createMediaStreamDestination();
      analyser = context.createAnalyser(); analyser.fftSize = 256;
      const silent = context.createGain(); silent.gain.value = 0;
      analyser.connect(silent); silent.connect(context.destination);
      for (const track of tracks.values()) attach(track);
      recorder = new MediaRecorder(destination.stream, { mimeType: 'audio/webm;codecs=opus', audioBitsPerSecond: 32000 });
      recorder.ondataavailable = event => {
        if (!event.data.size) return;
        upload = upload.then(async () => {
          const buffer = new Uint8Array(await event.data.arrayBuffer());
          let binary = '';
          for (let i = 0; i < buffer.length; i += 16384) binary += String.fromCharCode(...buffer.subarray(i, i + 16384));
          await globalThis.__meetmindAudioChunk(btoa(binary));
          bytes += buffer.length; chunks += 1;
        }).catch(e => { error = String(e); });
      };
      recorder.onerror = () => { error = 'Browser audio recording failed'; };
      tracker = globalThis.MeetMindHints ? new globalThis.MeetMindHints.SpeakerTracker() : null;
      timer = setInterval(() => {
        const data = new Uint8Array(analyser.fftSize); analyser.getByteTimeDomainData(data);
        peak = Math.max(peak, ...data.map(value => Math.abs(value - 128)));
      }, 500);
      recorder.start(10000);
      return stats();
    },
    hints(final = false) {
      if (!tracker) return [];
      if (final) return tracker.flush(Date.now());
      const region = globalThis.MeetMindHints.findCaptionRegion(document);
      return region ? tracker.update(globalThis.MeetMindHints.parseCaptionBlocks(region), Date.now()) : [];
    },
    async stop() {
      clearInterval(timer);
      if (recorder && recorder.state !== 'inactive') await new Promise(resolve => {
        recorder.addEventListener('stop', resolve, { once: true }); recorder.stop();
      });
      await upload;
      if (context) await context.close();
      if (error) throw new Error(error);
      return stats();
    }
  };
})();
