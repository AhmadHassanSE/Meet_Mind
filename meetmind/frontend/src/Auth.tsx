import { useEffect, useState } from 'react';
import { Zap } from 'lucide-react';
import { api, type Me } from './api';

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
  return <div className="auth-shell"><form className="panel form auth-card" onSubmit={e => { e.preventDefault(); void submit(); }}>
    <div className="brand"><Zap/><strong>MeetMind</strong></div>
    <h1>{signup ? (config?.has_users === false ? 'Set up your workspace' : 'Create your account') : 'Sign in'}</h1>
    {config?.has_users === false && <p className="muted">This is the first account, so it becomes the workspace admin and an organizer. Existing local meetings are assigned to it.</p>}
    {signup && config?.has_users && <p className="muted">New accounts start as members. Ask an admin for organizer access to create meetings.</p>}
    {error && <p role="alert" className="error">{error}</p>}
    {signup && config?.has_users && !config.signup_open ? <p className="error">Sign-up is closed. Ask an admin to create your account.</p> : <>
      {signup && <label>Name<input required maxLength={100} value={name} onChange={e => setName(e.target.value)} autoComplete="name"/></label>}
      <label>Email<input required type="email" maxLength={254} value={email} onChange={e => setEmail(e.target.value)} autoComplete="email"/></label>
      <label>Password<input required type="password" minLength={signup ? 10 : 1} maxLength={256} value={password} onChange={e => setPassword(e.target.value)} autoComplete={signup ? 'new-password' : 'current-password'}/></label>
      {signup && <small className="muted">At least 10 characters.</small>}
      <button className="primary" disabled={busy || !config}>{busy ? 'Please wait…' : signup ? 'Create account' : 'Sign in'}</button></>}
    {config?.has_users && <p className="muted">{signup ? <>Already have an account? <a href="/login" onClick={e => { e.preventDefault(); navigate('/login'); }}>Sign in</a></>
      : config.signup_open && <>New here? <a href="/signup" onClick={e => { e.preventDefault(); navigate('/signup'); }}>Create an account</a></>}</p>}
  </form></div>;
}
