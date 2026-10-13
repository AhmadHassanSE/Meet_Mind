import pytest
from nlp.data import contextualize
from nlp.experiments import validate_config


def test_context_is_causal_label_free_and_never_crosses_meetings():
    rows = [{'id': str(i), 'meeting_id': 'a' if i < 3 else 'b', 'start': i,
             'speaker': 'S', 'text': word, 'label': 'SECRET_GOLD', 'context': 'old'}
            for i, word in enumerate(['first', 'second', 'third', 'fourth'])]
    rebuilt = contextualize(list(reversed(rows)), 2, 'recent_first')
    by_id = {r['id']: r for r in rebuilt}
    assert by_id['2']['context'] == 'same speaker: second same speaker: first'
    assert by_id['3']['context'] == ''
    assert all('SECRET_GOLD' not in r['context'] for r in rebuilt)
    assert rows[2]['context'] == 'old'
    assert [r['id'] for r in rebuilt] == ['3', '2', '1', '0']


def test_target_first_keeps_target_and_newest_context_with_serving_parity(tmp_path):
    transformers = pytest.importorskip('transformers')
    torch = pytest.importorskip('torch')
    from types import SimpleNamespace
    from nlp.encoding import encode_pairs
    from scripts.train_bert import EncodedRows
    from app.bert import DialogueClassifier
    vocab = tmp_path/'vocab.txt'
    vocab.write_text('[PAD]\n[UNK]\n[CLS]\n[SEP]\n[MASK]\nsend\nyes\nother\nspeaker\n:\n')
    tokenizer = transformers.BertTokenizerFast(vocab_file=str(vocab))
    rows = [{'text': 'send '*6, 'context': 'other speaker: yes '*20, 'label': 'inf'}]
    encoded = encode_pairs(tokenizer, [rows[0]['text']], [rows[0]['context']], 12,
                           strategy='target_first', padding=True, return_tensors='pt')
    assert encoded['input_ids'][0, 1:7].tolist() == [tokenizer.convert_tokens_to_ids('send')]*6
    training = EncodedRows(rows, tokenizer, ['inf'], 12, 'target_first')[0]
    assert training['input_ids'] == encoded['input_ids'][0].tolist()
    captured = []
    def model(**tokens):
        captured.append(tokens['input_ids'].tolist())
        return SimpleNamespace(logits=torch.tensor([[1., 0.], [1., 0.]]))
    classifier = DialogueClassifier.__new__(DialogueClassifier)
    classifier.torch, classifier.tokenizer, classifier.model = torch, tokenizer, model
    classifier.labels = ['inf', 'off']
    classifier.metadata = dict(context_turns=1, context_order='recent_first', pair_truncation='target_first',
                               max_length=12, review_threshold=.7, review_margin=.15,
                               label_descriptions={'inf':'Inform', 'off':'Offer'})
    result = classifier.predict([{'id':1, 'speaker':'S', 'text':'yes '*30},
                                 {'id':2, 'speaker':'T', 'text':'send '*6}])
    assert not result[1]['target_text_truncated'] and result[1]['input_truncated']
    assert captured[0][1] == encoded['input_ids'][0].tolist()


def test_optimizer_decay_and_focal_loss_have_finite_gradients():
    torch = pytest.importorskip('torch')
    transformers = pytest.importorskip('transformers')
    from nlp.training import ClassificationLoss, class_weights, optimizer_groups
    model = transformers.BertForSequenceClassification(transformers.BertConfig(
        vocab_size=12, hidden_size=16, num_hidden_layers=2, num_attention_heads=2,
        intermediate_size=32, num_labels=2))
    cfg = dict(learning_rate=2e-5, weight_decay=.01, group_optimizer_parameters=True,
               layer_lr_decay=.9, head_lr_multiplier=2., class_weighting='effective_number',
               class_weight_cap=5.)
    groups = optimizer_groups(model,cfg)
    lookup = {id(p):g for g in groups for p in g['params']}
    assert len(lookup) == len(list(model.parameters()))
    assert lookup[id(model.classifier.weight)]['lr'] == 4e-5
    assert lookup[id(model.bert.embeddings.word_embeddings.weight)]['lr'] < 2e-5
    assert all(lookup[id(p)]['weight_decay']==0 for n,p in model.named_parameters()
               if n.endswith('.bias') or 'LayerNorm.' in n)
    weights = class_weights({'a':1000,'b':2}, ['a','b'], cfg, 'cpu')
    assert weights[1] > weights[0] and weights.max() <= 5
    logits = torch.tensor([[1000.,-1000.],[0.,1.]],requires_grad=True)
    targets = torch.tensor([1,0])
    loss = ClassificationLoss(weights, focal_gamma=1.5)(logits,targets)
    loss.backward()
    assert torch.isfinite(loss) and torch.isfinite(logits.grad).all()
    ce = ClassificationLoss(weights)(logits,targets)
    assert torch.allclose(ce, ClassificationLoss(weights,focal_gamma=0)(logits,targets))


@pytest.mark.parametrize('change', [
    {'class_weighting':'typo'}, {'context_turns':-1}, {'context_turns':True},
    {'context_order':'future'}, {'pair_truncation':'unknown'}, {'max_length':1024},
    {'layer_lr_decay':0}, {'effective_number_beta':1}, {'warmup_ratio':1},
    {'head_lr_multiplier':0}, {'class_weight_cap':0}, {'focal_gamma':-1},
    {'focal_gamma':1.5,'label_smoothing':.1}, {'layer_lr_decay':float('nan')},
])
def test_invalid_training_options_are_rejected(change):
    with pytest.raises(ValueError):
        validate_config({'learning_rate':2e-5, **change})
