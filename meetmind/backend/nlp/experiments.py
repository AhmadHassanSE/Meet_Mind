"""Experiment configuration and validation-only report comparisons."""
import hashlib
import json
import math
from pathlib import Path


def validate_config(cfg):
    for key in ('epochs', 'batch_size', 'max_length', 'gradient_accumulation_steps'):
        value = cfg.get(key, 1)
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise ValueError(f'{key} must be a positive integer')
    if cfg.get('device', 'auto') not in {'auto', 'cpu', 'cuda'}:
        raise ValueError('device must be auto, cpu or cuda')
    if cfg.get('precision', 'fp32') not in {'fp32', 'fp16', 'bf16'}:
        raise ValueError('precision must be fp32, fp16 or bf16')
    if cfg.get('precision', 'fp32') != 'fp32' and cfg.get('device') == 'cpu':
        raise ValueError('This trainer enables mixed precision only on CUDA')
    if not math.isfinite(cfg['learning_rate']) or cfg['learning_rate'] <= 0:
        raise ValueError('learning_rate must be finite and positive')
    if cfg.get('max_validation_examples', 0) and cfg.get('stage') != 'smoke-test':
        raise ValueError('Validation sampling is allowed only for a smoke-test, never model selection')
    if cfg.get('stage') == 'full-training-candidate' and cfg.get('max_train_examples', 0):
        raise ValueError('Full-training candidates must use the complete training split')
    if cfg.get('class_weighting', 'none') not in {'none', 'sqrt_inverse', 'effective_number'}:
        raise ValueError('Unsupported class_weighting')
    if cfg.get('context_order', 'chronological') not in {'chronological', 'recent_first'}:
        raise ValueError('Unsupported context_order')
    if cfg.get('pair_truncation', 'longest_first') not in {'longest_first', 'target_first'}:
        raise ValueError('Unsupported pair_truncation')
    if cfg.get('max_length', 128) > 512:
        raise ValueError('BERT-base supports at most 512 positions')
    if 'context_turns' in cfg:
        value = cfg['context_turns']
        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 16:
            raise ValueError('context_turns must be an integer from 0 to 16')
    for key, default, low, high in [('layer_lr_decay', 1., 0., 1.),
                                  ('effective_number_beta', .999, 0., 1.),
                                  ('warmup_ratio', .1, 0., 1.),
                                  ('label_smoothing', 0., 0., 1.)]:
        value = cfg.get(key, default)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
            raise ValueError(f'{key} must be finite')
        if not low <= value <= high or (key in {'layer_lr_decay', 'effective_number_beta'} and value == 0):
            raise ValueError(f'Invalid {key}')
        if key in {'effective_number_beta', 'warmup_ratio', 'label_smoothing'} and value == 1:
            raise ValueError(f'{key} must be less than 1')
    for key, default, minimum in [('head_lr_multiplier', 1., 0.), ('focal_gamma', 0., 0.),
                                  ('class_weight_cap', None, 0.)]:
        value = cfg.get(key, default)
        if value is None and key == 'class_weight_cap':
            continue
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value < minimum:
            raise ValueError(f'Invalid {key}')
        if key != 'focal_gamma' and value == 0:
            raise ValueError(f'{key} must be positive')
    if cfg.get('focal_gamma', 0) and cfg.get('label_smoothing', 0):
        raise ValueError('Focal loss and label smoothing cannot be combined in this trainer')


def comparison(reports, reference=None):
    """Rank verified predictions on identical validation rows, never test results."""
    from nlp.metrics import classification_metrics
    candidates, signatures, datasets = [], set(), set()
    for filename in reports:
        path = Path(filename)
        report = json.loads(path.read_text(encoding='utf-8'))
        if report['split'] != 'validation':
            raise ValueError('Only validation reports may guide comparison/selection')
        if report['checkpoint_stage'] == 'smoke-test':
            raise ValueError('Smoke tests cannot be ranked as trained candidates')
        predictions = report['predictions']
        if not predictions or len({p['id'] for p in predictions}) != len(predictions):
            raise ValueError('Missing or duplicate prediction IDs')
        labels = report['scores']['bert']['label_order']
        ordered = sorted(predictions, key=lambda p: p['id'])
        if any(p['gold'] not in labels or p['predicted'] not in labels for p in predictions):
            raise ValueError('Prediction labels differ from ontology')
        signature = hashlib.sha256(json.dumps([(p['id'], p['gold']) for p in ordered]).encode()).hexdigest()
        signatures.add((signature, tuple(labels)))
        datasets.add(report['dataset_manifest_sha256'])
        scores = classification_metrics([p['gold'] for p in predictions], [p['predicted'] for p in predictions], labels)
        recorded = report['scores']['bert']
        for key in ('accuracy', 'macro_f1', 'weighted_f1', 'examples'):
            if not math.isclose(scores[key], recorded[key], rel_tol=1e-8, abs_tol=1e-8):
                raise ValueError('Recorded metrics do not match evaluation predictions')
        candidates.append({'report': str(path), 'model_name': report.get('model_name'),
                           'checkpoint_stage': report['checkpoint_stage'],
                           'model_weights_sha256': report['model_weights_sha256'],
                           'train_examples': report['train_examples'],
                           'max_length': report.get('max_length'),
                           'scores': {k: scores[k] for k in ('accuracy', 'macro_f1', 'weighted_f1', 'examples')},
                           'per_class': scores['per_class']})
    if not candidates or len(datasets) != 1 or len(signatures) != 1:
        raise ValueError('Compare only identical dataset versions, validation IDs, gold labels and ontology')
    candidates.sort(key=lambda x: (-x['scores']['macro_f1'], x['report']))
    summary = {'selection_metric': 'validation macro F1', 'test_used_for_selection': False,
               'dataset_manifest_sha256': next(iter(datasets)),
               'validation_rows_sha256': next(iter(signatures))[0],
               'ranked_candidates': candidates, 'selected_report': candidates[0]['report'],
               'limitations': ['Dialogue-act results do not measure commitment extraction accuracy.',
                              'Different training budgets and sequence lengths are reported; this is not an architecture-only ablation.',
                              'Validation is used for selection, not an independent final performance estimate.']}
    if reference is not None:
        matches = [c for c in candidates if Path(c['report']).resolve() == Path(reference).resolve()]
        if len(matches) != 1:
            raise ValueError('Reference report must be included exactly once')
        summary['reference_report'] = matches[0]['report']
        summary['selected_macro_f1_gain'] = candidates[0]['scores']['macro_f1'] - matches[0]['scores']['macro_f1']
    return summary
