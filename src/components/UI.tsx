import { CheckIcon, ExclamationTriangleIcon } from "@heroicons/react/24/outline";
import { ReactNode } from "react";

export function PageHeader({ title, subtitle, action }: { title: string; subtitle?: string; action?: ReactNode }) {
  return <div className="mb-6 flex flex-col gap-3 md:flex-row md:items-end md:justify-between"><div><h2 className="text-2xl font-bold md:text-3xl">{title}</h2>{subtitle ? <p className="mt-1 text-sm text-secondary">{subtitle}</p> : null}</div>{action}</div>;
}

export function StatCard({ value, label, tone }: { value: string; label: string; tone: string }) {
  const border = { accent: "border-t-accent", warning: "border-t-warning", purple: "border-t-purple", danger: "border-t-danger", success: "border-t-success" }[tone] ?? "border-t-accent";
  return <div className={`panel border-t-2 ${border} p-5`}><div className="text-3xl font-bold">{value}</div><p className="mt-2 text-sm text-secondary">{label}</p></div>;
}

export function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = { pending: "bg-warning/15 text-warning", approved: "bg-success/15 text-success", rejected: "bg-danger/15 text-danger", executed: "bg-accent/15 text-accent", completed: "border border-success text-success", overdue: "border border-danger text-danger", "in review": "bg-warning/15 text-warning", processing: "bg-accent/15 text-accent" };
  return <span className={`chip ${map[status] ?? "bg-surface-2 text-secondary"}`}>{status}</span>;
}

export function PriorityBadge({ priority }: { priority: string }) {
  const map: Record<string, string> = { CRITICAL: "bg-danger text-white", HIGH: "bg-warning text-bg", MEDIUM: "bg-accent text-white", LOW: "border border-muted text-secondary" };
  return <span className={`chip ${map[priority]}`}>{priority}</span>;
}

export function Confidence({ value }: { value: number }) {
  const tone = value >= 0.85 ? "text-success" : value >= 0.7 ? "text-warning" : "text-danger";
  return <span className={`inline-flex items-center gap-2 font-mono text-xs ${tone}`}>{Array.from({ length: 5 }, (_, i) => <span key={i}>{i < Math.round(value * 5) ? "●" : "○"}</span>)} {value.toFixed(2)}</span>;
}

export function ActionItemCard({ item }: { item: { task: string; owner: string; due: string; priority: string; status: string; confidence: number; stale?: boolean } }) {
  return <article className="soft-panel p-4">
    {item.stale ? <div className="mb-3 flex items-center gap-2 rounded-md border border-warning/40 bg-warning/10 p-2 text-xs text-warning"><ExclamationTriangleIcon className="h-4 w-4" /> This item was also raised in the 15 Jul meeting.</div> : null}
    <div className="flex items-start justify-between gap-3">
      <label className="flex gap-3"><input type="checkbox" className="mt-1 h-4 w-4 rounded border-border bg-bg" defaultChecked={item.status === "completed"} /><span className="font-semibold">{item.task}</span></label>
      <PriorityBadge priority={item.priority} />
    </div>
    <div className="mt-3 flex flex-wrap items-center gap-3 text-sm text-secondary">
      <span>Owner: {item.owner}</span><span>Due: <span className={item.due === "Overdue" ? "text-danger" : item.due === "Tomorrow" ? "text-warning" : ""}>{item.due}</span></span><Confidence value={item.confidence} /><StatusBadge status={item.status} />
    </div>
  </article>;
}

export function Skeleton() {
  return <div className="panel space-y-3 p-5">{Array.from({ length: 4 }, (_, i) => <div key={i} className="h-5 animate-pulse rounded bg-surface-2" />)}</div>;
}

export function EmptyState({ title }: { title: string }) {
  return <div className="panel grid min-h-48 place-items-center p-8 text-center"><div><CheckIcon className="mx-auto h-10 w-10 text-success" /><p className="mt-3 font-semibold">{title}</p></div></div>;
}
