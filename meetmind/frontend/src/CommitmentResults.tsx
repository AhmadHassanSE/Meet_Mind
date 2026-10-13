import { useState } from 'react';

export type CommitmentEvidence = { quote: string; source_ids: number[]; speaker?: string | null; start?: number | null; end?: number | null };
export type Commitment = {
  id?: string; revision?: number; task: string; owner: string | null; deadline: string | null;
  source_id: number; needs_review: boolean; kind?: string; status?: string; review_status?: string;
  review_reasons?: string[]; evidence?: CommitmentEvidence[];
  original?: { task: string; owner: string | null; deadline: string | null; status?: string };
  review_history?: { revision: number; at: string; decision: string; note: string }[];
};
export type ReviewData = { revision: number; task: string; owner: string | null; deadline: string | null; decision: string; note: string };
export type CommitmentMeeting = {
  status: string; model: string | null; actions: Commitment[]; action_candidates?: Commitment[];
  extraction?: { warnings: string[]; spacy: { model: string; version?: string } };
  segments: { id: number; source: string }[];
};
type ReviewHandler = (id: string, data: ReviewData) => Promise<void>;

function Result({ item, meeting, onReview, disabled }: { item: Commitment; meeting: CommitmentMeeting; onReview: ReviewHandler; disabled: boolean }) {
  const [editing, setEditing] = useState(false);
  const [task, setTask] = useState(item.task);
  const [owner, setOwner] = useState(item.owner || '');
  const [deadline, setDeadline] = useState(item.deadline || '');
  const [note, setNote] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const reviewed = item.review_status && item.review_status !== 'pending';
  const cancellation = (item.original?.status || item.status) === 'possible_cancellation';
  async function submit(decision: string) {
    if (!item.id) return;
    setSaving(true); setError('');
    try {
      await onReview(item.id, { revision: item.revision || 0, task, owner: owner || null, deadline: deadline || null, decision, note });
      setEditing(false); setNote('');
    } catch (e) { setError((e as Error).message); }
    finally { setSaving(false); }
  }
  return <article className="commitment-result" data-id={item.id} data-status={item.status || 'proposed'}>
    <span className={`pill${reviewed ? '' : ' warning'}`}>{reviewed ? item.review_status : cancellation ? 'Possible cancellation' : item.kind && item.kind !== 'commitment' ? item.kind : 'Needs review'}</span>
    <h3 dir="auto">{item.task}</h3><p className="muted">Owner: {item.owner || 'Unresolved'} · Due: {item.deadline || 'Unresolved'}</p>
    {item.evidence?.length ? item.evidence.map((e, i) => <blockquote key={i}><small className="mint">{e.source_ids.map(id => `#${id}`).join(', ')}{e.speaker ? ` · ${e.speaker}` : ''}{e.start != null ? ` · ${e.start.toFixed(1)}s–${e.end?.toFixed(1)}s` : ''}</small><p dir="auto">{e.quote}</p></blockquote>) : <blockquote>{meeting.segments.find(s => s.id === item.source_id)?.source}</blockquote>}
    {!!item.review_reasons?.length && <details><summary>Review details</summary><ul>{item.review_reasons.map(reason => <li key={reason}>{reason.replaceAll('_', ' ')}</li>)}</ul></details>}
    {!!item.review_history?.length && <details className="review-history"><summary>Review history ({item.review_history.length})</summary>
      <p className="muted">Original extraction: {item.original?.task} · {item.original?.owner || 'Unresolved'} · {item.original?.deadline || 'Unresolved'}</p>
      {item.review_history.map(event => <p key={event.revision}><strong>{event.decision}</strong> · {new Date(event.at).toLocaleString()}{event.note && <> · {event.note}</>}</p>)}
    </details>}
    {editing ? <form className="review-form" onSubmit={e => { e.preventDefault(); void submit('pending'); }}>
      <label>Task<textarea dir="auto" aria-label="Task" required maxLength={1000} value={task} onChange={e => setTask(e.target.value)}/></label>
      <label>Owner<input dir="auto" aria-label="Owner" maxLength={200} value={owner} onChange={e => setOwner(e.target.value)} placeholder="Unresolved"/></label>
      <label>Deadline<input dir="auto" aria-label="Deadline" maxLength={200} value={deadline} onChange={e => setDeadline(e.target.value)} placeholder="Unresolved"/></label>
      <label>Review note<textarea dir="auto" aria-label="Review note" maxLength={2000} value={note} onChange={e => setNote(e.target.value)}/></label>
      <p className="muted">Corrections are your input; the original extraction and source evidence are retained. Approval does not execute the task.</p>
      {cancellation && <p className="mint">Check the cancellation evidence. Add a note explaining your decision before approving.</p>}
      <div className="review-controls">
        <button type="submit" disabled={saving || disabled || !task.trim()}>Save changes for review</button>
        {item.kind !== 'cancellation' && <button type="button" className="primary" disabled={saving || disabled || !task.trim() || (cancellation && !note.trim())} onClick={() => void submit('approved')}>{item.kind === 'suggestion' || item.kind === 'request' ? 'Approve as commitment' : 'Approve commitment'}</button>}
        <button type="button" disabled={saving || disabled || !task.trim()} onClick={() => void submit('rejected')}>Reject</button>
        <button type="button" disabled={saving} onClick={() => { setEditing(false); setError(''); }}>Cancel</button>
      </div>{error && <p role="alert" className="error">{error}</p>}
    </form> : <button disabled={disabled || !item.id} onClick={() => { setTask(item.task); setOwner(item.owner || ''); setDeadline(item.deadline || ''); setEditing(true); }}>Review / edit</button>}
  </article>;
}

export function CommitmentResults({ meeting, onReview, disabled = false }: { meeting: CommitmentMeeting; onReview: ReviewHandler; disabled?: boolean }) {
  const count = [...meeting.actions, ...(meeting.action_candidates || [])].filter(item => item.review_status === 'approved').length;
  return <section className="panel commitment-results"><h2>Extracted commitments</h2>
    <p className="muted">{count} approved. Review evidence, correct the fields, then approve or reject each item. Blank owners and deadlines stay unresolved.</p>
    {[...meeting.actions, ...(meeting.action_candidates || [])].some(item => item.review_history?.length) && <p className="muted">Your review decisions are saved. To extract again, upload a new copy of this meeting; this keeps your reviewed work intact.</p>}
    {meeting.status === 'uploaded' ? <div className="empty">Run extraction to identify commitments.</div>
      : !meeting.actions.length ? <div className="empty">No explicit commitments extracted. Review the transcript and candidates below.</div>
      : meeting.actions.map((item, i) => <Result key={item.id || i} item={item} meeting={meeting} onReview={onReview} disabled={disabled}/>)}
    {!!meeting.action_candidates?.length && <div className="action-candidates"><h2>Suggestions, requests and cancellations</h2>
      <p className="muted">Suggestions and requests can become commitments through your explicit approval. Cancellation statements cannot be approved as tasks.</p>
      {meeting.action_candidates.map((item, i) => <Result key={item.id || i} item={item} meeting={meeting} onReview={onReview} disabled={disabled}/>)}</div>}
    {meeting.extraction?.warnings.map(warning => <p className="muted" key={warning}>{warning}</p>)}
    {meeting.extraction && <small className="muted">English entities: {meeting.extraction.spacy.model} {meeting.extraction.spacy.version}</small>}
    {meeting.model && <p className="muted">Interpreted locally with {meeting.model}</p>}
  </section>;
}
