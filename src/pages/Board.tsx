import { actions } from "../data";
import { ActionItemCard, PageHeader } from "../components/UI";

export function Board() {
  document.title = "Action items - MeetMind";
  return <div><PageHeader title="Action items" subtitle="Track ownership, priority, deadlines, and generated artifacts" /><div className="mb-4 flex flex-wrap gap-2"><button className="btn-primary">All</button><button className="btn-secondary">Mine</button><button className="btn-secondary">Overdue</button><button className="btn-secondary">At risk</button></div><div className="grid gap-4 xl:grid-cols-2">{actions.map((item) => <ActionItemCard key={item.task} item={item} />)}</div></div>;
}
