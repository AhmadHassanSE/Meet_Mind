"""Conservative source-language rules, not an Urdu parser or trained NER model."""
import re
import unicodedata
from functools import lru_cache

STOP = set('i will the a an to by on in of and is are send not do can could should we you it this that main mein mai me hum aap tum woh wo yeh ye hai hain ho hoon hun kar karo karna karein karen karunga karungi karega karegi karenge ga gi ge ko ka ki ke tak se aur nahi nahin nai mat chahiye shayad sakta sakti sakte dunga dungi doon dun diya dena bhej bhejna bhejunga bhejungi kal aaj'.split())
STOP.update('میں ہم آپ تم وہ یہ ہے ہیں ہوں ہو کو کا کی کے تک سے اور نہیں مت گا گی گے کروں کریں کرنا کر بھیج دوں دو دیں کل آج'.split())
NEGATIVE = re.compile(r"(?<!\w)(?:not|never|won['’]?t|can['’]?t|cannot|don['’]?t|no longer|nahi|nahin|nai|nhi|mat|نہیں|نہ|مت)(?!\w)",re.I)
CANCEL = re.compile(r'(?<!\w)(?:cancel|cancelled|canceled|withdraw|scrap|منسوخ|کینسل)(?!\w)',re.I)
FUTURE = re.compile(r'(?<!\w)(?:karunga|karungi|krunga|krungi|karoonga|karoongi|karenge|karega|karegi|bhejunga|bhejungi|bhejoonga|bhejoongi|dunga|dungi|doonga|doongi|ga|gi|ge|گا|گی|گے|وعدہ)(?!\w)',re.I)
UNCERTAIN = re.compile(r'(?<!\w)(?:could|might|should|maybe|perhaps|if|chahiye|shayad|sakta|sakti|sakte|cha[h]?iye|agar|چاہیے|چاہیئے|شاید|سکتا|سکتی|سکتے|اگر)(?!\w)',re.I)
FIRST = re.compile(r'(?:^|[،,])\s*(?:i|main|mein|mai|میں)(?!\w)',re.I)
AMBIGUOUS = {'main','mein','mai','hum','aap','tum','woh','wo','yeh','ye','team','unknown','none','میں','ہم','آپ','تم','وہ','یہ'}
DATE = re.compile(r'(?<!\w)(?:(?:(?:دوپہر|صبح|شام|رات)\s+)?(?:ایک|دو|تین|چار|پانچ|چھ|سات|آٹھ|نو|دس|گیارہ|بارہ|[0-9۰-۹]+)\s+بجے(?:\s+تک)?|(?:دوپہر|صبح|شام|رات)\s+تک|(?:(?:aglay|agle|agli|next|this|اگلے|اگلی|آئندہ|اس|اسی)\s+)?(?:kal|aaj|parson|parso|jumma|juma|peer|mangal|budh|jumerat|hafta|itwar|monday|tuesday|wednesday|thursday|friday|saturday|sunday|week|month|کل|آج|پرسوں|پیر|منگل|بدھ|جمعرات|جمعہ|ہفتے|ہفتہ|اتوار|مہینے)(?:\s+(?:subah|shaam|sham|raat|dopahar|صبح|شام|رات|دوپہر))?(?:\s+(?:tak|ko|تک|کو))?)(?!\w)',re.I)


@lru_cache(maxsize=1)
def nlp():
    import spacy
    pipeline=spacy.blank('xx')
    pipeline.add_pipe('sentencizer',config={'punct_chars':['.','!','?','۔','؟']})
    return pipeline


def terms(text):
    # Normalize only comparison keys. Evidence and source offsets stay untouched.
    normalized=unicodedata.normalize('NFKC',text).lower().translate(str.maketrans({'ي':'ی','ك':'ک'}))
    return {w for w in re.findall(r'[^\W_]+',normalized) if len(w)>1 and w not in STOP}


def dates(text):
    return [{'text':m[0],'start':m.start(),'end':m.end(),'method':'urdu_roman_rule'} for m in DATE.finditer(text)]


def kind(quote, proposed):
    if NEGATIVE.search(quote) or CANCEL.search(quote):
        return 'cancellation',['negated_or_cancelled_source']
    if proposed=='commitment':
        if quote.rstrip().endswith(('?','؟')):return 'request',['non_committal_language']
        if UNCERTAIN.search(quote):return 'suggestion',['non_committal_language']
        if not FUTURE.search(quote) and not re.search(r"\bwill\b|\bi['’]ll\b|\bpromise\b|\bagree\b",quote,re.I):
            return 'suggestion',['explicit_commitment_not_found']
    return proposed,[]


def owner(proposal,unit):
    if FIRST.search(proposal.quote) and unit['speaker'] and proposal.kind=='commitment' and not NEGATIVE.search(proposal.quote) and not CANCEL.search(proposal.quote):
        return unit['speaker'],'speaker',['urdu_owner_rule_requires_review']
    candidate=(proposal.owner or '').strip()
    if candidate and candidate.lower() not in AMBIGUOUS:
        # Merely naming a recipient later in the sentence does not assign them work.
        match=re.match(r'\s*('+re.escape(candidate)+r')(?!\w)',proposal.quote,re.I)
        if match:return match[1],'explicit_name',['urdu_owner_rule_requires_review']
    return None,'unresolved',['owner_missing_or_ambiguous']
