import { useEffect, useState } from 'react';
import { ShieldCheck } from 'lucide-react';
import { Bridge, Contours, Logo } from './ui';
import { api, type Me } from './api';

const stages = [
  { label: 'Ingest', detail: 'Transcripts, audio and Google Meet, transcribed locally' },
  { label: 'Extract', detail: 'BERT dialogue acts, spaCy entities, calibrated confidence' },
  { label: 'Agent draft', detail: 'LangGraph drafts, checked by the policy engine' },
  { label: 'Human approve', detail: 'The owner approves the exact draft' },
  { label: 'Execute', detail: 'Gmail and Jira, delivered at most once', gold: true },
];

/** Sign-in and sign-up. The first account in a new workspace becomes its admin. */
export function AuthScreen({ mode, onSignedIn, navigate }: { mode: 'login' | 'signup'; onSignedIn: (me: Me) => void; navigate: (path: string) => void }) {
  const [config, setConfig] = useState<{ has_users: boolean; signup_open: boolean } | null>(null);
  const [email, setEmail] = useState(''), [name, setName] = useState(''), [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  useEffect(() => { void api<typeof config>('/auth/config').then(setConfig).catch(e => setError(e.message)); }, []);
  const signup = mode === 'signup' || config?.has_users === false;
  async function submit() {
    setBusy(true); setError('');
    try {
      await api(signup ? '/auth/signup' : '/auth/login', 'POST', signup ? { email, name, password } : { email, password });
      onSignedIn(await api<Me>('/auth/me'));
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  return <div className="auth-shell">
    <section className="auth-brand" aria-label="About MeetMind">
      <Contours className="auth-contours" rings={12} seed={2}/>
      <div className="auth-brand-inner">
        <div className="auth-lockup"><Logo size={68}/><div><p className="wordmark">MeetMind</p><p className="tagline">Conversation to Execution</p></div></div>
        <p className="objective">An AI agent that turns meeting talk into human-approved action.</p>
        <Bridge vertical label="The five-stage bridge" stages={stages}/>
        <p className="auth-foot">Final Year Project, FAST NUCES Islamabad</p>
      </div>
    </section>
    <div className="auth-main">
      <form className="panel form auth-card" onSubmit={e => { e.preventDefault(); void submit(); }}>
        <div className="brand auth-card-brand"><Logo size={36}/><strong>MeetMind</strong></div>
        <h1>{signup ? (config?.has_users === false ? 'Set up your workspace' : 'Create your account') : 'Sign in'}</h1>
        <p className="muted">{signup ? 'Every commitment links back to what was said, and nothing is sent without approval.' : 'Welcome back. Pick up where your meetings left off.'}</p>
        {config?.has_users === false && <p className="note">This is the first account, so it becomes the workspace admin and an organizer. Existing local meetings are assigned to it.</p>}
        {signup && config?.has_users && <p className="note">New accounts start as members. Ask an admin for organizer access to create meetings.</p>}
        {error && <p role="alert" className="error">{error}</p>}
        {signup && config?.has_users && !config.signup_open ? <p className="error">Sign-up is closed. Ask an admin to create your account.</p> : <>
          {signup && <label>Name<input required maxLength={100} value={name} onChange={e => setName(e.target.value)} autoComplete="name"/></label>}
          <label>Email<input required type="email" maxLength={254} value={email} onChange={e => setEmail(e.target.value)} autoComplete="email" placeholder="you@example.com"/></label>
          <label>Password<input required type="password" minLength={signup ? 10 : 1} maxLength={256} value={password} onChange={e => setPassword(e.target.value)} autoComplete={signup ? 'new-password' : 'current-password'}/></label>
          {signup && <small className="muted">At least 10 characters.</small>}
          <button className="primary wide" disabled={busy || !config}>{busy ? 'Please wait…' : signup ? 'Create account' : 'Sign in'}</button></>}
        {config?.has_users && <p className="muted switch">{signup ? <>Already have an account? <a href="/login" onClick={e => { e.preventDefault(); navigate('/login'); }}>Sign in</a></>
          : config.signup_open && <>New here? <a href="/signup" onClick={e => { e.preventDefault(); navigate('/signup'); }}>Create an account</a></>}</p>}
        <p className="assurance"><ShieldCheck size={15} aria-hidden="true"/>Runs on local models. The model never chooses recipients.</p>
      </form>
    </div>
  </div>;
}
