import pytest

from nlp import rules


@pytest.mark.parametrize('text,label', [
    ('Yeah.', 'bck'), ('Mm-hmm', 'bck'), ('Um', 'stl'), ('So the', 'fra'), ('and then we-', 'fra'),
    ('Should we use a rubber case?', 'el.sug'), ('That works, right?', 'el.ass'),
    ('What do you mean by that', 'el.und'), ('How much does it cost?', 'el.inf'),
    ("I'll send the drawings after lunch.", 'off'), ("Let's go with the yellow one.", 'sug'),
    ('I think the battery is too big.', 'ass'), ('So you mean the casing.', 'und'),
    ('Great, thanks.', 'be.pos'), ('Sorry about that.', 'be.neg'),
    ('The remote has twelve buttons.', 'inf'), ('', 'fra'),
])
def test_rule_labels(text, label):
    assert rules.predict(text) == label


def test_rules_only_emit_ami_labels():
    ami = {'bck', 'stl', 'fra', 'inf', 'el.inf', 'sug', 'el.sug', 'off', 'el.und', 'ass', 'el.ass', 'und',
           'be.pos', 'be.neg', 'oth'}
    assert {label for label, _ in rules.RULES} | {'bck', 'stl', 'fra', 'inf'} <= ami
