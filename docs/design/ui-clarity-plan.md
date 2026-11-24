# MeetMind UI clarity plan

## Goal

Help a first-time user answer three questions quickly: which meeting needs attention, what should I do next, and what will happen if I approve something? Keep the existing MeetMind visual identity and preserve the advanced analysis for people who need it.

## Current direction already in the frontend

The active app is `meetmind/frontend` (the root `src/` folder is an older prototype). The current redesign has already simplified the main navigation to Meetings, Add meeting, My approvals and All follow-ups; added plain-language meeting states and attention prompts; centered the meeting page on a next step; and moved model scores, workflow history and source metadata behind a technical-details setting.

## Prioritized work

### 1. Make the simplified controls obvious

- Give the technical-details toggle a visible text label, not just an icon.
- Keep its accessible name and pressed state in sync with the visible label.
- Keep the control compact enough for the header on narrow screens.

### 2. Make the first meeting action easy to choose

- Keep the Add a meeting page organized around the input the user already has: pasted text, transcript file, audio, video recording or a live Meet.
- Keep one short explanation next to each choice and show only the fields relevant to that choice.
- On narrow screens, allow the choices to scroll or wrap without clipping their labels or hiding the selected state.
- Keep processing progress, errors and the next action visible together.

### 3. Make meeting review feel like one guided task

- Keep the next-step panel above the meeting sections and use plain verbs for each state: Find action items, Review items and Choose follow-ups.
- Explain that owners approve drafts before delivery, at the point where the organizer chooses email or Jira.
- Keep evidence next to each suggested action and let users jump from the evidence to its transcript line.
- Make the current section and outstanding review count easy to identify.

### 4. Reduce noise in lists and approvals

- Keep default meeting cards focused on title, date, current state and reviewed count.
- Use filters and search only when there is enough content to need them; always provide a clear way back to all meetings.
- In approval views, show recipient, destination and the exact content to be sent before the decision buttons.
- Keep technical confidence scores and audit history behind the details setting or an explicitly opened history section.

### 5. Check responsive and accessibility behavior

- Review the main flows at mobile, tablet and desktop widths.
- Confirm keyboard operation, visible focus, readable contrast, reduced-motion behavior, and screen-reader names for tabs, filters, progress and icon buttons.
- Use real user walkthroughs to catch confusing labels and revise the plan based on observed friction.

## Delivery order

1. Finish the current redesign controls and responsive treatment.
2. Walk through Add a meeting → review action items → choose follow-ups → approve a draft, simplifying any step that needs unexplained product knowledge.
3. Review meetings and approval lists with empty, loading, error and populated states.
4. Validate keyboard and screen-reader use, then refine from user feedback.

## Done when

- A new user can add a meeting and identify the next action without needing technical terminology.
- A reviewer can distinguish a proposed item from an approved item and find the supporting transcript evidence.
- A draft reviewer can see what will be delivered and who will receive it before approving.
- Core controls remain understandable and usable at narrow widths and with a keyboard.
