import { useEffect, useState } from 'react';
import { api } from './api';
import type { Commitment } from './CommitmentResults';

type Draft = { id: string; status: string; subject: string; to: string[]; task: string; approval_valid: boolean;
  delivery: { status: string; detail?: string } | null };
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
  const selected = approved.filter(item => chosen[item.id!]);
  const reviewWait = flow.waiting_for?.waiting_for === 'commitment_review';
  return <section className="panel workflow">
    <div className="row"><h2>Workflow{flow.run ? ` · run ${flow.run}` : ''}</h2><span className={`pill${flow.status === 'failed' ? ' warning' : ''}`}>{flow.status.replace('_', ' ')}</span></div>
    {flow.status !== 'not_started' && <ol className="stages" aria-label="Workflow stages">{flow.stages.map((stage, index) =>
      <li key={stage} className={index < position || flow.status === 'completed' ? 'done' : index === position ? 'current' : ''}>{stageLabel[stage]}</li>)}</ol>}
    {error && <p role="alert" className="error">{error}</p>}
    {flow.status === 'not_started' && <><p className="muted">Runs extraction, then pauses for your commitment review. After you choose follow-ups and recipients it drafts them, checks policy and waits for each owner's approval. Nothing is sent without that approval.</p>
      {flow.can_control && <button className="primary" disabled={busy} onClick={() => void act('')}>Start workflow</button>}</>}
    {flow.status === 'running' && <p className="muted">Working on: {stageLabel[flow.stage || ''] || flow.stage}…</p>}
    {flow.status === 'failed' && <><p className="error">{flow.error}</p>{flow.can_control && <button className="primary" disabled={busy} onClick={() => void act('/retry')}>Retry from this step</button>}</>}
    {reviewWait && (flow.can_control ? <div className="workflow-review">
      <p className="muted">Review and approve commitments below, link owners, then choose which approved items get a follow-up email. Recipients are never chosen by the model.</p>
      {!approved.length && <p className="muted">No approved commitments yet.</p>}
      {approved.map(item => <div className="follow-up" key={item.id}>
        <label className="check"><input type="checkbox" checked={Boolean(chosen[item.id!])} onChange={e => setChosen({ ...chosen, [item.id!]: e.target.checked })}/> <span dir="auto">{item.task}</span></label>
        {chosen[item.id!] && <input aria-label={`Recipients for ${item.task}`} placeholder="person@example.com, colleague@example.com" value={recipients[item.id!] || ''} onChange={e => setRecipients({ ...recipients, [item.id!]: e.target.value })}/>}
      </div>)}
      <div className="review-controls">
        <button className="primary" disabled={busy || !selected.length || selected.some(item => !recipients[item.id!]?.trim())}
          onClick={() => void act('/resume', { follow_ups: selected.map(item => ({ commitment_id: item.id, to: recipients[item.id!].split(',').map(v => v.trim()).filter(Boolean) })) })}>Create {selected.length || ''} follow-up draft{selected.length === 1 ? '' : 's'}</button>
        <button disabled={busy} onClick={() => void act('/resume', { follow_ups: [] })}>Finish without follow-ups</button></div>
    </div> : <p className="muted">Waiting for the organizer to finish reviewing commitments.</p>)}
    {!!flow.drafts.length && <div className="workflow-drafts"><h3>Follow-up drafts</h3>{flow.drafts.map(draft => <p key={draft.id}>
      <strong dir="auto">{draft.subject || draft.task}</strong> <small className="muted">→ {draft.to.join(', ')} · {draft.status === 'approved' && !draft.approval_valid ? 'approval outdated' : draft.status}{draft.delivery ? ` · ${draft.delivery.status.replace('_', ' ')}` : ''}</small>
      {draft.delivery?.detail && <small className="muted"> · {draft.delivery.detail}</small>}</p>)}
      {flow.waiting_for?.waiting_for === 'draft_approval' && <div className="row"><span className="muted">Waiting for each owner's decision in My approvals.</span>
        <button onClick={() => navigate('/queue')}>Open My approvals</button>{flow.can_control && <button disabled={busy} onClick={() => void act('/check')}>Check again</button>}</div>}</div>}
    {flow.status === 'completed' && flow.can_control && <button disabled={busy} onClick={() => void act('')}>Run again</button>}
    {!!flow.history.length && <details><summary>Workflow history ({flow.history.length})</summary>{flow.history.map((event, index) =>
      <p key={index} className="audit-row">{event.event.replaceAll('_', ' ')} · {new Date(event.at).toLocaleString()}{event.actor ? ` · ${event.actor}` : ''}</p>)}</details>}
  </section>;
}
