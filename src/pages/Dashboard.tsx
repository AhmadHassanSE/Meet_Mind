import { ArrowRightIcon, EnvelopeIcon } from "@heroicons/react/24/outline";
import { Link } from "react-router-dom";
import toast from "react-hot-toast";
import { actions, approvals, meetings, stats } from "../data";
import { ActionItemCard, PageHeader, StatCard, StatusBadge } from "../components/UI";

export function Dashboard() {
  document.title = "Dashboard - MeetMind";
  return <div>
    <PageHeader title="Welcome back, Ahmed" subtitle="Tuesday, 28 July 2026" action={<Link to="/upload" className="btn-primary">Upload meeting <ArrowRightIcon className="h-5 w-5" /></Link>} />
    <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">{stats.map(([value, label, tone]) => <StatCard key={label} value={value} label={label} tone={tone} />)}</section>
    <section className="mt-6 grid gap-6 xl:grid-cols-2">
      <div className="panel p-5"><h3 className="mb-4 font-bold">Recent meetings</h3><div className="space-y-2">{meetings.map((m) => <Link to="/meetings" key={m.title} className="flex items-center justify-between rounded-md p-3 hover:bg-surface-2"><div><p className="font-semibold">{m.title}</p><p className="text-sm text-secondary">{m.meta}</p></div><StatusBadge status={m.status} /></Link>)}</div></div>
      <div className="panel p-5"><h3 className="mb-4 font-bold">Pending approvals</h3><div className="space-y-2">{approvals.map((a) => <div key={a.title} className="flex items-center justify-between gap-3 rounded-md p-3 hover:bg-surface-2"><EnvelopeIcon className="h-5 w-5 text-accent" /><div className="flex-1"><p className="font-semibold">{a.title}</p><p className="text-sm text-secondary">"{a.body}"</p></div><button onClick={() => toast.success("Approval opened")} className="btn-primary min-h-9 px-3 py-1">Review</button></div>)}</div></div>
      <div className="panel p-5"><h3 className="mb-4 font-bold">My action items</h3><div className="space-y-3">{actions.slice(0, 3).map((item) => <ActionItemCard key={item.task} item={item} />)}</div></div>
      <div className="panel p-5"><h3 className="mb-4 font-bold">At-risk items</h3><div className="space-y-3">{actions.slice(0, 2).map((item, i) => <div key={item.task} className="soft-panel flex items-center justify-between gap-3 p-4"><div><p className="font-semibold">{item.owner} - {item.task}</p><p className={i === 0 ? "text-danger" : "text-warning"}>Risk: {i === 0 ? "84%" : "71%"}</p></div><button onClick={() => toast("Reminder queued")} className="btn-secondary">Nudge</button></div>)}</div></div>
    </section>
  </div>;
}
