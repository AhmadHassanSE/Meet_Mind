"""Keyword rule baseline for AMI dialogue acts.

Rules follow surface cues described in the AMI dialogue-act manual. They were
written once, before any test-split inspection, and are not tuned on data. The
first matching rule wins; anything unmatched is labelled ``inf``.
"""
import re

BACKCHANNEL = {'yeah', 'yes', 'yep', 'yup', 'mm', 'mm-hmm', 'mm-mm', 'uh-huh', 'hmm', 'okay', 'ok', 'right', 'sure',
               'alright', 'uh huh', 'aha', 'ah'}
STALL = {'um', 'uh', 'so', 'well', 'and', 'but', 'okay so', 'right so', 'um so', 'uh so'}
RULES = [
    ('el.sug', r'\b(should we|shall we|do we want to|what if we|could we|can we)\b.*\?'),
    ('el.ass', r"(\b(do you agree|don't you think|do you think so|isn't it|aren't they|is that okay|is that alright)\b.*\?|\bright\?$)"),
    ('el.und', r"\b(what do you mean|sorry\?|pardon|what was that|can you repeat)\b"),
    ('el.inf', r'\?'),
    ('off', r"\b(i'll|i will|i can|let me|i'm going to|i am going to|i could)\b"),
    ('sug', r"\b(we should|you should|let's|let us|we could|maybe we|how about|why don't we|i suggest|we need to|we have to)\b"),
    ('ass', r"\b(i think|i agree|i don't think|i guess|i reckon|probably|i'm not sure|i believe|i feel)\b"),
    ('und', r"\b(you mean|so you're saying|so you mean)\b"),
    ('be.neg', r"^(sorry|oh no|damn|oops)\b"),
    ('be.pos', r"^(good|great|nice|cool|excellent|thanks|thank you|cheers|brilliant)\b"),
]
COMPILED = [(label, re.compile(pattern)) for label, pattern in RULES]


def predict(text):
    """Return one AMI dialogue-act label for an utterance."""
    clean = re.sub(r'\s+', ' ', text.strip().lower())
    bare = clean.strip(' .,!')
    if not bare:
        return 'fra'
    if bare in BACKCHANNEL:
        return 'bck'
    if bare in STALL:
        return 'stl'
    if clean.endswith('-') or (len(bare.split()) <= 2 and not clean.endswith(('.', '?', '!'))):
        return 'fra'
    for label, pattern in COMPILED:
        if pattern.search(clean):
            return label
    return 'inf'
