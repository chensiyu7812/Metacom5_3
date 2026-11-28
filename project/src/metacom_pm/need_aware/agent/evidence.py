"""WP3 fixed evidence supply over one owner's legal store (CPU only, no LLM call).

One bounded strong-baseline build, not a retrieval study: every parameter below is fixed
before any WP3 model call and none is tuned on outcomes.

Reused mechanisms (not re-invented):
  * GE2 ``union_intervals``: inclusive original-turn intervals; overlapping or adjacent spans
    of the same history share one rendering (de-duplication), source coordinates preserved.
  * GE2 rendering discipline: complete original turns, original roles ("said by"), source
    (chronological) order, no wrapper prose in the scored text, nothing cropped mid-turn.
  * NAA reader ``record_line`` / ``pack`` and the WP2 dense/BM25 index (B0/B1 rankings).
  * GE2 parent-session expansion has no PersonaMem-v2 counterpart: a history is one flat
    message list without session boundaries or dates, so the parent IS the whole history.
    No boundary is invented; adjacency enters through windows that straddle turns.

E0 is an *equivalent adaptation* of Raw-RAG (arXiv 2610.30755, Appendix B.1), not a
reproduction: 256-token windows, 32-token overlap, dense top-128 candidates, reranked
top-15, each kept window rendered as the complete source turns that overlap it.
Deviations, all fixed in advance: window tokens counted with the local BGE tokenizer
(paper: GPT-4 tokenizer); first stage BGE-small-en-v1.5 (paper: Qwen3-Embedding-4B or
text-embedding-3-small); reranker Qwen3-Reranker-0.6B on CPU (paper: Qwen3-Reranker-4B
or Cohere Rerank-v3.5); expanded turns are de-duplicated and rendered chronologically
(paper default keeps repeats; LoCoMo/LongMemEval in relevance order); the paper has no
evidence cap, E0 uses the common native cap of 8,192 evidence tokens (whole windows are
skipped, never cropped) and E0s the same ranking at 1,536.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import random

from ..data.contracts import digest
from ..memory import reader as R
from ...rl1v3.journal.ge2_retrieval import union_intervals

SUPPLY_VERSION = 'naa-wp3-supply-v1'
WINDOW_TOKENS, WINDOW_OVERLAP = 256, 32
DENSE_CANDIDATES, RERANK_KEEP = 128, 15
NATIVE_BUDGET, COMPACT_BUDGET = 8192, 1536
RERANKER_ID = 'Qwen/Qwen3-Reranker-0.6B@e61197ed45024b0ed8a2d74b80b4d909f1255473'
RERANK_INSTRUCTION = ('Given the current request a user makes to their long-term assistant, retrieve the '
                      'earlier conversation passages that help respond to it')
NOISE_SEED = 'naa-wp3-cnoise-v1'
SPEAKER = {True: 'user', False: 'assistant'}


@dataclass(frozen=True)
class Window:
    window_id: str
    lo: int            # first overlapping unit order (inclusive)
    hi: int            # last overlapping unit order (inclusive)
    text: str          # decoded window tokens; ranking signal only, never rendered


def windows(units, tokenizer, *, size=WINDOW_TOKENS, overlap=WINDOW_OVERLAP):
    """Fixed token windows over the speaker-labelled history, each linked to its source turns."""
    stream, owner = [], []
    for u in sorted(units, key=lambda x: x.order):
        ids = tokenizer.encode(SPEAKER[u.is_current_user] + ': ' + u.original_text, add_special_tokens=False)
        stream += ids
        owner += [u.order] * len(ids)
    if not stream:
        return []
    stride = size - overlap
    starts = list(range(0, max(1, len(stream) - overlap), stride))
    out = []
    for s in starts:
        e = min(len(stream), s + size)
        lo, hi = owner[s], owner[e - 1]
        wid = 'w:' + hashlib.sha256(f'{s}:{e}:{lo}:{hi}'.encode()).hexdigest()[:16]
        out.append(Window(wid, lo, hi, tokenizer.decode(stream[s:e])))
    return out


def window_spec_identity(encoder_id):
    return 'naawin:' + digest(dict(version=SUPPLY_VERSION, size=WINDOW_TOKENS, overlap=WINDOW_OVERLAP,
                                   labels=SPEAKER, encoder=encoder_id))


def dense_candidates(windows_, vectors, query_vector, k=DENSE_CANDIDATES):
    scored = [(sum(a * b for a, b in zip(vectors[w.window_id], query_vector)), w) for w in windows_]
    return [w for _, w in sorted(scored, key=lambda x: (-x[0], x[1].lo, x[1].window_id))[:k]]


class QwenReranker:
    """Official Qwen3-Reranker yes/no scoring (model card), CPU, fp32, deterministic."""

    PREFIX = ('<|im_start|>system\nJudge whether the Document meets the requirements based on the Query and '
              'the Instruct provided. Note that the answer can only be "yes" or "no".<|im_end|>\n<|im_start|>user\n')
    SUFFIX = '<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n'

    def __init__(self, path, *, threads=16, batch=16, max_length=1024):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        torch.set_num_threads(threads)
        self.torch = torch
        self.tok = AutoTokenizer.from_pretrained(path, padding_side='left', local_files_only=True)
        self.model = AutoModelForCausalLM.from_pretrained(path, dtype=torch.float32, local_files_only=True).eval()
        self.yes = self.tok.convert_tokens_to_ids('yes')
        self.no = self.tok.convert_tokens_to_ids('no')
        self.pre = self.tok.encode(self.PREFIX, add_special_tokens=False)
        self.suf = self.tok.encode(self.SUFFIX, add_special_tokens=False)
        self.batch, self.max_length = batch, max_length
        self.tokens_scored = 0

    def score(self, query, documents):
        pairs = [f'<Instruct>: {RERANK_INSTRUCTION}\n<Query>: {query}\n<Document>: {d}' for d in documents]
        out = []
        with self.torch.inference_mode():
            for i in range(0, len(pairs), self.batch):
                enc = self.tok(pairs[i:i + self.batch], padding=False, truncation='longest_first',
                               return_attention_mask=False,
                               max_length=self.max_length - len(self.pre) - len(self.suf))
                ids = [self.pre + e + self.suf for e in enc['input_ids']]
                self.tokens_scored += sum(map(len, ids))
                batch = self.tok.pad({'input_ids': ids}, padding=True, return_tensors='pt')
                last = self.model(**batch).logits[:, -1, :]
                two = self.torch.stack([last[:, self.no], last[:, self.yes]], dim=1)
                out += self.torch.nn.functional.log_softmax(two, dim=1)[:, 1].exp().tolist()
        return out


def rerank(candidates, scores, keep=RERANK_KEEP):
    order = sorted(zip(scores, candidates), key=lambda x: (-x[0], x[1].lo, x[1].window_id))
    return [(w, s) for s, w in order[:keep]]


def unit_cost(count_tokens, unit):
    return count_tokens(R.record_line('H00', unit)) + 1          # identical to reader.pack


def pack_windows(ranked_windows, store, count_tokens, budget):
    """Greedy over reranked windows: a window enters with ALL turns it overlaps (minus turns
    already delivered) or is skipped whole; union de-duplicates; render chronologically."""
    by_order = {u.order: u for u in store.units}
    chosen, used, kept, skipped = {}, 0, [], []
    for w in ranked_windows:
        new = [by_order[o] for o in range(w.lo, w.hi + 1) if o in by_order and o not in chosen]
        cost = sum(unit_cost(count_tokens, u) for u in new)
        if used + cost > budget:
            skipped.append(w.window_id)
            continue
        for u in new:
            chosen[u.order] = u
        used += cost
        kept.append(w)
    intervals = union_intervals([[w.lo, w.hi] for w in kept]) if kept else []
    units = tuple(sorted(chosen.values(), key=lambda u: u.order))
    return R.Packed(units=units, priority_ids=tuple(w.window_id for w in ranked_windows),
                    skipped_over_budget=tuple(skipped), tokens=used), intervals


def with_background(c_packed, store, count_tokens, budget, task_id):
    """C+noise: C's units unchanged + legal same-owner/cutoff non-reference records drawn in a
    fixed seeded order until the budget; never filtered by relevance, answers or outputs.
    Rendering stays in source order, so evidence positions follow the original history."""
    ref = {u.unit_id for u in c_packed.units}
    pool = sorted((u for u in store.units if u.unit_id not in ref), key=lambda u: u.order)
    seed = int(hashlib.sha256(f'{NOISE_SEED}|{task_id}'.encode()).hexdigest()[:16], 16)
    random.Random(seed).shuffle(pool)
    chosen, used = list(c_packed.units), c_packed.tokens
    for u in pool:
        cost = unit_cost(count_tokens, u)
        if used + cost <= budget:
            chosen.append(u)
            used += cost
    chosen.sort(key=lambda u: u.order)
    background = [u for u in chosen if u.unit_id not in ref]
    flags = dict(background_units=len(background),
                 background_forget_or_change=sum(bool(u.constraint_candidates) for u in background),
                 background_third_party=sum(bool(u.third_party_mention) for u in background),
                 reference_positions=[i for i, u in enumerate(chosen) if u.unit_id in ref])
    return R.Packed(units=tuple(chosen), priority_ids=c_packed.priority_ids, skipped_over_budget=(),
                    tokens=used), flags


def coverage(delivered_units, direct_ids, store):
    """Diagnostic only (needs A's Direct coordinates, never a runtime input)."""
    if not direct_ids:
        return None
    by = store.by_id()
    got = {u.unit_id for u in delivered_units}
    ref = [x for x in direct_ids if x in by]
    user = [x for x in ref if by[x].is_current_user]
    other = [x for x in ref if not by[x].is_current_user]
    frac = lambda xs: (sum(x in got for x in xs) / len(xs)) if xs else None
    return dict(reference_units=len(ref), recall=frac(ref), user_recall=frac(user), nonuser_recall=frac(other),
                complete_group=bool(ref) and all(x in got for x in ref),
                undeliverable=len(direct_ids) - len(ref))
