import { useEffect, useState, type ReactNode } from 'react';
import { Check, Loader2 } from 'lucide-react';
import { api } from './api';
import type { Commitment } from './CommitmentResults';
import { useDetails } from './ui';

type Draft = { id: string; status: string; subject: string; to: string[]; task: string; approval_valid: boolean;
  delivery: { status: string; detail?: string; url?: string } | null };
type Workflow = { status: 'not_started' | 'running' | 'waiting' | 'failed' | 'completed'; stage?: string; run?: number;
  waiting_for?: { waiting_for: 'commitment_review' | 'draft_approval'; pending?: string[] } | null; error?: string | null;
  stages: string[]; drafts: Draft[]; can_control: boolean;
  history: { at: string; event: string; actor?: string }[] };
type Step = 'find' | 'review' | 'follow' | 'send' | 'done';
const steps: [Exclude<Step, 'send' | 'done'>, string][] = [['find', 'Find action items'], ['review', 'Review them'], ['follow', 'Follow up']];
const draftLabel: Record<string, string> = { drafting: 'being written', draft: 'waiting for approval', approved: 'approved',
  rejected: 'rejected', source_changed: 'out of date', failed: 'could not be written' };
/** Where one follow-up stands, in words: delivery outcome first, then the approval state. */
function draftState(draft: Draft) {
  if (draft.delivery) return `${draft.delivery.status.replace('_', ' ')}${draft.delivery.detail ? ` (${draft.delivery.detail})` : ''}`;
  if (draft.status === 'approved' && !draft.approval_valid) return 'needs a new approval';
  return draftLabel[draft.status] || draft.status;
}
function DraftList({ drafts }: { drafts: Draft[] }) {
  return <ul className="draft-states">{drafts.map(draft => <li key={draft.id}><span dir="auto">{draft.subject || draft.task}</span>
    <small className="muted">{draft.to.length ? draft.to.join(', ') : 'Jira'} · {draftState(draft)}
      {draft.delivery?.url && <> · <a href={draft.delivery.url} target="_blank" rel="noreferrer">open issue</a></>}</small></li>)}</ul>;
}
const pending = (item: Commitment) => !item.review_status || item.review_status === 'pending';
const wait = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));

/** The one thing to do next on a meeting: find action items, review them, then choose follow-ups.
 *  Follow-ups run through the meeting's LangGraph workflow; nothing is sent without the owner's approval. */
export function NextStep({ meetingId, status, actions, candidates, canOrganize, finding, onFind, onChanged, onReview, navigate }: {
  meetingId: string; status: string; actions: Commitment[]; candidates: Commitment[]; canOrganize: boolean; finding: boolean;
  onFind: () => void; onChanged: () => void; onReview: () => void; navigate: (path: string) => void }) {
  const details = useDetails();
  const [flow, setFlow] = useState<Workflow | null>(null);
  const [recipients, setRecipients] = useState<Record<string, string>>({});
  const [chosen, setChosen] = useState<Record<string, boolean>>({});
  const [again, setAgain] = useState(false);
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const load = () => api<Workflow>(`/meetings/${meetingId}/workflow`).then(value => { setFlow(value); return value; });
  useEffect(() => { setFlow(null); setAgain(false); void load().catch(e => setError(e.message)); }, [meetingId]);
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

  /** Starts a workflow run if needed (it reuses the existing extraction), then hands it the chosen follow-ups. */
  async function followUp(followUps: object[]) {
    setBusy(true); setError('');
    try {
      let current = flow ?? await load();
      if (current.waiting_for?.waiting_for !== 'commitment_review') {
        current = await api<Workflow>(`/meetings/${meetingId}/workflow`, 'POST', {});
        for (let i = 0; i < 90 && current.waiting_for?.waiting_for !== 'commitment_review' && current.status !== 'failed'; i++) {
          await wait(1000); current = await load();
        }
        if (current.status === 'failed') throw new Error(current.error || 'The follow-up step failed. Try again.');
        if (current.waiting_for?.waiting_for !== 'commitment_review') throw new Error('The follow-up step is taking longer than expected. Refresh the page in a moment.');
      }
      setFlow(await api<Workflow>(`/meetings/${meetingId}/workflow/resume`, 'POST', { follow_ups: followUps }));
      setChosen({}); setAgain(false); onChanged();
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }
  async function act(path: string) {
    setBusy(true); setError('');
    try { setFlow(await api<Workflow>(`/meetings/${meetingId}/workflow${path}`, 'POST', {})); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  const all = [...actions, ...candidates];
  const toReview = all.filter(pending).length;
  const extracting = finding || (flow?.status === 'running' && flow.stage === 'extract');
  const step: Step = status === 'uploaded' || extracting ? 'find'
    : toReview > 0 ? 'review'
    : again ? 'follow'
    : !flow || flow.status === 'not_started' || flow.waiting_for?.waiting_for === 'commitment_review' ? (approved.length ? 'follow' : 'done')
    : flow.status === 'completed' ? 'done' : 'send';
  const position = step === 'send' || step === 'done' ? 3 : steps.findIndex(([id]) => id === step);

  const emails = approved.filter(item => chosen[item.id! + ':email']);
  const tickets = approved.filter(item => chosen[item.id! + ':jira']);
  const followUps = [...emails.map(item => ({ commitment_id: item.id, channel: 'email', to: (recipients[item.id!] || '').split(',').map(v => v.trim()).filter(Boolean) })),
    ...tickets.map(item => ({ commitment_id: item.id, channel: 'jira' }))];

  let body: ReactNode;
  if (step === 'find') body = extracting
    ? <p className="next-lead"><Loader2 className="spin" size={18} aria-hidden="true"/> Reading the transcript for tasks, owners and dates. This runs on this computer and can take a minute.</p>
    : canOrganize ? <><p className="next-lead">Let MeetMind read the transcript and list who agreed to do what.</p>
        <button className="primary" disabled={busy} onClick={onFind}>Find action items</button></>
      : <p className="next-lead">The organizer hasn't looked for action items in this meeting yet.</p>;
  else if (step === 'review') body = canOrganize
    ? <><p className="next-lead"><strong>{toReview} item{toReview === 1 ? '' : 's'}</strong> to check. Approve the ones that are right, reject the rest. You can fix any detail with “Edit details”.</p>
        <button className="primary" onClick={onReview}>Go to the first one</button></>
    : <p className="next-lead">The organizer is checking {toReview} action item{toReview === 1 ? '' : 's'}.</p>;
  else if (step === 'follow') body = canOrganize ? <>
    <p className="next-lead">Choose how to follow up on the approved items. Each one is drafted for you, and the item's owner approves it before anything is sent.</p>
    <div className="follow-list">{approved.map(item => <div className="follow-up" key={item.id}>
      <span className="follow-task" dir="auto">{item.task}</span>
      <div className="review-controls">
        <label className="check"><input type="checkbox" aria-label={`Email for ${item.task}`} checked={Boolean(chosen[item.id! + ':email'])} onChange={e => setChosen({ ...chosen, [item.id! + ':email']: e.target.checked })}/> Email</label>
        <label className="check"><input type="checkbox" aria-label={`Jira ticket for ${item.task}`} checked={Boolean(chosen[item.id! + ':jira'])} onChange={e => setChosen({ ...chosen, [item.id! + ':jira']: e.target.checked })}/> Jira ticket</label></div>
      {chosen[item.id! + ':email'] && <input aria-label={`Recipients for ${item.task}`} placeholder="Email addresses, separated by commas" value={recipients[item.id!] || ''} onChange={e => setRecipients({ ...recipients, [item.id!]: e.target.value })}/>}
    </div>)}</div>
    <div className="review-controls">
      <button className="primary" disabled={busy || !followUps.length || emails.some(item => !recipients[item.id!]?.trim())}
        onClick={() => void followUp(followUps)}>{busy ? 'Writing drafts…' : `Create ${followUps.length || ''} follow-up draft${followUps.length === 1 ? '' : 's'}`}</button>
      <button disabled={busy} onClick={() => void followUp([])}>No follow-ups needed</button>
      {again && <button className="text-button" disabled={busy} onClick={() => setAgain(false)}>Cancel</button>}</div>
  </> : <p className="next-lead">The organizer is choosing follow-ups for the approved items.</p>;
  else if (step === 'send') body = <>
    {flow?.status === 'failed' ? <><p className="error">{flow.error || 'Something went wrong while preparing follow-ups.'}</p>
        {flow.can_control && <button className="primary" disabled={busy} onClick={() => void act('/retry')}>Try again</button>}</>
      : flow?.status === 'running' ? <p className="next-lead"><Loader2 className="spin" size={18} aria-hidden="true"/> Writing and checking the follow-up drafts…</p>
      : <p className="next-lead">Follow-ups are waiting for each owner's approval.</p>}
    {!!flow?.drafts.length && <DraftList drafts={flow.drafts}/>}
    {flow?.waiting_for?.waiting_for === 'draft_approval' && <div className="review-controls"><button className="primary" onClick={() => navigate('/queue')}>Open My approvals</button>
      {flow.can_control && <button disabled={busy} onClick={() => void act('/check')}>Check again</button>}</div>}
  </>;
  else body = <>
    <p className="next-lead"><Check size={18} aria-hidden="true"/> {approved.length ? 'All done for this meeting.' : all.length ? 'All items are reviewed. None were approved, so there is nothing to follow up.' : 'Nothing to follow up.'}</p>
    {!!flow?.drafts.length && <DraftList drafts={flow.drafts}/>}
    {canOrganize && approved.length > 0 && flow?.status === 'completed' && <button onClick={() => setAgain(true)}>Create more follow-ups</button>}
  </>;

  return <section className="panel next-step" aria-label="Next step">
    <ol className="step-track">{steps.map(([id, label], index) =>
      <li key={id} className={index < position ? 'done' : index === position ? 'current' : ''} aria-current={index === position ? 'step' : undefined}>
        <span className="step-dot" aria-hidden="true">{index < position ? <Check size={14}/> : index + 1}</span>{label}</li>)}</ol>
    <div className="next-body">{body}</div>
    {error && <p role="alert" className="error">{error}</p>}
    {details && flow && <details className="tech"><summary>Workflow details (LangGraph run {flow.run || '–'}, {flow.status.replace('_', ' ')}{flow.stage ? `, stage ${flow.stage}` : ''})</summary>
      {flow.history.map((event, index) => <p key={index} className="audit-row">{event.event.replaceAll('_', ' ')} · {new Date(event.at).toLocaleString()}{event.actor ? ` · ${event.actor}` : ''}</p>)}</details>}
  </section>;
}
