"""Seed synthetic review fixtures into an explicitly isolated browser-test DB."""
import argparse
import json
import os
from pathlib import Path
from uuid import uuid4
from app import main, review


def main_check():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not os.environ.get('MEETMIND_DB'):
        raise ValueError('Set MEETMIND_DB to a dedicated test database before seeding')
    text = 'Sara: I will send the report by Friday.\nAli: We should book the room.\nAli: Cancel the budget report.'
    meeting = main.create_meeting(main.MeetingInput(title='Review browser fixture ' + str(uuid4()), transcript=text))
    def item(task, kind, source, quote):
        return {'task': task, 'owner': 'Sara' if kind == 'commitment' else None,
                'deadline': 'by Friday' if kind == 'commitment' else None,
                'kind': kind, 'status': 'proposed' if kind == 'commitment' else kind,
                'source_id': source, 'source_ids': [source], 'needs_review': True,
                'review_reasons': ['human_review_required'],
                'evidence': [{'quote': quote, 'source_ids': [source]}]}
    meeting.update(status='extracted', actions=[item('Send report', 'commitment', 1, 'I will send the report by Friday.')],
                   action_candidates=[item('Book room', 'suggestion', 2, 'We should book the room.'),
                                      item('Cancel budget report', 'cancellation', 3, 'Cancel the budget report.')])
    review.initialize(meeting)
    main.save(meeting)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(meeting), encoding='utf-8')
    print('Seeded isolated synthetic review fixture:', meeting['id'])


if __name__ == '__main__':
    main_check()
