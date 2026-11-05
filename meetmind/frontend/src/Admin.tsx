import { useEffect, useState } from 'react';
import { api, type Me } from './api';

type UserRow = { id: string; email: string; name: string; role: 'member' | 'organizer'; is_admin: boolean; active: boolean; created_at: string };
type RoleRequest = { id: string; user_id: string; name: string; email: string; reason: string; status: string; created_at: string; note: string | null };
type AuditEntry = { id: string; at: string; action: string; actor_email: string | null; target: string | null; detail: unknown };

export function Admin({ me }: { me: Me }) {
  const [tab, setTab] = useState<'users' | 'requests' | 'audit' | 'settings'>('requests');
  const [users, setUsers] = useState<UserRow[]>([]), [requests, setRequests] = useState<RoleRequest[]>([]);
  const [audit, setAudit] = useState<AuditEntry[]>([]), [signupOpen, setSignupOpen] = useState(true);
  const [notes, setNotes] = useState<Record<string, string>>({}), [passwords, setPasswords] = useState<Record<string, string>>({});
  const [draft, setDraft] = useState({ name: '', email: '', password: '', role: 'member' as UserRow['role'] });
  const [error, setError] = useState(''), [message, setMessage] = useState(''), [busy, setBusy] = useState(false);
  const load = () => Promise.all([api<UserRow[]>('/admin/users').then(setUsers), api<RoleRequest[]>('/admin/organizer-requests').then(setRequests),
    api<AuditEntry[]>('/admin/audit').then(setAudit), api<{ signup_open: boolean }>('/admin/settings').then(s => setSignupOpen(s.signup_open))]);
  useEffect(() => { void load().catch(e => setError(e.message)); }, []);
  async function run(action: () => Promise<unknown>, done: string) {
    setBusy(true); setError(''); setMessage('');
    try { await action(); await load(); setMessage(done); } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  const update = (user: UserRow, change: Partial<UserRow>, done: string) => run(() => api(`/admin/users/${user.id}`, 'PATCH', change), done);
  return <><p className="eyebrow">ADMIN</p><h1>Workspace administration</h1>
    <p className="muted">Admins oversee the workspace. Business approvals belong to item owners and organizers; an admin override must be justified and is audited.</p>
    {error && <p role="alert" className="error">{error}</p>}{message && <p role="status" className="mint">{message}</p>}
    <div className="tabs" role="tablist">{([['requests', `Organizer requests (${requests.length})`], ['users', 'Users'], ['audit', 'Audit log'], ['settings', 'Settings']] as const).map(([id, label]) =>
      <button key={id} role="tab" aria-selected={tab === id} className={tab === id ? 'active' : ''} onClick={() => setTab(id)}>{label}</button>)}</div>
    {tab === 'requests' && <section className="panel">{!requests.length && <p className="muted">No pending organizer requests.</p>}
      {requests.map(r => <article className="admin-row" key={r.id}><div><strong>{r.name}</strong> <small className="muted">{r.email} · {new Date(r.created_at).toLocaleString()}</small><p dir="auto">{r.reason}</p></div>
        <input aria-label="Decision note" placeholder="Note (optional)" maxLength={1000} value={notes[r.id] || ''} onChange={e => setNotes({ ...notes, [r.id]: e.target.value })}/>
        <div className="review-controls"><button className="primary" disabled={busy} onClick={() => void run(() => api(`/admin/organizer-requests/${r.id}`, 'POST', { decision: 'approved', note: notes[r.id] || '' }), `${r.name} is now an organizer.`)}>Approve</button>
          <button disabled={busy} onClick={() => void run(() => api(`/admin/organizer-requests/${r.id}`, 'POST', { decision: 'rejected', note: notes[r.id] || '' }), 'Request rejected.')}>Reject</button></div></article>)}
    </section>}
    {tab === 'users' && <form className="panel form new-user" onSubmit={e => { e.preventDefault(); void run(async () => { await api('/admin/users', 'POST', draft); setDraft({ ...draft, email: '', name: '', password: '' }); }, 'Account created. Share the initial password with the user directly.'); }}>
      <h2>Create account</h2>
      <div className="row"><input aria-label="New user name" placeholder="Name" required maxLength={100} value={draft.name} onChange={e => setDraft({ ...draft, name: e.target.value })}/>
        <input aria-label="New user email" placeholder="Email" type="email" required value={draft.email} onChange={e => setDraft({ ...draft, email: e.target.value })}/>
        <input aria-label="Initial password" placeholder="Initial password (10+ characters)" type="password" required minLength={10} value={draft.password} onChange={e => setDraft({ ...draft, password: e.target.value })}/>
        <select aria-label="New user role" value={draft.role} onChange={e => setDraft({ ...draft, role: e.target.value as UserRow['role'] })}><option value="member">Member</option><option value="organizer">Organizer</option></select>
        <button className="primary" disabled={busy}>Create</button></div></form>}
    {tab === 'users' && <section className="panel table-wrap"><table><thead><tr><th>Name</th><th>Role</th><th>Admin</th><th>Status</th><th>Reset password</th></tr></thead><tbody>
      {users.map(u => <tr key={u.id}><td><strong>{u.name}</strong><br/><small className="muted">{u.email}</small></td>
        <td><select aria-label={`Role for ${u.email}`} value={u.role} disabled={busy} onChange={e => void update(u, { role: e.target.value as UserRow['role'] }, 'Role updated.')}><option value="member">Member</option><option value="organizer">Organizer</option></select></td>
        <td><input type="checkbox" aria-label={`Admin: ${u.email}`} checked={u.is_admin} disabled={busy} onChange={e => void update(u, { is_admin: e.target.checked }, 'Admin access updated.')}/></td>
        <td><button disabled={busy || u.id === me.id} onClick={() => void update(u, { active: !u.active }, u.active ? 'Account deactivated; its sessions and tokens were revoked.' : 'Account reactivated.')}>{u.active ? 'Deactivate' : 'Reactivate'}</button></td>
        <td className="row"><input type="password" aria-label={`New password for ${u.email}`} placeholder="New password" minLength={10} value={passwords[u.id] || ''} onChange={e => setPasswords({ ...passwords, [u.id]: e.target.value })}/>
          <button disabled={busy || (passwords[u.id] || '').length < 10} onClick={() => void run(async () => { await api(`/admin/users/${u.id}/password`, 'POST', { password: passwords[u.id] }); setPasswords({ ...passwords, [u.id]: '' }); }, 'Password reset; the user must sign in again.')}>Reset</button></td></tr>)}
    </tbody></table></section>}
    {tab === 'audit' && <section className="panel">{!audit.length && <p className="muted">No audit events yet.</p>}
      {audit.map(a => <p key={a.id} className="audit-row"><strong>{a.action.replaceAll('_', ' ')}</strong> · {new Date(a.at).toLocaleString()} · {a.actor_email || 'system'}{a.target ? ` · ${a.target}` : ''}{a.detail ? <small className="muted"> · {JSON.stringify(a.detail)}</small> : null}</p>)}
    </section>}
    {tab === 'settings' && <section className="panel form"><h2>Sign-up</h2>
      <label className="check"><input type="checkbox" checked={signupOpen} disabled={busy} onChange={e => void run(() => api('/admin/settings', 'PATCH', { signup_open: e.target.checked }), 'Settings saved.')}/> Allow anyone who can reach this server to create a member account</label>
      <p className="muted">When closed, admins create accounts under Users.</p></section>}
  </>;
}
