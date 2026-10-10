"""Local checkpoint inference; never silently use a randomly initialized head."""
import json
import os
from pathlib import Path
import threading

from nlp.data import ACTION_LABELS, build_inputs, sha256

DEFAULT_MODEL = Path(__file__).parents[1] / 'models' / 'dialogue-bert'
_lock = threading.Lock()
_cached = None


class BertUnavailable(RuntimeError):
    pass


def model_path():
    return Path(os.getenv('BERT_MODEL_PATH', str(DEFAULT_MODEL))).resolve()


def status():
    path = model_path()
    if not (path / 'meetmind_model.json').is_file():
        return {'status': 'checkpoint missing', 'task': 'ami_dialogue_act'}
    try:
        metadata = json.loads((path / 'meetmind_model.json').read_text(encoding='utf-8'))
        return {'status': 'checkpoint available', 'task': metadata['task'],
                'model': metadata['model_name'], 'stage': metadata['checkpoint_stage'],
                'validation_macro_f1': metadata['validation_macro_f1']}
    except (OSError, ValueError, KeyError):
        return {'status': 'invalid checkpoint', 'task': 'ami_dialogue_act'}


class DialogueClassifier:
    def __init__(self, path):
        try:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
        except ImportError as error:
            raise BertUnavailable('Install the nlp extra before running BERT inference.') from error
        self.torch = torch
        self.path = Path(path)
        try:
            self.metadata = json.loads((self.path / 'meetmind_model.json').read_text(encoding='utf-8'))
            if self.metadata['task'] != 'ami_dialogue_act' or self.metadata['schema_version'] != 1:
                raise ValueError('Unsupported task/schema')
            self.tokenizer = AutoTokenizer.from_pretrained(self.path, local_files_only=True)
            self.model, info = AutoModelForSequenceClassification.from_pretrained(
                self.path, local_files_only=True, use_safetensors=True,
                attn_implementation='eager', output_loading_info=True)
            labels = [self.model.config.id2label[i] for i in range(self.model.config.num_labels)]
            if (self.model.config.model_type != 'bert' or labels != self.metadata['labels'] or
                    info['missing_keys'] or info['unexpected_keys'] or info.get('mismatched_keys')):
                raise ValueError('Checkpoint weights/labels do not match the saved task')
            self.labels = labels
            self.metadata['model_weights_sha256'] = sha256(self.path / 'model.safetensors')
            torch.set_num_threads(int(os.getenv('BERT_CPU_THREADS', '4')))
            self.model.eval()
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise BertUnavailable('BERT checkpoint is missing or invalid. Train and configure BERT_MODEL_PATH.') from error

    def predict(self, segments):
        pairs = build_inputs(segments, self.metadata['context_turns'])
        results = []
        threshold, margin_threshold = self.metadata['review_threshold'], self.metadata['review_margin']
        with self.torch.inference_mode():
            for offset in range(0, len(pairs), 32):
                batch = pairs[offset:offset + 32]
                tokens = self.tokenizer([x[0] for x in batch], [x[1] for x in batch],
                                         padding=True, truncation='longest_first',
                                         max_length=self.metadata['max_length'], return_tensors='pt')
                probabilities = self.model(**tokens).logits.softmax(-1).tolist()
                for segment, probs in zip(segments[offset:offset + 32], probabilities):
                    top = sorted(range(len(probs)), key=lambda i: probs[i], reverse=True)
                    label, score = self.labels[top[0]], probs[top[0]]
                    margin = score - probs[top[1]]
                    reasons = []
                    if score < threshold: reasons.append('low_model_score')
                    if margin < margin_threshold: reasons.append('close_alternative_label')
                    if label in ACTION_LABELS: reasons.append('possible_action_is_not_a_confirmed_commitment')
                    results.append({'source_id': segment['id'], 'label': label,
                                    'description': self.metadata['label_descriptions'][label],
                                    'score': score, 'margin': margin,
                                    'possible_action': label in ACTION_LABELS,
                                    'needs_review': bool(reasons), 'review_reasons': reasons,
                                    'top_labels': [{'label': self.labels[i], 'score': probs[i]} for i in top[:3]]})
        return results


def classify(segments):
    global _cached
    with _lock:
        path = model_path()
        metadata_path = path / 'meetmind_model.json'
        if not metadata_path.is_file():
            raise BertUnavailable('No fine-tuned BERT checkpoint configured. Train a model and set BERT_MODEL_PATH.')
        key = (str(path), metadata_path.stat().st_mtime_ns)
        if _cached is None or _cached[0] != key:
            _cached = (key, DialogueClassifier(path))
        classifier = _cached[1]
        predictions = classifier.predict(segments)
        metadata = {k: classifier.metadata[k] for k in [
            'model_name', 'model_revision', 'checkpoint_stage', 'best_epoch',
            'validation_macro_f1', 'dataset_manifest_sha256', 'model_weights_sha256', 'confidence_calibrated']}
        return {'task': 'ami_dialogue_act', 'predictions': predictions, 'model': metadata}
