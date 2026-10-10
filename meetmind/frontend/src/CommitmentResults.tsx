export type CommitmentEvidence = { quote: string; source_ids: number[]; speaker?: string | null; start?: number | null; end?: number | null };
export type Commitment = {
  task: string; owner: string | null; deadline: string | null; source_id: number; needs_review: boolean;
  kind?: string; status?: string; review_reasons?: string[]; evidence?: CommitmentEvidence[];
};
export type CommitmentMeeting = {
  status: string; model: string | null; actions: Commitment[]; action_candidates?: Commitment[];
  extraction?: { warnings: string[]; spacy: { model: string; version?: string } };
  segments: { id: number; source: string }[];
};
function Result({ item, meeting }: { item: Commitment; meeting: CommitmentMeeting }) {
  return <article className="commitment-result" data-status={item.status || 'proposed'}>
    <span className="pill warning">{item.status === 'possible_cancellation' ? 'Possible cancellation' : item.kind && item.kind !== 'commitment' ? item.kind : 'Needs review'}</span>
    <h3>{item.task}</h3><p className="muted">Owner: {item.owner || 'Unresolved'} · Due: {item.deadline || 'Unresolved'}</p>
    {item.evidence?.length ? item.evidence.map((e, i) => <blockquote key={i}><small className="mint">{e.source_ids.map(id => `#${id}`).join(', ')}{e.speaker ? ` · ${e.speaker}` : ''}{e.start != null ? ` · ${e.start.toFixed(1)}s–${e.end?.toFixed(1)}s` : ''}</small><p>{e.quote}</p></blockquote>) : <blockquote>{meeting.segments.find(s => s.id === item.source_id)?.source}</blockquote>}
    {!!item.review_reasons?.length && <details><summary>Review details</summary><ul>{item.review_reasons.map(reason => <li key={reason}>{reason.replaceAll('_', ' ')}</li>)}</ul></details>}
  </article>;
}
export function CommitmentResults({ meeting }: { meeting: CommitmentMeeting }) {
  return <section className="panel commitment-results"><h2>Extracted commitments</h2>
    <p className="muted">Proposed tasks require human review. Relative deadlines retain the meeting’s wording.</p>
    {meeting.status === 'uploaded' ? <div className="empty">Run extraction to identify commitments.</div>
      : !meeting.actions.length ? <div className="empty">No explicit commitments extracted. Review the transcript and candidates below.</div>
      : meeting.actions.map((item, i) => <Result key={i} item={item} meeting={meeting}/>)}
    {!!meeting.action_candidates?.length && <div className="action-candidates"><h2>Suggestions, requests and cancellations</h2>
      <p className="muted">These statements are kept separate from proposed commitments.</p>
      {meeting.action_candidates.map((item, i) => <Result key={i} item={item} meeting={meeting}/>)}</div>}
    {meeting.extraction?.warnings.map(warning => <p className="muted" key={warning}>{warning}</p>)}
    {meeting.extraction && <small className="muted">Entities: {meeting.extraction.spacy.model} {meeting.extraction.spacy.version}</small>}
    {meeting.model && <p className="muted">Interpreted locally with {meeting.model}</p>}
  </section>;
}
