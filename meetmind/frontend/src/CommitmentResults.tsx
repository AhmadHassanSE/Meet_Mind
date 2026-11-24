import { useState } from 'react';
import type { Access, DirectoryUser } from './api';
import { useDetails } from './ui';

export type CommitmentEvidence = { quote: string; source_ids: number[]; speaker?: string | null; start?: number | null; end?: number | null };
export type Commitment = {
  id?: string; revision?: number; task: string; owner: string | null; deadline: string | null;
  source_id: number; needs_review: boolean; kind?: string; status?: string; review_status?: string;
  review_reasons?: string[]; evidence?: CommitmentEvidence[]; assignee?: { id: string; name: string; email: string } | null;
  deadline_normalized?: string | null; priority?: 'high' | 'normal' | 'low'; priority_cue?: string | null;
  deadline_resolution?: { method: string; reason: string | null; reference_date?: string };
  confidence?: { score: number; action_probability: number | null };
  original?: { task: string; owner: string | null; deadline: string | null; status?: string };
  review_history?: { revision: number; at: string; decision: string; note: string; reviewer?: string }[];
};
export type ReviewData = { revision: number; task: string; owner: string | null; deadline: string | null; decision: string; note: string;
  deadline_date?: string | null; priority?: 'high' | 'normal' | 'low' };
export type CommitmentMeeting = {
  status: string; model: string | null; actions: Commitment[]; action_candidates?: Commitment[];
  extraction?: { warnings: string[]; spacy: { model: string; version?: string } };
  segments: { id: number; source: string }[];
};
type ReviewHandler = (id: string, data: ReviewData) => Promise<void>;
type AssignHandler = (id: string, revision: number, userId: string | null) => Promise<void>;
type Rights = { access?: Access | null; directory?: DirectoryUser[]; onAssign?: AssignHandler; onShowSource?: (ids: number[]) => void };

const kindLabel: Record<string, string> = { suggestion: 'Suggestion', request: 'Request', cancellation: 'Cancellation' };

/** Plain-language status for an item: what a person still has to do with it. */
function statusPill(item: Commitment) {
  if (item.review_status === 'approved') return { label: 'Approved', tone: ' ok' };
  if (item.review_status === 'rejected') return { label: 'Rejected', tone: ' bad' };
  if ((item.original?.status || item.status) === 'possible_cancellation') return { label: 'Possibly cancelled · to review', tone: ' warning' };
  if (item.kind && kindLabel[item.kind]) return { label: `${kindLabel[item.kind]} · to review`, tone: ' warning' };
  return { label: 'To review', tone: ' warning' };
}

const formatDate = (iso: string) => new Date(iso + 'T00:00').toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' });
const formatTime = (seconds: number) => `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`;

function Result({ item, meeting, onReview, onDraft, disabled, access, directory = [], onAssign, onShowSource }: { item: Commitment; meeting: CommitmentMeeting; onReview: ReviewHandler; onDraft?: (item: Commitment)=>void; disabled: boolean } & Rights) {
  // Without access info (older callers) keep the previous single-user behaviour.
  const organize = access ? access.can_organize : true;
  const owned = Boolean(item.id && access?.owned_items.includes(item.id));
  const details = useDetails();
  const [editing, setEditing] = useState(false);
  const [task, setTask] = useState(item.task);
  const [owner, setOwner] = useState(item.owner || '');
  const [deadline, setDeadline] = useState(item.deadline || '');
  const [note, setNote] = useState('');
  const [deadlineDate, setDeadlineDate] = useState(item.deadline_normalized || '');
  const [priority, setPriority] = useState(item.priority || 'normal');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const pending = !item.review_status || item.review_status === 'pending';
  const cancellation = (item.original?.status || item.status) === 'possible_cancellation';
  const pill = statusPill(item);
  function startEditing() {
    setTask(item.task); setOwner(item.owner || ''); setDeadline(item.deadline || ''); setDeadlineDate(item.deadline_normalized || '');
    setPriority(item.priority || 'normal'); setError(''); setEditing(true);
  }
  async function submit(decision: string, fromForm = true) {
    if (!item.id) return;
    setSaving(true); setError('');
    // A quick decision keeps the extracted fields; the form sends the reviewer's corrections.
    const fields = fromForm ? { task, owner: owner || null, deadline: deadline || null, note, priority,
      deadline_date: deadlineDate && deadlineDate !== item.deadline_normalized ? deadlineDate : null }
      : { task: item.task, owner: item.owner, deadline: item.deadline, note: '', priority: item.priority || 'normal', deadline_date: null };
    try {
      // A date is sent only when the reviewer changed it; otherwise the server re-resolves the wording.
      await onReview(item.id, { revision: item.revision || 0, decision, ...fields });
      setEditing(false); setNote('');
    } catch (e) { setError((e as Error).message); }
    finally { setSaving(false); }
  }
  const due = item.deadline_normalized ? formatDate(item.deadline_normalized) : item.deadline;
  const evidence = item.evidence?.length ? item.evidence : null;
  const busy = saving || disabled || !item.id;
  return <article className={`commitment-result${pending ? ' is-pending' : ''}`} data-id={item.id} data-status={item.status || 'proposed'}>
    <div className="item-top"><span className={`pill${pill.tone}`}>{pill.label}</span>
      {item.priority === 'high' && <span className="pill warning">High priority</span>}</div>
    <h3 dir="auto">{item.task}</h3>
    <p className="item-meta"><span><strong>Owner</strong> {item.owner || <em>not named</em>}</span>
      <span><strong>Due</strong> {due || <em>no date</em>}</span>
      {item.assignee && <span><strong>Account</strong> {item.assignee.name}{owned ? ' (you)' : ''}</span>}</p>
    {evidence ? evidence.map((e, i) => <blockquote key={i}>
      <p dir="auto">“{e.quote}”</p>
      <small className="muted">{e.speaker || 'Unknown speaker'}{e.start != null ? ` at ${formatTime(e.start)}` : ''}{details ? ` · line ${e.source_ids.map(id => `#${id}`).join(', ')}` : ''}
        {onShowSource && e.source_ids.length > 0 && <> · <button type="button" className="text-button" onClick={() => onShowSource(e.source_ids)}>Show in transcript</button></>}</small>
    </blockquote>) : <blockquote><p dir="auto">{meeting.segments.find(s => s.id === item.source_id)?.source}</p></blockquote>}
    {details && (item.confidence || item.priority_cue || !!item.review_reasons?.length) && <div className="tech">
      {item.confidence && <p>Review score {item.confidence.score.toFixed(2)}{item.confidence.action_probability != null ? ` · BERT action probability ${item.confidence.action_probability.toFixed(2)}` : ''}</p>}
      {item.priority_cue && <p>Priority cue: “{item.priority_cue}” ({item.priority})</p>}
      {item.deadline_resolution && <p>Deadline resolution: {item.deadline_resolution.method}{item.deadline_resolution.reason ? ` · ${item.deadline_resolution.reason}` : ''}</p>}
      {!!item.review_reasons?.length && <p>Flagged because: {item.review_reasons.map(reason => reason.replaceAll('_', ' ')).join('; ')}</p>}</div>}
    {editing ? <form className="review-form" onSubmit={e => { e.preventDefault(); void submit('pending'); }}>
      <label>Task<textarea dir="auto" aria-label="Task" required maxLength={1000} value={task} onChange={e => setTask(e.target.value)}/></label>
      <div className="form-pair">
        <label>Owner<input dir="auto" aria-label="Owner" maxLength={200} value={owner} onChange={e => setOwner(e.target.value)} placeholder="Not named"/></label>
        <label>Due (as said)<input dir="auto" aria-label="Deadline" maxLength={200} value={deadline} onChange={e => setDeadline(e.target.value)} placeholder="No date"/></label>
        <label>Due date<input type="date" aria-label="Deadline date" value={deadlineDate} onChange={e => setDeadlineDate(e.target.value)}/></label>
        <label>Priority<select aria-label="Priority" value={priority} onChange={e => setPriority(e.target.value as 'high' | 'normal' | 'low')}><option value="high">High</option><option value="normal">Normal</option><option value="low">Low</option></select></label>
      </div>
      {organize && onAssign && item.id && item.kind !== 'cancellation' && <label>Owner's MeetMind account
        <select aria-label="Owner account" value={item.assignee?.id || ''} disabled={busy}
          onChange={e => { setSaving(true); setError(''); onAssign(item.id!, item.revision || 0, e.target.value || null).catch(err => setError((err as Error).message)).finally(() => setSaving(false)); }}>
          <option value="">Not linked</option>
          {directory.map(user => <option key={user.id} value={user.id}>{user.name} ({user.email})</option>)}
        </select><small>Linking an account lets that person approve follow-ups for this item.</small></label>}
      <label>Note (optional){cancellation && ' — required to approve a possible cancellation'}<textarea dir="auto" aria-label="Review note" maxLength={2000} value={note} onChange={e => setNote(e.target.value)}/></label>
      <div className="review-controls">
        {item.kind !== 'cancellation' && <button type="button" className="primary" disabled={busy || !task.trim() || (cancellation && !note.trim())} onClick={() => void submit('approved')}>Approve</button>}
        <button type="button" disabled={busy || !task.trim()} onClick={() => void submit('rejected')}>Reject</button>
        <button type="submit" disabled={busy || !task.trim()}>Save without deciding</button>
        <button type="button" className="text-button" disabled={saving} onClick={() => { setEditing(false); setError(''); }}>Cancel</button>
      </div>{error && <p role="alert" className="error">{error}</p>}
    </form> : <div className="card-actions">
      {organize && pending && item.kind !== 'cancellation' && !cancellation && <button className="primary" disabled={busy} onClick={() => void submit('approved', false)}>Approve</button>}
      {organize && pending && <button disabled={busy} onClick={() => void submit('rejected', false)}>Reject</button>}
      {organize && <button className={pending ? 'text-button' : undefined} disabled={busy} onClick={startEditing}>{pending ? 'Edit details' : 'Change'}</button>}
      {item.review_status === 'approved' && onDraft && (organize || owned) && <button disabled={disabled} onClick={() => onDraft(item)}>Draft follow-up</button>}
    </div>}
    {!!item.review_history?.length && <details className="review-history"><summary>History ({item.review_history.length})</summary>
      <p className="muted">First found as: {item.original?.task} · {item.original?.owner || 'no owner'} · {item.original?.deadline || 'no date'}</p>
      {item.review_history.map(event => <p key={event.revision}><strong>{event.decision}</strong> · {new Date(event.at).toLocaleString()}{event.reviewer && <> · {event.reviewer}</>}{event.note && <> · {event.note}</>}</p>)}
    </details>}
    {!editing && error && <p role="alert" className="error">{error}</p>}
  </article>;
}

export function CommitmentResults({ meeting, onReview, onDraft, disabled = false, ...rights }: { meeting: CommitmentMeeting; onReview: ReviewHandler; onDraft?: (item:Commitment)=>void; disabled?: boolean } & Rights) {
  const details = useDetails();
  const candidates = meeting.action_candidates || [];
  return <section className="commitment-results">
    {meeting.status === 'uploaded' ? <div className="panel empty"><h3>No action items yet</h3><p className="muted">Use “Find action items” above to read the transcript and list who agreed to do what.</p></div>
      : !meeting.actions.length && !candidates.length ? <div className="panel empty"><h3>No action items found</h3><p className="muted">Nobody clearly committed to a task in this meeting. You can still read the transcript.</p></div>
      : <>{meeting.actions.map((item, i) => <Result key={item.id || i} item={item} meeting={meeting} onReview={onReview} onDraft={onDraft} disabled={disabled} {...rights}/>)}
        {!!candidates.length && <div className="action-candidates"><h2>Maybe action items</h2>
          <p className="muted">Suggestions and requests only become action items if you approve them. Cancellations can only be rejected or noted.</p>
          {candidates.map((item, i) => <Result key={item.id || i} item={item} meeting={meeting} onReview={onReview} disabled={disabled} {...rights}/>)}</div>}</>}
    {meeting.extraction?.warnings.map(warning => <p className="muted" key={warning}>{warning}</p>)}
    {details && meeting.extraction && <small className="muted">English entities: {meeting.extraction.spacy.model} {meeting.extraction.spacy.version}{meeting.model ? ` · interpreted locally with ${meeting.model}` : ''}</small>}
  </section>;
}

