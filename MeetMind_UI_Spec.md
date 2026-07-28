# MeetMind — UI Specification
> Hand this file to your frontend agent to generate a professional, production-ready UI.

---

## 1. Project Overview

**Product:** MeetMind — Meeting Capture + Action-Item Execution Agent  
**Stack:** React 18 + TypeScript + Tailwind CSS  
**Purpose:** An AI-powered web app that converts meeting transcripts into structured action items, drafts follow-up emails and tasks, and tracks accountability across all meetings.  
**Primary user:** A professional who runs or attends recurring meetings and needs to close the gap between what was discussed and what actually gets done.

---

## 2. Design System

### 2.1 Color Palette

```
--color-bg:          #0B1120   /* page background — deep navy */
--color-surface:     #111827   /* card / panel surface */
--color-surface-2:   #1A2D52   /* elevated surface (modals, popovers) */
--color-border:      #1E3A6E   /* subtle borders */
--color-border-strong: #2D5099 /* hover / active borders */

--color-accent:      #2D7DD2   /* primary blue — CTAs, active states */
--color-accent-2:    #0D9488   /* teal — secondary actions, tags */
--color-success:     #10B981   /* green — completed, approved */
--color-warning:     #F59E0B   /* amber — pending, at-risk */
--color-danger:      #EF4444   /* red — overdue, rejected */
--color-purple:      #7C3AED   /* purple — agents, AI actions */

--color-text-primary:   #F1F5F9  /* headings, primary labels */
--color-text-secondary: #94A3B8  /* subtitles, descriptions */
--color-text-muted:     #475569  /* timestamps, meta info */
```

### 2.2 Typography

```
Display / Headings:  Inter (700)
Body:                Inter (400, 500)
Monospace / Code:    JetBrains Mono (for confidence scores, IDs, code)

Scale:
  --text-xs:   11px
  --text-sm:   13px
  --text-base: 15px
  --text-lg:   18px
  --text-xl:   22px
  --text-2xl:  28px
  --text-3xl:  36px
```

### 2.3 Spacing

```
Base unit: 4px
--space-1:  4px
--space-2:  8px
--space-3:  12px
--space-4:  16px
--space-6:  24px
--space-8:  32px
--space-12: 48px
--space-16: 64px
```

### 2.4 Border Radius

```
--radius-sm:  6px    /* tags, badges */
--radius-md:  10px   /* cards, inputs */
--radius-lg:  16px   /* modals, panels */
--radius-full: 9999px /* pills, avatars */
```

### 2.5 Shadows

```
--shadow-card:   0 1px 3px rgba(0,0,0,0.4), 0 0 0 1px #1E3A6E
--shadow-modal:  0 8px 32px rgba(0,0,0,0.6), 0 0 0 1px #2D5099
--shadow-glow:   0 0 20px rgba(45,125,210,0.15)
```

### 2.6 Component Tokens

```
/* Confidence score colors */
--confidence-high:   #10B981   /* ≥ 0.85 */
--confidence-medium: #F59E0B   /* 0.70 – 0.84 */
--confidence-low:    #EF4444   /* < 0.70 */

/* Priority colors */
--priority-critical: #EF4444
--priority-high:     #F59E0B
--priority-medium:   #2D7DD2
--priority-low:      #475569

/* Status colors */
--status-pending:    #F59E0B
--status-approved:   #10B981
--status-rejected:   #EF4444
--status-executed:   #2D7DD2
--status-overdue:    #EF4444
--status-completed:  #10B981
```

---

## 3. Layout Architecture

```
┌─────────────────────────────────────────────────────────┐
│  SIDEBAR (240px fixed)  │  MAIN CONTENT (flex 1)        │
│                         │                               │
│  Logo + wordmark        │  Top bar (search + user)      │
│  ─────────────────      │  ─────────────────────────    │
│  Navigation items       │  Page content (scrollable)    │
│                         │                               │
│  ─────────────────      │                               │
│  User avatar + name     │                               │
│  Settings shortcut      │                               │
└─────────────────────────────────────────────────────────┘
```

- Sidebar is fixed, non-scrolling, 240px wide on desktop
- Collapses to icon-only rail (64px) on tablet
- Full-screen drawer on mobile
- Main content area scrolls independently
- Top bar is sticky within the main content area

---

## 4. Navigation Structure

### Sidebar Navigation Items

```
Logo: "MeetMind" wordmark with a small lightning bolt icon

Primary Nav:
  🏠  Dashboard          /dashboard
  📋  Meetings           /meetings
  ✅  Action items       /board
  ⏳  Approval queue     /approvals        [badge: pending count]
  🧠  Knowledge graph    /graph
  📊  Analytics          /analytics

Secondary Nav (bottom):
  ⚙️  Settings           /settings
  [User avatar] [Name]   /profile
```

### Active State
- Left accent bar (3px, --color-accent)
- Background: --color-surface-2
- Text: --color-text-primary

### Badge
- Circular red dot with white number for unreviewed approvals
- Position: top-right of the nav item icon

---

## 5. Pages

---

### 5.1 Dashboard (`/dashboard`)

**Purpose:** The home screen. Give the user an instant snapshot of their meeting workload.

#### Layout
```
┌─────────────────────────────────────────────────────────┐
│  Welcome back, [Name]                    [Upload meeting]│
│  Monday, 28 July 2026                                   │
├─────────┬─────────┬─────────┬─────────────────────────  │
│  Stat   │  Stat   │  Stat   │  Stat                     │
│  card   │  card   │  card   │  card                     │
├─────────┴─────────┴─────────┴─────────────────────────  │
│                                                         │
│  ┌──────────────────────┐  ┌───────────────────────┐   │
│  │  Recent meetings     │  │  Pending approvals    │   │
│  │                      │  │                       │   │
│  │  [meeting row]       │  │  [approval row]       │   │
│  │  [meeting row]       │  │  [approval row]       │   │
│  │  [meeting row]       │  │  [approval row]       │   │
│  │  View all →          │  │  View all →           │   │
│  └──────────────────────┘  └───────────────────────┘   │
│                                                         │
│  ┌──────────────────────┐  ┌───────────────────────┐   │
│  │  My action items     │  │  At-risk items        │   │
│  │  (due this week)     │  │  (predicted to miss)  │   │
│  │  [item row]          │  │  [item row]           │   │
│  │  [item row]          │  │  [item row]           │   │
│  └──────────────────────┘  └───────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

#### Stat Cards (4 across)
Each card has:
- Large number (--text-3xl, bold)
- Label below (--text-sm, --color-text-secondary)
- Subtle icon top-right
- Thin colored top border matching the metric's semantic color

```
Card 1: Total meetings processed  (--color-accent border)
Card 2: Open action items         (--color-warning border)
Card 3: Pending approvals         (--color-purple border)
Card 4: Overdue items             (--color-danger border)
```

#### Recent Meetings Panel
Each row:
```
[●] Meeting title                          [status badge]
    3 action items · 2 pending · 28 Jul      [→ icon]
```
- `●` = colored dot indicating status (teal=completed, amber=in-review, blue=processing)
- Status badge: pill shaped, matches status color
- Hover: background lifts to --color-surface-2, full row is clickable

#### Pending Approvals Panel
Each row:
```
[📧] Draft email → Sara                    [Review]
     "Send proposal to client by Friday"
```
- Icon indicates artifact type (email, task, calendar, slack)
- "Review" button: primary small variant

#### My Action Items (due this week)
```
[ ] Update client proposal         HIGH    Due: Tomorrow
[ ] Book demo room                 MED     Due: Thu
[✓] Send project brief             LOW     Completed
```
- Checkbox to mark complete
- Priority chip
- Due date colored: red if overdue, amber if due today/tomorrow, gray otherwise

#### At-Risk Items Panel
```
[⚠] Sara — Submit legal review        Risk: 84%    [Nudge]
[⚠] Bilal — Update server config      Risk: 71%    [Nudge]
```
- Risk percentage in --color-danger or --color-warning
- "Nudge" button sends a reminder notification

---

### 5.2 Upload Meeting (`/upload`)

**Purpose:** Accept a meeting transcript and kick off processing.

#### Layout
```
┌─────────────────────────────────────────────────────────┐
│  Upload a meeting                                       │
│  Paste text, upload a file, or connect a live feed      │
│                                                         │
│  ┌─── Tab bar ──────────────────────────────────────┐  │
│  │  [Text / paste]  [File upload]  [Audio]  [Live]  │  │
│  └──────────────────────────────────────────────────┘  │
│                                                         │
│  ┌─── Active tab content ───────────────────────────┐  │
│  │  (see per-tab specs below)                       │  │
│  └──────────────────────────────────────────────────┘  │
│                                                         │
│  ┌─── Meeting metadata ─────────────────────────────┐  │
│  │  Meeting title: [____________________]           │  │
│  │  Date:          [____________________]           │  │
│  │  Attendees:     [____________________]  [+ Add]  │  │
│  │  Project tag:   [____________________]           │  │
│  └──────────────────────────────────────────────────┘  │
│                                                         │
│                         [Cancel]  [Process meeting →]  │
└─────────────────────────────────────────────────────────┘
```

#### Tab: Text / Paste
- Large textarea, monospace font, placeholder: "Paste your meeting transcript here..."
- Line count shown bottom-right
- Character counter

#### Tab: File Upload
- Drag-and-drop zone with dashed border (--color-border-strong)
- Center: upload icon + "Drop your file here or click to browse"
- Accepted formats listed below: `.txt .docx .vtt .md`
- On file drop: show filename, size, estimated processing time

#### Tab: Audio
- Drag-and-drop zone for audio files
- Accepted: `.mp3 .wav .m4a .ogg`
- Show waveform preview after upload (placeholder waveform SVG)
- "Language" select dropdown (default: English)

#### Tab: Live (Zoom / Teams)
- Instructions: "Connect your Zoom or Teams meeting to receive a live transcript"
- [Connect Zoom] button → OAuth flow
- [Connect Teams] button → OAuth flow
- Status indicator: "Not connected" / "Listening..."

#### Processing State (after submit)
Replace upload form with progress UI:
```
┌─────────────────────────────────────────────────────────┐
│  Processing your meeting                                │
│                                                         │
│  [●] Cleaning transcript          ✓ Done               │
│  [●] Identifying speakers         ✓ Done               │
│  [●] Running NLP pipeline         ⟳ In progress...     │
│  [○] Extracting action items      — Waiting            │
│  [○] Generating drafts            — Waiting            │
│                                                         │
│  Estimated time remaining: ~18 seconds                  │
└─────────────────────────────────────────────────────────┘
```

---

### 5.3 Meetings List (`/meetings`)

**Purpose:** Browse all processed meetings.

#### Layout
```
┌─────────────────────────────────────────────────────────┐
│  Meetings                      [Search...]  [+ Upload]  │
│                                                         │
│  Filter: [All ▾]  [Date range ▾]  [Project ▾]          │
│                                                         │
│  ┌───────────────────────────────────────────────────┐ │
│  │  [meeting card]                                   │ │
│  │  [meeting card]                                   │ │
│  │  [meeting card]                                   │ │
│  └───────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

#### Meeting Card
```
┌────────────────────────────────────────────────────────┐
│  Q3 Product Review                    [completed ●]    │
│  28 Jul 2026  ·  Ahmed, Sara, Bilal  ·  47 min         │
│                                                        │
│  5 action items   2 pending   1 overdue   0 stale      │
│                                                        │
│  "Discussed API performance, decided to defer Redis    │
│  migration to Q4..."                           [Open→] │
└────────────────────────────────────────────────────────┘
```

- Card background: --color-surface
- Hover: --color-surface-2 + --shadow-card
- Status badge top-right
- Summary is the first sentence of the AI-generated executive summary
- Stat row uses colored micro-badges for counts

---

### 5.4 Meeting Detail (`/meetings/:id`)

**Purpose:** Full detail view of one processed meeting.

#### Layout
```
┌──────────────────────────────────────────────────────────────┐
│  ← Back to meetings                                          │
│  Q3 Product Review                              [completed ●] │
│  28 Jul 2026  ·  Ahmed, Sara, Bilal  ·  47 min               │
├──────────────────┬───────────────────────────────────────────┤
│  LEFT PANEL      │  RIGHT PANEL                              │
│  (320px)         │  (flex 1)                                 │
│                  │                                           │
│  [Summary]       │  [Action items tab] [Transcript tab]      │
│  [Decisions]     │                                           │
│  [Attendees]     │  Content area                             │
│  [Tags]          │                                           │
│  [Export PDF]    │                                           │
└──────────────────┴───────────────────────────────────────────┘
```

#### Left Panel — Summary Section
- AI-generated executive summary (2–3 sentences)
- Decisions list (bullet points, each prefixed with a gavel icon)
- Attendees with avatar initials and follow-through rate badge
- Tag chips for project labels
- [Download meeting minutes PDF] button

#### Right Panel — Action Items Tab
Each action item card:
```
┌────────────────────────────────────────────────────────┐
│  [  ] Send updated proposal to client        [HIGH ●]  │
│                                                        │
│  Owner: Sara          Due: 30 Jul 2026                 │
│  Requested by: Ahmed  Confidence: 0.91 ●               │
│                                                        │
│  Source: "Sara, can you send the proposal by Thursday" │
│                                                        │
│  Artifacts: [📧 Draft email]  [📋 Jira ticket]        │
│                                                        │
│  [Approve all]   [Edit]   [Reject]         [pending ●] │
└────────────────────────────────────────────────────────┘
```

- Confidence score shown as colored dot + number
- Source utterance shown in italics with a quotation bar on left
- Artifacts as clickable chips that open a preview modal
- Stale item warning banner if this item was raised in a prior meeting

#### Right Panel — Transcript Tab
- Full transcript rendered with speaker labels on left
- Each speaker name is a colored pill (consistent color per speaker)
- Highlighted segments that generated action items (teal background)
- Timestamps shown on hover
- Search bar to find text within the transcript

---

### 5.5 Action Item Board (`/board`)

**Purpose:** Kanban-style board of all action items across all meetings.

#### Layout
```
┌───────────────────────────────────────────────────────────────┐
│  Action items                   [Search...]  [Filter ▾]       │
│  Filter by: [Owner ▾] [Project ▾] [Priority ▾] [Date ▾]      │
├────────────┬────────────┬──────────────┬──────────┬──────────┤
│  PENDING   │  APPROVED  │  IN PROGRESS │  DONE    │  OVERDUE │
│  (12)      │  (5)       │  (8)         │  (34)    │  (3)     │
├────────────┼────────────┼──────────────┼──────────┼──────────┤
│  [card]    │  [card]    │  [card]      │  [card]  │  [card]  │
│  [card]    │  [card]    │  [card]      │  [card]  │  [card]  │
│  [card]    │            │  [card]      │          │          │
└────────────┴────────────┴──────────────┴──────────┴──────────┘
```

#### Board Card
```
┌──────────────────────────────────┐
│  Send proposal to client  [HIGH] │
│  Sara  ·  Due 30 Jul             │
│  Q3 Review meeting               │
│  Confidence: ████░ 0.91          │
└──────────────────────────────────┘
```
- Draggable between columns
- Column header has count badge
- Overdue column has a red tinted header

---

### 5.6 Approval Queue (`/approvals`)

**Purpose:** Review and act on all AI-generated artifacts before they are executed.

#### Layout
```
┌─────────────────────────────────────────────────────────┐
│  Approval queue                        [Bulk approve ▾] │
│  7 items waiting for your review                        │
│                                                         │
│  Filter: [All ▾]  [Emails]  [Tasks]  [Calendar]  [Slack]│
│                                                         │
│  ┌───────────────────────────────────────────────────┐ │
│  │  [approval item]                                  │ │
│  │  [approval item]                                  │ │
│  └───────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

#### Approval Item Card
```
┌────────────────────────────────────────────────────────────┐
│  📧  Draft email                                  HIGH ●   │
│  To: client@company.com  ·  From the Q3 Review meeting     │
│  ─────────────────────────────────────────────────────     │
│  Subject: Project update — as discussed on 28 Jul          │
│                                                            │
│  Hi Sarah,                                                 │
│  Following our meeting today, I wanted to confirm the      │
│  next steps we agreed on...                   [Show full]  │
│                                                            │
│  Source action item: "Send the client an update by Fri"    │
│  Confidence: 0.91  ·  Owner: Ahmed  ·  Due: 30 Jul        │
│  ─────────────────────────────────────────────────────     │
│  [Edit draft]          [Reject]           [✓ Approve]      │
└────────────────────────────────────────────────────────────┘
```

Artifact type icons:
- 📧 Email
- 📋 Jira/Trello/Asana task
- 📅 Calendar event
- 💬 Slack message

Approve button: --color-success background  
Reject button: --color-danger outlined  
Edit draft: opens inline editor within the card

---

### 5.7 Knowledge Graph (`/graph`)

**Purpose:** Interactive visualization of people, meetings, and commitments over time.

#### Layout
```
┌───────────────────────────────────────────────────────────┐
│  Knowledge graph              [Search nodes...]  [Filter] │
├──────────────────────────────────┬────────────────────────┤
│  GRAPH CANVAS (flex 1)           │  DETAIL PANEL (300px)  │
│                                  │                        │
│  Force-directed node graph       │  Selected node info    │
│  using React Force Graph         │                        │
│  (d3 force simulation)           │  Name, type, stats     │
│                                  │  Linked items          │
│  Node colors:                    │  History               │
│  Blue  = Person                  │                        │
│  Teal  = Meeting                 │                        │
│  Amber = Action item             │                        │
│  Red   = Overdue item            │                        │
│  Green = Completed item          │                        │
│                                  │                        │
│  [Zoom in] [Zoom out] [Reset]    │                        │
└──────────────────────────────────┴────────────────────────┘
```

#### Detail Panel (when a node is selected)
**Person node:**
```
Ahmed Hassan
─────────────────────────
Follow-through rate: 78%   ████░
Open items: 5
Total commitments: 42
Avg completion time: 2.3 days

Recent commitments:
  · Send proposal (Due: 30 Jul) — Pending
  · Review API docs (Due: 25 Jul) — Done
```

**Meeting node:**
```
Q3 Product Review
─────────────────────────
28 Jul 2026  ·  47 min
Attendees: Ahmed, Sara, Bilal

5 action items
2 decisions made
1 stale item flagged
```

---

### 5.8 Analytics (`/analytics`)

**Purpose:** Data visualizations showing team productivity and meeting effectiveness.

#### Layout
```
┌──────────────────────────────────────────────────────┐
│  Analytics              Date range: [Last 30 days ▾] │
├───────────┬───────────┬──────────────────────────────┤
│  Stat     │  Stat     │  Stat                        │
│  card     │  card     │  card                        │
├───────────┴───────────┴──────────────────────────────┤
│  ┌─────────────────────────┐  ┌────────────────────┐ │
│  │  Completion rate        │  │  Items by person   │ │
│  │  Line chart over time   │  │  Horizontal bar    │ │
│  └─────────────────────────┘  └────────────────────┘ │
│  ┌─────────────────────────┐  ┌────────────────────┐ │
│  │  Items by priority      │  │  Aging report      │ │
│  │  Donut chart            │  │  Table             │ │
│  └─────────────────────────┘  └────────────────────┘ │
└──────────────────────────────────────────────────────┘
```

#### Stat Cards
- Completion rate this month (with delta vs last month, green/red arrow)
- Average time to completion
- Meetings processed
- Items at risk right now

#### Charts (use Recharts)
- **Completion rate over time:** LineChart with two lines (completed on time vs total)
- **Items by person:** HorizontalBarChart sorted by open items descending
- **Items by priority:** PieChart / DonutChart with legend
- **Aging report:** Table with columns: Item, Owner, Meeting, Days open, Risk score

#### Export Button
- [Export PDF] top right — downloads current view as PDF

---

### 5.9 Settings (`/settings`)

**Purpose:** Configure integrations, agent policy, and user preferences.

#### Layout (tabbed)
```
Tabs: [Profile]  [Integrations]  [Agent policy]  [Notifications]  [Team]  [Data & Privacy]
```

#### Tab: Integrations
Each integration as a card:
```
┌────────────────────────────────────────────────────┐
│  [Gmail icon]  Gmail                  [Connected ●] │
│  ahmed@company.com                   [Disconnect]   │
└────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────┐
│  [Jira icon]  Jira                   [Connect →]   │
│  Create tasks in your Jira projects                 │
└────────────────────────────────────────────────────┘
```
Integrations: Gmail, Outlook, Jira, Trello, Asana, Google Calendar, Slack, Teams, Zoom

#### Tab: Agent Policy
Controls what agents can do without human approval:
```
┌────────────────────────────────────────────────────┐
│  Send emails automatically                         │
│  Require approval for all external emails   [○]    │
│                                                    │
│  Create Jira tickets automatically          [●]    │
│  Minimum confidence required:  [0.90 ▾]            │
│                                                    │
│  Send Slack messages automatically          [●]    │
│                                                    │
│  Approval timeout (hours):  [24 _____]             │
│  Escalate to: [Meeting organizer ▾]                │
└────────────────────────────────────────────────────┘
```
- Toggle switches for each policy
- Confidence threshold sliders
- Save button at bottom

#### Tab: Notifications
```
  Pending approvals reminder:   [●]  Every [4 ▾] hours
  Deadline approaching (48hr):  [●]
  At-risk item detected:        [●]
  Stale item resurfaced:        [●]
  Weekly summary email:         [●]  Every [Monday ▾]
```

---

## 6. Reusable Components

### 6.1 Action Item Card (reused on Dashboard, Board, Meeting Detail)
Props: `task, owner, deadline, priority, status, confidence, artifacts, sourceUtterance, isStale`

```
┌────────────────────────────────────────────────────┐
│  [checkbox]  Task description             [PRIORITY]│
│  Owner: Sara  ·  Due: 30 Jul  ·  ● 0.91 confidence │
│  [stale warning if isStale]                        │
│  [artifact chips]              [status badge]      │
└────────────────────────────────────────────────────┘
```

### 6.2 Artifact Preview Modal
Opens when user clicks an artifact chip. Full-screen centered modal:
```
┌────────────────────────────────────────────────────┐
│  📧 Draft email                              [✕]   │
│  ─────────────────────────────────────────────     │
│  To: [editable input]                              │
│  Subject: [editable input]                         │
│  ─────────────────────────────────────────────     │
│  [Rich text editor with draft body]                │
│                                                    │
│  Source: "Sara, send the proposal by Thursday"     │
│  Confidence: 0.91                                  │
│  ─────────────────────────────────────────────     │
│  [Reject]                    [Save]  [✓ Approve]   │
└────────────────────────────────────────────────────┘
```

### 6.3 Status Badge
```
pending   → amber pill
approved  → green pill
rejected  → red pill
executed  → blue pill
completed → green outline pill
overdue   → red outline pill
```

### 6.4 Confidence Indicator
```
High (≥0.85):   ████● in green    "0.91"
Medium (≥0.70): ████○ in amber    "0.78"
Low (<0.70):    ██○○○ in red      "0.61"  + ⚠ flag for review
```

### 6.5 Priority Badge
```
CRITICAL  → red filled
HIGH      → amber filled
MEDIUM    → blue filled
LOW       → gray outlined
```

### 6.6 Empty States
Each page has an empty state when no data exists:

- Meetings list: "No meetings yet. Upload your first transcript to get started." + [Upload meeting] button
- Board: "No action items found for the selected filters."
- Approval queue: "You're all caught up. No approvals waiting." + checkmark illustration
- At-risk panel: "No at-risk items right now." + shield icon

### 6.7 Toast Notifications
Appear bottom-right, auto-dismiss after 4s:
```
✓ Email approved and sent to client@company.com
✕ Failed to create Jira ticket — check your connection
ℹ 3 new action items extracted from Q3 Review
⚠ 2 items from last week's meeting are still unresolved
```

### 6.8 Top Bar
```
┌───────────────────────────────────────────────────┐
│  [🔍 Search meetings, items, people...]    [🔔] [👤]│
└───────────────────────────────────────────────────┘
```
- Global search opens a command-palette style modal
- Bell icon shows notification count badge
- Avatar opens dropdown: Profile / Settings / Sign out

---

## 7. Key Interaction Patterns

### 7.1 Approve with one click
- Clicking [✓ Approve] on any artifact immediately shows a loading spinner for 800ms, then transitions to a green "Sent ✓" state
- No confirmation dialog unless the artifact is high-risk (external email with >3 recipients)

### 7.2 Inline editing
- Clicking [Edit draft] on an approval card expands the card inline to show an editable version
- No modal — editing happens in place
- [Save changes] and [Cancel] appear at the bottom of the expanded card

### 7.3 Stale item warning
- A yellow banner appears at the top of any action item card that was raised in a prior meeting:
  ```
  ⚠ This item was also raised in the 15 Jul meeting and was not completed.
  ```

### 7.4 Processing status
- When a meeting is being processed, a subtle pulsing dot appears next to the meeting in the list
- A floating toast in bottom-right shows: "Processing Q3 Review..." with a spinner
- On completion: "Q3 Review is ready — 5 action items found" with a [View] button

### 7.5 Global search (command palette)
- Triggered by Ctrl+K or clicking the search bar
- Full-screen modal with search input at top
- Results appear in categories: Meetings, Action items, People
- Keyboard navigable

### 7.6 Bulk approve
- Checkbox appears on hover for each approval card
- Selecting multiple shows a sticky bottom bar: "3 selected — [Approve all] [Reject all]"

---

## 8. Responsive Breakpoints

```
Mobile:   < 768px   — single column, bottom tab nav
Tablet:   768–1024px — sidebar collapses to icon rail
Desktop:  > 1024px  — full sidebar + content
```

---

## 9. Accessibility

- All interactive elements have `aria-label`
- Color is never the sole indicator (always paired with icon or text)
- Focus ring: 2px solid --color-accent, offset 2px
- Reduced motion: all animations wrapped in `@media (prefers-reduced-motion: no-preference)`
- Minimum touch target: 44px × 44px on mobile
- Keyboard navigation: Tab order follows visual order

---

## 10. Page Titles & Meta

```
Dashboard:      "Dashboard — MeetMind"
Meetings:       "Meetings — MeetMind"
Meeting detail: "[Meeting title] — MeetMind"
Board:          "Action items — MeetMind"
Approvals:      "Approval queue — MeetMind"
Graph:          "Knowledge graph — MeetMind"
Analytics:      "Analytics — MeetMind"
Settings:       "Settings — MeetMind"
```

---

## 11. Implementation Notes for Agent

1. Use **React 18 + TypeScript** with functional components and hooks only
2. Use **Tailwind CSS** for all styling — no CSS modules, no styled-components
3. Use **React Router v6** for routing
4. Use **Recharts** for all charts
5. Use **React Force Graph** for the knowledge graph visualization
6. Use **Zustand** for global state (current user, active meeting, approval queue count)
7. All API calls use **Axios** with a base URL from `import.meta.env.VITE_API_URL`
8. Use **React Query (TanStack Query)** for server state management and caching
9. All modals use **Headless UI** Dialog component
10. Icons use **Heroicons** (outline variant only)
11. Dates use **date-fns** for formatting
12. Every page must have a loading skeleton state and an error state
13. Use `react-hot-toast` for toast notifications
14. Confidence scores display as a 5-dot progress indicator + numeric value
15. All tables support sorting by clicking column headers
16. The sidebar `pending approvals` badge must poll `/api/v1/approvals/queue/count` every 30 seconds

---

*This specification covers all pages, components, interactions, and design tokens needed to build the full MeetMind frontend. Build each page in the order listed in Section 5. Start with the design system tokens in Section 2 before writing any component code.*
