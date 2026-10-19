import { useEffect, useRef, useState } from 'react';
import type { Commitment } from './CommitmentResults';

type Draft = { id: string; meeting_id: string; meeting_title: string; status: string; revision: number;
  to: string[]; subject: string; body: string; model: string; approval_valid: boolean; source_current: boolean;
  source: { task: string; owner: string | null; deadline: string | null; evidence: { quote: string }[] };
  policy: { can_approve: boolean; violations: string[] };
  history: { at: string; action: string; note: string; revision: number }[] };
export type DraftSource = { meeting_id: string; commitment: Commitment };
const labels: Record<string,string> = {drafting:'Generating', draft:'Needs approval', approved:'Approved',
  rejected:'Rejected', source_changed:'Source changed', failed:'Generation failed'};
async function api<T>(path: string, method='GET', body?: object): Promise<T> {
  const response=await fetch(`/api${path}`, {method, headers:body ? {'Content-Type':'application/json'} : undefined,
    body:body ? JSON.stringify(body) : undefined});
  const value=await response.json();
  if(!response.ok) throw Object.assign(new Error(typeof value.detail==='string' ? value.detail : 'Check the draft fields and try again.'), {status:response.status});
  return value;
}

export function ArtifactWorkspace({source, onMeeting}: {source: DraftSource | null; onMeeting:(id:string)=>Promise<void>}) {
  const [drafts,setDrafts]=useState<Draft[]>([]), [draft,setDraft]=useState<Draft | null>(null);
  const [recipients,setRecipients]=useState(''), [to,setTo]=useState(''), [subject,setSubject]=useState(''), [body,setBody]=useState('');
  const [busy,setBusy]=useState(false), [error,setError]=useState('');
  const requestKey=useRef(crypto.randomUUID());
  const refresh=()=>api<Draft[]>('/artifacts').then(list=>{
    setDrafts(list);setDraft(current=>current ? list.find(item=>item.id===current.id) || current : null);
  });
  useEffect(()=>{void refresh().catch(e=>setError(e.message));},[]);
  useEffect(()=>{setRecipients('');setDraft(null);setError('');requestKey.current=crypto.randomUUID();},[source]);
  useEffect(()=>{if(draft){setTo(draft.to.join(', '));setSubject(draft.subject);setBody(draft.body);}},[draft?.id,draft?.revision]);
  useEffect(()=>{
    if(draft?.status!=='drafting') return;
    let disposed=false;
    const timer=setInterval(()=>{void api<Draft>(`/artifacts/${draft.id}`).then(value=>{
      if(!disposed)setDraft(value);
    }).catch(e=>{if(!disposed)setError(e.message);});},1500);
    return ()=>{disposed=true;clearInterval(timer);};
  },[draft?.id,draft?.status]);
  async function create() {
    if(!source?.commitment.id || busy)return;
    setBusy(true);setError('');
    try {
      const result=await api<Draft>(`/meetings/${source.meeting_id}/artifacts`,'POST',{
        commitment_id:source.commitment.id,commitment_revision:source.commitment.revision || 0,
        to:recipients.split(',').map(v=>v.trim()).filter(Boolean),idempotency_key:requestKey.current});
      setDraft(result);await refresh();requestKey.current=crypto.randomUUID();
    } catch(e) {
      setError((e as Error).message);
      if((e as {status?:number}).status)requestKey.current=crypto.randomUUID();
      void refresh().catch(()=>{});
    } finally {setBusy(false);}
  }
  async function save(decision?: 'approved' | 'rejected') {
    if(!draft || busy)return;
    setBusy(true);setError('');
    try {
      const updated=decision
        ? await api<Draft>(`/artifacts/${draft.id}/review`,'POST',{revision:draft.revision,decision})
        : await api<Draft>(`/artifacts/${draft.id}`,'PATCH',{revision:draft.revision,
            to:to.split(',').map(v=>v.trim()).filter(Boolean),subject,body});
      setDraft(updated);await refresh();
    } catch(e){setError((e as Error).message);}finally{setBusy(false);}
  }
  const dirty=Boolean(draft && (to!==draft.to.join(', ') || subject!==draft.subject || body!==draft.body));
  const editable=Boolean(draft && ['draft','approved','rejected'].includes(draft.status));
  return <><p className="eyebrow">REVIEWED FOLLOW-UP</p><h1>Follow-up drafts</h1>
    <p className="muted">Create an email from an approved commitment, check its content and recipients, then approve or reject the draft. Delivery connections are coming next.</p>
    {error && <p role="alert" className="error">{error}</p>}
    {source && <form className="panel form" onSubmit={e=>{e.preventDefault();void create();}}>
      <h2>Create follow-up email</h2><p dir="auto">{source.commitment.task}</p>
      <label>Recipient email addresses<input required value={recipients} onChange={e=>{setRecipients(e.target.value);requestKey.current=crypto.randomUUID();}} placeholder="person@example.com, colleague@example.com" disabled={busy}/></label>
      <small className="muted">Enter recipients explicitly; an owner's name is not an email address.</small>
      <button className="primary" disabled={busy || !recipients.trim()}>{busy ? 'Generating locally…' : 'Generate email draft'}</button>
    </form>}
    {!source && !draft && <p className="muted">Open a meeting, approve a commitment and choose “Draft follow-up” to create an email.</p>}
    <div className="artifact-layout"><section className="panel artifact-list"><div className="row"><h2>Saved drafts</h2><button onClick={()=>void refresh().catch(e=>setError(e.message))}>Refresh drafts</button></div>
      {!drafts.length && <p className="muted">No drafts yet.</p>}
      {drafts.map(item=><button className="artifact-entry" key={item.id} onClick={()=>{setDraft(item);setError('');}}>
        <strong>{item.subject || item.source.task}</strong><small>{item.meeting_title} · {labels[item.status] || item.status}</small>
      </button>)}
    </section>
    {draft && <section className="panel artifact-detail"><div className="row"><h2>Email draft</h2><span className="pill">{draft.status==='approved' && !draft.approval_valid ? 'Approval outdated' : labels[draft.status] || draft.status}</span></div>
      <p className="muted">Source commitment: <span dir="auto">{draft.source.task}</span></p>
      <p className="muted">Owner: {draft.source.owner || 'Unresolved'} · Due: {draft.source.deadline || 'Unresolved'}</p>
      {draft.source.evidence.map((e,i)=><blockquote dir="auto" key={i}>{e.quote}</blockquote>)}
      {!draft.source_current && <p role="status" className="error">The source commitment changed. Review it in the meeting and create a new draft.</p>}
      {draft.policy.violations.map(reason=><p className="error" key={reason}>{reason}</p>)}
      <form className="form" onSubmit={e=>{e.preventDefault();void save();}}>
        <label>To<input required aria-label="Draft recipients" value={to} onChange={e=>setTo(e.target.value)} disabled={!editable || busy}/></label>
        <label>Subject<input aria-label="Subject" dir="auto" required maxLength={200} value={subject} onChange={e=>setSubject(e.target.value)} disabled={!editable || busy}/></label>
        <label>Message<textarea aria-label="Message" dir="auto" required maxLength={8000} value={body} onChange={e=>setBody(e.target.value)} disabled={!editable || busy}/></label>
        {editable && <><div className="review-controls"><button type="submit" disabled={busy || !dirty}>Save draft changes</button>
          <button type="button" className="primary" disabled={busy || dirty || !draft.policy.can_approve || draft.approval_valid} onClick={()=>void save('approved')}>Approve draft</button>
          <button type="button" disabled={busy || dirty || draft.status==='rejected'} onClick={()=>void save('rejected')}>Reject draft</button></div>
          <p className="muted">{dirty ? 'Save your edits before approving. Changes require a new approval.' : draft.approval_valid ? 'This exact draft is approved. It has not been sent.' : 'Check the recipients, dates and wording before approving.'}</p></>}
      </form>
      <button onClick={()=>void onMeeting(draft.meeting_id)}>Open source meeting</button>
      <button disabled={busy} onClick={()=>void api<Draft>(`/artifacts/${draft.id}`).then(setDraft).catch(e=>setError(e.message))}>Reload draft</button>
      <details><summary>Draft history ({draft.history.length})</summary>{draft.history.map((event,i)=><p key={i}><strong>{event.action.replaceAll('_',' ')}</strong> · {new Date(event.at).toLocaleString()}{event.note && ` · ${event.note}`}</p>)}</details>
    </section>}</div>
  </>;
}
