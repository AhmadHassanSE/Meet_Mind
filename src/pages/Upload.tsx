import { CloudArrowUpIcon, MicrophoneIcon, VideoCameraIcon } from "@heroicons/react/24/outline";
import { useState } from "react";
import { PageHeader } from "../components/UI";

const tabs = ["Text / paste", "File upload", "Audio", "Live"];

export function Upload() {
  document.title = "Upload meeting - MeetMind";
  const [tab, setTab] = useState(tabs[0]);
  const [processing, setProcessing] = useState(false);
  const [text, setText] = useState("");
  if (processing) return <div><PageHeader title="Processing your meeting" /><div className="panel mx-auto max-w-3xl p-6">{["Cleaning transcript", "Identifying speakers", "Running NLP pipeline", "Extracting action items", "Generating drafts"].map((step, i) => <div key={step} className="flex items-center justify-between border-b border-border py-4 last:border-0"><span className="flex items-center gap-3"><span className={`h-3 w-3 rounded-full ${i < 2 ? "bg-success" : i === 2 ? "pulse-dot bg-accent" : "border border-secondary"}`} />{step}</span><span className="text-sm text-secondary">{i < 2 ? "Done" : i === 2 ? "In progress..." : "Waiting"}</span></div>)}<p className="mt-5 text-sm text-secondary">Estimated time remaining: ~18 seconds</p></div></div>;
  return <div><PageHeader title="Upload a meeting" subtitle="Paste text, upload a file, or connect a live feed" /><div className="panel p-5">
    <div className="mb-5 flex flex-wrap gap-2">{tabs.map((item) => <button key={item} onClick={() => setTab(item)} className={item === tab ? "btn-primary" : "btn-secondary"}>{item}</button>)}</div>
    {tab === "Text / paste" ? <div><textarea value={text} onChange={(e) => setText(e.target.value)} className="input min-h-72 w-full font-mono" placeholder="Paste your meeting transcript here..." /><p className="mt-2 text-right text-xs text-secondary">{text.split(/\n/).length} lines · {text.length} characters</p></div> : null}
    {tab === "File upload" ? <Drop icon={<CloudArrowUpIcon />} text="Drop your file here or click to browse" formats=".txt .docx .vtt .md" /> : null}
    {tab === "Audio" ? <Drop icon={<MicrophoneIcon />} text="Drop an audio file here" formats=".mp3 .wav .m4a .ogg" extra={<div className="mt-5 h-16 rounded-md bg-[repeating-linear-gradient(90deg,#2D7DD2_0_4px,transparent_4px_14px)] opacity-70" />} /> : null}
    {tab === "Live" ? <div className="soft-panel p-6"><VideoCameraIcon className="mb-4 h-10 w-10 text-accent" /><p className="mb-4 text-secondary">Connect your Zoom or Teams meeting to receive a live transcript.</p><div className="flex gap-3"><button className="btn-primary">Connect Zoom</button><button className="btn-secondary">Connect Teams</button></div><p className="mt-4 text-sm text-warning">Status: Not connected</p></div> : null}
    <div className="mt-6 grid gap-4 md:grid-cols-2"><input className="input" placeholder="Meeting title" /><input className="input" type="date" /><input className="input" placeholder="Attendees" /><input className="input" placeholder="Project tag" /></div>
    <div className="mt-6 flex justify-end gap-3"><button className="btn-secondary">Cancel</button><button onClick={() => setProcessing(true)} className="btn-primary">Process meeting</button></div>
  </div></div>;
}

function Drop({ icon, text, formats, extra }: { icon: JSX.Element; text: string; formats: string; extra?: JSX.Element }) {
  return <div className="soft-panel border-dashed p-10 text-center">{<span className="mx-auto block h-12 w-12 text-accent">{icon}</span>}<p className="mt-3 font-semibold">{text}</p><p className="mt-2 text-sm text-secondary">Accepted formats: {formats}</p>{extra}</div>;
}
