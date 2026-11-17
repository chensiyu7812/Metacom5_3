"""B8e real-terminal instances (``pmrl1v3-b8e-real-interface-v1``): training side of the B6e -> B8e interface.

A ``RealInstance`` wraps one prefix: a factory for the real read port (WS-A PrefixPort or the B5 v2
adapter), the TerminalTable produced by ``evaluate.terminal_registry`` and the formal replay's
reachable subsets.  It plugs into the existing BC / OneShot / PPO / NoText code through the same
``make_env`` / ``oracle_dp`` / ``feasible_subsets`` / ``rewards`` interface as the programmatic task.

Rules:
* episodes run through ``C0FiniteHeadEnv`` with the reader's dynamic capacity mask; a STOP on a
  terminal without a computed ER record raises ``PendingTerminal`` - never a 0 reward;
* ``oracle_dp`` / OneShot targets need a COMPLETE table (every reachable subset computed); a partial
  table raises ``IncompleteTable``.  ``trainable`` keeps only complete instances for every arm and
  reports the excluded ones with their reason (same set for Text and NoText);
* rewards for unreachable subsets are NaN placeholders, masked out by ``feasible_subsets``.
Training on a few prefixes only shows the engineering loop runs; train/test on the same prefixes is
never evidence of generalisation or of PPO superiority.
"""
from __future__ import annotations

import dataclasses
import hashlib
import math
from typing import Callable

import numpy as np

from ..env import finite_head as E
from ..env.c0_binding import C0FiniteHeadEnv, TerminalIdentity, TerminalTable

INTERFACE = "pmrl1v3-b8e-real-interface-v1"
ARMS = ("OneShot", "Seq-BC", "Seq-BC-NoText", "PPO", "PPO-NoText")


class IncompleteTable(RuntimeError):
    pass


@dataclasses.dataclass
class RealInstance:
    instance_id: str
    port_factory: Callable[[], object]
    identity: TerminalIdentity
    table: TerminalTable
    report: dict
    reachable: tuple[int, ...]

    @property
    def complete(self) -> bool:
        return bool(self.report["complete"]) and self.report["computed"] == len(self.reachable)

    @property
    def available_mask(self) -> int:
        return E.mask_of(tuple(h for m in self.reachable for h in E.heads_of(m)))

    @property
    def rewards(self) -> tuple[float, ...]:
        if not self.complete:
            raise IncompleteTable(f"{self.instance_id}: partial table "
                                  f"({self.report['computed']}/{len(self.reachable)} computed)")
        env = make_env(self)
        return tuple(float(env.step(_replay(env, m), E.STOP)[1]) if m in self.reachable else math.nan
                     for m in range(E.N_SUBSETS))

    def feasible(self, mask: int) -> bool:
        return mask in self.reachable


def _replay(env, mask: int):
    s = env.reset()
    for h in E.heads_of(mask):
        s, _, _, _ = env.step(s, E.GET[h])
    return s


def make_env(inst: RealInstance) -> C0FiniteHeadEnv:
    port = inst.port_factory()
    return C0FiniteHeadEnv(prefix=port.prefix, history_sessions=port.prefix.cutoff_rank,
                           availability=dict(port.availability()),
                           read=lambda h, acquired: port.read(h, acquired=acquired), identity=inst.identity,
                           table=inst.table, prefix_tokens=port.base_tokens, read_takes_acquired=True,
                           dynamic_mask=port.action_mask)


def feasible_subsets(inst: RealInstance, max_gets: int = len(E.HEADS)) -> tuple[int, ...]:
    if not inst.complete:
        raise IncompleteTable(f"{inst.instance_id}: partial table cannot define OneShot targets")
    return tuple(m for m in inst.reachable if bin(m).count("1") <= max_gets)


def oracle_dp(inst: RealInstance, max_gets: int = len(E.HEADS)) -> E.DPResult:
    if not inst.complete:
        raise IncompleteTable(f"{inst.instance_id}: a partial table is not an Oracle table")
    r = inst.rewards
    return E.solve_dp({m: r[m] for m in inst.reachable}, available=inst.available_mask, max_gets=max_gets,
                      feasible=inst.feasible)


def trainable(instances, arm: str) -> tuple[list, list]:
    if arm not in ARMS:
        raise ValueError(f"unknown arm {arm}")
    kept, excluded = [], []
    for i in instances:
        (kept if i.complete else excluded).append(i)
    return kept, [dict(instance_id=i.instance_id, reason="partial_terminal_table", computed=i.report["computed"],
                       reachable=len(i.reachable), refused=i.report["refused"], missing=i.report["missing"])
                  for i in excluded]


class HashingTextEncoder:
    """Interface-check text featuriser (hashed word counts, L2-normalised).  Not a research encoder."""
    identity = "pmrl1v3-b8e-interface-hashing-bow-v1"

    def __init__(self, dim: int = 32):
        self.dim = dim

    def __call__(self, text: str) -> np.ndarray:
        v = np.zeros(self.dim, dtype=np.float32)
        for w in text.lower().split():
            v[int(hashlib.sha256(w.encode()).hexdigest()[:8], 16) % self.dim] += 1.0
        n = float(np.linalg.norm(v))
        return v / n if n else v
