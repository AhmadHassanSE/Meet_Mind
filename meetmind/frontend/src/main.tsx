import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { FileText, Upload, ArrowRight, Cpu, Inbox, Video, Mail, User, Shield, LogOut, Search, Sun, Moon, Monitor, CornerDownLeft } from 'lucide-react';
import '@fontsource-variable/inter';
import '@fontsource-variable/fraunces';
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
import { WorkflowPanel } from './WorkflowPanel';
import { Logo, useCountUp } from './ui';
import { api, useRoute, SIGNED_OUT, type Access, type DirectoryUser, type Me } from './api';

type DialoguePrediction = { source_id: number; label: string; description: string; score: number; possible_action: boolean; needs_review: boolean; review_reasons: string[]; top_labels: { label: string; score: number }[] };
type Meeting = PreparedMeeting & Omit<CommitmentMeeting, 'segments'> & { id: string; title: string; status: string; model: string | null; source_type?: string; created_at?: string; meeting_date?: string; access?: Access | null; segments: { id: number; speaker: string | null; text: string; source: string; start?: number | null; end?: number | null; parent_source_id?: number; source_start?: number; source_end?: number }[]; dialogue_analysis?: { language_processing?: LanguageProcessingInfo; predictions: DialoguePrediction[]; model: { model_name: string; checkpoint_stage: string } } };
type Member = { id: string; name: string; email: string; role: string };
type Theme = 'system' | 'light' | 'dark';
const roleLabel: Record<string, string> = { organizer: 'Organizer', owner: 'Owner', viewer: 'Viewer', admin: 'Admin (view only)' };
const statusLabel: Record<string, string> = { uploaded: 'Not analysed', extracted: 'Extracted' };

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

function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(() => {
    try { return (localStorage.getItem('meetmind-theme') as Theme) || 'system'; } catch { return 'system'; }
  });
  useEffect(() => {
    if (theme === 'system') delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = theme;
    try { localStorage.setItem('meetmind-theme', theme); } catch { /* storage unavailable */ }
  }, [theme]);
  return [theme, () => setTheme(t => t === 'system' ? 'light' : t === 'light' ? 'dark' : 'system')];
}

function Workspace({ me, path, navigate, reloadMe, signOut }: { me: Me; path: string; navigate: (path: string) => void; reloadMe: () => Promise<void>; signOut: () => void }) {
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [draftSource, setDraftSource] = useState<DraftSource | null>(null);
  const [selected, setSelected] = useState<Meeting | null>(null);
  const [directory, setDirectory] = useState<DirectoryUser[]>([]);
  const [waiting, setWaiting] = useState(0);
  const [health, setHealth] = useState({ ollama: 'checking', model: 'llama3.2:latest', bert: { status: 'checking', stage: '' } });
  const [busy, setBusy] = useState<'extract' | 'bert' | 'review' | null>(null);
  const [error, setError] = useState('');
  const [palette, setPalette] = useState(false);
  const [theme, cycleTheme] = useTheme();
  const organizer = me.role === 'organizer';
  const meetingId = path.match(/^\/meetings\/([^/]+)$/)?.[1] || null;
  const refresh = () => api<Meeting[]>('/meetings').then(list => { setMeetings(list); setLoaded(true); });
  useEffect(() => {
    Promise.all([refresh(), api<typeof health>('/health').then(setHealth)]).catch(e => { setError(e.message); setLoaded(true); });
    // Resume an unfinished capture or upload after a refresh, as before routing existed.
    if (path === '/' && organizer) {
      if (localStorage.getItem('meetmind-bot-id')) navigate('/bot');
      else if (localStorage.getItem('meetmind-ingestion-job')) navigate('/upload');
    }
  }, []);
  useEffect(() => {
    const open = (e: KeyboardEvent) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setPalette(p => !p); } };
    window.addEventListener('keydown', open);
    return () => window.removeEventListener('keydown', open);
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
  const go = (to: string) => { if (to === '/drafts') setDraftSource(null); navigate(to); };
  const link = (to: string, label: React.ReactNode, active = path === to) =>
    <a href={to} className={active ? 'active' : ''} aria-current={active ? 'page' : undefined} onClick={e => { e.preventDefault(); go(to); }}>{label}</a>;
  const pages = [{ to: '/', label: 'Meetings', show: true }, { to: '/queue', label: 'My approvals', show: true },
    { to: '/drafts', label: 'Follow-up drafts', show: true }, { to: '/upload', label: 'Upload transcript', show: organizer },
    { to: '/bot', label: 'Google Meet bot', show: organizer }, { to: '/account', label: 'Account', show: true },
    { to: '/admin', label: 'Admin', show: me.is_admin }].filter(p => p.show);
  const pageTitle = meetingId ? selected?.title || 'Meeting' : pages.find(p => p.to === path)?.label || 'Meetings';
  const access = selected?.access;
  let page: React.ReactNode;
  if (path === '/upload') page = organizer ? <UploadMeeting onReady={openMeeting}/> : <NeedsOrganizer navigate={navigate}/>;
  else if (path === '/bot') page = organizer ? <MeetingBot onReady={openMeeting}/> : <NeedsOrganizer navigate={navigate}/>;
  else if (path === '/drafts' || path === '/queue') page = <ArtifactWorkspace queue={path === '/queue'} source={path === '/drafts' ? draftSource : null} onMeeting={id => navigate(`/meetings/${id}`)}/>;
  else if (path === '/account') page = <Account me={me} onChanged={reloadMe}/>;
  else if (path === '/admin') page = me.is_admin ? <Admin me={me}/> : <p className="error">Admin access required.</p>;
  else if (meetingId) page = !selected ? (error ? null : <MeetingSkeleton/>) : <MeetingPage meeting={selected} access={access} health={health} busy={busy}
    directory={directory} navigate={navigate} run={run} onReview={reviewCommitment} onAssign={assign} refresh={refresh}
    onDraft={item => { setDraftSource({ meeting_id: selected.id, commitment: item }); navigate('/drafts'); }}
    onChanged={() => void api<Meeting>(`/meetings/${selected.id}`).then(m => setSelected(current => current?.id === m.id ? m : current)).catch(() => {})}/>;
  else page = <Home me={me} meetings={meetings} loaded={loaded} waiting={waiting} navigate={navigate}/>;
  return <div className="shell"><aside>
    <a className="brand" href="/" onClick={e => { e.preventDefault(); go('/'); }}><Logo/><strong>MeetMind</strong></a>
    <nav aria-label="Main">
      <p className="nav-group">Work</p>
      {link('/', <><FileText size={18} aria-hidden="true"/> Meetings</>, path === '/' || Boolean(meetingId))}
      {link('/queue', <><Inbox size={18} aria-hidden="true"/> My approvals{waiting > 0 && <span className="count" aria-label={`${waiting} waiting`}>{waiting}</span>}</>)}
      {link('/drafts', <><Mail size={18} aria-hidden="true"/> Follow-up drafts</>)}
      {organizer && <><p className="nav-group">Capture</p>
        {link('/upload', <><Upload size={18} aria-hidden="true"/> Upload transcript</>)}
        {link('/bot', <><Video size={18} aria-hidden="true"/> Google Meet bot</>)}</>}
      <p className="nav-group">Settings</p>
      {link('/account', <><User size={18} aria-hidden="true"/> Account</>)}
      {me.is_admin && link('/admin', <><Shield size={18} aria-hidden="true"/> Admin</>)}
    </nav>
    <div className="local" title={`BERT: ${health.bert.status}`}><Cpu size={16} aria-hidden="true"/><div>Local models<small>Ollama {health.ollama} · {health.model}</small></div></div>
    <div className="signed-in"><div><strong>{me.name}</strong><small>{me.role === 'organizer' ? 'Organizer' : 'Member'}{me.is_admin ? ' · Admin' : ''}</small></div><button aria-label="Sign out" title="Sign out" onClick={signOut}><LogOut size={16}/></button></div></aside>
    <main><header>
      <span className="page-title">{pageTitle}</span>
      <div className="header-tools">
        <button className="search-trigger" onClick={() => setPalette(true)}><Search size={15} aria-hidden="true"/><span>Jump to…</span><kbd>Ctrl K</kbd></button>
        <button className="icon-button" aria-label={`Theme: ${theme}. Change theme`} title={`Theme: ${theme}`} onClick={cycleTheme}>
          {theme === 'light' ? <Sun size={16}/> : theme === 'dark' ? <Moon size={16}/> : <Monitor size={16}/>}</button>
      </div></header>
      <div className="content">{error && <div role="alert" className="error">{error}</div>}
        <div className="page" key={meetingId || path}>{page}</div>
      </div></main>
    {palette && <CommandPalette pages={pages} meetings={meetings} onClose={() => setPalette(false)} go={to => { setPalette(false); go(to); }}/>}
  </div>;
}

function Home({ me, meetings, loaded, waiting, navigate }: { me: Me; meetings: Meeting[]; loaded: boolean; waiting: number; navigate: (path: string) => void }) {
  const [query, setQuery] = useState('');
  const organizer = me.role === 'organizer';
  const commitments = meetings.reduce((n, m) => n + m.actions.length, 0);
  const approved = meetings.reduce((n, m) => n + m.actions.filter(a => a.review_status === 'approved').length, 0);
  const shown = meetings.filter(m => m.title.toLowerCase().includes(query.trim().toLowerCase()));
  const hour = new Date().getHours();
  const greeting = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening';
  return <>
    <div className="page-head"><div><h1>{greeting}, {me.name.split(' ')[0]}</h1>
      <p className="muted">{waiting ? `${waiting} follow-up${waiting === 1 ? ' is' : 's are'} waiting for your decision.` : 'Nothing is waiting for your decision.'} Every commitment links back to what was said.</p></div>
      {organizer && <button className="primary" onClick={() => navigate('/upload')}><Upload size={17} aria-hidden="true"/> Upload meeting</button>}</div>
    <div className="stats">
      <Stat value={meetings.length} label={me.is_admin ? 'Meetings in workspace' : 'Your meetings'} ready={loaded}/>
      <Stat value={commitments} label="Extracted commitments" detail={commitments ? `${approved} approved by a person` : undefined} ready={loaded}/>
      <button className="panel stat-link" onClick={() => navigate('/queue')}><Stat value={waiting} label="Waiting for your approval" detail="Open My approvals" ready={loaded} bare/></button>
    </div>
    <div className="row library-head"><h2>Meeting library</h2>
      {meetings.length > 3 && <label className="search"><Search size={15} aria-hidden="true"/><input type="search" aria-label="Search meetings" placeholder="Search meetings" value={query} onChange={e => setQuery(e.target.value)}/></label>}</div>
    {!loaded ? <div className="library">{[0, 1, 2].map(i => <div className="panel meeting skeleton" key={i} aria-hidden="true"><span/><span/></div>)}</div>
      : shown.length ? <div className="library">{shown.map((m, index) => <MeetingCard key={m.id} meeting={m} index={index} onOpen={() => navigate(`/meetings/${m.id}`)}/>)}</div>
      : meetings.length ? <div className="panel empty"><h3>No meeting matches “{query}”</h3><p className="muted">Try another word from the meeting title.</p><button onClick={() => setQuery('')}>Clear search</button></div>
      : <div className="panel empty"><FileText size={32} aria-hidden="true"/><h3>A clearer follow-up starts here.</h3>{organizer ? <><p className="muted">Upload your first transcript to build your meeting library.</p><button className="primary" onClick={() => navigate('/upload')}>Add a meeting <ArrowRight size={17} aria-hidden="true"/></button></>
        : <p className="muted">Meetings appear here when an organizer assigns you an action item or adds you to a meeting.</p>}</div>}</>;
}

function Stat({ value, label, detail, ready, bare }: { value: number; label: string; detail?: string; ready: boolean; bare?: boolean }) {
  const shown = useCountUp(ready ? value : 0);
  const body = <><strong>{shown}</strong><span>{label}</span>{detail && <small>{detail}</small>}</>;
  return bare ? body : <div className="panel">{body}</div>;
}

function MeetingCard({ meeting, index, onOpen }: { meeting: Meeting; index: number; onOpen: () => void }) {
  const total = meeting.actions.length;
  const approved = meeting.actions.filter(a => a.review_status === 'approved').length;
  const date = meeting.meeting_date || meeting.created_at;
  return <button className="panel meeting" style={{ '--i': Math.min(index, 12) } as React.CSSProperties} onClick={onOpen}>
    <FileText className="mint" aria-hidden="true"/>
    <div><h3>{meeting.title}</h3>
      <p className="muted">{date ? new Date(date).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }) + ' · ' : ''}{meeting.segments.length} utterances · {total ? `${approved}/${total} commitments approved` : 'no commitments yet'}{meeting.access ? ` · ${roleLabel[meeting.access.role]}` : ''}</p>
      {total > 0 && <span className="progress-line" aria-hidden="true"><span style={{ transform: `scaleX(${approved / total})` }}/></span>}</div>
    <span className={`pill${meeting.status === 'uploaded' ? ' quiet' : ''}`}>{statusLabel[meeting.status] || meeting.status}</span>
    <ArrowRight size={18} aria-hidden="true"/></button>;
}

function MeetingPage({ meeting, access, health, busy, directory, navigate, run, onReview, onAssign, onDraft, onChanged, refresh }: {
  meeting: Meeting; access?: Access | null; health: { bert: { status: string; stage: string } }; busy: string | null; directory: DirectoryUser[];
  navigate: (path: string) => void; run: (kind: 'extract' | 'bert', action: string) => Promise<void>; onReview: (id: string, data: ReviewData) => Promise<void>;
  onAssign: (id: string, revision: number, userId: string | null) => Promise<void>; onDraft: (item: CommitmentMeeting['actions'][number]) => void;
  onChanged: () => void; refresh: () => Promise<void>;
}) {
  const [spotlight, setSpotlight] = useState<number[]>([]);
  const reviewed = [...meeting.actions, ...(meeting.action_candidates || [])].some(item => item.review_history?.length);
  // Evidence spotlight: scroll the transcript to the quoted sentence and highlight it.
  function showSource(ids: number[]) {
    setSpotlight(ids);
    document.getElementById(`segment-${ids[0]}`)?.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'center' });
    window.setTimeout(() => setSpotlight([]), 2600);
  }
  const date = meeting.meeting_date || meeting.created_at;
  return <>
    <button className="back" onClick={() => navigate('/')}>← All meetings</button>
    <div className="page-head"><div><h1>{meeting.title}</h1>
      <p className="muted">{date ? new Date(date).toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }) + ' · ' : ''}{meeting.segments.length} utterances · {meeting.source_type || 'text'} · {statusLabel[meeting.status] || meeting.status}</p>
      {access && <p className="muted role-line">Your role: <span className="pill">{roleLabel[access.role]}</span>{access.role === 'admin' && ' Your access to this meeting is recorded in the audit log.'}</p>}</div>
      {access?.can_organize && <button className="primary" disabled={busy !== null || reviewed} title={reviewed ? 'Reviewed meetings keep their decisions; upload a new copy to extract again.' : undefined}
        onClick={() => void run('extract', 'extract')}>{busy === 'extract' ? 'Extracting locally…' : 'Extract commitments'}<Cpu size={17} aria-hidden="true"/></button>}</div>
    <nav className="section-nav" aria-label="On this page">
      {[['workflow', 'Workflow'], ['commitments', 'Commitments'], ['analysis', 'Dialogue analysis'], ['people', 'People']].map(([id, label]) =>
        <a key={id} href={`#${id}`} onClick={e => { e.preventDefault(); document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' }); }}>{label}</a>)}</nav>
    <div id="workflow" className="anchor"><WorkflowPanel meetingId={meeting.id} actions={meeting.actions} navigate={navigate} onChanged={onChanged}/></div>
    <div className="columns anchor" id="commitments"><section className="panel transcript"><h2>Transcript evidence</h2>{meeting.segments.map(s =>
      <article key={s.id} id={`segment-${s.id}`} className={spotlight.includes(s.id) ? 'spotlight' : undefined}><small className="mint">#{s.id} · {s.speaker || 'Unknown speaker'}{s.start != null ? ` · ${s.start.toFixed(1)}s – ${s.end?.toFixed(1)}s` : ''}</small><p dir="auto">{s.text}</p>{s.parent_source_id != null && <details><summary>Source turn #{s.parent_source_id}</summary><p>{meeting.source_segments?.find(parent => parent.id === s.parent_source_id)?.text}</p><small className="muted">Characters {s.source_start}–{s.source_end}</small></details>}</article>)}</section>
      <CommitmentResults onDraft={onDraft} meeting={meeting} onReview={onReview} disabled={busy !== null}
        access={access} directory={directory} onAssign={onAssign} onShowSource={showSource}/></div>
    <section className="panel bert-summary anchor" id="analysis"><div className="row"><div><h2>BERT dialogue analysis</h2><p className="muted">{health.bert.status}{health.bert.stage ? ` · ${health.bert.stage}` : ''}</p></div>{access?.can_organize && <button className="primary" disabled={busy !== null} onClick={() => void run('bert', 'classify')}>{busy === 'bert' ? 'Processing locally…' : 'Analyze with BERT'}<Cpu size={17} aria-hidden="true"/></button>}</div><p className="muted">Classifies each utterance's dialogue act and highlights possible actions. Offers and suggestions still need a person's approval before they become tasks.</p>{meeting.dialogue_analysis && <><small className="muted">{meeting.dialogue_analysis.model.model_name} · {meeting.dialogue_analysis.model.checkpoint_stage}</small><div className="dialogue-results">{meeting.dialogue_analysis.predictions.map(prediction => <article key={prediction.source_id}><span className={`pill${prediction.possible_action ? ' warning' : ''}`}>#{prediction.source_id} · {prediction.description}</span> <small className="muted">Model score {prediction.score.toFixed(3)}</small><p dir="auto">{meeting.segments.find(s => s.id === prediction.source_id)?.text}</p>{prediction.needs_review && <small className="mint">Review: {prediction.review_reasons.map(reason => reason.replaceAll('_', ' ')).join('; ')}</small>}<small className="muted dialogue-alternatives">Alternatives: {prediction.top_labels.map(label => `${label.label} ${label.score.toFixed(3)}`).join(' · ')}</small></article>)}</div></>}</section>
    <LanguageProcessing profile={meeting.language_profile} analysis={meeting.dialogue_analysis?.language_processing}/><PreparedTranscript meeting={meeting}/>
    <div id="people" className="anchor"><MeetingMembers meetingId={meeting.id} canOrganize={Boolean(access?.can_organize)} directory={directory} onDeleted={() => { void refresh(); navigate('/'); }}/></div>
    <div className="row downloads"><span className="muted">Download transcript</span><div><a href={`/api/meetings/${meeting.id}/transcript?format=txt`}>TXT</a> <a href={`/api/meetings/${meeting.id}/transcript?format=json`}>JSON</a>{meeting.segments.some(s => s.start != null) && <> <a href={`/api/meetings/${meeting.id}/transcript?format=vtt`}>VTT</a></>}</div></div>
  </>;
}

function MeetingSkeleton() {
  return <div className="skeleton-page" aria-busy="true" aria-label="Loading meeting"><span className="skeleton-line wide"/><span className="skeleton-line"/><div className="panel skeleton tall"/><div className="columns"><div className="panel skeleton tall"/><div className="panel skeleton tall"/></div></div>;
}

function CommandPalette({ pages, meetings, onClose, go }: { pages: { to: string; label: string }[]; meetings: Meeting[]; onClose: () => void; go: (to: string) => void }) {
  const [query, setQuery] = useState(''), [active, setActive] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const items = useMemo(() => {
    const q = query.trim().toLowerCase();
    return [...pages.map(p => ({ to: p.to, label: p.label, kind: 'Page' })),
      ...meetings.map(m => ({ to: `/meetings/${m.id}`, label: m.title, kind: 'Meeting' }))]
      .filter(item => item.label.toLowerCase().includes(q)).slice(0, 12);
  }, [query, pages, meetings]);
  useEffect(() => { input.current?.focus(); }, []);
  useEffect(() => { setActive(0); }, [query]);
  function key(e: React.KeyboardEvent) {
    if (e.key === 'Escape') onClose();
    else if (e.key === 'ArrowDown') { e.preventDefault(); setActive(a => Math.min(a + 1, items.length - 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setActive(a => Math.max(a - 1, 0)); }
    else if (e.key === 'Enter' && items[active]) go(items[active].to);
  }
  return <div className="palette-backdrop" onMouseDown={onClose}>
    <div className="palette" role="dialog" aria-modal="true" aria-label="Jump to a page or meeting" onMouseDown={e => e.stopPropagation()} onKeyDown={key}>
      <label className="palette-input"><Search size={17} aria-hidden="true"/><input ref={input} role="combobox" aria-expanded="true" aria-controls="palette-list"
        aria-activedescendant={items[active] ? `palette-${active}` : undefined} placeholder="Jump to a page or meeting" value={query} onChange={e => setQuery(e.target.value)}/><kbd>Esc</kbd></label>
      <ul id="palette-list" role="listbox">{items.length ? items.map((item, index) =>
        <li key={item.to} id={`palette-${index}`} role="option" aria-selected={index === active} onMouseEnter={() => setActive(index)} onClick={() => go(item.to)}>
          <span>{item.label}</span><small>{item.kind}</small>{index === active && <CornerDownLeft size={14} aria-hidden="true"/>}</li>)
        : <li className="palette-empty" role="option" aria-selected="false">No page or meeting matches “{query}”.</li>}</ul>
    </div></div>;
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
    <ul>{members.map(member => <li key={member.id + member.role}><span className="avatar" aria-hidden="true">{member.name.slice(0, 1).toUpperCase()}</span><span><strong>{member.name}</strong> <small className="muted">{member.email}</small></span><span className="pill">{roleLabel[member.role] || member.role}</span>
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
