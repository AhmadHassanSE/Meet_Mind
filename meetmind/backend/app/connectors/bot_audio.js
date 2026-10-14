// Installed before navigation. Observe incoming WebRTC tracks only; never the
// local microphone, system loopback, screen, or another tab's audio.
(() => {
  if (globalThis.__meetmindBotAudio) return;
  const tracks = new Map(), connections = new Map(), peers = new Set();
  let context, destination, recorder, upload = Promise.resolve(), error = null;
  let bytes = 0, chunks = 0, timer, tracker, peak = 0, analyser;
  let playbackErrors = 0;
  const detach = id => {
    const entry = connections.get(id);
    if (!entry) return;
    connections.delete(id);
    entry.source.disconnect(); entry.player.pause();
    entry.player.srcObject = null; entry.player.remove(); entry.clone.stop();
  };
  const connect = track => {
    if (track.kind !== 'audio' || tracks.get(track.id) === track) return;
    detach(track.id);
    tracks.set(track.id, track);
    if (context) attach(track);
  };
  const attach = track => {
    if (connections.has(track.id) || track.readyState === 'ended') return;
    // Chromium needs a playing media element to pull received WebRTC audio.
    // Own a zero-volume playback sink instead of depending on Meet's UI player.
    // Clone the remote track so page muting cannot disable our recording copy.
    const clone = track.clone(); clone.enabled = true;
    const stream = new MediaStream([clone]);
    const player = document.createElement('audio');
    player.autoplay = true; player.volume = 0; player.hidden = true;
    player.srcObject = stream; (document.body || document.documentElement).appendChild(player);
    const source = context.createMediaStreamSource(stream);
    source.connect(destination);
    source.connect(analyser);
    const entry = { source, player, clone };
    connections.set(track.id, entry);
    player.play().catch(() => { if (connections.get(track.id) === entry) playbackErrors += 1; });
    track.addEventListener('ended', () => { if (connections.get(track.id) === entry) detach(track.id); }, { once: true });
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
    audio_context_state: context?.state || 'not_started', playback_errors: playbackErrors,
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
        if (context.state === 'suspended') context.resume().catch(() => {});
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
      for (const id of [...connections.keys()]) detach(id);
      if (context) await context.close();
      if (error) throw new Error(error);
      return stats();
    }
  };
})();
