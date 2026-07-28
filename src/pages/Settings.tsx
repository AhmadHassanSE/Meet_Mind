import { useState } from "react";
import { PageHeader } from "../components/UI";

const tabs = ["Profile", "Integrations", "Agent policy", "Notifications", "Team", "Data & Privacy"];
const integrations = ["Gmail", "Outlook", "Jira", "Trello", "Asana", "Google Calendar", "Slack", "Teams", "Zoom"];

export function Settings() {
  document.title = "Settings - MeetMind";
  const [tab, setTab] = useState("Integrations");
  return <div><PageHeader title="Settings" subtitle="Configure integrations, agent policy, and preferences" /><div className="mb-5 flex gap-2 overflow-x-auto">{tabs.map((item) => <button key={item} onClick={() => setTab(item)} className={item === tab ? "btn-primary whitespace-nowrap" : "btn-secondary whitespace-nowrap"}>{item}</button>)}</div>
    {tab === "Integrations" ? <div className="grid gap-4 xl:grid-cols-2">{integrations.map((name, i) => <div key={name} className="panel flex items-center justify-between gap-4 p-5"><div><p className="font-bold">{name}</p><p className="text-sm text-secondary">{i < 2 ? "ahmed@company.com" : `Create and sync ${name} artifacts`}</p></div><button className={i < 2 ? "btn-secondary" : "btn-primary"}>{i < 2 ? "Disconnect" : "Connect"}</button></div>)}</div> : null}
    {tab === "Agent policy" ? <div className="panel max-w-3xl space-y-5 p-5"><Toggle label="Require approval for all external emails" enabled={false} /><Toggle label="Create Jira tickets automatically" enabled /><label className="block text-sm text-secondary">Minimum confidence required<input type="range" min="70" max="99" defaultValue="90" className="mt-3 w-full accent-accent" /></label><Toggle label="Send Slack messages automatically" enabled /><input className="input w-full" defaultValue="24" aria-label="Approval timeout hours" /><select className="input w-full"><option>Meeting organizer</option><option>Team lead</option></select><button className="btn-primary">Save policy</button></div> : null}
    {tab === "Notifications" ? <div className="panel max-w-3xl space-y-4 p-5">{["Pending approvals reminder every 4 hours", "Deadline approaching within 48 hours", "At-risk item detected", "Stale item resurfaced", "Weekly summary email every Monday"].map((item) => <Toggle key={item} label={item} enabled />)}</div> : null}
    {!["Integrations", "Agent policy", "Notifications"].includes(tab) ? <div className="panel p-8 text-secondary">Settings for {tab} are ready for backend preferences.</div> : null}
  </div>;
}

function Toggle({ label, enabled }: { label: string; enabled?: boolean }) {
  return <label className="flex min-h-11 items-center justify-between gap-4"><span>{label}</span><input type="checkbox" defaultChecked={enabled} className="h-5 w-5 accent-accent" /></label>;
}
