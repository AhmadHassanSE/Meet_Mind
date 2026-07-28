export const stats = [
  ["128", "Meetings processed", "accent"],
  ["34", "Open action items", "warning"],
  ["7", "Pending approvals", "purple"],
  ["5", "Overdue items", "danger"],
] as const;

export const meetings = [
  { title: "Q3 Product Review", status: "completed", meta: "5 action items · 2 pending · 28 Jul" },
  { title: "Enterprise Renewal Sync", status: "in review", meta: "3 action items · 1 pending · 27 Jul" },
  { title: "Platform Reliability Standup", status: "processing", meta: "Live transcript · 26 Jul" },
];

export const actions = [
  { task: "Update client proposal", owner: "Sara", due: "Tomorrow", priority: "HIGH", status: "pending", confidence: 0.91, stale: true },
  { task: "Book demo room", owner: "Bilal", due: "Thu", priority: "MEDIUM", status: "approved", confidence: 0.82 },
  { task: "Send project brief", owner: "Ahmed", due: "Completed", priority: "LOW", status: "completed", confidence: 0.96 },
  { task: "Submit legal review", owner: "Sara", due: "Overdue", priority: "CRITICAL", status: "overdue", confidence: 0.74 },
];

export const approvals = [
  { type: "email", title: "Draft email to Sara", body: "Send proposal to client by Friday", confidence: 0.91 },
  { type: "task", title: "Create Jira ticket", body: "Investigate billing webhook retries", confidence: 0.78 },
  { type: "calendar", title: "Schedule follow-up", body: "Book legal review for Thursday", confidence: 0.88 },
];

export const chartData = [
  { day: "1 Jul", done: 12, total: 18 },
  { day: "8 Jul", done: 21, total: 29 },
  { day: "15 Jul", done: 27, total: 35 },
  { day: "22 Jul", done: 33, total: 42 },
  { day: "28 Jul", done: 41, total: 48 },
];
