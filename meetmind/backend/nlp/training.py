"""Explicit, auditable optimization options; no validation-derived loss weights."""
import math
import re
import torch
from torch import nn
from torch.nn import functional as F


def class_weights(counts, labels, cfg, device):
    mode = cfg.get('class_weighting', 'none')
    if mode == 'none':
        return None
    frequencies = torch.tensor([counts[label] for label in labels], dtype=torch.float64)
    if (frequencies <= 0).any():
        raise ValueError('Every class needs training support')
    if mode == 'sqrt_inverse':
        weights = (frequencies.sum() / (len(labels)*frequencies)).sqrt()
    elif mode == 'effective_number':
        beta = cfg.get('effective_number_beta', .999)
        # Numerically stable (1-beta)/(1-beta**n).
        weights = (1-beta) / (-torch.expm1(frequencies * math.log(beta)))
        weights /= weights.mean()
    else:
        raise ValueError('Unsupported class weighting')
    if cfg.get('class_weight_cap') is not None:
        weights = weights.clamp(max=cfg['class_weight_cap'])
    return weights.to(device=device, dtype=torch.float32)


class ClassificationLoss(nn.Module):
    def __init__(self, weights=None, *, focal_gamma=0., label_smoothing=0.):
        super().__init__()
        self.register_buffer('weights', weights)
        self.gamma = focal_gamma
        self.smoothing = label_smoothing

    def forward(self, logits, targets):
        # Compute probabilities/loss in fp32 even under mixed-precision BERT.
        logits = logits.float()
        if not self.gamma:
            return F.cross_entropy(logits, targets, weight=self.weights,
                                   label_smoothing=self.smoothing)
        log_pt = F.log_softmax(logits, -1).gather(1, targets[:, None]).squeeze(1)
        losses = -(1-log_pt.exp()).pow(self.gamma)*log_pt
        if self.weights is None:
            return losses.mean()
        weights = self.weights[targets]
        return (losses*weights).sum()/weights.sum()


def optimizer_groups(model, cfg):
    """Optional BERT layer LR decay, faster task head, no bias/norm decay.

    Legacy configs retain their exact single-group optimizer configuration.
    """
    if not cfg.get('group_optimizer_parameters', False):
        return [{'params': list(model.parameters()), 'lr': cfg['learning_rate'],
                 'weight_decay': cfg.get('weight_decay', .01)}]
    groups = {}
    layers = model.config.num_hidden_layers
    decay = cfg.get('layer_lr_decay', 1.)
    for name, param in model.named_parameters():
        if not param.requires_grad:
            continue
        match = re.search(r'bert\.encoder\.layer\.(\d+)\.', name)
        if match:
            multiplier = decay ** (layers-1-int(match[1]))
        elif name.startswith('bert.embeddings.'):
            multiplier = decay ** layers
        elif name.startswith('classifier.'):
            multiplier = cfg.get('head_lr_multiplier', 1.)
        else:
            multiplier = 1.
        weight_decay = 0. if name.endswith('.bias') or 'LayerNorm.' in name else cfg.get('weight_decay', .01)
        key = (cfg['learning_rate']*multiplier, weight_decay)
        groups.setdefault(key, []).append(param)
    return [{'params': params, 'lr': lr, 'weight_decay': wd}
            for (lr, wd), params in groups.items()]
