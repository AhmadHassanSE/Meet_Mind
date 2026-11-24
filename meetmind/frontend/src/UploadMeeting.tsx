import React, { useEffect, useRef, useState } from 'react';
import { ArrowRight, Upload, FileText, Mic, Video, X, CheckCircle2, Radio } from 'lucide-react';
import { apiFetch } from './api';
import { MeetingBot } from './MeetingBot';

type Job = { id: string; status: string; progress: number; message: string; meeting_id: string | null };
const formats: Record<Exclude<Tab, 'meet'>, string> = {
  text: '', transcript: '.txt,.md,.docx,.vtt,.srt',
  audio: '.wav,.mp3,.m4a,.ogg,.flac,.aac', recording: '.mp4,.webm,.mov,.mkv',
};
const tabs = [{ id: 'text', label: 'Paste text', icon: FileText }, { id: 'transcript', label: 'Transcript file', icon: Upload },
  { id: 'audio', label: 'Audio', icon: Mic }, { id: 'recording', label: 'Video recording', icon: Video },
  { id: 'meet', label: 'Live Google Meet', icon: Radio }] as const;
export type Tab = 'text' | 'transcript' | 'audio' | 'recording' | 'meet';
const tabHelp: Record<Tab, string> = {
  text: 'Paste the conversation, one line per speaker, such as “Sara: I will send it by Friday.”',
  transcript: 'Upload a transcript file. Speaker names and times are kept when the file has them.',
  audio: 'Upload an audio recording. MeetMind turns the speech into text on this computer.',
  recording: 'Upload a saved Meet, Teams or screen recording with clear meeting audio.',
  meet: 'Send a note-taker into a meeting that is happening now. It records the audio and makes a transcript when you stop it.',
};
const stageName: Record<string, string> = { queued: 'Waiting', decoding: 'Reading file', loading_model: 'Preparing',
  transcribing: 'Writing transcript', saving: 'Saving', completed: 'Done' };

async function readResponse(response: Response) {
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Upload failed. Check the title and file, then retry.');
  return data;
}

export function UploadMeeting({ onReady, initialTab = 'text' }: { onReady: (id: string) => Promise<void>; initialTab?: Tab }) {
  // An unfinished Meet capture reopens on its own tab after a reload.
  const [tab, setTab] = useState<Tab>(() => { try { return localStorage.getItem('meetmind-bot-id') ? 'meet' : initialTab; } catch { return initialTab; } });
  const [title, setTitle] = useState('');
  const [text, setText] = useState('');
  const [language, setLanguage] = useState('auto');
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [jobId, setJobId] = useState<string | null>(() => localStorage.getItem('meetmind-ingestion-job'));
  const [job, setJob] = useState<Job | null>(null);
  const [dragging, setDragging] = useState(false);
  const ready = useRef(onReady);
  ready.current = onReady;
  const input = useRef<HTMLInputElement>(null);
  const submitting = useRef(false);
  const running = busy || Boolean(jobId);
  const accept = tab === 'meet' ? '' : formats[tab];

  useEffect(() => {
    if (!file || !['audio', 'recording'].includes(tab)) { setPreview(''); return; }
    const url = URL.createObjectURL(file); setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file, tab]);

  useEffect(() => {
    if (!jobId) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const controller = new AbortController();
    async function poll() {
      try {
        const response = await apiFetch(`/api/ingestion/jobs/${jobId}`, { signal: controller.signal });
        if (response.status === 404) {
          if (!stopped) { localStorage.removeItem('meetmind-ingestion-job'); setJobId(null); setError('This job no longer exists. Upload your recording again.'); }
          return;
        }
        const result: Job = await readResponse(response);
        if (stopped) return;
        setJob(result); setError('');
        if (result.status === 'failed' || result.status === 'completed') {
          localStorage.removeItem('meetmind-ingestion-job'); setJobId(null);
          if (result.status === 'failed') setError(result.message);
          else if (result.meeting_id) await ready.current(result.meeting_id);
          return;
        }
        timer = setTimeout(poll, 1200);
      } catch (e) {
        if (stopped) return;
        setError(`Progress check failed: ${(e as Error).message}. Retrying…`);
        timer = setTimeout(poll, 3000);
      }
    }
    void poll();
    return () => { stopped = true; controller.abort(); clearTimeout(timer); };
  }, [jobId]);

  function choose(candidate: File | undefined) {
    if (!candidate) return;
    const extension = '.' + candidate.name.split('.').pop()?.toLowerCase();
    const limit = tab === 'transcript' ? 2 * 1024 * 1024 : 200 * 1024 * 1024;
    if (!accept.split(',').includes(extension)) { setError('Choose a supported file for this tab.'); return; }
    if (!candidate.size || candidate.size > limit) { setError(`Choose a non-empty file under ${tab === 'transcript' ? '2' : '200'} MB.`); return; }
    setFile(candidate); setError('');
    if (!title) setTitle(candidate.name.replace(/\.[^.]+$/, ''));
  }

  async function submit() {
    if (submitting.current || running) return;
    submitting.current = true; setBusy(true); setError(''); setJob(null);
    try {
      if (tab === 'text') {
        const meeting = await readResponse(await apiFetch('/api/meetings', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title, transcript: text, input_language: language }) }));
        await onReady(meeting.id);
      } else {
        if (!file) throw new Error('Choose a file first.');
        const body = new FormData(); body.append('title', title); body.append('file', file); body.append('input_language', language);
        const media = tab === 'audio' || tab === 'recording';
        const result = await readResponse(await apiFetch(`/api/ingestion/${media ? 'media' : 'transcript'}`, { method: 'POST', body }));
        if (media) { localStorage.setItem('meetmind-ingestion-job', result.id); setJob(result); setJobId(result.id); }
        else await onReady(result.id);
      }
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); submitting.current = false; }
  }

  const tabIndex = tabs.findIndex(t => t.id === tab);
  return <><div className="page-head"><div><h1>Add a meeting</h1><p className="muted">Choose what you have. MeetMind makes a transcript, then helps you find and follow up on action items.</p></div></div>
    <div className="upload-tabs" role="tablist" aria-label="Meeting input type" style={{ '--tab': tabIndex, '--tabs': tabs.length } as React.CSSProperties}>
      <span className="tab-thumb" aria-hidden="true"/>
      {tabs.map(t => <button type="button" role="tab" aria-selected={tab === t.id} disabled={running} key={t.id} className="tab-button" onClick={() => { setTab(t.id); setFile(null); setError(''); setJob(null); }}><t.icon size={17} aria-hidden="true"/>{t.label}</button>)}</div>
    <p className="muted tab-help">{tabHelp[tab]}</p>
    {tab === 'meet' ? <MeetingBot onReady={onReady} embedded/> :
    <form className="panel form ingestion-form" onSubmit={e => { e.preventDefault(); void submit(); }}>
      {error && <div role="alert" className="error">{error}</div>}
      <label>Meeting title<input required disabled={running} maxLength={200} value={title} onChange={e => setTitle(e.target.value)} placeholder="Weekly product review"/></label>
      <label>Meeting language<select aria-label="Meeting language" disabled={running} value={language} onChange={e => setLanguage(e.target.value)}>
        <option value="auto">Auto detect</option><option value="en">English</option><option value="ur">Urdu — اردو</option>
        <option value="roman-ur">Roman Urdu</option>
      </select><small>Auto detect works for most meetings. Pick the language yourself for very short transcripts.</small></label>
      {tab === 'text' ? <label>Transcript<textarea aria-label="Transcript" dir="auto" required disabled={running} maxLength={500000} value={text} onChange={e => setText(e.target.value)} placeholder={'Paste your meeting transcript here…\n\nSara: I will send the proposal by Friday.\nAhmed: Let’s review the budget next week.'}/><small>{text.length.toLocaleString()} / 500,000 characters</small></label> : <div>
        <input ref={input} key={tab} className="visually-hidden" aria-label={`Choose ${tab} file`} type="file" disabled={running} accept={accept} onChange={e => choose(e.target.files?.[0])}/>
        <button type="button" disabled={running} className={`dropzone ${dragging ? 'dragging' : ''}`} onClick={() => input.current?.click()} onDragOver={e => { e.preventDefault(); if (!running) setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={e => { e.preventDefault(); setDragging(false); if (!running) choose(e.dataTransfer.files[0]); }}><span className="drop-icon" aria-hidden="true"><Upload size={28}/></span><strong>{file ? file.name : 'Drop your file here or click to browse'}</strong><span>{accept.split(',').join(' · ')} · up to {tab === 'transcript' ? '2 MB' : '200 MB / 2 hours'}</span></button>
        {file && <div className="row file-summary"><span className="muted">{(file.size / 1024 / 1024).toFixed(2)} MB · {file.name}</span><button className="back" type="button" aria-label="Remove selected file" disabled={running} onClick={() => { setFile(null); if (input.current) input.current.value = ''; }}><X size={18}/></button></div>}
        {preview && (tab === 'audio' ? <audio controls src={preview} className="media-preview"/> : <video controls src={preview} className="media-preview"/>)}
      </div>}
      {(running || job) && <section className="progress-panel" aria-live="polite"><div className="row"><strong>{job?.message || 'Uploading and validating your meeting…'}</strong>{job && <span className="mint">{job.progress}%</span>}</div><progress aria-label="Ingestion progress" max={100} value={job ? job.progress : undefined}/><ol className="stage-list">{(() => { const order = ['queued', 'decoding', 'loading_model', 'transcribing', 'saving', 'completed']; const at = order.indexOf(job?.status || 'queued');
        return order.map((stage, i) => <li key={stage} className={i < at ? 'done' : i === at ? 'mint current' : 'muted'}>{stageName[stage]}</li>); })()}</ol></section>}
      <div className="row"><span className="muted"><CheckCircle2 size={14}/> Your transcript stays in this local workspace.</span><button className="primary" disabled={running || !title.trim() || (tab === 'text' ? !text.trim() : !file)}>{running ? 'Processing…' : 'Process meeting'}<ArrowRight size={17}/></button></div>
    </form>}</>;
}
