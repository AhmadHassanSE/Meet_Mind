import { meetings } from "../data";
import { PageHeader, StatusBadge } from "../components/UI";

export function Meetings() {
  document.title = "Meetings - MeetMind";
  return <div><PageHeader title="Meetings" subtitle="Processed transcripts, action counts, and review status" /><div className="panel overflow-hidden">{meetings.map((m) => <div key={m.title} className="flex items-center justify-between gap-4 border-b border-border p-5 last:border-0"><div><p className="font-semibold">{m.title}</p><p className="text-sm text-secondary">{m.meta}</p></div><StatusBadge status={m.status} /></div>)}</div></div>;
}
