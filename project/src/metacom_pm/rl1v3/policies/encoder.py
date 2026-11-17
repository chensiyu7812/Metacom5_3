"""Observation -> feature vector.  Reads only the visible Observation fields.

Accepts the C0 ``Observation`` (attributes) or the B5 core's dict with the same
field names: prefix, acquired[head, ordinal, reading_text, tokens],
availability[head, available, count], action_mask, input_tokens.  It never
receives the instance, terminal table, oracle values or unread text, so it
cannot leak them.  ``use_text=False`` is the NoText ablation: read flags stay,
read-text embeddings are zeroed; the prefix text is kept.
"""
from __future__ import annotations

import math
from typing import Callable

import numpy as np

from ..env import finite_head as E


def _get(obj, name):
    return obj[name] if isinstance(obj, dict) else getattr(obj, name)


def _prefix_text(prefix) -> str:
    if isinstance(prefix, str):
        return prefix
    turns = _get(prefix, "turns")  # C0 VisiblePrefix
    return "\n".join(f"{_get(t, 'role')}: {_get(t, 'text')}" for t in turns)


class ObservationEncoder:
    def __init__(self, text_encoder: Callable[[str], np.ndarray], text_dim: int, *,
                 use_text: bool = True, token_scale: float = 1200.0, max_count: int = 5):
        self.text, self.d, self.use_text = text_encoder, text_dim, use_text
        self.token_scale, self.max_count = token_scale, max_count
        self.layout = (("prefix_text", text_dim), ("available", 4), ("log_count", 4),
                       ("read_flag", 4), ("read_text", 4 * text_dim),
                       ("action_mask", len(E.ACTIONS)), ("input_tokens", 1))
        self.dim = sum(n for _, n in self.layout)

    def __call__(self, obs) -> np.ndarray:
        v = np.zeros(self.dim, dtype=np.float32)
        d, i = self.d, 0
        v[i:i + d] = self.text(_prefix_text(_get(obs, "prefix")))
        i += d
        for a in _get(obs, "availability"):
            k = E.HEADS.index(_get(a, "head"))
            v[i + k] = float(bool(_get(a, "available")))
            v[i + 4 + k] = math.log1p(_get(a, "count")) / math.log1p(self.max_count)
        i += 8
        for r in _get(obs, "acquired"):
            k = E.HEADS.index(_get(r, "head"))
            v[i + k] = 1.0
            if self.use_text:
                v[i + 4 + k * d:i + 4 + (k + 1) * d] = self.text(_get(r, "reading_text"))
        i += 4 + 4 * d
        for a in _get(obs, "action_mask"):
            v[i + E.ACTIONS.index(a)] = 1.0
        i += len(E.ACTIONS)
        v[i] = _get(obs, "input_tokens") / self.token_scale
        return v

    @staticmethod
    def mask(obs) -> np.ndarray:
        m = np.zeros(len(E.ACTIONS), dtype=bool)
        for a in _get(obs, "action_mask"):
            m[E.ACTIONS.index(a)] = True
        return m
