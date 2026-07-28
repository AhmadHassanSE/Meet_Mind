import ForceGraph2D from "react-force-graph-2d";
import { PageHeader } from "../components/UI";

const graphData = {
  nodes: [
    { id: "Q3 Product Review", group: "meeting" },
    { id: "Sara", group: "person" },
    { id: "Bilal", group: "person" },
    { id: "Proposal update", group: "item" },
    { id: "Legal review", group: "item" },
  ],
  links: [
    { source: "Q3 Product Review", target: "Sara" },
    { source: "Q3 Product Review", target: "Bilal" },
    { source: "Sara", target: "Proposal update" },
    { source: "Bilal", target: "Legal review" },
  ],
};

export function Graph() {
  document.title = "Knowledge graph - MeetMind";
  return <div><PageHeader title="Knowledge graph" subtitle="Meetings, people, decisions, and unresolved items" /><div className="panel h-[620px] overflow-hidden p-2"><ForceGraph2D graphData={graphData} nodeAutoColorBy="group" backgroundColor="#111827" linkColor={() => "#2D5099"} nodeCanvasObject={(node, ctx, scale) => { const label = String(node.id); ctx.fillStyle = node.color as string; ctx.beginPath(); ctx.arc(node.x ?? 0, node.y ?? 0, 7, 0, 2 * Math.PI); ctx.fill(); ctx.fillStyle = "#F1F5F9"; ctx.font = `${12 / scale}px Inter`; ctx.fillText(label, (node.x ?? 0) + 10, (node.y ?? 0) + 4); }} /></div></div>;
}
