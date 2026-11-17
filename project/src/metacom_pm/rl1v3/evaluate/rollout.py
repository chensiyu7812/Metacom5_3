"""Rollouts through the real B5 FiniteHeadEnv and summary metrics.

Every episode is executed by ``env.step``; a policy can only see
``env.observe(state)``.  Illegal actions raise inside the environment (they
are never silently counted), so a finished evaluation implies zero illegal
actions.
"""
from __future__ import annotations

import math
from collections import defaultdict
from typing import Callable, Mapping, Sequence

import numpy as np

from ..env import finite_head as E


def run_policy(instances: Sequence, make_env: Callable, act: Callable) -> list[dict]:
    """One-at-a-time rollout; ``act(obs, env, state) -> action``."""
    out = []
    for inst in instances:
        env = make_env(inst)
        s, total = env.reset(), 0.0
        while not s.done:
            s, r, _, _ = env.step(s, act(env.observe(s), env, s))
            total += r
        out.append(dict(instance_id=inst.instance_id, ret=total, n_gets=len(s.order),
                        terminal_mask=s.mask, order=s.order))
    return out


def batched_greedy(instances: Sequence, make_env: Callable, encoder,
                   choose: Callable[[np.ndarray, np.ndarray], np.ndarray]) -> list[dict]:
    """Lock-step rollout; ``choose(X[B,D], M[B,A]) -> action indices``."""
    envs = [make_env(i) for i in instances]
    states = [e.reset() for e in envs]
    totals = [0.0] * len(envs)
    active = list(range(len(envs)))
    while active:
        obs = [envs[k].observe(states[k]) for k in active]
        X = np.stack([encoder(o) for o in obs])
        M = np.stack([encoder.mask(o) for o in obs])
        acts = choose(X, M)
        nxt = []
        for k, a in zip(active, acts):
            states[k], r, done, _ = envs[k].step(states[k], E.ACTIONS[int(a)])
            totals[k] += r
            if not done:
                nxt.append(k)
        active = nxt
    return [dict(instance_id=i.instance_id, ret=totals[k], n_gets=len(states[k].order),
                 terminal_mask=states[k].mask, order=states[k].order)
            for k, i in enumerate(instances)]


def execute_subset(inst, make_env, subset: int) -> dict:
    """Commit to a subset up front: GET its heads (canonical order) then STOP."""
    env = make_env(inst)
    s, total = env.reset(), 0.0
    for h in E.heads_of(subset):
        a = E.GET[h]
        if a in env.legal_actions(s):
            s, r, _, _ = env.step(s, a)
            total += r
    s, r, _, _ = env.step(s, E.STOP)
    return dict(instance_id=inst.instance_id, ret=total + r, n_gets=len(s.order),
                terminal_mask=s.mask, order=s.order)


def summarize(results: Sequence[Mapping], instances: Sequence, *,
              bayes: Mapping[str, float] | None = None,
              oracle: Mapping[str, float] | None = None) -> dict:
    rets = np.array([r["ret"] for r in results], dtype=np.float64)
    gets = np.array([r["n_gets"] for r in results], dtype=np.float64)
    cue_of = {i.instance_id: i.cue for i in instances}
    by_cue = defaultdict(list)
    for r in results:
        by_cue[cue_of[r["instance_id"]]].append(r["ret"])
    out = dict(n=len(rets), mean_return=round(float(rets.mean()), 6),
               se=round(float(rets.std(ddof=1) / math.sqrt(len(rets))), 6),
               mean_gets=round(float(gets.mean()), 4),
               off_rate=round(float((gets == 0).mean()), 4),
               by_cue={c: round(float(np.mean(v)), 6) for c, v in sorted(by_cue.items())})
    if bayes is not None:
        out["regret_vs_bayes"] = round(float(np.mean(
            [bayes[r["instance_id"]] - r["ret"] for r in results])), 6)
    if oracle is not None:
        out["regret_vs_oracle"] = round(float(np.mean(
            [oracle[r["instance_id"]] - r["ret"] for r in results])), 6)
    return out
