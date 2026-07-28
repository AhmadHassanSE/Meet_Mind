import { Dialog } from "@headlessui/react";
import { useState } from "react";
import toast from "react-hot-toast";
import { approvals } from "../data";
import { Confidence, PageHeader } from "../components/UI";

export function Approvals() {
  document.title = "Approval queue - MeetMind";
  const [open, setOpen] = useState(false);
  return <div><PageHeader title="Approval queue" subtitle="Review AI-generated emails, tasks, and calendar drafts" /><div className="grid gap-4">{approvals.map((a) => <article key={a.title} className="panel p-5"><div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between"><div><p className="font-bold">{a.title}</p><p className="text-secondary">"{a.body}"</p><Confidence value={a.confidence} /></div><div className="flex gap-2"><button onClick={() => setOpen(true)} className="btn-secondary">Edit draft</button><button onClick={() => toast.success("Approved and sent")} className="btn-primary">Approve</button></div></div></article>)}</div><Dialog open={open} onClose={setOpen} className="relative z-50"><div className="fixed inset-0 bg-black/60" /><div className="fixed inset-x-4 top-12 mx-auto max-w-2xl rounded-lg bg-surface-2 p-5 shadow-modal"><h3 className="text-lg font-bold">Draft email</h3><input className="input mt-4 w-full" defaultValue="sara@company.com" /><input className="input mt-3 w-full" defaultValue="Proposal follow-up" /><textarea className="input mt-3 min-h-44 w-full" defaultValue="Hi Sara, please send the updated proposal to the client by Friday." /><div className="mt-4 flex justify-end gap-2"><button onClick={() => setOpen(false)} className="btn-secondary">Reject</button><button className="btn-secondary">Save</button><button onClick={() => setOpen(false)} className="btn-primary">Approve</button></div></div></Dialog></div>;
}
