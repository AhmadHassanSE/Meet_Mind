from app import artifact_graph as g, artifacts, auth

CONTEXT = {'meeting_title': 'Release planning', 'meeting_date': 'Sunday 15 November 2026', 'task': 'Send the report',
           'owner': 'Sara', 'deadline_wording': 'by Friday', 'deadline_date': 'Friday 20 November 2026', 'priority': 'normal',
           'sender_name': 'Ayesha', 'evidence': []}


def email(subject, body):
    return {'subject': subject, 'body': body}


def test_a_faithful_draft_has_no_warnings():
    draft = email('Report due Friday 20 November', 'Hi Sara,\n\nThanks for joining Release planning on Sunday 15 November 2026. '
                  "You'll send the report by Friday 20 November 2026.\n\nThanks,\nAyesha")
    assert g.check_facts(draft, CONTEXT) == []


def test_invented_and_misused_dates_are_flagged():
    warnings = g.check_facts(email('Report due 22 November', 'Please send it by November 22nd.'), CONTEXT)
    assert any('subject mentions 22 November' in w for w in warnings)
    assert any('body mentions 22 November' in w for w in warnings)
    no_deadline = {**CONTEXT, 'deadline_wording': None, 'deadline_date': None}
    warnings = g.check_facts(email('Demo room due Sunday 15 November', 'Please book it.'), no_deadline)
    assert 'The subject uses the meeting date as if it were a deadline.' in warnings
    assert 'The subject implies a deadline, but none was agreed.' in warnings


def test_quotes_must_be_verbatim_and_priority_must_match():
    context = {**CONTEXT, 'evidence': [{'quote': "Sara, can you update the board tomorrow? It's urgent.", 'speaker': 'Ayesha'}]}
    altered = email('Board', 'As discussed: "Sara, can you update the board tomorrow. It\'s urgent."')
    assert any('word for word' in w for w in g.check_facts(altered, context))
    exact = email('Board', 'As discussed: "Sara, can you update the board tomorrow? It\'s urgent."')
    assert not any('word for word' in w for w in g.check_facts(exact, context))
    # "urgent" inside the quoted evidence does not count as the draft saying so.
    assert any('high priority, but the draft' in w for w in g.check_facts(exact, {**context, 'priority': 'high'}))
    assert any('was not marked high priority' in w for w in g.check_facts(email('Send the report', 'Due: Friday.\n\nPriority: high.'), CONTEXT))


def test_missing_urgency_and_placeholders_are_flagged():
    urgent = {**CONTEXT, 'priority': 'high'}
    assert any('high priority' in w for w in g.check_facts(email('Report', 'Please send it.'), urgent))
    assert g.check_facts(email('Report', 'This is urgent: please send it.'), urgent) == []
    assert any('placeholder' in w for w in g.check_facts(email('Report', 'Thanks,\n[Your Name]'), CONTEXT))


def test_quoted_evidence_line_is_restored_verbatim(monkeypatch):
    import asyncio
    import json
    context = {**CONTEXT, 'evidence': [{'quote': "Sara, can you update the board tomorrow? It's urgent.", 'speaker': 'Ayesha'}]}

    async def reworded(*args):
        return json.dumps({'subject': 'Board update', 'body': 'Hi Sara,\\n\\nAs discussed: "Sara, update the board tomorrow."\\n\\nThanks,\\nAyesha'})
    monkeypatch.setattr(g, 'ollama_draft', reworded)
    draft, steps, warnings = asyncio.run(g.generate(context, 'http://ollama', 'fixture'))
    assert 'As discussed: "Sara, can you update the board tomorrow? It\'s urgent."' in draft['body']
    assert '\\n' not in draft['body'] and not any('word for word' in w for w in warnings)


def test_ticket_description_comes_only_from_reviewed_facts():
    body = g.ticket_body({**CONTEXT, 'evidence': [{'quote': 'I will send the report by Friday.', 'speaker': 'Sara'}]})
    assert body.split('\n\n') == ['Agreed in Release planning (Sunday 15 November 2026).', 'Owner: Sara.',
                                  'Due: Friday 20 November 2026.', 'Evidence: "I will send the report by Friday." (Sara)']
    urgent = g.ticket_body({**CONTEXT, 'owner': None, 'deadline_date': None, 'deadline_wording': None, 'priority': 'high'})
    assert 'Owner: not assigned.' in urgent and 'Due: no deadline agreed.' in urgent and 'Priority: high.' in urgent


def test_drafting_context_holds_reviewed_facts_and_never_recipients():
    meeting = {'title': 'Release planning', 'created_at': '2026-11-15T09:00:00+00:00'}
    source = {'task': 'Send the report', 'owner': 'Sara', 'deadline': 'by Friday', 'deadline_normalized': '2026-11-20',
              'priority': 'high', 'evidence': [{'quote': 'I will send the report by Friday.', 'speaker': 'Sara'}]}
    user = auth.User('u1', 'ayesha@example.com', 'Ayesha', 'organizer', False)
    context = artifacts.draft_context(meeting, source, user)
    assert context['deadline_date'] == 'Friday 20 November 2026' and context['meeting_date'] == 'Sunday 15 November 2026'
    assert context['sender_name'] == 'Ayesha' and context['priority'] == 'high'
    assert context['evidence'] == [{'speaker': 'Sara', 'quote': 'I will send the report by Friday.'}]
    assert 'to' not in context and 'ayesha@example.com' not in str(context)
