# MeetMind annotation guideline (team labelling)

These labels are **the team's own annotations**. They are used to:

1. check how well two people agree on AMI dialogue acts (inter-annotator agreement, Cohen's κ), and compare both with the AMI gold labels;
2. build a small end-to-end set to measure commitment, owner and deadline extraction.

Label independently: do not discuss items until both sheets are finished. Record your name and the date in the sheet's file name.

## Part 1: dialogue acts (`annotation/sample.csv`)

Fill the `label` column with exactly one code. Use the utterance and its preceding context.

| Code | Use when the speaker… | Examples |
|---|---|---|
| `inf` | gives information or a fact | "The remote has twelve buttons." |
| `ass` | gives an opinion or evaluation | "I think the yellow one looks better." |
| `sug` | proposes an action for the group or someone else | "We should use a rubber case." / "Let's go with that." |
| `off` | offers or commits to do something themselves | "I'll send the drawings after lunch." |
| `el.inf` | asks for information | "How much does it cost?" |
| `el.ass` | asks for an opinion | "What do you think of the colour?" |
| `el.sug` | asks for a suggestion or offer | "Should we use solar cells?" / "Who can take this?" |
| `el.und` | asks whether something was understood | "Do you see what I mean?" |
| `und` | shows (non-)understanding | "So you mean the casing." |
| `bck` | backchannel only, no content | "Yeah." "Mm-hmm." |
| `stl` | stalling or filler | "Um…" "So…" |
| `fra` | fragment, abandoned or cut-off utterance | "And then we-" |
| `be.pos` | positive social act: thanks, praise, greeting | "Great, thanks." |
| `be.neg` | negative social act: apology, frustration | "Sorry about that." |
| `oth` | none of the above | |

Rules:
- Choose the speaker's main function. A question that proposes ("Shall we…?") is `el.sug`, not `el.inf`.
- "I will / I'll / let me" + a task is `off`. "We should / let's" is `sug`.
- Do not look at the hidden AMI label file before both people are done.
- Mark `unsure` = `1` when you hesitated; this helps the disagreement review.

## Part 2: end-to-end commitments (`evaluation/e2e/*.json`)

For each short real or consented transcript (English, Urdu or Roman Urdu), list the **gold** action items a careful person would record:

```json
{"id": "e2e-01", "language": "en", "meeting_date": "2026-11-11",
 "transcript": "Sara: I will send the report by Friday.\nAli: We should book the room.",
 "gold": [{"kind": "commitment", "task": "Send the report", "owner": "Sara", "deadline_date": "2026-11-13",
           "quote": "I will send the report by Friday."},
          {"kind": "suggestion", "task": "Book the room", "owner": null, "deadline_date": null,
           "quote": "We should book the room."}]}
```

- `kind`: `commitment` (an explicit promise or accepted assignment), `suggestion`, `request` or `cancellation`.
- `owner`: the person who will do it, exactly as named in the transcript, or `null` if not stated. Never guess.
- `deadline_date`: the calendar date (ISO) implied by the meeting date, or `null`.
- `quote`: the shortest exact transcript span that supports the item.

Cover these cases across the set:
- an explicit commitment;
- an implicit commitment ("sure, I can do that");
- a missing owner;
- an ambiguous date ("Monday or Friday");
- a negation;
- a meeting with no tasks;
- a later cancellation.

Two people should agree on each gold file. Record any disagreements in the file's `notes` field.
