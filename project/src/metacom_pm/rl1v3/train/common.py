"""Seeding, parameter fingerprints, checkpoints and JSONL logs (CPU only)."""
from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

import numpy as np
import torch

TORCH_THREADS = 4


def seed_everything(seed: int) -> torch.Generator:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.set_num_threads(TORCH_THREADS)
    torch.use_deterministic_algorithms(True)
    g = torch.Generator()
    g.manual_seed(seed)
    return g


def param_sha256(model: torch.nn.Module) -> str:
    h = hashlib.sha256()
    for name, p in sorted(model.state_dict().items()):
        h.update(name.encode())
        h.update(p.detach().cpu().contiguous().numpy().tobytes())
    return h.hexdigest()


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def save_checkpoint(path: Path, *, model, optimizer, step: int, torch_gen: torch.Generator,
                    np_rng: np.random.Generator | None, extra: dict) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(dict(model=model.state_dict(), optimizer=optimizer.state_dict(), step=step,
                    torch_gen=torch_gen.get_state(), torch_global=torch.get_rng_state(),
                    np_rng=None if np_rng is None else np_rng.bit_generator.state,
                    param_sha256=param_sha256(model), extra=extra), path)
    return file_sha256(path)


def load_checkpoint(path: Path, *, model, optimizer, torch_gen: torch.Generator,
                    np_rng: np.random.Generator | None) -> dict:
    ck = torch.load(path, map_location="cpu", weights_only=False)
    model.load_state_dict(ck["model"])
    optimizer.load_state_dict(ck["optimizer"])
    torch_gen.set_state(ck["torch_gen"])
    torch.set_rng_state(ck["torch_global"])
    if np_rng is not None and ck["np_rng"] is not None:
        np_rng.bit_generator.state = ck["np_rng"]
    if param_sha256(model) != ck["param_sha256"]:
        raise ValueError("checkpoint parameter fingerprint mismatch")
    return ck


class JsonlLog:
    def __init__(self, path: Path | None):
        self.path = path
        self.rows: list[dict] = []
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)

    def __call__(self, row: dict) -> None:
        self.rows.append(row)
        if self.path is not None:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, sort_keys=True) + "\n")
