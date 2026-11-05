import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Zap, FileText, Upload, ArrowRight, Cpu, Inbox, Video, Mail, User, Shield, LogOut } from 'lucide-react';
import './styles.css';
import { ArtifactWorkspace, type DraftSource } from './ArtifactWorkspace';
import { MeetingBot } from './MeetingBot';
import { UploadMeeting } from './UploadMeeting';
import { CommitmentResults, type CommitmentMeeting, type ReviewData } from './CommitmentResults';
import { PreparedTranscript, type PreparedMeeting } from './PreparedTranscript';
import { LanguageProcessing, type LanguageProcessingInfo } from './LanguageProcessing';
import { AuthScreen } from './Auth';
import { Account } from './Account';
import { Admin } from './Admin';
import { api, useRoute, SIGNED_OUT, type Access, type DirectoryUser, type Me } from './api';

type DialoguePrediction = { source_id: number; label: string; description: string; score: number; possible_action: boolean; needs_review: boolean; review_reasons: string[]; top_labels: { label: string; score: number }[] };
type Meeting = PreparedMeeting & Omit<CommitmentMeeting, 'segments'> & { id: string; title: string; status: string; model: string | null; source_type?: string; access?: Access | null; segments: { id: number; speaker: string | null; text: string; source: string; start?: number | null; end?: number | null; parent_source_id?: number; source_start?: number; source_end?: number }[]; dialogue_analysis?: { language_processing?: LanguageProcessingInfo; predictions: DialoguePrediction[]; model: { model_name: string; checkpoint_stage: string } } };
type Member = { id: string; name: string; email: string; role: string };
const roleLabel: Record<string, string> = { organizer: 'Organizer', owner: 'Owner', viewer: 'Viewer', admin: 'Admin (view only)' };

function App() {
  const [me, setMe] = useState<Me | null | undefined>(undefined);
  const [path, navigate] = useRoute();
  const loadMe = () => api<Me>('/auth/me').then(setMe);
  useEffect(() => {
    void loadMe().catch(() => setMe(null));
    const signedOut = () => setMe(null);
    window.addEventListener(SIGNED_OUT, signedOut);
    return () => window.removeEventListener(SIGNED_OUT, signedOut);
  }, []);
  if (me === undefined) return <div className="auth-shell"><p className="muted">Loading MeetMind…</p></div>;
  if (me === null) return <AuthScreen mode={path === '/signup' ? 'signup' : 'login'} navigate={navigate}
    onSignedIn={value => { setMe(value); if (path === '/login' || path === '/signup') navigate('/'); }}/>;
  return <Workspace me={me} path={path} navigate={navigate} reloadMe={loadMe}
    signOut={() => void api('/auth/logout', 'POST').finally(() => { setMe(null); navigate('/login'); })}/>;
}

function Workspace({ me, path, navigate, reloadMe, signOut }: { me: Me; path: string; navigate: (path: string) => void; reloadMe: () => Promise<void>; signOut: () => void }) {
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [draftSource, setDraftSource] = useState<DraftSource | null>(null);
  const [selected, setSelected] = useState<Meeting | null>(null);
  const [directory, setDirectory] = useState<DirectoryUser[]>([]);
  const [waiting, setWaiting] = useState(0);
  const [health, setHealth] = useState({ ollama: 'checking', model: 'llama3.2:latest', bert: { status: 'checking', stage: '' } });
  const [busy, setBusy] = useState<'extract' | 'bert' | 'review' | null>(null);
  const [error, setError] = useState('');
  const organizer = me.role === 'organizer';
  const meetingId = path.match(/^\/meetings\/([^/]+)$/)?.[1] || null;
  const refresh = () => api<Meeting[]>('/meetings').then(setMeetings);
  useEffect(() => {
    Promise.all([refresh(), api<typeof health>('/health').then(setHealth)]).catch(e => setError(e.message));
    // Resume an unfinished capture or upload after a refresh, as before routing existed.
    if (path === '/' && organizer) {
      if (localStorage.getItem('meetmind-bot-id')) navigate('/bot');
      else if (localStorage.getItem('meetmind-ingestion-job')) navigate('/upload');
    }
  }, []);
  useEffect(() => { void api<unknown[]>('/artifacts?awaiting_me=true').then(list => setWaiting(list.length)).catch(() => {}); }, [path]);
  useEffect(() => {
    setError('');
    if (!meetingId) { setSelected(null); return; }
    // Accounts can be created at any time, so refresh the owner picker per meeting.
    void api<DirectoryUser[]>('/users/directory').then(setDirectory).catch(() => {});
    if (selected?.id === meetingId) return;
    setSelected(null);
    void api<Meeting>(`/meetings/${meetingId}`).then(setSelected).catch(e => setError(e.message));
  }, [meetingId]);
  async function openMeeting(id: string) { await refresh().catch(() => {}); navigate(`/meetings/${id}`); }
  async function run(kind: 'extract' | 'bert', action: string) {
    if (!selected) return;
    setBusy(kind); setError('');
    try { setSelected(await api<Meeting>(`/meetings/${selected.id}/${action}`, 'POST', {})); await refresh(); }
    catch (e) { setError((e as Error).message); } finally { setBusy(null); }
  }
  async function reviewCommitment(id: string, data: ReviewData) {
    if (!selected) return;
    setBusy('review');
    try {
      const updated = await api<Meeting>(`/meetings/${selected.id}/commitments/${id}/review`, 'POST', data);
      setSelected(current => current?.id === updated.id ? updated : current);
      await refresh();
    } finally { setBusy(null); }
  }
  async function assign(id: string, revision: number, userId: string | null) {
    if (!selected) return;
    const updated = await api<Meeting>(`/meetings/${selected.id}/commitments/${id}/assignee`, 'PUT', { revision, user_id: userId });
    setSelected(current => current?.id === updated.id ? updated : current);
    await refresh();
  }
  const link = (to: string, label: React.ReactNode, active = path === to) =>
    <a href={to} className={active ? 'active' : ''} onClick={e => { e.preventDefault(); if (to === '/drafts') setDraftSource(null); navigate(to); }}>{label}</a>;
  const access = selected?.access;
  let page: React.ReactNode;
  if (path === '/upload') page = organizer ? <UploadMeeting onReady={openMeeting}/> : <NeedsOrganizer navigate={navigate}/>;
  else if (path === '/bot') page = organizer ? <MeetingBot onReady={openMeeting}/> : <NeedsOrganizer navigate={navigate}/>;
  else if (path === '/drafts' || path === '/queue') page = <ArtifactWorkspace queue={path === '/queue'} source={path === '/drafts' ? draftSource : null} onMeeting={id => navigate(`/meetings/${id}`)}/>;
  else if (path === '/account') page = <Account me={me} onChanged={reloadMe}/>;
  else if (path === '/admin') page = me.is_admin ? <Admin me={me}/> : <p className="error">Admin access required.</p>;
  else if (meetingId) page = !selected ? <p className="muted">{error ? '' : 'Loading meeting…'}</p> : <>
    <button className="back" onClick={() => navigate('/')}>← All meetings</button>
    <p className="eyebrow">MEETING WORKSPACE</p><h1>{selected.title}</h1>
    {access && <p className="muted">Your role: <span className="pill">{roleLabel[access.role]}</span>{access.role === 'admin' && ' Your access to this meeting is recorded in the audit log.'}</p>}
    <div className="row"><p className="muted">{selected.segments.length} utterances · {selected.source_type || 'text'} · {selected.status}</p>{access?.can_organize && <button className="primary" disabled={busy !== null || [...selected.actions, ...(selected.action_candidates || [])].some(item => item.review_history?.length)} onClick={() => void run('extract', 'extract')}>{busy === 'extract' ? 'Extracting locally…' : 'Extract commitments'}<Cpu size={17}/></button>}</div>
    <section className="panel bert-summary"><div className="row"><div><h2>BERT dialogue analysis</h2><p className="muted">{health.bert.status}{health.bert.stage ? ` · ${health.bert.stage}` : ''}</p></div>{access?.can_organize && <button className="primary" disabled={busy !== null} onClick={() => void run('bert', 'classify')}>{busy === 'bert' ? 'Processing locally…' : 'Analyze with BERT'}<Cpu size={17}/></button>}</div><p className="muted">Classifies dialogue acts and highlights possible actions. Offers and suggestions require review before becoming tasks. Scores are uncalibrated model outputs.</p>{selected.dialogue_analysis && <><small className="muted">{selected.dialogue_analysis.model.model_name} · {selected.dialogue_analysis.model.checkpoint_stage}</small><div className="dialogue-results">{selected.dialogue_analysis.predictions.map(prediction => <article key={prediction.source_id}><span className={`pill${prediction.possible_action ? ' warning' : ''}`}>#{prediction.source_id} · {prediction.description}</span> <small className="muted">Model score {prediction.score.toFixed(3)}</small><p dir="auto">{selected.segments.find(s => s.id === prediction.source_id)?.text}</p>{prediction.needs_review && <small className="mint">Review: {prediction.review_reasons.map(reason => reason.replaceAll('_', ' ')).join('; ')}</small>}<small className="muted dialogue-alternatives">Alternatives: {prediction.top_labels.map(label => `${label.label} ${label.score.toFixed(3)}`).join(' · ')}</small></article>)}</div></>}</section>
    <div className="row downloads"><span className="muted">Download transcript</span><div><a href={`/api/meetings/${selected.id}/transcript?format=txt`}>TXT</a> <a href={`/api/meetings/${selected.id}/transcript?format=json`}>JSON</a>{selected.segments.some(s => s.start != null) && <> <a href={`/api/meetings/${selected.id}/transcript?format=vtt`}>VTT</a></>}</div></div>
    <MeetingMembers meetingId={selected.id} canOrganize={Boolean(access?.can_organize)} directory={directory} onDeleted={() => { void refresh(); navigate('/'); }}/>
    <LanguageProcessing profile={selected.language_profile} analysis={selected.dialogue_analysis?.language_processing}/><PreparedTranscript meeting={selected}/>
    <div className="columns"><section className="panel"><h2>Transcript evidence</h2>{selected.segments.map(s => <article key={s.id}><small className="mint">#{s.id} · {s.speaker || 'Unknown speaker'}{s.start != null ? ` · ${s.start.toFixed(1)}s – ${s.end?.toFixed(1)}s` : ''}</small><p dir="auto">{s.text}</p>{s.parent_source_id != null && <details><summary>Source turn #{s.parent_source_id}</summary><p>{selected.source_segments?.find(parent => parent.id === s.parent_source_id)?.text}</p><small className="muted">Characters {s.source_start}–{s.source_end}</small></details>}</article>)}</section>
    <CommitmentResults onDraft={item => { setDraftSource({ meeting_id: selected.id, commitment: item }); navigate('/drafts'); }} meeting={selected} onReview={reviewCommitment} disabled={busy !== null}
      access={access} directory={directory} onAssign={assign}/></div>
  </>;
  else page = <><div className="row"><div><p className="eyebrow">FROM CONVERSATION TO CLARITY</p><h1>Your meeting workspace.</h1><p className="muted">Capture discussions. Surface commitments. Keep the evidence.</p></div>{organizer && <button className="primary" onClick={() => navigate('/upload')}><Upload size={17}/> Upload meeting</button>}</div>
    <div className="stats"><div className="panel"><strong>{meetings.length}</strong><span>{me.is_admin ? 'Meetings in workspace' : 'Your meetings'}</span></div><div className="panel"><strong>{meetings.reduce((n, m) => n + m.actions.length, 0)}</strong><span>Extracted commitments</span></div><div className="panel"><strong>{waiting}</strong><span>Waiting for your approval</span></div></div>
    <h2>Meeting library</h2>{meetings.length ? <div className="library">{meetings.map(m => <button className="panel meeting" key={m.id} onClick={() => navigate(`/meetings/${m.id}`)}><FileText className="mint"/><div><h3>{m.title}</h3><p className="muted">{m.segments.length} utterances · {m.actions.length} commitments{m.access ? ` · ${roleLabel[m.access.role]}` : ''}</p></div><span className="pill">{m.status}</span><ArrowRight size={18}/></button>)}</div>
      : <div className="panel empty"><FileText size={32}/><h3>A clearer follow-up starts here.</h3>{organizer ? <><p className="muted">Upload your first transcript to build your meeting library.</p><button className="primary" onClick={() => navigate('/upload')}>Add a meeting <ArrowRight size={17}/></button></>
        : <p className="muted">Meetings appear here when an organizer assigns you an action item or adds you to a meeting.</p>}</div>}</>;
  return <div className="shell"><aside><div className="brand"><Zap/><strong>MeetMind</strong></div><p className="eyebrow">LOCAL WORKSPACE</p>
    <nav>{link('/', <><FileText size={19}/> Meetings</>, path === '/' || Boolean(meetingId))}
      {organizer && link('/upload', <><Upload size={19}/> Upload transcript</>)}
      {organizer && link('/bot', <><Video size={19}/> Google Meet bot</>)}
      {link('/queue', <><Inbox size={19}/> My approvals{waiting > 0 && <span className="count">{waiting}</span>}</>)}
      {link('/drafts', <><Mail size={19}/> Follow-up drafts</>)}
      {link('/account', <><User size={19}/> Account</>)}
      {me.is_admin && link('/admin', <><Shield size={19}/> Admin</>)}</nav>
    <div className="local"><Cpu size={19}/><div>Ollama · {health.ollama}<small>{health.model}</small></div></div>
    <div className="signed-in"><div><strong>{me.name}</strong><small>{me.role === 'organizer' ? 'Organizer' : 'Member'}{me.is_admin ? ' · Admin' : ''}</small></div><button aria-label="Sign out" title="Sign out" onClick={signOut}><LogOut size={17}/></button></div></aside>
    <main><header><span>Iteration 02 <span className="muted">/ Reviewed follow-up</span></span><span className="pill">Local inference</span></header><div className="content">{error && <div role="alert" className="error">{error}</div>}
      {page}
    </div></main></div>;
}

function NeedsOrganizer({ navigate }: { navigate: (path: string) => void }) {
  return <div className="panel empty"><h3>Organizer access needed</h3><p className="muted">Organizers create, upload and capture meetings. Request access from your account page; an admin approves it.</p>
    <button className="primary" onClick={() => navigate('/account')}>Go to account</button></div>;
}

function MeetingMembers({ meetingId, canOrganize, directory, onDeleted }: { meetingId: string; canOrganize: boolean; directory: DirectoryUser[]; onDeleted: () => void }) {
  const [members, setMembers] = useState<Member[]>([]), [choice, setChoice] = useState(''), [confirm, setConfirm] = useState(false);
  const [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const load = () => api<Member[]>(`/meetings/${meetingId}/members`).then(setMembers);
  useEffect(() => { setConfirm(false); void load().catch(e => setError(e.message)); }, [meetingId]);
  async function act(action: () => Promise<unknown>) {
    setBusy(true); setError('');
    try { await action(); await load(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  const candidates = directory.filter(user => !members.some(member => member.id === user.id));
  return <section className="panel members"><h2>People</h2>
    {error && <p role="alert" className="error">{error}</p>}
    <ul>{members.map(member => <li key={member.id + member.role}><span><strong>{member.name}</strong> <small className="muted">{member.email}</small></span><span className="pill">{roleLabel[member.role] || member.role}</span>
      {canOrganize && member.role === 'viewer' && <button disabled={busy} onClick={() => void act(() => api(`/meetings/${meetingId}/members/${member.id}`, 'DELETE'))}>Remove</button>}</li>)}</ul>
    {canOrganize && <><form className="row" onSubmit={e => { e.preventDefault(); void act(async () => { await api(`/meetings/${meetingId}/members`, 'POST', { user_id: choice }); setChoice(''); }); }}>
      <select aria-label="Add viewer" value={choice} onChange={e => setChoice(e.target.value)}><option value="">Add a viewer…</option>{candidates.map(user => <option key={user.id} value={user.id}>{user.name} ({user.email})</option>)}</select>
      <button disabled={busy || !choice}>Add viewer</button></form>
      <p className="muted">Owners appear automatically when you link an action item to their account. Viewers can read the meeting but cannot approve anything.</p>
      {confirm ? <div className="row danger"><span>Delete this meeting, its drafts and assignments? This cannot be undone.</span>
        <button disabled={busy} onClick={() => { setBusy(true); api(`/meetings/${meetingId}`, 'DELETE').then(onDeleted, e => { setError(e.message); setBusy(false); }); }}>Delete permanently</button><button onClick={() => setConfirm(false)}>Cancel</button></div>
        : <button className="link-danger" onClick={() => setConfirm(true)}>Delete meeting…</button>}</>}
  </section>;
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);
