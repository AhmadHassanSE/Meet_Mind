"""Fine-tune BERT; choose checkpoints by validation macro F1, never test scores."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import platform
import random
import time

import numpy as np
import torch
from torch.utils.data import DataLoader, Dataset
from transformers import AutoConfig, AutoModelForSequenceClassification, AutoTokenizer, get_linear_schedule_with_warmup

from nlp.data import load_split, sha256, training_sample, write_json
from nlp.metrics import classification_metrics


class EncodedRows(Dataset):
    def __init__(self, rows, tokenizer, labels, max_length):
        self.encodings = tokenizer([r['text'] for r in rows], [r['context'] for r in rows],
                                   truncation='longest_first', max_length=max_length, padding=False)
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
    args = parser.parse_args()
    cfg = json.loads(args.config.read_text(encoding='utf-8'))
    output = Path(cfg['output'])
    if output.exists() and any(output.iterdir()):
        raise ValueError('Output exists: choose a new run directory to preserve experiment evidence')
    train, manifest = load_split(cfg['data'], 'train')
    validation, other = load_split(cfg['data'], 'validation')
    if manifest != other:
        raise ValueError('Dataset manifest changed during loading')
    labels = sorted(manifest['labels'])
    seed = cfg['seed']
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
    torch.set_num_threads(cfg.get('cpu_threads', 4))
    torch.use_deterministic_algorithms(True, warn_only=True)
    device = torch.device('cuda' if torch.cuda.is_available() and cfg.get('device', 'auto') != 'cpu' else 'cpu')
    train = training_sample(train, cfg.get('max_train_examples', 0), seed)
    if set(r['label'] for r in train) != set(labels):
        raise ValueError('Training sample lacks an ontology class')
    pretrained_config = AutoConfig.from_pretrained(cfg['model'], revision=cfg.get('revision', 'main'))
    if pretrained_config.model_type != 'bert':
        raise ValueError('This pipeline requires a BERT checkpoint')
    revision = getattr(pretrained_config, '_commit_hash', None) or cfg.get('revision', 'main')
    tokenizer = AutoTokenizer.from_pretrained(cfg['model'], revision=revision)
    model = AutoModelForSequenceClassification.from_pretrained(
        cfg['model'], revision=revision, num_labels=len(labels),
        id2label=dict(enumerate(labels)), label2id={v: k for k, v in enumerate(labels)},
        attn_implementation='eager', use_safetensors=True).to(device)
    from transformers import DataCollatorWithPadding
    collator = DataCollatorWithPadding(tokenizer)
    train_loader = DataLoader(EncodedRows(train, tokenizer, labels, cfg['max_length']),
                              batch_size=cfg['batch_size'], shuffle=True, collate_fn=collator,
                              generator=torch.Generator().manual_seed(seed))
    val_loader = DataLoader(EncodedRows(validation, tokenizer, labels, cfg['max_length']),
                            batch_size=cfg.get('eval_batch_size', 64), collate_fn=collator)
    optimizer = torch.optim.AdamW(model.parameters(), lr=cfg['learning_rate'], weight_decay=cfg.get('weight_decay', .01))
    accumulation = cfg.get('gradient_accumulation_steps', 1)
    total_steps = math.ceil(len(train_loader) / accumulation) * cfg['epochs']
    scheduler = get_linear_schedule_with_warmup(optimizer, int(total_steps * .1), total_steps)
    counts = Counter(r['label'] for r in train)
    weights = torch.tensor([(len(train) / (len(labels) * counts[label])) ** .5 for label in labels], device=device)
    criterion = torch.nn.CrossEntropyLoss(weight=weights if cfg.get('class_weighting') == 'sqrt_inverse' else None)
    output.mkdir(parents=True, exist_ok=True)
    resolved = {**cfg, 'resolved_revision': revision, 'device_used': str(device),
                'train_examples_used': len(train), 'train_counts': dict(counts),
                'training_ids_sha256': __import__('hashlib').sha256('\n'.join(sorted(r['id'] for r in train)).encode()).hexdigest(),
                'dataset_manifest_sha256': sha256(Path(cfg['data']) / 'manifest.json'),
                'python': platform.python_version(), 'torch': torch.__version__,
                'transformers': __import__('transformers').__version__}
    write_json(output / 'run_config.json', resolved)
    best, stale, history = -1., 0, []
    started = time.monotonic()
    for epoch in range(cfg['epochs']):
        model.train(); optimizer.zero_grad(set_to_none=True)
        running = 0.
        for step, batch in enumerate(train_loader):
            targets = batch.pop('labels').to(device)
            logits = model(**{k: v.to(device) for k, v in batch.items()}).logits
            loss = criterion(logits, targets)
            running += loss.item()
            # Correct scaling for the final partial accumulation group.
            group_size = min(accumulation, len(train_loader) - (step // accumulation) * accumulation)
            (loss / group_size).backward()
            if (step + 1) % accumulation == 0 or step + 1 == len(train_loader):
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.)
                optimizer.step(); scheduler.step(); optimizer.zero_grad(set_to_none=True)
            if (step + 1) % 100 == 0:
                print(f'epoch={epoch+1} batch={step+1}/{len(train_loader)} loss={running/(step+1):.4f}', flush=True)
        gold, predictions = predict(model, val_loader, device)
        result = classification_metrics([labels[i] for i in gold], [labels[i] for i in predictions], labels)
        history.append({'epoch': epoch + 1, 'train_loss': running / len(train_loader),
                        'elapsed_seconds': time.monotonic() - started, 'validation': result})
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
                'context_turns': manifest['context_turns'], 'max_length': cfg['max_length'],
                'review_threshold': .7, 'review_margin': .15, 'best_epoch': epoch + 1,
                'validation_macro_f1': best, 'dataset_manifest_sha256': resolved['dataset_manifest_sha256'],
                'checkpoint_stage': cfg.get('stage', 'experiment'), 'confidence_calibrated': False,
                'test_used_for_selection': False})
        else:
            stale += 1
            if stale >= cfg.get('patience', 2):
                break
    print(f'Best checkpoint: {output / "best"}; validation macro F1: {best:.4f}', flush=True)


if __name__ == '__main__':
    main()
