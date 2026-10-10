import json
from pathlib import Path
import sys
import pytest
from nlp.data import sha256, write_json
from nlp.experiments import comparison, validate_config
from nlp.metrics import classification_metrics


def report(tmp_path, name, predicted, **changes):
    gold = ['inf', 'off']
    scores = classification_metrics(gold, predicted, gold)
    value = {'split': 'validation', 'checkpoint_stage': 'full-training-candidate',
             'dataset_manifest_sha256': 'same-dataset', 'model_weights_sha256': name,
             'train_examples': 100, 'model_name': name, 'scores': {'bert': scores},
             'predictions': [{'id': str(i), 'gold': g, 'predicted': p} for i, (g, p) in enumerate(zip(gold, predicted))]}
    value.update(changes)
    path = tmp_path / f'{name}.json'
    write_json(path, value)
    return path


def test_comparison_uses_same_validation_rows_and_reports_gain(tmp_path):
    pilot = report(tmp_path, 'pilot', ['inf', 'inf'], train_examples=24)
    base = report(tmp_path, 'base', ['inf', 'off'])
    result = comparison([pilot, base], reference=pilot)
    assert result['selected_report'] == str(base)
    assert result['selected_macro_f1_gain'] > 0
    assert not result['test_used_for_selection']
    assert result['ranked_candidates'][0]['train_examples'] == 100


@pytest.mark.parametrize('change', [
    {'split': 'test'}, {'checkpoint_stage': 'smoke-test'},
    {'dataset_manifest_sha256': 'other'},
    {'predictions': [{'id': 'different', 'gold': 'inf', 'predicted': 'inf'}]},
    {'predictions': [{'id': 'same', 'gold': 'inf', 'predicted': 'inf'}] * 2},
])
def test_invalid_comparisons_fail(tmp_path, change):
    pilot = report(tmp_path, 'pilot', ['inf', 'inf'])
    other = report(tmp_path, 'other', ['inf', 'off'], **change)
    with pytest.raises(ValueError):
        comparison([pilot, other])


def test_config_rejects_sampled_full_training_and_validation():
    cfg = {'learning_rate': 2e-5, 'stage': 'full-training-candidate', 'max_train_examples': 10}
    with pytest.raises(ValueError): validate_config(cfg)
    with pytest.raises(ValueError): validate_config({'learning_rate': 2e-5, 'max_validation_examples': 10})
    with pytest.raises(ValueError): validate_config({'learning_rate': 2e-5, 'device': 'cpu', 'precision': 'fp16'})


def test_interrupted_training_resumes_exact_weights_without_test_access(tmp_path, monkeypatch):
    torch = pytest.importorskip('torch')
    transformers = pytest.importorskip('transformers')
    from scripts import train_bert
    model_dir = tmp_path / 'pretrained'
    model_dir.mkdir()
    vocabulary = model_dir / 'vocab.txt'
    vocabulary.write_text('[PAD]\n[UNK]\n[CLS]\n[SEP]\n[MASK]\ni\nwill\nsend\nreport\nyes\n', encoding='utf-8')
    tokenizer = transformers.BertTokenizerFast(vocab_file=str(vocabulary))
    tokenizer.save_pretrained(model_dir)
    torch.manual_seed(7)
    transformers.BertForSequenceClassification(transformers.BertConfig(
        vocab_size=10, hidden_size=16, num_hidden_layers=1, num_attention_heads=2,
        intermediate_size=32, num_labels=2)).save_pretrained(model_dir, safe_serialization=True)
    data = tmp_path / 'data'
    data.mkdir()
    manifest = {'labels': {'inf': 'Inform', 'off': 'Offer'}, 'context_turns': 0, 'splits': {}}
    for split, meeting, count in [('train', 'TR0001a', 8), ('validation', 'VA0001a', 4), ('test', 'TE0001a', 2)]:
        path = data / f'{split}.jsonl'
        rows = [{'id': f'{split}-{i}', 'text': 'I will send report' if i % 2 else 'yes',
                 'context': '', 'label': 'off' if i % 2 else 'inf', 'meeting_id': meeting} for i in range(count)]
        path.write_text('\n'.join(json.dumps(r) for r in rows), encoding='utf-8')
        manifest['splits'][split] = {'meetings': [meeting], 'sha256': sha256(path)}
    write_json(data / 'manifest.json', manifest)
    # Corrupt the final test file: training must never try to read or verify it.
    (data / 'test.jsonl').write_text('DO NOT LOAD FINAL TEST', encoding='utf-8')
    cfg = {'model': str(model_dir), 'revision': 'main', 'data': str(data),
           'stage': 'smoke-test', 'seed': 42, 'max_length': 16, 'batch_size': 2,
           'eval_batch_size': 2, 'gradient_accumulation_steps': 3, 'epochs': 2,
           'learning_rate': 1e-3, 'patience': 5, 'cpu_threads': 1, 'device': 'cpu',
           'precision': 'fp32', 'save_epoch_state': True}
    config = tmp_path / 'config.json'
    def invoke(output, resume=False):
        write_json(config, {**cfg, 'output': str(output)})
        monkeypatch.setattr(sys, 'argv', ['train', '--config', str(config)] + (['--resume'] if resume else []))
        train_bert.main()
    uninterrupted = tmp_path / 'uninterrupted'
    invoke(uninterrupted)
    original_predict = train_bert.predict
    calls = 0
    def interrupt(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError('Simulated disconnect')
        return original_predict(*args)
    monkeypatch.setattr(train_bert, 'predict', interrupt)
    resumed = tmp_path / 'resumed'
    with pytest.raises(RuntimeError, match='disconnect'): invoke(resumed)
    monkeypatch.setattr(train_bert, 'predict', original_predict)
    invoke(resumed, resume=True)
    assert sha256(resumed / 'epoch-0002/model.safetensors') == sha256(uninterrupted / 'epoch-0002/model.safetensors')
    assert json.loads((resumed / 'status.json').read_text())['status'] == 'completed'
    with pytest.raises(ValueError, match='already finished'): invoke(resumed, resume=True)
