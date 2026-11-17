"""ENGINEERING-ONLY programmatic FiniteHead task for the B8e preflight.

Fully synthetic and isolated: this module imports no dataset loader and reads
no file.  Every "text" is a symbol plus a paraphrase index, embedded by a
deterministic hash-seeded encoder that stands in for BGE.  Nothing here is a
user experience, a resource record or a natural-support outcome; results only
show whether the training stack (env -> observation -> optimizer -> eval) can
learn a solvable GET/STOP problem.

Design (answer is verifiable):

* latent need in {none, method, hist_MP, hist_ME, hist_MS} is private;
* the visible prefix text is a paraphrase of a cue symbol; cues are partly
  ambiguous (``cue_event`` = hist_ME or hist_MS, ``cue_vague`` = mostly none);
* reading ME reveals ``me_fact`` (fact is here) or ``me_pointer_session``
  (fact lives in a past session -> MS), so reading-dependent decisions beat
  any one-shot subset and any policy without reading text (NoText);
* terminal reward R(S) = 0.5 + gain(relevant head read) - sum GET cost
  - misuse per irrelevant read; depends only on the acquired subset;
* MS is large; native capacity masks it for long prefixes.

References: per-instance oracle DP (privileged, knows the latent) and the
exact Bayes-optimal observation-limited policy (expectimax over the cue
posterior and reading outcomes).
"""
from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

import numpy as np

from . import finite_head as E

TASK_ID = "pmrl1v3-b8e-preflight-programmatic-v1"
EVIDENCE_TIER = "engineering_only"
NEEDS = ("none", "method", "hist_MP", "hist_ME", "hist_MS")
CUE_POSTERIOR: Mapping[str, Mapping[str, float]] = {
    "cue_none": {"none": 1.0},
    "cue_method": {"method": 1.0},
    "cue_profile": {"hist_MP": 1.0},
    "cue_event": {"hist_ME": 0.5, "hist_MS": 0.5},
    "cue_vague": {"none": 0.6, "hist_ME": 0.2, "hist_MS": 0.2},
}
CUE_PRIOR: Mapping[str, float] = {"cue_none": .25, "cue_method": .15, "cue_profile": .15,
                                  "cue_event": .30, "cue_vague": .15}
BASE = 0.5
GAIN: Mapping[str, tuple[str, float]] = {"method": ("RS", .30), "hist_MP": ("MP", .40),
                                         "hist_ME": ("ME", .40), "hist_MS": ("MS", .40)}
GET_COST: Mapping[str, float] = {"RS": .04, "MP": .03, "ME": .05, "MS": .15}
MISUSE = .03
UNIT_TOKENS: Mapping[str, int] = {"RS": 150, "MP": 50, "ME": 120, "MS": 700}
CAPACITY = 1200
PREFIX_TOKENS = (100, 600)
P_AVAILABLE = 0.9
MAX_GETS = 4
TEXT_DIM = 32
PARAPHRASE_NOISE = 0.6


def relevant_head(need: str) -> str | None:
    return GAIN[need][0] if need in GAIN else None


def terminal_reward(mask: int, need: str) -> float:
    rel = relevant_head(need)
    r = BASE
    for h in E.heads_of(mask):
        r -= GET_COST[h]
        r += GAIN[need][1] if h == rel else -MISUSE
    return round(r, 12)


def reading_symbol(head: str, need: str) -> str:
    if head == "RS":
        return "rs_card_fit" if need == "method" else "rs_card_generic"
    if head == "MP":
        return "mp_fact" if need == "hist_MP" else "mp_other"
    if head == "ME":
        return {"hist_ME": "me_fact", "hist_MS": "me_pointer_session"}.get(need, "me_other")
    return "ms_fact" if need == "hist_MS" else "ms_other"


def paraphrase(symbol: str, k: int) -> str:
    return f"{symbol} ~{k}"


def symbol_of(text: str) -> str:
    return text.split(" ~", 1)[0]


def _hash_rng(key: str) -> np.random.Generator:
    return np.random.default_rng(int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big"))


class SyntheticTextEncoder:
    """Deterministic stand-in for a frozen text encoder: shared symbol direction
    plus paraphrase-specific noise, L2-normalised."""
    identity = f"{TASK_ID}|hash-encoder|dim={TEXT_DIM}|noise={PARAPHRASE_NOISE}"

    def __init__(self, dim: int = TEXT_DIM, noise: float = PARAPHRASE_NOISE):
        self.dim, self.noise = dim, noise
        self._cache: dict[str, np.ndarray] = {}

    def __call__(self, text: str) -> np.ndarray:
        v = self._cache.get(text)
        if v is None:
            base = _hash_rng("sym|" + symbol_of(text)).standard_normal(self.dim)
            noise = _hash_rng("para|" + text).standard_normal(self.dim)
            v = base + self.noise * noise
            v = (v / np.linalg.norm(v)).astype(np.float32)
            self._cache[text] = v
        return v


@dataclass(frozen=True)
class Instance:
    instance_id: str
    cue: str                         # private (visible only as paraphrased prefix text)
    need: str                        # private latent
    prefix_text: str                 # visible
    prefix_tokens: int               # visible through Observation.input_tokens
    availability: tuple[int, ...]    # visible counts in E.HEADS order
    reading_texts: tuple[str, ...]   # private until the head is read
    rewards: tuple[float, ...]       # private 16-terminal table indexed by subset mask

    @property
    def available_mask(self) -> int:
        return E.mask_of([h for h, c in zip(E.HEADS, self.availability) if c > 0])

    def feasible(self, mask: int) -> bool:
        return self.prefix_tokens + sum(UNIT_TOKENS[h] for h in E.heads_of(mask)) <= CAPACITY


def generate(n: int, seed: int, paraphrases: Sequence[int], split: str) -> tuple[Instance, ...]:
    rng = np.random.default_rng(seed)
    cues, cue_p = list(CUE_PRIOR), np.array(list(CUE_PRIOR.values()))
    out = []
    for i in range(n):
        cue = cues[rng.choice(len(cues), p=cue_p / cue_p.sum())]
        post = CUE_POSTERIOR[cue]
        need = list(post)[rng.choice(len(post), p=np.array(list(post.values())))]
        avail = tuple(int(rng.integers(1, 6)) if rng.random() < P_AVAILABLE else 0
                      for _ in E.HEADS)
        tokens = int(rng.integers(PREFIX_TOKENS[0], PREFIX_TOKENS[1] + 1))
        pick = lambda: int(paraphrases[rng.integers(len(paraphrases))])  # noqa: E731
        out.append(Instance(
            instance_id=f"{TASK_ID}:{split}:{seed}:{i}",
            cue=cue, need=need,
            prefix_text=paraphrase(cue, pick()),
            prefix_tokens=tokens,
            availability=avail,
            reading_texts=tuple(paraphrase(reading_symbol(h, need), pick()) for h in E.HEADS),
            rewards=tuple(terminal_reward(m, need) for m in range(E.N_SUBSETS)),
        ))
    return tuple(out)


def make_env(inst: Instance, *, max_gets: int = MAX_GETS,
             observation_factory: Callable[..., object] | None = None) -> E.FiniteHeadEnv:
    texts = dict(zip(E.HEADS, inst.reading_texts))

    def reader(head: str) -> E.ReadUnit:
        return E.ReadUnit(head=head, reading_text=texts[head], tokens=UNIT_TOKENS[head],
                          record_ids=(f"{inst.instance_id}:{head}",), cost_s=GET_COST[head])

    def lookup(mask: int) -> E.TerminalOutcome:
        return E.TerminalOutcome(reward=inst.rewards[mask],
                                 key_sha256=hashlib.sha256(
                                     f"{inst.instance_id}|{E.canonical_path(mask)}".encode()
                                 ).hexdigest())

    return E.FiniteHeadEnv(availability=dict(zip(E.HEADS, inst.availability)), reader=reader,
                           terminal_lookup=lookup, prefix_tokens=inst.prefix_tokens,
                           token_capacity=CAPACITY, max_gets=max_gets, unit_tokens=UNIT_TOKENS,
                           observation_factory=observation_factory,
                           visible_prefix=inst.prefix_text)


# ----------------------------------------------------------------- references

def oracle_dp(inst: Instance, max_gets: int = MAX_GETS) -> E.DPResult:
    """Privileged per-instance optimum (knows the latent need)."""
    return E.solve_dp(dict(enumerate(inst.rewards)), available=inst.available_mask,
                      max_gets=max_gets, feasible=inst.feasible)


def _bayes_q(belief: tuple[tuple[str, float], ...], mask: int, inst: Instance,
             max_gets: int, memo: dict) -> dict[str, float]:
    key = (belief, mask)
    if key in memo:
        return memo[key]
    z = sum(p for _, p in belief)
    q = {E.STOP: sum(p * terminal_reward(mask, n) for n, p in belief) / z}
    if bin(mask).count("1") < max_gets:
        for h in E.heads_of(inst.available_mask & ~mask):
            nxt = mask | E.BIT[h]
            if not inst.feasible(nxt):
                continue
            groups: dict[str, list] = defaultdict(list)
            for n, p in belief:
                groups[reading_symbol(h, n)].append((n, p))
            q[E.GET[h]] = sum(sum(p for _, p in g) / z * max(
                _bayes_q(tuple(g), nxt, inst, max_gets, memo).values()) for g in groups.values())
    memo[key] = q
    return q


def bayes_action(inst: Instance, mask: int, observed: Mapping[str, str],
                 max_gets: int = MAX_GETS) -> str:
    """Observation-limited optimal action given the cue and symbols read so far."""
    belief = tuple((n, p) for n, p in CUE_POSTERIOR[inst.cue].items()
                   if all(reading_symbol(h, n) == s for h, s in observed.items()))
    q = _bayes_q(belief, mask, inst, max_gets, {})
    best = max(q.values())
    return next(a for a in E.ACTIONS if a in q and q[a] >= best - 1e-12)


def bayes_expected_value(inst: Instance, max_gets: int = MAX_GETS) -> float:
    return max(_bayes_q(tuple(CUE_POSTERIOR[inst.cue].items()), 0, inst, max_gets, {}).values())


def feasible_subsets(inst: Instance, max_gets: int = MAX_GETS) -> tuple[int, ...]:
    return tuple(m for m in range(E.N_SUBSETS)
                 if (m & ~inst.available_mask) == 0 and bin(m).count("1") <= max_gets
                 and inst.feasible(m))
