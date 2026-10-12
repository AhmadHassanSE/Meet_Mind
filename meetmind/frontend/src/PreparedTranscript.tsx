type Preparation = { source_count: number; utterance_count: number; duplicate_section_removed: boolean; warnings: string[] };
export type PreparedMeeting = {
  id: string;
  language_profile?: { label: string };
  original_transcript?: string;
  preprocessing?: Preparation;
  source_segments?: { id: number; text: string }[];
};
export function PreparedTranscript({ meeting }: { meeting: PreparedMeeting }) {
  if (!meeting.preprocessing) return null;
  const p = meeting.preprocessing;
  return <section className="panel preparation"><h2>Transcript preparation</h2>
    <p className="muted">{p.source_count} source turns prepared as {p.utterance_count} utterances.
      {p.duplicate_section_removed && ' Matching duplicate report section removed.'}</p>
    {p.warnings.map(warning => <p className="mint" key={warning}>{warning}</p>)}
    <p className="muted">Split utterances retain their source speaker and time range. Times refer to the complete source turn.</p>
    <details><summary>Original transcript</summary><pre dir="auto">{meeting.original_transcript}</pre>
      <a href={`/api/meetings/${meeting.id}/transcript?format=original`}>Download original text</a></details>
  </section>;
}
