export type LanguageProcessingInfo = { warnings: string[]; translations: { source_id: number; english: string }[] };
export function LanguageProcessing({ profile, analysis }: { profile?: { label: string }; analysis?: LanguageProcessingInfo }) {
  if (!profile && !analysis) return null;
  return <section className="panel language-processing"><h2>Meeting language{profile ? ` · ${profile.label}` : ''}</h2>
    {analysis ? <><p className="muted">Original text is retained as evidence. BERT analyzes an English translation produced locally.</p>
      {analysis.warnings.map(w => <p className="muted" key={w}>{w}</p>)}
      <details><summary>Review English translations used for BERT</summary>{analysis.translations.map(t => <p dir="ltr" key={t.source_id}><strong>#{t.source_id}</strong> {t.english}</p>)}</details></>
      : <p className="muted">Urdu and Roman Urdu use local translation for English BERT analysis. Review the original wording before approving commitments.</p>}
  </section>;
}
