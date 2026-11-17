"""PPO on the FiniteHead environment (V3.1 §6.10 settings), CPU, resumable.

Episodes run through ``env.step``; reward only at STOP (gamma = 1); GAE over
complete episodes (terminal value 0).  Each round collects complete episodes
until at least ``steps_per_round`` transitions, then runs ``epochs`` passes of
minibatch clipped-surrogate updates.  The critic sees exactly the actor's
observation features (same whitelist).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Sequence

import numpy as np
import torch

from ..env import finite_head as E
from ..evaluate import rollout as RO
from ..policies.mlp import ActorCritic
from .common import JsonlLog, load_checkpoint, param_sha256, save_checkpoint
from .supervised import greedy_choose


@dataclass(frozen=True)
class PPOConfig:
    rounds: int = 200
    steps_per_round: int = 2048
    n_envs: int = 128
    epochs: int = 4
    minibatch: int = 256
    lr: float = 3e-4
    clip: float = 0.2
    ent_coef: float = 0.01
    vf_coef: float = 0.5
    gae_lambda: float = 0.95
    gamma: float = 1.0
    max_grad_norm: float = 0.5
    eval_every: int = 5
    ckpt_every: int = 50


def collect(model: ActorCritic, instances: Sequence, make_env: Callable, encoder,
            n_steps: int, n_envs: int, rng: np.random.Generator, gen: torch.Generator):
    """Complete episodes until >= n_steps transitions."""
    def new():
        inst = instances[int(rng.integers(len(instances)))]
        env = make_env(inst)
        return dict(env=env, s=env.reset(), traj=[])

    slots = [new() for _ in range(n_envs)]
    episodes, steps, launched = [], 0, n_envs
    while slots:
        obs = [sl["env"].observe(sl["s"]) for sl in slots]
        X = torch.tensor(np.stack([encoder(o) for o in obs]))
        M = torch.tensor(np.stack([encoder.mask(o) for o in obs]))
        with torch.no_grad():
            dist = model.dist(X, M)
            a = torch.multinomial(dist.probs, 1, generator=gen).squeeze(-1)
            logp = dist.log_prob(a)
            v = model.value(X)
        keep = []
        for k, sl in enumerate(slots):
            s2, r, done, _ = sl["env"].step(sl["s"], E.ACTIONS[int(a[k])])
            sl["traj"].append((X[k], M[k], int(a[k]), float(logp[k]), float(v[k]), r))
            sl["s"] = s2
            steps += 1
            if done:
                episodes.append(sl["traj"])
                if steps < n_steps:
                    keep.append(new())
                    launched += 1
            else:
                keep.append(sl)
        slots = keep
    return episodes, steps


def gae(rewards, values, gamma: float, lam: float):
    adv, last = [0.0] * len(rewards), 0.0
    for t in reversed(range(len(rewards))):
        nv = values[t + 1] if t + 1 < len(values) else 0.0
        delta = rewards[t] + gamma * nv - values[t]
        last = delta + gamma * lam * last
        adv[t] = last
    return adv, [a + v for a, v in zip(adv, values)]


def update(model: ActorCritic, opt, episodes, cfg: PPOConfig, gen: torch.Generator) -> dict:
    X, M, A, LP, ADV, RET = [], [], [], [], [], []
    for ep in episodes:
        rs = [t[5] for t in ep]
        vs = [t[4] for t in ep]
        adv, ret = gae(rs, vs, cfg.gamma, cfg.gae_lambda)
        for t, ad, rt in zip(ep, adv, ret):
            X.append(t[0]); M.append(t[1]); A.append(t[2]); LP.append(t[3])
            ADV.append(ad); RET.append(rt)
    X, M = torch.stack(X), torch.stack(M)
    A, LP = torch.tensor(A), torch.tensor(LP)
    ADV, RET = torch.tensor(ADV, dtype=torch.float32), torch.tensor(RET, dtype=torch.float32)
    ADVn = (ADV - ADV.mean()) / (ADV.std() + 1e-8)
    stats = dict(policy_loss=0.0, value_loss=0.0, entropy=0.0, approx_kl=0.0, clip_frac=0.0,
                 grad_norm=0.0)
    n_updates = 0
    for _ in range(cfg.epochs):
        perm = torch.randperm(len(X), generator=gen)
        for i in range(0, len(perm), cfg.minibatch):
            idx = perm[i:i + cfg.minibatch]
            dist = model.dist(X[idx], M[idx])
            lp = dist.log_prob(A[idx])
            ratio = torch.exp(lp - LP[idx])
            s1 = ratio * ADVn[idx]
            s2 = torch.clamp(ratio, 1 - cfg.clip, 1 + cfg.clip) * ADVn[idx]
            pl = -torch.min(s1, s2).mean()
            vl = ((model.value(X[idx]) - RET[idx]) ** 2).mean()
            ent = dist.entropy().mean()
            loss = pl + cfg.vf_coef * vl - cfg.ent_coef * ent
            opt.zero_grad()
            loss.backward()
            gn = torch.nn.utils.clip_grad_norm_(model.parameters(), cfg.max_grad_norm)
            opt.step()
            n_updates += 1
            with torch.no_grad():
                stats["policy_loss"] += float(pl)
                stats["value_loss"] += float(vl)
                stats["entropy"] += float(ent)
                stats["approx_kl"] += float((LP[idx] - lp).mean())
                stats["clip_frac"] += float(((ratio - 1).abs() > cfg.clip).float().mean())
                stats["grad_norm"] += float(gn)
    out = {k: v / n_updates for k, v in stats.items()}
    out["optimizer_steps"] = n_updates
    return out


def train_ppo(model: ActorCritic, train: Sequence, dev: Sequence, make_env: Callable, encoder,
              cfg: PPOConfig, *, gen: torch.Generator, rng: np.random.Generator, log: JsonlLog,
              ckpt_dir: Path | None, method: str, start_round: int = 0, opt=None,
              stop_after: int | None = None) -> dict:
    opt = opt or torch.optim.Adam(model.parameters(), lr=cfg.lr)
    best, best_round, total_steps, ckpts = -1e9, start_round, 0, {}
    best_path = None if ckpt_dir is None else ckpt_dir / "best.pt"
    last = stop_after or cfg.rounds
    for rnd in range(start_round + 1, last + 1):
        episodes, steps = collect(model, train, make_env, encoder, cfg.steps_per_round,
                                  cfg.n_envs, rng, gen)
        st = update(model, opt, episodes, cfg, gen)
        total_steps += st["optimizer_steps"]
        rets = [sum(t[5] for t in ep) for ep in episodes]
        gets = [sum(1 for t in ep if t[2] != 0) for ep in episodes]
        row = dict(method=method, round=rnd, env_steps=steps, episodes=len(episodes),
                   train_return=float(np.mean(rets)), train_gets=float(np.mean(gets)), **st)
        if rnd % cfg.eval_every == 0 or rnd == last:
            res = RO.batched_greedy(dev, make_env, encoder, greedy_choose(model))
            row["dev_return"] = float(np.mean([r["ret"] for r in res]))
            row["dev_gets"] = float(np.mean([r["n_gets"] for r in res]))
            if row["dev_return"] > best:
                best, best_round = row["dev_return"], rnd
                if best_path is not None:
                    ckpts["best"] = save_checkpoint(best_path, model=model, optimizer=opt,
                                                    step=rnd, torch_gen=gen, np_rng=rng,
                                                    extra=dict(cfg=asdict(cfg), method=method,
                                                               dev_return=best))
        log(row)
        if ckpt_dir is not None and (rnd % cfg.ckpt_every == 0 or rnd == last):
            ckpts[f"round_{rnd}"] = save_checkpoint(
                ckpt_dir / f"round_{rnd:04d}.pt", model=model, optimizer=opt, step=rnd,
                torch_gen=gen, np_rng=rng, extra=dict(cfg=asdict(cfg), method=method))
    return dict(best_dev_return=best, best_round=best_round, optimizer_steps=total_steps,
                final_param_sha256=param_sha256(model), checkpoints_sha256=ckpts, opt=opt)


def resume(path: Path, model: ActorCritic, cfg: PPOConfig, gen: torch.Generator,
           rng: np.random.Generator):
    opt = torch.optim.Adam(model.parameters(), lr=cfg.lr)
    ck = load_checkpoint(path, model=model, optimizer=opt, torch_gen=gen, np_rng=rng)
    return opt, int(ck["step"])
