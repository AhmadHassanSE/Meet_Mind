import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Zap, FileText, Upload, ArrowRight, Cpu } from 'lucide-react';
import './styles.css';
import { MeetingBot } from './MeetingBot';
import { UploadMeeting } from './UploadMeeting';
import { CommitmentResults, type CommitmentMeeting, type ReviewData } from './CommitmentResults';
import { PreparedTranscript, type PreparedMeeting } from './PreparedTranscript';
import { LanguageProcessing, type LanguageProcessingInfo } from './LanguageProcessing';

type DialoguePrediction = { source_id: number; label: string; description: string; score: number; possible_action: boolean; needs_review: boolean; review_reasons: string[]; top_labels: { label: string; score: number }[] };
type Meeting = PreparedMeeting & Omit<CommitmentMeeting, 'segments'> & { id: string; title: string; status: string; model: string | null; source_type?: string; segments: { id: number; speaker: string | null; text: string; source: string; start?: number | null; end?: number | null; parent_source_id?: number; source_start?: number; source_end?: number }[]; dialogue_analysis?: { language_processing?: LanguageProcessingInfo; predictions: DialoguePrediction[]; model: { model_name: string; checkpoint_stage: string } } };
async function request<T>(path: string, body?: object): Promise<T> {
  const response = await fetch(`/api${path}`, body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : undefined);
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Request failed. Check your input and try again.');
  return data;
}
function App() {
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [selected, setSelected] = useState<Meeting | null>(null);
  const [view, setView] = useState<'meetings' | 'upload' | 'bot'>(() => localStorage.getItem('meetmind-bot-id') ? 'bot' : localStorage.getItem('meetmind-ingestion-job') ? 'upload' : 'meetings');
  const [health, setHealth] = useState({ ollama: 'checking', model: 'llama3.2:latest', bert: { status: 'checking', stage: '' } });
  const [busy, setBusy] = useState<'extract' | 'bert' | 'review' | null>(null);
  const [error, setError] = useState('');
  const refresh = () => request<Meeting[]>('/meetings').then(setMeetings);
  useEffect(() => { Promise.all([refresh(), request<typeof health>('/health').then(setHealth)]).catch(e => setError(e.message)); }, []);
  async function openMeeting(id: string) {
    const meeting = await request<Meeting>(`/meetings/${id}`);
    await refresh();
    setSelected(meeting); setView('meetings'); setError('');
  }
  async function extract() {
    if (!selected) return;
    setBusy('extract'); setError('');
    try { setSelected(await request<Meeting>(`/meetings/${selected.id}/extract`, {})); await refresh(); }
    catch (e) { setError((e as Error).message); } finally { setBusy(null); }
  }
  async function classify() {
    if (!selected) return;
    setBusy('bert'); setError('');
    try { setSelected(await request<Meeting>(`/meetings/${selected.id}/classify`, {})); await refresh(); }
    catch (e) { setError((e as Error).message); } finally { setBusy(null); }
  }
  async function reviewCommitment(id: string, data: ReviewData) {
    if (!selected) return;
    setBusy('review');
    try {
      const updated = await request<Meeting>(`/meetings/${selected.id}/commitments/${id}/review`, data);
      setSelected(current => current?.id === updated.id ? updated : current);
      await refresh();
    } finally { setBusy(null); }
  }
  return <div className="shell"><aside><div className="brand"><Zap/><strong>MeetMind</strong></div><p className="eyebrow">LOCAL WORKSPACE</p><nav><button className={view === 'meetings' ? 'active' : ''} onClick={() => { setView('meetings'); setSelected(null); }}><FileText size={19}/> Meetings</button><button className={view === 'upload' ? 'active' : ''} onClick={() => setView('upload')}><Upload size={19}/> Upload transcript</button><button className={view === 'bot' ? 'active' : ''} onClick={() => setView('bot')}>Google Meet bot</button></nav><div className="local"><Cpu size={19}/><div>Ollama · {health.ollama}<small>{health.model}</small></div></div></aside><main><header><span>Iteration 01 <span className="muted">/ R&D and NLP pipeline</span></span><span className="pill">Local inference</span></header><div className="content">{error && <div role="alert" className="error">{error}</div>}
    {view === 'bot' ? <MeetingBot onReady={openMeeting}/> : view === 'upload' ? <UploadMeeting onReady={openMeeting}/>
    : selected ? <>
      <button className="back" onClick={() => setSelected(null)}>← All meetings</button>
      <p className="eyebrow">MEETING WORKSPACE</p><h1>{selected.title}</h1>
      <div className="row"><p className="muted">{selected.segments.length} utterances · {selected.source_type || 'text'} · {selected.status}</p><button className="primary" disabled={busy !== null || [...selected.actions, ...(selected.action_candidates || [])].some(item => item.review_history?.length)} onClick={extract}>{busy === 'extract' ? 'Extracting locally…' : 'Extract commitments'}<Cpu size={17}/></button></div>
      <section className="panel bert-summary"><div className="row"><div><h2>BERT dialogue analysis</h2><p className="muted">{health.bert.status}{health.bert.stage ? ` · ${health.bert.stage}` : ''}</p></div><button className="primary" disabled={busy !== null} onClick={classify}>{busy === 'bert' ? 'Processing locally…' : 'Analyze with BERT'}<Cpu size={17}/></button></div><p className="muted">Classifies dialogue acts and highlights possible actions. Offers and suggestions require review before becoming tasks. Scores are uncalibrated model outputs.</p>{selected.dialogue_analysis && <><small className="muted">{selected.dialogue_analysis.model.model_name} · {selected.dialogue_analysis.model.checkpoint_stage}</small><div className="dialogue-results">{selected.dialogue_analysis.predictions.map(prediction => <article key={prediction.source_id}><span className={`pill${prediction.possible_action ? ' warning' : ''}`}>#{prediction.source_id} · {prediction.description}</span> <small className="muted">Model score {prediction.score.toFixed(3)}</small><p dir="auto">{selected.segments.find(s => s.id === prediction.source_id)?.text}</p>{prediction.needs_review && <small className="mint">Review: {prediction.review_reasons.map(reason => reason.replaceAll('_', ' ')).join('; ')}</small>}<small className="muted dialogue-alternatives">Alternatives: {prediction.top_labels.map(label => `${label.label} ${label.score.toFixed(3)}`).join(' · ')}</small></article>)}</div></>}</section>
      <div className="row downloads"><span className="muted">Download transcript</span><div><a href={`/api/meetings/${selected.id}/transcript?format=txt`}>TXT</a> <a href={`/api/meetings/${selected.id}/transcript?format=json`}>JSON</a>{selected.segments.some(s => s.start != null) && <> <a href={`/api/meetings/${selected.id}/transcript?format=vtt`}>VTT</a></>}</div></div>
      <LanguageProcessing profile={selected.language_profile} analysis={selected.dialogue_analysis?.language_processing}/><PreparedTranscript meeting={selected}/>
      <div className="columns"><section className="panel"><h2>Transcript evidence</h2>{selected.segments.map(s => <article key={s.id}><small className="mint">#{s.id} · {s.speaker || 'Unknown speaker'}{s.start != null ? ` · ${s.start.toFixed(1)}s – ${s.end?.toFixed(1)}s` : ''}</small><p dir="auto">{s.text}</p>{s.parent_source_id != null && <details><summary>Source turn #{s.parent_source_id}</summary><p>{selected.source_segments?.find(parent => parent.id === s.parent_source_id)?.text}</p><small className="muted">Characters {s.source_start}?{s.source_end}</small></details>}</article>)}</section>
      <CommitmentResults meeting={selected} onReview={reviewCommitment} disabled={busy !== null}/></div>
    </>
    : <><div className="row"><div><p className="eyebrow">FROM CONVERSATION TO CLARITY</p><h1>Your meeting workspace.</h1><p className="muted">Capture discussions. Surface commitments. Keep the evidence.</p></div><button className="primary" onClick={() => setView('upload')}><Upload size={17}/> Upload meeting</button></div><div className="stats"><div className="panel"><strong>{meetings.length}</strong><span>Saved meetings</span></div><div className="panel"><strong>{meetings.reduce((n, m) => n + m.actions.length, 0)}</strong><span>Extracted commitments</span></div><div className="panel"><strong>01</strong><span>Active iteration</span></div></div><h2>Meeting library</h2>{meetings.length ? <div className="library">{meetings.map(m => <button className="panel meeting" key={m.id} onClick={() => void openMeeting(m.id).catch(e => setError(e.message))}><FileText className="mint"/><div><h3>{m.title}</h3><p className="muted">{m.segments.length} utterances · {m.actions.length} commitments</p></div><span className="pill">{m.status}</span><ArrowRight size={18}/></button>)}</div> : <div className="panel empty"><FileText size={32}/><h3>A clearer follow-up starts here.</h3><p className="muted">Upload your first transcript to build your meeting library.</p><button className="primary" onClick={() => setView('upload')}>Add a meeting <ArrowRight size={17}/></button></div>}</>}
  </div></main></div>;
}
createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);
