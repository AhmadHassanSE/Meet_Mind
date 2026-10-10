"""Evaluate a frozen checkpoint against baselines on validation or held-out test."""
import argparse
from collections import Counter
import json
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline

from app.bert import DialogueClassifier
from nlp.data import load_split, sha256, training_sample, write_json
from nlp.metrics import classification_metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--data', type=Path, default=Path('data/ami-da-v1'))
    parser.add_argument('--split', choices=['validation', 'test'], default='validation')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Preserve the existing evaluation: choose a new output file')
    train, manifest = load_split(args.data, 'train')
    rows, _ = load_split(args.data, args.split)
    classifier = DialogueClassifier(args.checkpoint)
    manifest_hash = sha256(args.data / 'manifest.json')
    if classifier.metadata['dataset_manifest_sha256'] != manifest_hash:
        raise ValueError('Checkpoint was trained with a different dataset manifest')
    cfg = json.loads((args.checkpoint.parent / 'run_config.json').read_text(encoding='utf-8'))
    train = training_sample(train, cfg.get('max_train_examples', 0), cfg['seed'])
    labels = sorted(manifest['labels'])
    gold = [r['label'] for r in rows]
    majority = Counter(r['label'] for r in train).most_common(1)[0][0]
    baseline = make_pipeline(TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_features=60000, sublinear_tf=True),
                             LogisticRegression(C=1., max_iter=1000, class_weight='balanced', random_state=cfg['seed']))
    def texts(items):
        return [r['text'] + ' [CONTEXT] ' + r['context'] for r in items]
    baseline.fit(texts(train), [r['label'] for r in train])
    baseline_labels = baseline.predict(texts(rows)).tolist()
    predictions = []
    # Prepared context must remain exactly as in training, including pilot sampling.
    import torch
    torch.set_num_threads(cfg.get('cpu_threads', 4))
    with torch.inference_mode():
        for offset in range(0, len(rows), 64):
            batch = rows[offset:offset + 64]
            tokens = classifier.tokenizer([r['text'] for r in batch], [r['context'] for r in batch],
                         padding=True, truncation='longest_first', max_length=classifier.metadata['max_length'], return_tensors='pt')
            probs = classifier.model(**tokens).logits.softmax(-1).tolist()
            for row, prob in zip(batch, probs):
                label = labels[max(range(len(prob)), key=lambda i: prob[i])]
                predictions.append({'id': row['id'], 'meeting_id': row['meeting_id'],
                                    'gold': row['label'], 'predicted': label, 'score': max(prob)})
    scores = {'majority': classification_metrics(gold, [majority] * len(gold), labels),
              'tfidf_logistic': classification_metrics(gold, baseline_labels, labels),
              'bert': classification_metrics(gold, [p['predicted'] for p in predictions], labels)}
    result = {'split': args.split, 'checkpoint': str(args.checkpoint),
              'checkpoint_stage': classifier.metadata['checkpoint_stage'],
              'model_name': classifier.metadata['model_name'], 'model_revision': classifier.metadata['model_revision'],
              'max_length': classifier.metadata['max_length'],
              'dataset_manifest_sha256': manifest_hash, 'model_weights_sha256': sha256(args.checkpoint / 'model.safetensors'),
              'train_examples': len(train), 'selection_metric': 'validation macro F1 only',
              'scores': scores, 'predictions': predictions,
              'limitations': ['Dialogue-act metrics are not action-item extraction metrics.',
                              'Gold AMI dialogue-act boundaries; uploaded speaker turns/ASR differ.',
                              'Custom session-disjoint split; not comparable to published standard-split numbers.',
                              'Uncalibrated scores; no guaranteed best model claim.']}
    write_json(args.output, result)
    print(json.dumps({name: {k: v for k, v in score.items() if k in ['accuracy', 'macro_f1', 'weighted_f1', 'examples']}
                      for name, score in scores.items()}, indent=2))


if __name__ == '__main__':
    main()
