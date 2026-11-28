"""Minimal LoRA for NAA WP4 generator adaptation (no new dependency).

The frozen WP2 inference environment (transformers 5.17, torch 2.7.1) has no peft, and the
local peft env cannot load Qwen3.5 / Gemma-4. A ~60-line LoRA keeps one environment for
training and inference, so the adapted generator is the base checkpoint (unchanged SHA)
plus an adapter file whose SHA-256 is bound into the manifest. Base weights never receive
gradients; inference merges W <- W + (alpha/r) * B @ A once after loading.
Language-model linear layers only: vision/audio towers and the output head are excluded.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

LORA_VERSION = 'naa-lora-v1'
EXCLUDE = ('vision', 'visual', 'audio', 'lm_head', 'embed', 'multi_modal_projector', 'mm_projector')


def _torch():
    import torch
    return torch


def target_names(model, suffixes):
    torch = _torch()
    out = []
    for name, mod in model.named_modules():
        if isinstance(mod, torch.nn.Linear) and name.split('.')[-1] in suffixes \
                and not any(x in name for x in EXCLUDE):
            out.append(name)
    return out


def _lora_class():
    torch = _torch()

    class LoRALinear(torch.nn.Module):
        def __init__(self, base, r, alpha, dropout):
            super().__init__()
            self.base, self.r, self.scale = base, r, alpha / r
            self.lora_A = torch.nn.Parameter(torch.empty(r, base.in_features, dtype=torch.float32,
                                                         device=base.weight.device))
            self.lora_B = torch.nn.Parameter(torch.zeros(base.out_features, r, dtype=torch.float32,
                                                         device=base.weight.device))
            torch.nn.init.kaiming_uniform_(self.lora_A, a=math.sqrt(5))
            self.drop = torch.nn.Dropout(dropout) if dropout else torch.nn.Identity()

        def forward(self, x):
            y = self.base(x)
            delta = (self.drop(x).to(torch.float32) @ self.lora_A.t()) @ self.lora_B.t()
            return y + (delta * self.scale).to(y.dtype)

    return LoRALinear


def apply(model, *, suffixes, r, alpha, dropout=0.):
    """Freeze every base parameter and wrap the selected linears. Returns the wrapped names."""
    LoRALinear = _lora_class()
    for p in model.parameters():
        p.requires_grad_(False)
    names = target_names(model, suffixes)
    if not names:
        raise ValueError('no LoRA target modules matched ' + ','.join(suffixes))
    for name in names:
        parent = model.get_submodule(name.rsplit('.', 1)[0]) if '.' in name else model
        child = name.rsplit('.', 1)[-1]
        setattr(parent, child, LoRALinear(getattr(parent, child), r, alpha, dropout))
    return names


def adapter_state(model):
    return {k: v.detach().cpu().contiguous() for k, v in model.state_dict().items() if '.lora_' in k}


def trainable(model):
    return [(n, p) for n, p in model.named_parameters() if p.requires_grad]


def save(path, model, config):
    from safetensors.torch import save_file
    path = Path(path); path.mkdir(parents=True, exist_ok=True)
    state = adapter_state(model)
    save_file(state, str(path / 'adapter.safetensors'))
    sha = hashlib.sha256((path / 'adapter.safetensors').read_bytes()).hexdigest()
    meta = dict(version=LORA_VERSION, config=config, tensors=len(state),
                parameters=int(sum(v.numel() for v in state.values())), adapter_sha256=sha)
    (path / 'adapter.json').write_text(json.dumps(meta, indent=2, sort_keys=True) + '\n')
    return meta


def merge(model, path, *, expected_sha256):
    """Inference: verify the adapter bytes, then fold B@A into the base weights in place."""
    torch = _torch()
    from safetensors.torch import load_file
    path = Path(path)
    sha = hashlib.sha256((path / 'adapter.safetensors').read_bytes()).hexdigest()
    if sha != expected_sha256:
        raise ValueError('adapter bytes differ from the bound identity')
    meta = json.loads((path / 'adapter.json').read_text())
    cfg = meta['config']; scale = cfg['alpha'] / cfg['r']
    state = load_file(str(path / 'adapter.safetensors'))
    names = sorted({k.rsplit('.lora_', 1)[0] for k in state})   # wrapped module names == base linear names
    if names != sorted(target_names(model, cfg['suffixes'])):
        raise ValueError('adapter targets do not match this architecture')
    with torch.no_grad():
        for n in names:
            lin = model.get_submodule(n)
            a, b = state[n + '.lora_A'], state[n + '.lora_B']
            lin.weight += (scale * (b.float() @ a.float())).to(lin.weight.dtype).to(lin.weight.device)
    return dict(adapter_sha256=sha, merged_modules=len(names), lora_version=meta['version'])
