"""Fine-tune BERT; choose checkpoints by validation macro F1, never test scores."""
import argparse
from collections import Counter
import json
import math
import os
from pathlib import Path
import platform
import random
import shutil
import time

import numpy as np
import torch
from torch.utils.data import DataLoader, Dataset
from transformers import AutoConfig, AutoModelForSequenceClassification, AutoTokenizer, get_linear_schedule_with_warmup

from nlp.data import contextualize, load_split, sha256, training_sample, write_json
from nlp.encoding import encode_pairs
from nlp.training import ClassificationLoss, class_weights, optimizer_groups
from nlp.metrics import classification_metrics
from nlp.experiments import validate_config


class EncodedRows(Dataset):
    def __init__(self, rows, tokenizer, labels, max_length, strategy='longest_first'):
        self.encodings = encode_pairs(tokenizer, [r['text'] for r in rows], [r['context'] for r in rows],
                                      max_length, strategy=strategy)
        self.targets = [labels.index(r['label']) for r in rows]

    def __len__(self):
        return len(self.targets)

    def __getitem__(self, index):
        return {**{k: v[index] for k, v in self.encodings.items()}, 'labels': self.targets[index]}


def predict(model, loader, device):
    model.eval()
    gold, predicted = [], []
    with torch.inference_mode():
        for batch in loader:
            targets = batch.pop('labels')
            logits = model(**{k: v.to(device) for k, v in batch.items()}).logits
            gold.extend(targets.tolist())
            predicted.extend(logits.argmax(-1).cpu().tolist())
    return gold, predicted


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--resume', action='store_true', help='Resume the latest completed epoch with optimizer/RNG state')
    args = parser.parse_args()
    cfg = json.loads(args.config.read_text(encoding='utf-8'))
    os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')
    validate_config(cfg)
    output = Path(cfg['output'])
    if not args.resume and output.exists() and any(output.iterdir()):
        raise ValueError('Output exists: choose a new run directory to preserve experiment evidence')
    requested_device = cfg.get('device', 'auto')
    if requested_device == 'cuda' and not torch.cuda.is_available():
        raise ValueError('CUDA GPU required for this configuration. Enable a Colab/Kaggle GPU runtime.')
    device = torch.device('cuda' if torch.cuda.is_available() and requested_device != 'cpu' else 'cpu')
    precision = cfg.get('precision', 'fp32')
    if precision != 'fp32' and device.type != 'cuda':
        raise ValueError('Mixed-precision training requires CUDA in this trainer')
    if precision == 'bf16' and not torch.cuda.is_bf16_supported():
        raise ValueError('This GPU does not support bf16; choose fp16 or fp32')
    train, manifest = load_split(cfg['data'], 'train')
    validation, other = load_split(cfg['data'], 'validation')
    if manifest != other:
        raise ValueError('Dataset manifest changed during loading')
    labels = sorted(manifest['labels'])
    context_turns = cfg.get('context_turns', manifest['context_turns'])
    if 'context_turns' in cfg or 'context_order' in cfg:
        train = contextualize(train, context_turns, cfg.get('context_order', 'chronological'))
        validation = contextualize(validation, context_turns, cfg.get('context_order', 'chronological'))
    seed = cfg['seed']
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
    torch.set_num_threads(cfg.get('cpu_threads', 4))
    torch.use_deterministic_algorithms(True, warn_only=True)
    if cfg.get('max_validation_examples', 0):
        validation = training_sample(validation, cfg['max_validation_examples'], seed)
    train = training_sample(train, cfg.get('max_train_examples', 0), seed)
    if set(r['label'] for r in train) != set(labels):
        raise ValueError('Training sample lacks an ontology class')
    pretrained_config = AutoConfig.from_pretrained(cfg['model'], revision=cfg.get('revision', 'main'))
    if pretrained_config.model_type != 'bert':
        raise ValueError('This pipeline requires a BERT checkpoint')
    if cfg.get('stage') == 'full-training-candidate' and (pretrained_config.num_hidden_layers != 12 or pretrained_config.hidden_size != 768):
        raise ValueError('Full BERT-base configuration requires 12 layers and hidden size 768')
    revision = getattr(pretrained_config, '_commit_hash', None) or cfg.get('revision', 'main')
    resume_state, resume_dir = None, None
    if args.resume:
        checkpoints = sorted(p for p in output.glob('epoch-*') if (p / 'trainer-state.pt').is_file() and (p / 'complete.json').is_file())
        if not checkpoints:
            raise ValueError('No complete epoch checkpoint is available to resume')
        resume_dir = checkpoints[-1]
        saved = json.loads((output / 'run_config.json').read_text(encoding='utf-8'))
        if any(saved.get(k) != v for k, v in cfg.items()) or saved['dataset_manifest_sha256'] != sha256(Path(cfg['data']) / 'manifest.json'):
            raise ValueError('Resume configuration/dataset differs from the saved experiment')
        revision = saved['resolved_revision']
        resume_state = torch.load(resume_dir / 'trainer-state.pt', map_location='cpu', weights_only=True)
        if resume_state['finished']:
            raise ValueError('Training already finished; preserve it and create a new experiment')
    tokenizer = AutoTokenizer.from_pretrained(cfg['model'], revision=revision)
    model = AutoModelForSequenceClassification.from_pretrained(
        str(resume_dir) if resume_dir else cfg['model'], revision=None if resume_dir else revision, num_labels=len(labels),
        id2label=dict(enumerate(labels)), label2id={v: k for k, v in enumerate(labels)},
        attn_implementation='eager', use_safetensors=True).to(device)
    if cfg.get('gradient_checkpointing', False):
        model.gradient_checkpointing_enable()
    from transformers import DataCollatorWithPadding
    collator = DataCollatorWithPadding(tokenizer)
    generator = torch.Generator().manual_seed(seed)
    train_loader = DataLoader(EncodedRows(train, tokenizer, labels, cfg['max_length'], cfg.get('pair_truncation', 'longest_first')),
                              batch_size=cfg['batch_size'], shuffle=True, collate_fn=collator,
                              generator=generator)
    val_loader = DataLoader(EncodedRows(validation, tokenizer, labels, cfg['max_length'], cfg.get('pair_truncation', 'longest_first')),
                            batch_size=cfg.get('eval_batch_size', 64), collate_fn=collator)
    optimizer = torch.optim.AdamW(optimizer_groups(model, cfg), lr=cfg['learning_rate'], weight_decay=cfg.get('weight_decay', .01))
    accumulation = cfg.get('gradient_accumulation_steps', 1)
    total_steps = math.ceil(len(train_loader) / accumulation) * cfg['epochs']
    scheduler = get_linear_schedule_with_warmup(optimizer, int(total_steps * cfg.get('warmup_ratio', .1)), total_steps)
    counts = Counter(r['label'] for r in train)
    weights = class_weights(counts, labels, cfg, device)
    criterion = ClassificationLoss(weights, focal_gamma=cfg.get('focal_gamma', 0.),
                                   label_smoothing=cfg.get('label_smoothing', 0.))
    scaler = torch.amp.GradScaler('cuda', enabled=precision == 'fp16')
    amp_dtype = torch.float16 if precision == 'fp16' else torch.bfloat16
    output.mkdir(parents=True, exist_ok=True)
    resolved = {**cfg, 'resolved_revision': revision, 'device_used': str(device),
                'train_examples_used': len(train), 'train_counts': dict(counts),
                'validation_examples_used': len(validation), 'precision_used': precision,
                'gpu_name': torch.cuda.get_device_name(0) if device.type == 'cuda' else None,
                'parameter_count': sum(p.numel() for p in model.parameters()),
                'trainable_parameter_count': sum(p.numel() for p in model.parameters() if p.requires_grad),
                'training_ids_sha256': __import__('hashlib').sha256('\n'.join(sorted(r['id'] for r in train)).encode()).hexdigest(),
                'dataset_manifest_sha256': sha256(Path(cfg['data']) / 'manifest.json'),
                'python': platform.python_version(), 'torch': torch.__version__,
                'transformers': __import__('transformers').__version__}
    resolved['optimizer_groups'] = [{'lr': group['lr'], 'weight_decay': group['weight_decay'],
                                    'parameters': sum(p.numel() for p in group['params'])}
                                   for group in optimizer.param_groups]
    resolved['loss_weights'] = dict(zip(labels, weights.cpu().tolist())) if weights is not None else None
    resolved['context_turns_used'] = context_turns
    if not args.resume:
        write_json(output / 'run_config.json', resolved)
    best, stale, history = -1., 0, []
    start_epoch, previous_seconds = 0, 0.
    if resume_state:
        optimizer.load_state_dict(resume_state['optimizer'])
        scheduler.load_state_dict(resume_state['scheduler'])
        scaler.load_state_dict(resume_state['scaler'])
        torch.set_rng_state(resume_state['torch_rng'])
        generator.set_state(resume_state['loader_rng'])
        random.setstate(resume_state['python_rng'])
        if device.type == 'cuda':
            torch.cuda.set_rng_state_all(resume_state['cuda_rng'])
        np.random.set_state(('MT19937', np.array(resume_state['numpy_rng'][1], dtype='uint32'),
                             *resume_state['numpy_rng'][2:]))
        best, stale = resume_state['best'], resume_state['stale']
        history = resume_state['history']
        start_epoch, previous_seconds = resume_state['next_epoch'], resume_state['elapsed_seconds']
    started = time.monotonic()
    write_json(output / 'status.json', {'status': 'running', 'next_epoch': start_epoch + 1})
    for epoch in range(start_epoch, cfg['epochs']):
        model.train(); optimizer.zero_grad(set_to_none=True)
        running = 0.
        for step, batch in enumerate(train_loader):
            targets = batch.pop('labels').to(device)
            with torch.autocast(device_type=device.type, dtype=amp_dtype, enabled=precision != 'fp32'):
                logits = model(**{k: v.to(device) for k, v in batch.items()}).logits
                loss = criterion(logits, targets)
            if not torch.isfinite(loss):
                raise ValueError('Non-finite training loss; preserve checkpoints and inspect precision/data')
            running += loss.item()
            # Correct scaling for the final partial accumulation group.
            group_size = min(accumulation, len(train_loader) - (step // accumulation) * accumulation)
            scaler.scale(loss / group_size).backward()
            if (step + 1) % accumulation == 0 or step + 1 == len(train_loader):
                scaler.unscale_(optimizer)
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1., error_if_nonfinite=precision != 'fp16')
                old_scale = scaler.get_scale()
                scaler.step(optimizer); scaler.update()
                if scaler.get_scale() >= old_scale:
                    scheduler.step()
                optimizer.zero_grad(set_to_none=True)
            if (step + 1) % 100 == 0:
                print(f'epoch={epoch+1} batch={step+1}/{len(train_loader)} loss={running/(step+1):.4f}', flush=True)
        gold, predictions = predict(model, val_loader, device)
        result = classification_metrics([labels[i] for i in gold], [labels[i] for i in predictions], labels)
        history.append({'epoch': epoch + 1, 'train_loss': running / len(train_loader),
                        'elapsed_seconds': previous_seconds + time.monotonic() - started, 'validation': result})
        write_json(output / 'history.json', history)
        print(f"epoch={epoch+1} validation_macro_f1={result['macro_f1']:.4f} accuracy={result['accuracy']:.4f}", flush=True)
        if result['macro_f1'] > best:
            best, stale = result['macro_f1'], 0
            checkpoint = output / 'best'
            model.save_pretrained(checkpoint, safe_serialization=True)
            tokenizer.save_pretrained(checkpoint)
            write_json(checkpoint / 'meetmind_model.json', {
                'schema_version': 1, 'task': 'ami_dialogue_act', 'model_name': cfg['model'],
                'model_revision': revision, 'labels': labels, 'label_descriptions': manifest['labels'],
                'context_turns': context_turns, 'max_length': cfg['max_length'],
                'context_order': cfg.get('context_order', 'chronological'),
                'pair_truncation': cfg.get('pair_truncation', 'longest_first'),
                'review_threshold': .7, 'review_margin': .15, 'best_epoch': epoch + 1,
                'validation_macro_f1': best, 'dataset_manifest_sha256': resolved['dataset_manifest_sha256'],
                'checkpoint_stage': cfg.get('stage', 'experiment'), 'confidence_calibrated': False,
                'validation_examples_used': len(validation), 'train_examples_used': len(train),
                'test_used_for_selection': False})
        else:
            stale += 1
        finished = epoch + 1 == cfg['epochs'] or stale >= cfg.get('patience', 2)
        if cfg.get('save_epoch_state', False):
            directory = output / f'epoch-{epoch + 1:04d}'
            if directory.exists():
                # A partial write from an interrupted epoch is never a resume source.
                if (directory / 'complete.json').exists():
                    raise ValueError('Refusing to overwrite a completed epoch checkpoint')
                target = directory.resolve()
                if not target.is_relative_to(output.resolve()) or target == output.resolve():
                    raise ValueError('Invalid checkpoint cleanup path')
                shutil.rmtree(target)
            model.save_pretrained(directory, safe_serialization=True)
            tokenizer.save_pretrained(directory)
            numpy_rng = np.random.get_state()
            torch.save({'optimizer': optimizer.state_dict(), 'scheduler': scheduler.state_dict(),
                        'scaler': scaler.state_dict(), 'torch_rng': torch.get_rng_state(),
                        'cuda_rng': torch.cuda.get_rng_state_all() if device.type == 'cuda' else [],
                        'loader_rng': generator.get_state(), 'python_rng': random.getstate(),
                        'numpy_rng': (numpy_rng[0], numpy_rng[1].tolist(), *numpy_rng[2:]),
                        'best': best, 'stale': stale, 'history': history, 'next_epoch': epoch + 1,
                        'elapsed_seconds': history[-1]['elapsed_seconds'], 'finished': finished}, directory / 'trainer-state.pt')
            write_json(directory / 'complete.json', {'epoch': epoch + 1, 'finished': finished})
            for old in sorted(p for p in output.glob('epoch-*') if (p / 'complete.json').is_file())[:-2]:
                target = old.resolve()
                if not target.is_relative_to(output.resolve()) or target == output.resolve():
                    raise ValueError('Invalid checkpoint cleanup path')
                shutil.rmtree(target)
        write_json(output / 'status.json', {'status': 'completed' if finished else 'running',
                   'last_epoch': epoch + 1, 'best_validation_macro_f1': best,
                   'termination': 'early_stopping' if stale >= cfg.get('patience', 2) else 'epoch_limit' if finished else None})
        if finished:
            break
    print(f'Best checkpoint: {output / "best"}; validation macro F1: {best:.4f}', flush=True)


if __name__ == '__main__':
    main()
