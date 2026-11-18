import React, { useEffect, useState } from 'react';
import { GitBranch } from 'lucide-react';
import { api } from './api';
import type { Commitment } from './CommitmentResults';

type Draft = { id: string; status: string; subject: string; to: string[]; task: string; approval_valid: boolean;
  delivery: { status: string; detail?: string; url?: string } | null };
type Workflow = { status: 'not_started' | 'running' | 'waiting' | 'failed' | 'completed'; stage?: string; run?: number;
  waiting_for?: { waiting_for: 'commitment_review' | 'draft_approval'; pending?: string[] } | null; error?: string | null;
  stages: string[]; drafts: Draft[]; can_control: boolean;
  history: { at: string; event: string; actor?: string }[] };
const stageLabel: Record<string, string> = { extract: 'Extract', await_review: 'Review', draft: 'Draft', policy_check: 'Policy',
  await_approval: 'Approval', execute: 'Execute', completed: 'Done' };

/** The meeting's LangGraph workflow: progress, the organizer's review step and approval status. */
export function WorkflowPanel({ meetingId, actions, onChanged, navigate }: { meetingId: string; actions: Commitment[];
  onChanged: () => void; navigate: (path: string) => void }) {
  const [flow, setFlow] = useState<Workflow | null>(null);
  const [recipients, setRecipients] = useState<Record<string, string>>({});
  const [chosen, setChosen] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const load = () => api<Workflow>(`/meetings/${meetingId}/workflow`).then(setFlow);
  useEffect(() => { setFlow(null); void load().catch(e => setError(e.message)); }, [meetingId]);
  const live = flow?.status === 'running' || flow?.waiting_for?.waiting_for === 'draft_approval';
  useEffect(() => {
    if (!live) return;
    const timer = setInterval(() => { void load().then(() => onChanged()).catch(() => {}); }, 2000);
    return () => clearInterval(timer);
  }, [live, meetingId]);
  const approved = actions.filter(item => item.review_status === 'approved' && item.kind !== 'cancellation' && item.id);
  useEffect(() => {
    // Recipients start from the linked owner account; the organizer still confirms each one.
    setRecipients(current => Object.fromEntries(approved.map(item => [item.id!, current[item.id!] ?? item.assignee?.email ?? ''])));
  }, [approved.map(item => item.id + (item.assignee?.email || '')).join()]);
  async function act(path: string, body?: object) {
    setBusy(true); setError('');
    try { setFlow(await api<Workflow>(`/meetings/${meetingId}/workflow${path}`, 'POST', body ?? {})); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  if (!flow) return <section className="panel workflow"><h2>Workflow</h2><p className="muted">{error || 'Loading…'}</p></section>;
  const current = flow.status === 'completed' ? 'completed' : flow.stage;
  const position = flow.stages.indexOf(current || '');
  // A follow-up is an email (with confirmed recipients) and/or a Jira ticket per approved item.
  const selected = approved.filter(item => chosen[item.id! + ':email']);
  const tickets = approved.filter(item => chosen[item.id! + ':jira']);
  const followUps = [...selected.map(item => ({ commitment_id: item.id, channel: 'email', to: (recipients[item.id!] || '').split(',').map(v => v.trim()).filter(Boolean) })),
    ...tickets.map(item => ({ commitment_id: item.id, channel: 'jira' }))];
  const reviewWait = flow.waiting_for?.waiting_for === 'commitment_review';
  const progress = flow.status === 'completed' ? 1 : Math.max(0, position) / Math.max(1, flow.stages.length - 1);
  const tone = flow.status === 'failed' ? ' warning' : flow.status === 'completed' ? ' ok' : flow.status === 'not_started' ? ' quiet' : '';
  return <section className={`panel workflow status-${flow.status}${live || reviewWait ? ' beam' : ''}`}>
    <div className="row"><div className="workflow-title"><span className="workflow-icon" aria-hidden="true"><GitBranch size={18}/></span>
      <div><h2>Workflow{flow.run ? ` · run ${flow.run}` : ''}</h2><p className="muted">One LangGraph run per meeting, with saved checkpoints</p></div></div>
      <span className={`pill${tone}`}>{flow.status.replace('_', ' ')}</span></div>
    {flow.status !== 'not_started' && <div className="stages-scroll"><ol className="stages" aria-label="Workflow stages" style={{ '--p': progress } as React.CSSProperties}>{flow.stages.map((stage, index) =>
      <li key={stage} className={index < position || flow.status === 'completed' ? 'done' : index === position ? 'current' : ''}>{stageLabel[stage]}</li>)}</ol></div>}
    {error && <p role="alert" className="error">{error}</p>}
    {flow.status === 'not_started' && <><p className="muted">Runs extraction, then pauses for your commitment review. After you choose follow-ups and recipients it drafts them, checks policy and waits for each owner's approval. Nothing is sent without that approval.</p>
      {flow.can_control && <button className="primary" disabled={busy} onClick={() => void act('')}>Start workflow</button>}</>}
    {flow.status === 'running' && <p className="muted">Working on: {stageLabel[flow.stage || ''] || flow.stage}…</p>}
    {flow.status === 'failed' && <><p className="error">{flow.error}</p>{flow.can_control && <button className="primary" disabled={busy} onClick={() => void act('/retry')}>Retry from this step</button>}</>}
    {reviewWait && (flow.can_control ? <div className="workflow-review">
      <p className="muted">Review and approve commitments below, link owners, then choose which approved items get a follow-up email. Recipients are never chosen by the model.</p>
      {!approved.length && <p className="muted">No approved commitments yet.</p>}
      {approved.map(item => <div className="follow-up" key={item.id}>
        <span dir="auto">{item.task}</span>
        <div className="review-controls"><label className="check"><input type="checkbox" aria-label={`Email for ${item.task}`} checked={Boolean(chosen[item.id! + ':email'])} onChange={e => setChosen({ ...chosen, [item.id! + ':email']: e.target.checked })}/> Email</label>
          <label className="check"><input type="checkbox" aria-label={`Jira ticket for ${item.task}`} checked={Boolean(chosen[item.id! + ':jira'])} onChange={e => setChosen({ ...chosen, [item.id! + ':jira']: e.target.checked })}/> Jira ticket{item.assignee ? `, assigned to ${item.assignee.name}` : ', unassigned'}</label></div>
        {chosen[item.id! + ':email'] && <input aria-label={`Recipients for ${item.task}`} placeholder="person@example.com, colleague@example.com" value={recipients[item.id!] || ''} onChange={e => setRecipients({ ...recipients, [item.id!]: e.target.value })}/>}
      </div>)}
      <div className="review-controls">
        <button className="primary" disabled={busy || !followUps.length || selected.some(item => !recipients[item.id!]?.trim())}
          onClick={() => void act('/resume', { follow_ups: followUps })}>Create {followUps.length || ''} follow-up draft{followUps.length === 1 ? '' : 's'}</button>
        <button disabled={busy} onClick={() => void act('/resume', { follow_ups: [] })}>Finish without follow-ups</button></div>
    </div> : <p className="muted">Waiting for the organizer to finish reviewing commitments.</p>)}
    {!!flow.drafts.length && <div className="workflow-drafts"><h3>Follow-up drafts</h3>{flow.drafts.map(draft => <p key={draft.id}>
      <strong dir="auto">{draft.subject || draft.task}</strong> <small className="muted">→ {draft.to.length ? draft.to.join(', ') : 'Jira'} · {draft.status === 'approved' && !draft.approval_valid ? 'approval outdated' : draft.status}{draft.delivery ? ` · ${draft.delivery.status.replace('_', ' ')}` : ''}</small>
      {draft.delivery?.detail && <small className="muted"> · {draft.delivery.detail}</small>}{draft.delivery?.url && <> · <a href={draft.delivery.url} target="_blank" rel="noreferrer">open issue</a></>}</p>)}
      {flow.waiting_for?.waiting_for === 'draft_approval' && <div className="row"><span className="muted">Waiting for each owner's decision in My approvals.</span>
        <button onClick={() => navigate('/queue')}>Open My approvals</button>{flow.can_control && <button disabled={busy} onClick={() => void act('/check')}>Check again</button>}</div>}</div>}
    {flow.status === 'completed' && flow.can_control && <button disabled={busy} onClick={() => void act('')}>Run again</button>}
    {!!flow.history.length && <details><summary>Workflow history ({flow.history.length})</summary>{flow.history.map((event, index) =>
      <p key={index} className="audit-row">{event.event.replaceAll('_', ' ')} · {new Date(event.at).toLocaleString()}{event.actor ? ` · ${event.actor}` : ''}</p>)}</details>}
  </section>;
}
