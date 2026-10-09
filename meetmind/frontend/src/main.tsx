import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Zap, FileText, Upload, ArrowRight, Cpu, CheckCircle2 } from 'lucide-react';
import './styles.css';

type Action = { task: string; owner: string | null; deadline: string | null; source_id: number; needs_review: boolean };
type Meeting = { id: string; title: string; status: string; model: string | null; segments: { id: number; speaker: string | null; text: string; source: string }[]; actions: Action[] };
async function request<T>(path: string, body?: object): Promise<T> {
  const response = await fetch(`/api${path}`, body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : undefined);
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Request failed. Check your input and try again.');
  return data;
}
function App() {
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [selected, setSelected] = useState<Meeting | null>(null);
  const [view, setView] = useState<'meetings' | 'upload'>('meetings');
  const [health, setHealth] = useState({ ollama: 'checking', model: 'llama3.2:latest' });
  const [title, setTitle] = useState('');
  const [transcript, setTranscript] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const refresh = () => request<Meeting[]>('/meetings').then(setMeetings);
  useEffect(() => { Promise.all([refresh(), request<typeof health>('/health').then(setHealth)]).catch(e => setError(e.message)); }, []);
  async function save() {
    setBusy(true); setError('');
    try { const meeting = await request<Meeting>('/meetings', { title, transcript }); setSelected(meeting); setView('meetings'); setTitle(''); setTranscript(''); await refresh(); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  async function extract() {
    if (!selected) return;
    setBusy(true); setError('');
    try { setSelected(await request<Meeting>(`/meetings/${selected.id}/extract`, {})); await refresh(); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  return <div className="shell"><aside><div className="brand"><Zap/><strong>MeetMind</strong></div><p className="eyebrow">LOCAL WORKSPACE</p><nav><button className={view === 'meetings' ? 'active' : ''} onClick={() => { setView('meetings'); setSelected(null); }}><FileText size={19}/> Meetings</button><button className={view === 'upload' ? 'active' : ''} onClick={() => setView('upload')}><Upload size={19}/> Upload transcript</button></nav><div className="local"><Cpu size={19}/><div>Ollama · {health.ollama}<small>{health.model}</small></div></div></aside><main><header><span>Iteration 01 <span className="muted">/ R&D and NLP pipeline</span></span><span className="pill">Local inference</span></header><div className="content">{error && <div role="alert" className="error">{error}</div>}
    {view === 'upload' ? <><p className="eyebrow">CAPTURE THE CONVERSATION</p><h1>Bring your meeting into focus.</h1><p className="muted">Paste a transcript or choose a TXT / VTT file to get started.</p><form className="panel form" onSubmit={e => { e.preventDefault(); void save(); }}><label>Meeting title<input required maxLength={200} value={title} onChange={e => setTitle(e.target.value)} placeholder="Weekly product review"/></label><label className="file">Choose TXT or VTT<input type="file" accept=".txt,.vtt" onChange={async e => { const f = e.target.files?.[0]; if (f) { if (f.size > 64000) { setError('Choose a transcript under 64 KB.'); return; } setTranscript(await f.text()); if (!title) setTitle(f.name.replace(/\.[^.]+$/, '')); } }}/></label><label>Transcript<textarea required maxLength={16000} value={transcript} onChange={e => setTranscript(e.target.value)} placeholder={'Sara: I will send the proposal by Friday.\nAhmed: We should discuss the budget next week.'}/></label><div className="row"><span className="muted">{transcript.length.toLocaleString()} / 16,000 characters</span><button className="primary" disabled={busy || !title.trim() || !transcript.trim()}>{busy ? 'Saving…' : 'Save meeting'}<ArrowRight size={17}/></button></div></form></>
    : selected ? <><button className="back" onClick={() => setSelected(null)}>← All meetings</button><p className="eyebrow">MEETING WORKSPACE</p><h1>{selected.title}</h1><div className="row"><p className="muted">{selected.segments.length} utterances · {selected.status}</p><button className="primary" disabled={busy} onClick={extract}>{busy ? 'Extracting locally…' : 'Extract with Ollama'}<Cpu size={17}/></button></div><div className="columns"><section className="panel"><h2>Transcript evidence</h2>{selected.segments.map(s => <article key={s.id}><small className="mint">#{s.id} · {s.speaker || 'Unknown speaker'}</small><p>{s.text}</p></article>)}</section><section className="panel"><h2>Extracted commitments</h2><p className="muted">Model suggestions require human review. No confidence probability is claimed.</p>{selected.status === 'uploaded' ? <div className="empty">Run extraction to identify commitments.</div> : !selected.actions.length ? <div className="empty"><CheckCircle2/> No commitments detected. Review the transcript to verify.</div> : selected.actions.map((a, i) => <article key={i}><span className="pill warning">Needs review</span><h3>{a.task}</h3><p className="muted">Owner: {a.owner || 'Unresolved'} · Due: {a.deadline || 'Unresolved'}</p><blockquote>{selected.segments.find(s => s.id === a.source_id)?.source}</blockquote></article>)}{selected.model && <small className="muted">Generated with {selected.model}</small>}</section></div></>
    : <><div className="row"><div><p className="eyebrow">FROM CONVERSATION TO CLARITY</p><h1>Your meeting workspace.</h1><p className="muted">Capture discussions. Surface commitments. Keep the evidence.</p></div><button className="primary" onClick={() => setView('upload')}><Upload size={17}/> Upload meeting</button></div><div className="stats"><div className="panel"><strong>{meetings.length}</strong><span>Saved meetings</span></div><div className="panel"><strong>{meetings.reduce((n, m) => n + m.actions.length, 0)}</strong><span>Extracted commitments</span></div><div className="panel"><strong>01</strong><span>Active iteration</span></div></div><h2>Meeting library</h2>{meetings.length ? <div className="library">{meetings.map(m => <button className="panel meeting" key={m.id} onClick={() => setSelected(m)}><FileText className="mint"/><div><h3>{m.title}</h3><p className="muted">{m.segments.length} utterances · {m.actions.length} commitments</p></div><span className="pill">{m.status}</span><ArrowRight size={18}/></button>)}</div> : <div className="panel empty"><FileText size={32}/><h3>A clearer follow-up starts here.</h3><p className="muted">Upload your first transcript to build your meeting library.</p><button className="primary" onClick={() => setView('upload')}>Add a meeting <ArrowRight size={17}/></button></div>}</>}
  </div></main></div>;
}
createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);
