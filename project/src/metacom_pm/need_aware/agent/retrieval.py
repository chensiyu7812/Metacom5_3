"""NAA fixed retrieval over one owner's memory units (CPU).

The query is built ONLY from the runtime user request and current visible messages;
MCQ options are never part of it (query_text has no access to them). BM25 reuses the
GE2 shared-retrieval implementation (same tokenizer and Robertson IDF, k1=1.2, b=.75).
Dense uses a local BGE encoder on CPU with cached unit embeddings; hybrid is reciprocal
rank fusion. Scores are private ranking signals, never facts.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path

from ..data.contracts import digest
from ...rl1v3.journal.ge2_retrieval import _BM25, RetrievalConfig as _GE2Config

RETRIEVAL_VERSION = 'naa-fixed-retrieval-v1'
BGE_QUERY_PREFIX = 'Represent this sentence for searching relevant passages: '
BACKENDS = ('bm25', 'dense', 'hybrid')


def query_text(task):
    """Visible request only. Deliberately reads no other task field."""
    parts = [m['content'] for m in task.current_messages if m['role'] == 'user']
    parts.append(task.user_query)
    return '\n'.join(p for p in parts if p.strip())


@dataclass(frozen=True)
class RetrievalSpec:
    backend: str = 'hybrid'
    unit_filter: str = 'all'        # all | user_only
    expand_next: bool = False       # also deliver the reply that follows a hit
    rrf_k: int = 60
    dense_model: str = 'BAAI/bge-small-en-v1.5@5c38ec7c405ec4b44b94cc5a9bb96e735b38267a'
    dense_max_tokens: int = 512

    def __post_init__(self):
        if self.backend not in BACKENDS or self.unit_filter not in ('all', 'user_only') or self.rrf_k < 1:
            raise ValueError('unsupported retrieval spec')

    @property
    def identity(self):
        return 'naaret:' + digest(dict(version=RETRIEVAL_VERSION, spec=asdict(self),
                                       bm25=dict(k1=_GE2Config.bm25_k1, b=_GE2Config.bm25_b)))


class BGEEncoder:
    """CPU BGE (CLS pooling, L2-normalised). Imports torch only when constructed."""

    def __init__(self, path, *, threads=8, max_tokens=512, batch=32):
        import torch
        from transformers import AutoModel, AutoTokenizer
        torch.set_num_threads(threads)
        self.torch = torch
        self.tok = AutoTokenizer.from_pretrained(path, local_files_only=True)
        self.model = AutoModel.from_pretrained(path, local_files_only=True).eval()
        self.max_tokens, self.batch = max_tokens, batch
        self.truncated = 0

    def encode(self, texts):
        # Length-sorted batches (less padding); vectors are returned in input order.
        order = sorted(range(len(texts)), key=lambda i: len(texts[i]))
        out = [None] * len(texts)
        with self.torch.inference_mode():
            for i in range(0, len(order), self.batch):
                idx = order[i:i + self.batch]
                enc = self.tok([texts[j] for j in idx], padding=True, truncation=True,
                               max_length=self.max_tokens, return_tensors='pt')
                self.truncated += int((enc['attention_mask'].sum(1) >= self.max_tokens).sum())
                vec = self.torch.nn.functional.normalize(self.model(**enc).last_hidden_state[:, 0], dim=-1)
                for j, v in zip(idx, vec.tolist()):
                    out[j] = v
        return out


class EmbeddingCache:
    """Per-unit vectors keyed by (model, text hash); private, on the server."""

    def __init__(self, root, model_id):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.model_id = model_id

    def _path(self, store_id):
        name = hashlib.sha256((self.model_id + '|' + store_id).encode()).hexdigest()[:24]
        return self.root / f'{name}.json'

    def get_or_build(self, store, units, encoder):
        p = self._path(store.store_id)
        if p.exists():
            data = json.loads(p.read_text())
            if data['model'] == self.model_id and data['store_id'] == store.store_id:
                return {k: v for k, v in data['vectors'].items()}, True
        vecs = encoder.encode([u.original_text for u in units])
        data = dict(model=self.model_id, store_id=store.store_id,
                    vectors={u.unit_id: v for u, v in zip(units, vecs)})
        tmp = p.with_suffix('.tmp')
        tmp.write_text(json.dumps(data))
        tmp.replace(p)
        return data['vectors'], False


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


class OwnerIndex:
    """Index for exactly one owner store; foreign units cannot enter."""

    def __init__(self, store, spec, *, unit_vectors=None):
        self.store, self.spec = store, spec
        units = [u for u in store.units if spec.unit_filter == 'all' or u.is_current_user]
        if any(u.owner_id != store.owner_id for u in units):
            raise ValueError('foreign unit in owner index')
        self.units = units
        self.by_id = store.by_id()
        self.bm25 = _BM25({u.unit_id: u.original_text for u in units}, _GE2Config())
        self.vectors = unit_vectors
        if spec.backend in ('dense', 'hybrid') and (unit_vectors is None or set(unit_vectors) < {u.unit_id for u in units}):
            raise ValueError('dense/hybrid retrieval requires vectors for every indexed unit')

    def _bm25_rank(self, query):
        scored = [(self.bm25.score(u.unit_id, query), u) for u in self.units]
        return sorted(scored, key=lambda x: (-x[0], -x[1].order))

    def _dense_rank(self, query_vector):
        scored = [(_dot(self.vectors[u.unit_id], query_vector), u) for u in self.units]
        return sorted(scored, key=lambda x: (-x[0], -x[1].order))

    def rank(self, query, *, query_vector=None):
        if self.spec.backend == 'bm25':
            ranked = [u for _, u in self._bm25_rank(query)]
        elif self.spec.backend == 'dense':
            ranked = [u for _, u in self._dense_rank(query_vector)]
        else:
            fused = {}
            for ranking in (self._bm25_rank(query), self._dense_rank(query_vector)):
                for position, (_, u) in enumerate(ranking):
                    fused[u.unit_id] = fused.get(u.unit_id, 0.) + 1. / (self.spec.rrf_k + position + 1)
            ranked = sorted(self.units, key=lambda u: (-fused[u.unit_id], -u.order))
        if not self.spec.expand_next:
            return ranked
        order = {u.order: u for u in self.store.units}
        out, seen = [], set()
        for u in ranked:
            for v in (u, order.get(u.order + 1)):
                if v is not None and v.unit_id not in seen:
                    seen.add(v.unit_id)
                    out.append(v)
        return out


def recency(store):
    """Context Only priority: newest first (packed contiguously by the reader)."""
    return sorted(store.units, key=lambda u: -u.order)
