import { ArrowDownTrayIcon } from "@heroicons/react/24/outline";
import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { chartData } from "../data";
import { PageHeader, StatCard } from "../components/UI";

const people = [{ name: "Sara", open: 12 }, { name: "Bilal", open: 9 }, { name: "Ahmed", open: 7 }, { name: "Mina", open: 4 }];
const priority = [{ name: "Critical", value: 4, fill: "#EF4444" }, { name: "High", value: 12, fill: "#F59E0B" }, { name: "Medium", value: 18, fill: "#2D7DD2" }, { name: "Low", value: 9, fill: "#475569" }];

export function Analytics() {
  document.title = "Analytics - MeetMind";
  return <div><PageHeader title="Analytics" subtitle="Last 30 days" action={<button className="btn-secondary"><ArrowDownTrayIcon className="h-5 w-5" /> Export PDF</button>} />
    <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4"><StatCard value="86%" label="Completion rate" tone="success" /><StatCard value="2.4d" label="Avg time to completion" tone="accent" /><StatCard value="42" label="Meetings processed" tone="purple" /><StatCard value="6" label="Items at risk" tone="danger" /></section>
    <section className="mt-6 grid gap-6 xl:grid-cols-2">
      <Chart title="Completion rate"><LineChart data={chartData}><CartesianGrid stroke="#1E3A6E" /><XAxis dataKey="day" stroke="#94A3B8" /><YAxis stroke="#94A3B8" /><Tooltip /><Line type="monotone" dataKey="done" stroke="#10B981" strokeWidth={2} /><Line type="monotone" dataKey="total" stroke="#2D7DD2" strokeWidth={2} /></LineChart></Chart>
      <Chart title="Items by person"><BarChart data={people} layout="vertical"><XAxis type="number" stroke="#94A3B8" /><YAxis type="category" dataKey="name" stroke="#94A3B8" /><Tooltip /><Bar dataKey="open" fill="#2D7DD2" radius={4} /></BarChart></Chart>
      <Chart title="Items by priority"><PieChart><Pie data={priority} dataKey="value" innerRadius={55} outerRadius={85}>{priority.map((p) => <Cell key={p.name} fill={p.fill} />)}</Pie><Tooltip /></PieChart></Chart>
      <div className="panel p-5"><h3 className="mb-4 font-bold">Aging report</h3><div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead className="text-secondary"><tr><th className="py-2">Item</th><th>Owner</th><th>Days</th><th>Risk</th></tr></thead><tbody>{["Legal review", "Webhook retry", "Proposal update"].map((item, i) => <tr key={item} className="border-t border-border"><td className="py-3">{item}</td><td>{people[i].name}</td><td>{12 - i * 3}</td><td className="text-warning">{76 + i * 5}%</td></tr>)}</tbody></table></div></div>
    </section>
  </div>;
}

function Chart({ title, children }: { title: string; children: JSX.Element }) {
  return <div className="panel p-5"><h3 className="mb-4 font-bold">{title}</h3><div className="h-72"><ResponsiveContainer width="100%" height="100%">{children}</ResponsiveContainer></div></div>;
}
