import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { FileText, Plus, ArrowRight, Cpu, Inbox, Mail, User, Shield, LogOut, Search, Sun, Moon, Monitor, CornerDownLeft,
  CalendarDays, Download, FlaskConical, CheckCircle2, ListChecks } from 'lucide-react';
import '@fontsource-variable/inter';
import '@fontsource-variable/fraunces';
import './styles.css';
import { ArtifactWorkspace, type DraftSource } from './ArtifactWorkspace';
import { UploadMeeting } from './UploadMeeting';
import { CommitmentResults, type CommitmentMeeting, type ReviewData } from './CommitmentResults';
import { PreparedTranscript, type PreparedMeeting } from './PreparedTranscript';
import { LanguageProcessing, type LanguageProcessingInfo } from './LanguageProcessing';
import { AuthScreen } from './Auth';
import { Account } from './Account';
import { Admin } from './Admin';
import { NextStep } from './WorkflowPanel';
import { DetailsContext, Logo, Ring, speakerTone, useDetails, useDetailsSetting, useIndicator } from './ui';
import { api, useRoute, SIGNED_OUT, type Access, type DirectoryUser, type Me } from './api';

type DialoguePrediction = { source_id: number; label: string; description: string; score: number; possible_action: boolean; needs_review: boolean; review_reasons: string[]; top_labels: { label: string; score: number }[] };
type Meeting = PreparedMeeting & Omit<CommitmentMeeting, 'segments'> & { id: string; title: string; status: string; model: string | null; source_type?: string; created_at?: string; meeting_date?: string; access?: Access | null; segments: { id: number; speaker: string | null; text: string; source: string; start?: number | null; end?: number | null; parent_source_id?: number; source_start?: number; source_end?: number }[]; dialogue_analysis?: { language_processing?: LanguageProcessingInfo; predictions: DialoguePrediction[]; model: { model_name: string; checkpoint_stage: string } } };
type Member = { id: string; name: string; email: string; role: string };
type Theme = 'system' | 'light' | 'dark';
const roleLabel: Record<string, string> = { organizer: 'Organizer', owner: 'Owner', viewer: 'Viewer', admin: 'Admin (view only)' };
const clock = (seconds: number) => `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`;

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
  if (me === undefined) return <div className="boot" aria-busy="true"><Logo size={56}/><p className="muted">Loading MeetMind…</p></div>;
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

/** A meeting's state in plain words: still to analyse, items to review, or finished. */
type Filter = 'all' | 'new' | 'review' | 'done';
function meetingState(m: Meeting): Exclude<Filter, 'all'> {
  if (m.status === 'uploaded') return 'new';
  const items = [...m.actions, ...(m.action_candidates || [])];
  return items.every(a => a.review_status === 'approved' || a.review_status === 'rejected') ? 'done' : 'review';
}
const stateLabel = { new: 'Not analysed', review: 'To review', done: 'Reviewed' };

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
  const [details, toggleDetails] = useDetailsSetting();
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
  const activePath = meetingId ? '/' : path === '/bot' ? '/upload' : path;
  const [navRef, indicator] = useIndicator<HTMLElement>('a.active', [activePath, organizer, me.is_admin, waiting > 0]);
  const link = (to: string, label: React.ReactNode, active = activePath === to) =>
    <a href={to} className={active ? 'active' : ''} aria-current={active ? 'page' : undefined} onClick={e => { e.preventDefault(); go(to); }}>{label}</a>;
  const pages = [{ to: '/', label: 'Meetings', show: true }, { to: '/upload', label: 'Add meeting', show: organizer },
    { to: '/queue', label: 'My approvals', show: true }, { to: '/drafts', label: 'All follow-ups', show: true },
    { to: '/account', label: 'Account', show: true }, { to: '/admin', label: 'Admin', show: me.is_admin }].filter(p => p.show);
  const pageTitle = meetingId ? selected?.title || 'Meeting' : path === '/bot' ? 'Add meeting' : pages.find(p => p.to === path)?.label || 'Meetings';
  let page: React.ReactNode;
  if (path === '/upload' || path === '/bot') page = organizer ? <UploadMeeting onReady={openMeeting} initialTab={path === '/bot' ? 'meet' : 'text'}/> : <NeedsOrganizer navigate={navigate}/>;
  else if (path === '/drafts' || path === '/queue') page = <ArtifactWorkspace queue={path === '/queue'} source={path === '/drafts' ? draftSource : null} onMeeting={id => navigate(`/meetings/${id}`)}/>;
  else if (path === '/account') page = <Account me={me} onChanged={reloadMe}/>;
  else if (path === '/admin') page = me.is_admin ? <Admin me={me}/> : <p className="error">Admin access required.</p>;
  else if (meetingId) page = !selected ? (error ? null : <MeetingSkeleton/>) : <MeetingPage meeting={selected} health={health} busy={busy}
    directory={directory} navigate={navigate} run={run} onReview={reviewCommitment} onAssign={assign} refresh={refresh}
    onDraft={item => { setDraftSource({ meeting_id: selected.id, commitment: item }); navigate('/drafts'); }}
    onChanged={() => void api<Meeting>(`/meetings/${selected.id}`).then(m => setSelected(current => current?.id === m.id ? m : current)).catch(() => {})}/>;
  else page = <Home me={me} meetings={meetings} loaded={loaded} waiting={waiting} navigate={navigate}/>;
  return <DetailsContext.Provider value={details}><div className="shell"><aside className="sidebar">
    <a className="brand" href="/" onClick={e => { e.preventDefault(); go('/'); }}><Logo size={38}/><span><strong>MeetMind</strong><small>Meetings to follow-ups</small></span></a>
    <nav aria-label="Main" ref={navRef}>
      <span className="nav-indicator" aria-hidden="true" style={indicator}/>
      {link('/', <><FileText size={18} aria-hidden="true"/> Meetings</>)}
      {organizer && link('/upload', <><Plus size={18} aria-hidden="true"/> Add meeting</>)}
      {link('/queue', <><Inbox size={18} aria-hidden="true"/> My approvals{waiting > 0 && <span className="count" aria-label={`${waiting} waiting`}>{waiting}</span>}</>)}
      {link('/drafts', <><Mail size={18} aria-hidden="true"/> All follow-ups</>)}
      <p className="nav-group">Settings</p>
      {link('/account', <><User size={18} aria-hidden="true"/> Account</>)}
      {me.is_admin && link('/admin', <><Shield size={18} aria-hidden="true"/> Admin</>)}
    </nav>
    {details && <div className={`local${health.ollama === 'ready' ? ' up' : ''}`}><Cpu size={16} aria-hidden="true"/>
      <div>Local models<small>Ollama {health.ollama} · {health.model}</small><small>BERT {health.bert.status}</small></div></div>}
    <div className="signed-in"><span className="avatar" aria-hidden="true">{me.name.slice(0, 1).toUpperCase()}</span>
      <div><strong>{me.name}</strong><small>{me.role === 'organizer' ? 'Organizer' : 'Member'}{me.is_admin ? ', admin' : ''}</small></div>
      <button className="icon-button quiet" aria-label="Sign out" title="Sign out" onClick={signOut}><LogOut size={16}/></button></div></aside>
    <main><header className="topbar">
      <span className="page-title">{pageTitle}</span>
      <div className="header-tools">
        <button className="search-trigger" onClick={() => setPalette(true)}><Search size={15} aria-hidden="true"/><span>Find a meeting…</span><kbd>Ctrl K</kbd></button>
        <button className={`icon-button detail-toggle${details ? ' on' : ''}`} aria-pressed={details} aria-label={details ? 'Hide technical details' : 'Show technical details'}
          title={details ? 'Hide model scores, pipeline information and source metadata.' : 'Show model scores, pipeline information and source metadata.'} onClick={toggleDetails}><FlaskConical size={16}/><span>Details</span></button>
        <button className="icon-button" aria-label={`Theme: ${theme}. Change theme`} title={`Theme: ${theme}`} onClick={cycleTheme}>
          {theme === 'light' ? <Sun size={16}/> : theme === 'dark' ? <Moon size={16}/> : <Monitor size={16}/>}</button>
      </div></header>
      <div className="content">{error && <div role="alert" className="error">{error}</div>}
        <div className="page" key={meetingId || path}>{page}</div>
      </div></main>
    {palette && <CommandPalette pages={pages} meetings={meetings} onClose={() => setPalette(false)} go={to => { setPalette(false); go(to); }}/>}
  </div></DetailsContext.Provider>;
}

function Home({ me, meetings, loaded, waiting, navigate }: { me: Me; meetings: Meeting[]; loaded: boolean; waiting: number; navigate: (path: string) => void }) {
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<Filter>('all');
  const organizer = me.role === 'organizer';
  const q = query.trim().toLowerCase();
  const shown = meetings.filter(m => m.title.toLowerCase().includes(q) && (filter === 'all' || meetingState(m) === filter));
  const counts = { all: meetings.length, new: 0, review: 0, done: 0 };
  meetings.forEach(m => { counts[meetingState(m)] += 1; });
  const hour = new Date().getHours();
  const greeting = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening';
  const filters: [Filter, string][] = [['all', 'All'], ['review', 'To review'], ['new', 'Not analysed'], ['done', 'Reviewed']];
  // Only what needs a person's attention, most urgent first.
  const todo = [
    waiting > 0 && { key: 'approve', icon: Inbox, text: `${waiting} follow-up${waiting === 1 ? '' : 's'} waiting for your approval`, action: 'Review', onClick: () => navigate('/queue') },
    organizer && counts.review > 0 && { key: 'review', icon: ListChecks, text: `${counts.review} meeting${counts.review === 1 ? ' has' : 's have'} action items to review`, action: 'Show', onClick: () => setFilter('review') },
    organizer && counts.new > 0 && { key: 'new', icon: FileText, text: `${counts.new} meeting${counts.new === 1 ? ' is' : 's are'} not analysed yet`, action: 'Show', onClick: () => setFilter('new') },
  ].filter(Boolean) as { key: string; icon: typeof Inbox; text: string; action: string; onClick: () => void }[];
  return <>
    <div className="page-head home-head"><div><h1>{greeting}, {me.name.split(' ')[0]}</h1>
      <p className="muted">MeetMind finds the action items in your meetings and helps you follow up on them.</p></div>
      {organizer && <button className="primary" onClick={() => navigate('/upload')}><Plus size={17} aria-hidden="true"/> Add meeting</button>}</div>
    {loaded && meetings.length > 0 && <section className="todo" aria-label="Needs your attention">
      {todo.length ? todo.map(t => <button key={t.key} className="todo-item" onClick={t.onClick}><t.icon size={18} aria-hidden="true"/><span>{t.text}</span><span className="todo-go">{t.action} <ArrowRight size={15} aria-hidden="true"/></span></button>)
        : <p className="todo-clear"><CheckCircle2 size={18} aria-hidden="true"/> You're all caught up.</p>}
    </section>}
    <section className="library-section">
      <div className="row library-head"><h2>Meetings</h2>
        {meetings.length > 0 && <div className="library-tools">
          <div className="segmented" role="group" aria-label="Filter meetings">{filters.map(([id, label]) =>
            <button key={id} type="button" aria-pressed={filter === id} onClick={() => setFilter(id)}>{label}<span className="seg-count">{counts[id]}</span></button>)}</div>
          {meetings.length > 3 && <label className="search"><Search size={15} aria-hidden="true"/><input type="search" aria-label="Search meetings" placeholder="Search meetings" value={query} onChange={e => setQuery(e.target.value)}/></label>}
        </div>}</div>
      {!loaded ? <div className="library">{[0, 1, 2].map(i => <div className="panel meeting-skeleton skeleton" key={i} aria-hidden="true"><span/><span/></div>)}</div>
        : shown.length ? <div className="library">{shown.map(m => <MeetingCard key={m.id} meeting={m} onOpen={() => navigate(`/meetings/${m.id}`)}/>)}</div>
        : meetings.length ? <div className="panel empty"><h3>No meeting matches</h3><p className="muted">Try another word from the meeting title, or show all meetings.</p><button onClick={() => { setQuery(''); setFilter('all'); }}>Show all meetings</button></div>
        : <div className="panel empty"><span className="empty-mark"><Logo size={48}/></span><h3>No meetings yet</h3>{organizer ? <><p className="muted">Add a transcript, a recording or a live Google Meet. MeetMind then lists who agreed to do what.</p><button className="primary" onClick={() => navigate('/upload')}>Add your first meeting <ArrowRight size={17} aria-hidden="true"/></button></>
          : <p className="muted">Meetings appear here when an organizer adds you to one or gives you an action item.</p>}</div>}
    </section></>;
}

function MeetingCard({ meeting, onOpen }: { meeting: Meeting; onOpen: () => void }) {
  const items = [...meeting.actions, ...(meeting.action_candidates || [])];
  const reviewed = items.filter(a => a.review_status === 'approved' || a.review_status === 'rejected').length;
  const date = meeting.meeting_date || meeting.created_at;
  const state = meetingState(meeting);
  return <button className={`panel meeting state-${state}`} onClick={onOpen}>
    <span className="meeting-top"><span className={`pill${state === 'new' ? ' quiet' : state === 'done' ? ' ok' : ' warning'}`}>{stateLabel[state]}</span>
      {meeting.access && meeting.access.role !== 'organizer' && <span className="muted small">{roleLabel[meeting.access.role]}</span>}</span>
    <h3>{meeting.title}</h3>
    {date && <span className="meeting-meta"><span><CalendarDays size={14} aria-hidden="true"/>{new Date(date).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })}</span></span>}
    <span className="meeting-foot">{state !== 'new' && items.length > 0 && <Ring value={reviewed} total={items.length} size={30}/>}
      <span className="muted">{state === 'new' ? 'Open to find action items' : items.length ? `${reviewed} of ${items.length} action items reviewed` : 'No action items found'}</span>
      <ArrowRight size={18} aria-hidden="true" className="go"/></span>
  </button>;
}

type Tab = 'items' | 'transcript' | 'people' | 'details';

function MeetingPage({ meeting, health, busy, directory, navigate, run, onReview, onAssign, onDraft, onChanged, refresh }: {
  meeting: Meeting; health: { bert: { status: string; stage: string } }; busy: string | null; directory: DirectoryUser[];
  navigate: (path: string) => void; run: (kind: 'extract' | 'bert', action: string) => Promise<void>; onReview: (id: string, data: ReviewData) => Promise<void>;
  onAssign: (id: string, revision: number, userId: string | null) => Promise<void>; onDraft: (item: CommitmentMeeting['actions'][number]) => void;
  onChanged: () => void; refresh: () => Promise<void>;
}) {
  const details = useDetails();
  const access = meeting.access;
  const [tab, setTab] = useState<Tab>('items');
  const [spotlight, setSpotlight] = useState<number[]>([]);
  const [tabsRef, tabIndicator] = useIndicator<HTMLDivElement>('[aria-selected="true"]', [tab, details]);
  const all = [...meeting.actions, ...(meeting.action_candidates || [])];
  const speakers = new Set(meeting.segments.map(s => s.speaker).filter(Boolean)).size;
  useEffect(() => { if (!details && tab === 'details') setTab('items'); }, [details]);
  // Evidence spotlight: open the transcript at the quoted sentence and highlight it.
  useEffect(() => {
    if (!spotlight.length) return;
    document.getElementById(`segment-${spotlight[0]}`)?.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth', block: 'center' });
    const timer = window.setTimeout(() => setSpotlight([]), 2600);
    return () => window.clearTimeout(timer);
  }, [spotlight]);
  function showSource(ids: number[]) { setTab('transcript'); setSpotlight(ids); }
  function reviewFirst() {
    setTab('items');
    requestAnimationFrame(() => document.querySelector('.commitment-result.is-pending')?.scrollIntoView({ behavior: 'smooth', block: 'center' }));
  }
  const date = meeting.meeting_date || meeting.created_at;
  const predictions = meeting.dialogue_analysis?.predictions || [];
  const distribution = useMemo(() => {
    const tally = new Map<string, number>();
    predictions.forEach(p => tally.set(p.description, (tally.get(p.description) || 0) + 1));
    return [...tally.entries()].sort((a, b) => b[1] - a[1]).slice(0, 6);
  }, [predictions]);
  const tabs: [Tab, string][] = [['items', `Action items${all.length ? ` (${all.length})` : ''}`], ['transcript', 'Transcript'], ['people', 'People'],
    ...(details ? [['details', 'Technical details']] as [Tab, string][] : [])];
  const facts = [date && new Date(date).toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }),
    speakers ? `${speakers} speaker${speakers === 1 ? '' : 's'}` : null, meeting.language_profile?.label,
    access && access.role !== 'organizer' ? `You are ${access.role === 'admin' ? 'viewing as admin' : `a${access.role === 'owner' ? 'n' : ''} ${roleLabel[access.role].toLowerCase()}`}` : null].filter(Boolean);
  return <>
    <button className="back" onClick={() => navigate('/')}>← All meetings</button>
    <div className="meeting-hero"><div className="meeting-hero-copy"><h1>{meeting.title}</h1>
      <p className="muted">{facts.join(' · ')}</p>
      {access?.role === 'admin' && <p className="muted small">Your access to this meeting is recorded in the audit log.</p>}</div></div>
    <NextStep meetingId={meeting.id} status={meeting.status} actions={meeting.actions} candidates={meeting.action_candidates || []}
      canOrganize={Boolean(access?.can_organize)} finding={busy === 'extract'} navigate={navigate} onChanged={onChanged} onReview={reviewFirst}
      onFind={() => void run('extract', 'extract').then(() => setTab('items'))}/>
    <div className="meeting-tabs" role="tablist" aria-label="Meeting sections" ref={tabsRef}>
      {tabs.map(([id, label]) => <button key={id} type="button" role="tab" id={`tab-${id}`} aria-controls={`panel-${id}`} aria-selected={tab === id} onClick={() => setTab(id)}>{label}</button>)}
      <span className="tab-indicator" aria-hidden="true" style={tabIndicator}/></div>
    <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`} className="tab-panel">
      {tab === 'items' && <CommitmentResults onDraft={onDraft} meeting={meeting} onReview={onReview} disabled={busy !== null}
        access={access} directory={directory} onAssign={onAssign} onShowSource={showSource}/>}
      {tab === 'transcript' && <>
        <section className="panel transcript full"><div className="panel-head"><h2>Transcript</h2>
          <span className="downloads-inline"><Download size={15} aria-hidden="true"/> Download <a href={`/api/meetings/${meeting.id}/transcript?format=txt`}>TXT</a> <a href={`/api/meetings/${meeting.id}/transcript?format=json`}>JSON</a>{meeting.segments.some(s => s.start != null) && <> <a href={`/api/meetings/${meeting.id}/transcript?format=vtt`}>VTT</a></>}</span></div>
          {meeting.segments.map(s => <article key={s.id} id={`segment-${s.id}`} className={spotlight.includes(s.id) ? 'spotlight' : undefined}>
            <span className={`speaker tone-${speakerTone(s.speaker)}`} aria-hidden="true">{(s.speaker || '?').slice(0, 1).toUpperCase()}</span>
            <div className="utterance"><small className="mint">{details ? `#${s.id} · ` : ''}{s.speaker || 'Unknown speaker'}{s.start != null ? ` · ${details ? `${s.start.toFixed(1)}s – ${s.end?.toFixed(1)}s` : clock(s.start)}` : ''}</small><p dir="auto">{s.text}</p>
              {details && s.parent_source_id != null && <details><summary>Source turn #{s.parent_source_id}</summary><p>{meeting.source_segments?.find(parent => parent.id === s.parent_source_id)?.text}</p><small className="muted">Characters {s.source_start}–{s.source_end}</small></details>}</div></article>)}</section>
      </>}
      {tab === 'people' && <MeetingMembers meetingId={meeting.id} canOrganize={Boolean(access?.can_organize)} directory={directory} onDeleted={() => { void refresh(); navigate('/'); }}/>}
      {tab === 'details' && <>
        <section className="panel bert-summary"><div className="row"><div><h2>BERT dialogue analysis</h2><p className="muted">{health.bert.status}{health.bert.stage ? ` · ${health.bert.stage}` : ''}</p></div>{access?.can_organize && <button className="primary" disabled={busy !== null} onClick={() => void run('bert', 'classify')}>{busy === 'bert' ? 'Processing locally…' : 'Analyze with BERT'}<Cpu size={17} aria-hidden="true"/></button>}</div>
          <p className="muted">Classifies each utterance's dialogue act and highlights possible actions. Offers and suggestions still need a person's approval before they become tasks.</p>
          {busy === 'bert' && <div className="scanning" aria-hidden="true"><span/></div>}
          {meeting.dialogue_analysis && <><small className="muted">{meeting.dialogue_analysis.model.model_name} · {meeting.dialogue_analysis.model.checkpoint_stage}</small>
            {distribution.length > 0 && <div className="distribution" aria-label="Most frequent dialogue acts">{distribution.map(([label, count], i) =>
              <div className="dist-row" key={label} style={{ '--i': i } as React.CSSProperties}><span className="dist-label">{label}</span>
                <span className="dist-bar"><span style={{ transform: `scaleX(${count / distribution[0][1]})` }}/></span><span className="dist-count">{count}</span></div>)}</div>}
            <div className="dialogue-results">{predictions.map(prediction => <article key={prediction.source_id} className={prediction.possible_action ? 'action' : undefined}>
              <div className="row"><span className={`pill${prediction.possible_action ? ' warning' : ' quiet'}`}>#{prediction.source_id} · {prediction.description}</span>
                <span className="score"><span className="score-bar" aria-hidden="true"><span style={{ transform: `scaleX(${prediction.score})` }}/></span><small className="muted">Model score {prediction.score.toFixed(3)}</small></span></div>
              <p dir="auto">{meeting.segments.find(s => s.id === prediction.source_id)?.text}</p>
              {prediction.needs_review && <small className="mint">Review: {prediction.review_reasons.map(reason => reason.replaceAll('_', ' ')).join('; ')}</small>}
              <small className="muted dialogue-alternatives">Alternatives: {prediction.top_labels.map(label => `${label.label} ${label.score.toFixed(3)}`).join(' · ')}</small></article>)}</div></>}</section>
        <LanguageProcessing profile={meeting.language_profile} analysis={meeting.dialogue_analysis?.language_processing}/>
        <PreparedTranscript meeting={meeting}/>
        <p className="muted small">Source: {meeting.source_type || 'text'} · {meeting.segments.length} utterances · status {meeting.status}</p>
      </>}
    </div>
  </>;
}

function MeetingSkeleton() {
  return <div className="skeleton-page" aria-busy="true" aria-label="Loading meeting"><span className="skeleton-line wide"/><span className="skeleton-line"/><div className="panel skeleton tall"/><div className="panel skeleton tall"/></div>;
}

function CommandPalette({ pages, meetings, onClose, go }: { pages: { to: string; label: string }[]; meetings: Meeting[]; onClose: () => void; go: (to: string) => void }) {
  const [query, setQuery] = useState(''), [active, setActive] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const items = useMemo(() => {
    const q = query.trim().toLowerCase();
    return [...meetings.map(m => ({ to: `/meetings/${m.id}`, label: m.title, kind: 'Meeting' })),
      ...pages.map(p => ({ to: p.to, label: p.label, kind: 'Page' }))]
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
    <div className="palette" role="dialog" aria-modal="true" aria-label="Find a meeting or page" onMouseDown={e => e.stopPropagation()} onKeyDown={key}>
      <label className="palette-input"><Search size={17} aria-hidden="true"/><input ref={input} role="combobox" aria-expanded="true" aria-controls="palette-list"
        aria-activedescendant={items[active] ? `palette-${active}` : undefined} placeholder="Find a meeting or page" value={query} onChange={e => setQuery(e.target.value)}/><kbd>Esc</kbd></label>
      <ul id="palette-list" role="listbox">{items.length ? items.map((item, index) =>
        <li key={item.to} id={`palette-${index}`} role="option" aria-selected={index === active} onMouseEnter={() => setActive(index)} onClick={() => go(item.to)}>
          {item.kind === 'Meeting' ? <FileText size={16} aria-hidden="true"/> : <ArrowRight size={16} aria-hidden="true"/>}
          <span>{item.label}</span><small>{item.kind}</small>{index === active && <CornerDownLeft size={14} aria-hidden="true"/>}</li>)
        : <li className="palette-empty" role="option" aria-selected="false">Nothing matches “{query}”.</li>}</ul>
      <p className="palette-foot"><kbd>↑</kbd><kbd>↓</kbd> to move, <kbd>Enter</kbd> to open</p>
    </div></div>;
}

function NeedsOrganizer({ navigate }: { navigate: (path: string) => void }) {
  return <div className="panel empty"><span className="empty-mark"><Shield size={30} aria-hidden="true"/></span><h3>Only organizers can add meetings</h3><p className="muted">Ask for organizer access on your account page. An admin approves it.</p>
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
  return <section className="panel members"><div className="panel-head"><h2>People</h2><span className="muted">{members.length} with access</span></div>
    {error && <p role="alert" className="error">{error}</p>}
    <ul>{members.map(member => <li key={member.id + member.role}><span className={`avatar tone-${speakerTone(member.name)}`} aria-hidden="true">{member.name.slice(0, 1).toUpperCase()}</span><span><strong>{member.name}</strong> <small className="muted">{member.email}</small></span><span className="pill">{roleLabel[member.role] || member.role}</span>
      {canOrganize && member.role === 'viewer' && <button disabled={busy} onClick={() => void act(() => api(`/meetings/${meetingId}/members/${member.id}`, 'DELETE'))}>Remove</button>}</li>)}</ul>
    <p className="muted">Owners are added automatically when you link an action item to their account. Viewers can read the meeting but can't approve anything.</p>
    {canOrganize && <><form className="row add-member" onSubmit={e => { e.preventDefault(); void act(async () => { await api(`/meetings/${meetingId}/members`, 'POST', { user_id: choice }); setChoice(''); }); }}>
      <select aria-label="Add viewer" value={choice} onChange={e => setChoice(e.target.value)}><option value="">Add a viewer…</option>{candidates.map(user => <option key={user.id} value={user.id}>{user.name} ({user.email})</option>)}</select>
      <button disabled={busy || !choice}>Add viewer</button></form>
      <div className="danger-zone">{confirm ? <div className="row danger"><span>Delete this meeting, its drafts and assignments? This cannot be undone.</span>
        <button disabled={busy} onClick={() => { setBusy(true); api(`/meetings/${meetingId}`, 'DELETE').then(onDeleted, e => { setError(e.message); setBusy(false); }); }}>Delete permanently</button><button onClick={() => setConfirm(false)}>Cancel</button></div>
        : <button className="link-danger" onClick={() => setConfirm(true)}>Delete meeting…</button>}</div></>}
  </section>;
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>);
