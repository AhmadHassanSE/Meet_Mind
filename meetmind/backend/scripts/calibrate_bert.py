"""Fit temperature scaling for the frozen BERT checkpoint and measure calibration.

The temperature is fitted on **validation only** (negative log-likelihood). Expected
calibration error (ECE, 15 equal-width bins) and reliability bins are reported before
and after scaling on validation and on the held-out test split. Test is used only to
report calibration, never to choose the temperature or the model.
"""
import argparse
import json
from pathlib import Path

import numpy as np
from scipy.optimize import minimize_scalar

from app.bert import DialogueClassifier
from nlp.data import contextualize, load_split, sha256, write_json
from nlp.encoding import encode_pairs

BINS = 15


def logits_for(classifier, rows, batch_size):
    import torch
    torch.set_num_threads(4)
    meta, out = classifier.metadata, []
    with torch.inference_mode():
        for offset in range(0, len(rows), batch_size):
            batch = rows[offset:offset + batch_size]
            tokens = encode_pairs(classifier.tokenizer, [r['text'] for r in batch], [r['context'] for r in batch],
                                  meta['max_length'], strategy=meta.get('pair_truncation', 'longest_first'),
                                  padding=True, return_tensors='pt')
            out.append(classifier.model(**tokens).logits.float().numpy())
    return np.concatenate(out)


def softmax(logits, temperature):
    z = logits / temperature
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def nll(logits, gold, temperature):
    return float(-np.log(softmax(logits, temperature)[np.arange(len(gold)), gold] + 1e-12).mean())


def reliability(logits, gold, temperature):
    probs = softmax(logits, temperature)
    confidence, correct = probs.max(axis=1), probs.argmax(axis=1) == gold
    bins, ece = [], 0.0
    for low in np.linspace(0, 1, BINS, endpoint=False):
        mask = (confidence > low) & (confidence <= low + 1 / BINS)
        if mask.any():
            gap = abs(correct[mask].mean() - confidence[mask].mean())
            ece += mask.mean() * gap
            bins.append({'low': round(float(low), 4), 'count': int(mask.sum()),
                         'confidence': float(confidence[mask].mean()), 'accuracy': float(correct[mask].mean())})
    return {'ece': float(ece), 'nll': nll(logits, gold, temperature), 'accuracy': float(correct.mean()), 'bins': bins}


def svg(results, path):
    """Reliability diagram (validation and test, before/after) as a dependency-free SVG."""
    size, pad, panels = 260, 40, [('validation', 'before'), ('validation', 'after'), ('test', 'before'), ('test', 'after')]
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{len(panels) * (size + pad) + pad}" height="{size + 2 * pad + 20}" '
             'font-family="sans-serif" font-size="11">']
    for index, (split, stage) in enumerate(panels):
        x0, data = pad + index * (size + pad), results[split][stage]
        parts.append(f'<rect x="{x0}" y="{pad}" width="{size}" height="{size}" fill="none" stroke="#888"/>')
        parts.append(f'<line x1="{x0}" y1="{pad + size}" x2="{x0 + size}" y2="{pad}" stroke="#bbb" stroke-dasharray="4"/>')
        width = size / BINS
        for b in data['bins']:
            h = b['accuracy'] * size
            parts.append(f'<rect x="{x0 + b["low"] * size:.1f}" y="{pad + size - h:.1f}" width="{width - 1:.1f}" '
                         f'height="{h:.1f}" fill="#2f7d6d" opacity="0.8"/>')
        parts.append(f'<text x="{x0}" y="{pad - 8}">{split} {stage} scaling: ECE {data["ece"]:.3f}</text>')
        parts.append(f'<text x="{x0}" y="{pad + size + 16}">confidence →  (bars: accuracy)</text>')
    parts.append('</svg>')
    Path(path).write_text('\n'.join(parts), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--data', type=Path, default=Path('data/ami-da-v1'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--batch-size', type=int, default=32)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Choose a new output directory to preserve earlier evidence')
    classifier = DialogueClassifier(args.checkpoint)
    manifest = load_split(args.data, 'train')[1]
    labels = sorted(manifest['labels'])
    data = {}
    for split in ('validation', 'test'):
        rows, _ = load_split(args.data, split)
        meta = classifier.metadata
        # Same inputs as scripts/evaluate_bert.py: rebuild context only if the checkpoint used another setting.
        if meta['context_turns'] != manifest['context_turns'] or meta.get('context_order', 'chronological') != 'chronological':
            rows = contextualize(rows, meta['context_turns'], meta.get('context_order', 'chronological'))
        data[split] = (logits_for(classifier, rows, args.batch_size), np.array([labels.index(r['label']) for r in rows]))
        print(split, 'logits ready', len(rows), flush=True)
    logits, gold = data['validation']
    fitted = minimize_scalar(lambda t: nll(logits, gold, t), bounds=(0.05, 10), method='bounded')
    temperature = float(fitted.x)
    results = {split: {'before': reliability(l, g, 1.0), 'after': reliability(l, g, temperature)} for split, (l, g) in data.items()}
    args.output.mkdir(parents=True)
    calibration = {'method': 'temperature scaling', 'temperature': temperature, 'fitted_on': 'validation',
                   'bins': BINS, 'model_weights_sha256': sha256(args.checkpoint / 'model.safetensors'),
                   'dataset_manifest_sha256': sha256(args.data / 'manifest.json')}
    write_json(args.output / 'calibration.json', calibration)
    write_json(args.output / 'calibration_metrics.json', {**calibration, 'results': results})
    svg(results, args.output / 'reliability.svg')
    for split in results:
        print(split, {stage: {k: round(v, 4) for k, v in results[split][stage].items() if k != 'bins'} for stage in ('before', 'after')})
    print('temperature', round(temperature, 4))


if __name__ == '__main__':
    main()
