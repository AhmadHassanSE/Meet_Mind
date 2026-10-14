import { useEffect, useState } from 'react';
import { Video, Square, X, ArrowRight } from 'lucide-react';

type BotSession = { id: string; title: string; meeting_url: string; state: string; message: string;
  recorded_bytes: number; uploaded_chunks: number; remote_tracks: number; elapsed_seconds?: number;
  meeting_id?: string; job?: { progress: number; message: string };
  capture_stats?: { peak?: number; audio_context_state?: string; playback_errors?: number };
  events: { at: string; state: string; message: string }[] };
type Capabilities = { playwright_installed: boolean; ffmpeg_available: boolean };
const terminal = new Set(['completed', 'failed', 'cancelled']);
async function api<T>(path: string, body?: object): Promise<T> {
  const response = await fetch(`/api/meet/bots${path}`, body ? {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : undefined);
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Check the Meet link, title and recording confirmation.');
  return data;
}

export function MeetingBot({ onReady }: { onReady: (id: string) => Promise<void> }) {
  const [url, setUrl] = useState('');
  const [title, setTitle] = useState('Google Meet session');
  const [name, setName] = useState('MeetMind Notetaker');
  const [duration, setDuration] = useState(60);
  const [consent, setConsent] = useState(false);
  const [id, setId] = useState<string | null>(() => localStorage.getItem('meetmind-bot-id'));
  const [session, setSession] = useState<BotSession | null>(null);
  const [sessions, setSessions] = useState<BotSession[]>([]);
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const active = Boolean(id && (!session || !terminal.has(session.state)));
  useEffect(() => {
    Promise.all([api<Capabilities>('/capabilities').then(setCapabilities), api<BotSession[]>('').then(setSessions)])
      .catch(e => setError(e.message));
  }, []);
  useEffect(() => {
    if (!id) return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const result = await api<BotSession>(`/${id}`);
        if (disposed) return;
        setSession(result);
        if (terminal.has(result.state)) {
          localStorage.removeItem('meetmind-bot-id');
          api<BotSession[]>('').then(list => { if (!disposed) setSessions(list); }).catch(() => {});
        } else timer = setTimeout(poll, 1500);
      } catch (e) {
        if (!disposed) { setError((e as Error).message); timer = setTimeout(poll, 3000); }
      }
    };
    void poll();
    return () => { disposed = true; clearTimeout(timer); };
  }, [id]);
  async function start() {
    if (busy || active) return;
    setBusy(true); setError('');
    try {
      const result = await api<BotSession>('', { title, meeting_url: url, display_name: name,
        max_duration_minutes: duration, consent_confirmed: consent });
      localStorage.setItem('meetmind-bot-id', result.id); setSession(result); setId(result.id);
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  async function command(action: string) {
    if (!id || busy) return;
    setBusy(true); setError('');
    try { setSession(await api<BotSession>(`/${id}/${action}`, {})); }
    catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  return <><p className="eyebrow">LIVE MEETING CAPTURE</p><h1>Google Meet browser bot</h1>
    <p className="muted">Send a separate browser participant into your meeting. The host admits the bot; after recording, MeetMind transcribes locally.</p>
    <p className="muted">The Chrome extension is still available for recording from your own meeting tab. This bot uses a separate browser window and captures incoming meeting audio with its microphone and camera disabled.</p>
    {error && <p role="alert" className="error">{error}</p>}
    {capabilities && (!capabilities.playwright_installed || !capabilities.ffmpeg_available) && <p className="error">Bot setup is incomplete. Install the backend bot extra, Google Chrome and FFmpeg before starting.</p>}
    <form className="panel form" onSubmit={e => { e.preventDefault(); void start(); }}>
      <label>Google Meet link<input type="url" required disabled={active || busy} value={url} onChange={e => setUrl(e.target.value)} placeholder="https://meet.google.com/abc-defg-hij"/></label>
      <label>Meeting title<input required maxLength={200} disabled={active || busy} value={title} onChange={e => setTitle(e.target.value)}/></label>
      <label>Guest bot name<input required maxLength={80} disabled={active || busy} value={name} onChange={e => setName(e.target.value)}/><small>If Google requires sign-in, use a dedicated bot account. Meet uses that account’s display name.</small></label>
      <label>Maximum recording minutes<input type="number" min={1} max={120} required disabled={active || busy} value={duration} onChange={e => setDuration(Number(e.target.value))}/></label>
      <label className="bot-consent"><input type="checkbox" required disabled={active || busy} checked={consent} onChange={e => setConsent(e.target.checked)}/>The host and participants know this bot will record the meeting audio.</label>
      <button className="primary" disabled={active || busy || !consent || !capabilities?.playwright_installed || !capabilities.ffmpeg_available}><Video size={17}/>{busy ? 'Starting…' : 'Send bot to meeting'}</button>
    </form>
    {session && <section className="panel bot-status" aria-live="polite"><div className="row"><h2>{session.title}</h2><span className={`pill${session.state==='failed'?' warning':''}`}>{session.state.replaceAll('_',' ')}</span></div>
      <p>{session.message}</p><p className="muted">{session.uploaded_chunks} audio chunks · {(session.recorded_bytes/1024).toFixed(1)} KB uploaded · {session.remote_tracks} incoming audio tracks</p>
      {session.state==='recording' && session.capture_stats && <>
        <label>Incoming audio level<meter min={0} max={128} value={session.capture_stats.peak || 0} aria-label="Peak incoming audio level"/></label>
        <p className="muted">{(session.capture_stats.peak || 0)>0 ? 'Sound has been detected during this recording.' : 'Waiting for incoming sound. Track count alone does not mean speech is arriving.'}</p>
        {(session.elapsed_seconds || 0)>=10 && session.capture_stats.peak===0 && <p role="status" className="error">No incoming sound detected yet. Check that another participant is unmuted and audible in the bot browser. The bot does not record your local microphone.</p>}
      </>}
      {session.state==='needs_login' && <p className="muted">Finish sign-in or the Google prompt in the dedicated bot browser, then continue here. Passwords and verification codes never go into MeetMind.</p>}
      {session.job && <><p className="muted">{session.job.message}</p><progress max={100} value={session.job.progress} aria-label="Bot transcription progress"/></>}
      <div className="bot-controls">
        {session.state==='needs_login' && <button disabled={busy} onClick={() => void command('resume')}>Continue after sign-in</button>}
        {active && session.state!=='transcribing' && <><button disabled={busy} onClick={() => void command('stop')}><Square size={15}/>Stop and transcribe</button><button disabled={busy} onClick={() => void command('cancel')}><X size={15}/>Cancel and discard</button></>}
        {session.meeting_id && <button className="primary" onClick={() => void onReady(session.meeting_id!)}>Open transcript<ArrowRight size={17}/></button>}
      </div>
      {!!session.events.length && <details><summary>Session history</summary>{session.events.map((event,i) => <p className="muted" key={i}>{new Date(event.at).toLocaleTimeString()} · {event.state.replaceAll('_',' ')} · {event.message}</p>)}</details>}
    </section>}
    {!!sessions.length && <section className="panel bot-history"><h2>Recent bot sessions</h2>{sessions.map(item => <button className="meeting panel" key={item.id} onClick={() => { setSession(item); setId(item.id); }}><div><h3>{item.title}</h3><p className="muted">{item.state.replaceAll('_',' ')}</p></div><ArrowRight size={17}/></button>)}</section>}
  </>;
}
