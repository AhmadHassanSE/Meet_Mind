"""End-to-end extraction scoring against team-written gold files (evaluation/e2e/*.json).

For each gold file the real pipeline (BERT + spaCy + Ollama + grounding + deadline rules)
runs on the transcript in an isolated database, then predictions are matched to gold
items. Matching rule: greedy one-to-one by word overlap (Jaccard >= 0.5) between the gold
quote and the predicted evidence quote. Reported with explicit denominators:

* commitment precision / recall / F1 (kind == commitment on both sides)
* kind accuracy over matched items
* owner accuracy over matched gold commitments (case-insensitive; null == null is correct)
* deadline-date accuracy over matched gold commitments (ISO date equality; null == null)

Requires MEETMIND_DB pointing to a throwaway database, BERT_MODEL_PATH and a running Ollama.
"""
import argparse
import asyncio
import json
import os
import re
from pathlib import Path

THRESHOLD = 0.5


def words(text):
    return set(re.findall(r'\w+', (text or '').lower()))


def overlap(a, b):
    a, b = words(a), words(b)
    return len(a & b) / len(a | b) if a | b else 0.0


def match(gold, predicted):
    pairs = sorted(((overlap(g['quote'], p['quote']), gi, pi) for gi, g in enumerate(gold) for pi, p in enumerate(predicted)),
                   reverse=True)
    used_g, used_p, matches = set(), set(), []
    for score, gi, pi in pairs:
        if score >= THRESHOLD and gi not in used_g and pi not in used_p:
            used_g.add(gi); used_p.add(pi); matches.append((gold[gi], predicted[pi], score))
    return matches


def predictions(meeting):
    return [{'kind': i.get('kind', 'commitment'), 'task': i['task'], 'owner': i.get('owner'),
             'deadline_date': i.get('deadline_normalized'), 'quote': (i.get('evidence') or [{}])[0].get('quote', '')}
            for i in meeting.get('actions', []) + meeting.get('action_candidates', [])]


def score(cases):
    totals = {'gold_commitments': 0, 'predicted_commitments': 0, 'true_positive_commitments': 0,
              'matched': 0, 'kind_correct': 0, 'owner_correct': 0, 'deadline_correct': 0, 'matched_gold_commitments': 0}
    per_case = []
    for case_id, gold, predicted in cases:
        matches = match(gold, predicted)
        tp = sum(g['kind'] == p['kind'] == 'commitment' for g, p, _ in matches)
        commitments = [(g, p) for g, p, _ in matches if g['kind'] == 'commitment']
        owner = sum((g['owner'] or '').lower() == (p['owner'] or '').lower() for g, p in commitments)
        deadline = sum(g.get('deadline_date') == p.get('deadline_date') for g, p in commitments)
        row = {'case': case_id, 'gold_commitments': sum(g['kind'] == 'commitment' for g in gold),
               'predicted_commitments': sum(p['kind'] == 'commitment' for p in predicted),
               'true_positive_commitments': tp, 'matched': len(matches),
               'kind_correct': sum(g['kind'] == p['kind'] for g, p, _ in matches),
               'matched_gold_commitments': len(commitments), 'owner_correct': owner, 'deadline_correct': deadline}
        per_case.append(row)
        for key in totals:
            totals[key] += row[key]
    ratio = lambda a, b: a / b if b else None
    precision = ratio(totals['true_positive_commitments'], totals['predicted_commitments'])
    recall = ratio(totals['true_positive_commitments'], totals['gold_commitments'])
    f1 = 2 * precision * recall / (precision + recall) if precision and recall else 0.0
    return {'matching': f'greedy one-to-one, word Jaccard >= {THRESHOLD}', 'totals': totals,
            'commitment_precision': precision, 'commitment_recall': recall, 'commitment_f1': f1,
            'kind_accuracy': ratio(totals['kind_correct'], totals['matched']),
            'owner_accuracy': ratio(totals['owner_correct'], totals['matched_gold_commitments']),
            'deadline_accuracy': ratio(totals['deadline_correct'], totals['matched_gold_commitments']),
            'cases': per_case}


async def run_pipeline(case):
    from app import auth, main
    system = auth.User('evaluation', 'evaluation@localhost', 'Evaluation run', 'organizer', False)
    meeting = main.create_meeting(main.MeetingInput(title=case['id'], transcript=case['transcript'],
                                                    input_language=case.get('language', 'auto')), system)
    stored = main.get_meeting(meeting['id'])
    stored['meeting_date'] = case['meeting_date'] + 'T09:00:00+05:00'
    main.save(stored)
    return await main.extract_meeting(meeting['id'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gold', type=Path, default=Path('evaluation/e2e'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not os.environ.get('MEETMIND_DB'):
        raise ValueError('Set MEETMIND_DB to a throwaway database before running the pipeline')
    cases = []
    for path in sorted(args.gold.glob('*.json')):
        case = json.loads(path.read_text(encoding='utf-8'))
        meeting = asyncio.run(run_pipeline(case))
        cases.append((case['id'], case['gold'], predictions(meeting)))
        print(case['id'], 'extracted', flush=True)
    result = score(cases)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    print({k: v for k, v in result.items() if k != 'cases'})


if __name__ == '__main__':
    main()
