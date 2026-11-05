import { useEffect, useState } from 'react';
import { api, type Me } from './api';

type Token = { id: string; name: string; created_at: string; expires_at: string; last_used_at: string | null; revoked: number };

export function Account({ me, onChanged }: { me: Me; onChanged: () => Promise<void> }) {
  const [name, setName] = useState(me.name), [current, setCurrent] = useState(''), [next, setNext] = useState('');
  const [reason, setReason] = useState(''), [tokenName, setTokenName] = useState('Chrome extension');
  const [tokens, setTokens] = useState<Token[]>([]), [issued, setIssued] = useState('');
  const [message, setMessage] = useState(''), [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const loadTokens = () => me.role === 'organizer' ? api<Token[]>('/auth/tokens').then(setTokens) : Promise.resolve();
  useEffect(() => { void loadTokens().catch(e => setError(e.message)); }, [me.role]);
  async function run(action: () => Promise<unknown>, done: string) {
    setBusy(true); setError(''); setMessage('');
    try { await action(); setMessage(done); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  const request = me.organizer_request;
  return <><p className="eyebrow">ACCOUNT</p><h1>{me.name}</h1>
    <p className="muted">{me.email} · {me.role === 'organizer' ? 'Organizer' : 'Member'}{me.is_admin ? ' · Admin' : ''}</p>
    {error && <p role="alert" className="error">{error}</p>}{message && <p role="status" className="mint">{message}</p>}
    <div className="account-grid">
      <form className="panel form" onSubmit={e => { e.preventDefault(); void run(async () => { await api('/auth/me', 'PATCH', { name }); await onChanged(); }, 'Name updated.'); }}>
        <h2>Profile</h2><label>Display name<input required maxLength={100} value={name} onChange={e => setName(e.target.value)}/></label>
        <button disabled={busy || !name.trim() || name === me.name}>Save name</button>
      </form>
      <form className="panel form" onSubmit={e => { e.preventDefault(); void run(async () => { await api('/auth/me', 'PATCH', { current_password: current, new_password: next }); setCurrent(''); setNext(''); }, 'Password changed. Other sessions were signed out.'); }}>
        <h2>Password</h2>
        <label>Current password<input required type="password" value={current} onChange={e => setCurrent(e.target.value)} autoComplete="current-password"/></label>
        <label>New password<input required type="password" minLength={10} value={next} onChange={e => setNext(e.target.value)} autoComplete="new-password"/></label>
        <button disabled={busy}>Change password</button>
      </form>
      {me.role === 'member' && <form className="panel form" onSubmit={e => { e.preventDefault(); void run(async () => { await api('/auth/organizer-request', 'POST', { reason }); setReason(''); await onChanged(); }, 'Request sent to the admins.'); }}>
        <h2>Organizer access</h2>
        <p className="muted">Organizers upload and capture meetings, review extracted commitments and assign owners. An admin approves each request.</p>
        {request && <p className={request.status === 'rejected' ? 'error' : 'muted'}>Last request: {request.status}{request.note ? ` · ${request.note}` : ''}</p>}
        {request?.status === 'pending' ? <p className="muted">Waiting for an admin decision.</p> : <>
          <label>Why do you need it?<textarea required minLength={5} maxLength={1000} value={reason} onChange={e => setReason(e.target.value)}/></label>
          <button className="primary" disabled={busy || reason.trim().length < 5}>Request organizer access</button></>}
      </form>}
      {me.role === 'organizer' && <section className="panel form">
        <h2>Capture tokens</h2>
        <p className="muted">The Chrome extension uses a token to upload Meet recordings as you. A token cannot read meetings or approve anything.</p>
        {issued && <div className="token-issued"><p className="mint">Copy this token into the extension now. It is not shown again.</p><code>{issued}</code></div>}
        <form className="row" onSubmit={e => { e.preventDefault(); void run(async () => { setIssued((await api<{ token: string }>('/auth/tokens', 'POST', { name: tokenName })).token); await loadTokens(); }, 'Token created.'); }}>
          <input aria-label="Token name" required maxLength={80} value={tokenName} onChange={e => setTokenName(e.target.value)}/>
          <button disabled={busy}>Create token</button></form>
        {tokens.map(token => <div className="row token" key={token.id}><span><strong>{token.name}</strong><small className="muted"> · created {new Date(token.created_at).toLocaleDateString()} · {token.revoked ? 'revoked' : `expires ${new Date(token.expires_at).toLocaleDateString()}`}{token.last_used_at ? ` · last used ${new Date(token.last_used_at).toLocaleString()}` : ''}</small></span>
          {!token.revoked && <button disabled={busy} onClick={() => void run(async () => { await api(`/auth/tokens/${token.id}`, 'DELETE'); await loadTokens(); }, 'Token revoked.')}>Revoke</button>}</div>)}
      </section>}
    </div></>;
}
