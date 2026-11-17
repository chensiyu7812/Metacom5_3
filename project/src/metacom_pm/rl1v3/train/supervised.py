"""OneShot (subset soft targets) and Seq-BC (DP-optimal action imitation).

Labels come from the per-instance terminal table / oracle DP (training-side
supervision only).  Inputs are built exclusively from ``env.observe``.
"""
from __future__ import annotations

from typing import Callable, Sequence

import numpy as np
import torch
import torch.nn.functional as F

from ..env import finite_head as E
from ..evaluate import rollout as RO
from ..policies.mlp import ActorCritic, OneShotNet
from .common import JsonlLog, param_sha256


def _replay(env, mask: int):
    s = env.reset()
    for h in E.heads_of(mask):
        s, _, _, _ = env.step(s, E.GET[h])
    return s


# ------------------------------------------------------------------- OneShot

def oneshot_dataset(instances: Sequence, make_env: Callable, encoder, feasible_subsets: Callable,
                    tau: float = 0.05):
    X, M, T = [], [], []
    for inst in instances:
        env = make_env(inst)
        X.append(encoder(env.observe(env.reset())))
        feas = np.zeros(E.N_SUBSETS, dtype=bool)
        feas[list(feasible_subsets(inst))] = True
        r = np.array(inst.rewards, dtype=np.float64)
        z = np.where(feas, r / tau, -np.inf)
        t = np.exp(z - z.max())
        T.append((t / t.sum()).astype(np.float32))
        M.append(feas)
    return torch.tensor(np.stack(X)), torch.tensor(np.stack(M)), torch.tensor(np.stack(T))


def oneshot_choose(model: OneShotNet, X: torch.Tensor, M: torch.Tensor) -> np.ndarray:
    with torch.no_grad():
        return model(X, M).argmax(-1).numpy()


def train_oneshot(train, dev, make_env, encoder, feasible_subsets, *, gen: torch.Generator,
                  epochs: int, lr: float, batch: int, log: JsonlLog, tau: float = 0.05):
    Xtr, Mtr, Ttr = oneshot_dataset(train, make_env, encoder, feasible_subsets, tau)
    Xdv, Mdv, Tdv = oneshot_dataset(dev, make_env, encoder, feasible_subsets, tau)
    model = OneShotNet(encoder.dim)
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    best, best_state, steps = -1e9, None, 0
    for ep in range(1, epochs + 1):
        model.train()
        perm = torch.randperm(len(Xtr), generator=gen)
        tot = 0.0
        for i in range(0, len(perm), batch):
            idx = perm[i:i + batch]
            loss = -(Ttr[idx] * F.log_softmax(model(Xtr[idx], Mtr[idx]), -1)).sum(-1).mean()
            opt.zero_grad()
            loss.backward()
            opt.step()
            steps += 1
            tot += float(loss) * len(idx)
        model.eval()
        with torch.no_grad():
            dev_loss = float(-(Tdv * F.log_softmax(model(Xdv, Mdv), -1)).sum(-1).mean())
        picks = oneshot_choose(model, Xdv, Mdv)
        dev_ret = float(np.mean([RO.execute_subset(i, make_env, int(m))["ret"]
                                 for i, m in zip(dev, picks)]))
        log(dict(method="OneShot", epoch=ep, optimizer_steps=steps,
                 train_loss=tot / len(Xtr), dev_loss=dev_loss, dev_return=dev_ret))
        if dev_ret > best:
            best, best_state = dev_ret, {k: v.clone() for k, v in model.state_dict().items()}
    model.load_state_dict(best_state)
    return model, opt, dict(best_dev_return=best, optimizer_steps=steps,
                            param_sha256=param_sha256(model))


# -------------------------------------------------------------------- Seq-BC

def bc_dataset(instances: Sequence, make_env: Callable, encoder, oracle: Callable):
    """States on every DP-optimal branch; target uniform over tied optimal actions."""
    X, M, T = [], [], []
    for inst in instances:
        dp = oracle(inst)
        env = make_env(inst)
        stack, seen = [0], set()
        while stack:
            m = stack.pop()
            if m in seen:
                continue
            seen.add(m)
            obs = env.observe(_replay(env, m))
            acts = dp.optimal_actions[m]
            t = np.zeros(len(E.ACTIONS), dtype=np.float32)
            for a in acts:
                t[E.ACTIONS.index(a)] = 1.0 / len(acts)
            X.append(encoder(obs))
            M.append(encoder.mask(obs))
            T.append(t)
            stack.extend(m | E.BIT[E.HEAD_OF[a]] for a in acts if a != E.STOP)
    return torch.tensor(np.stack(X)), torch.tensor(np.stack(M)), torch.tensor(np.stack(T))


def greedy_choose(model: ActorCritic) -> Callable:
    def choose(X: np.ndarray, M: np.ndarray) -> np.ndarray:
        with torch.no_grad():
            return model.dist(torch.tensor(X), torch.tensor(M)).probs.argmax(-1).numpy()
    return choose


def train_bc(train, dev, make_env, encoder, oracle, *, gen: torch.Generator, epochs: int,
             lr: float, batch: int, log: JsonlLog, method: str = "Seq-BC"):
    Xtr, Mtr, Ttr = bc_dataset(train, make_env, encoder, oracle)
    Xdv, Mdv, Tdv = bc_dataset(dev, make_env, encoder, oracle)
    model = ActorCritic(encoder.dim)
    opt = torch.optim.Adam(model.actor.parameters(), lr=lr)
    best, best_state, steps = -1e9, None, 0
    for ep in range(1, epochs + 1):
        model.train()
        perm = torch.randperm(len(Xtr), generator=gen)
        tot = 0.0
        for i in range(0, len(perm), batch):
            idx = perm[i:i + batch]
            logp = torch.log_softmax(model.dist(Xtr[idx], Mtr[idx]).logits, -1)
            loss = -(Ttr[idx] * logp.clamp_min(-1e4)).sum(-1).mean()
            opt.zero_grad()
            loss.backward()
            opt.step()
            steps += 1
            tot += float(loss) * len(idx)
        model.eval()
        with torch.no_grad():
            lp = torch.log_softmax(model.dist(Xdv, Mdv).logits, -1).clamp_min(-1e4)
            dev_loss = float(-(Tdv * lp).sum(-1).mean())
            agree = float(((Tdv > 0).gather(1, lp.argmax(-1, keepdim=True))).float().mean())
        res = RO.batched_greedy(dev, make_env, encoder, greedy_choose(model))
        dev_ret = float(np.mean([r["ret"] for r in res]))
        log(dict(method=method, epoch=ep, optimizer_steps=steps, train_loss=tot / len(Xtr),
                 dev_loss=dev_loss, dev_expert_state_agreement=agree, dev_return=dev_ret,
                 n_train_states=len(Xtr)))
        if dev_ret > best:
            best, best_state = dev_ret, {k: v.clone() for k, v in model.state_dict().items()}
    model.load_state_dict(best_state)
    return model, opt, dict(best_dev_return=best, optimizer_steps=steps,
                            n_train_states=len(Xtr), param_sha256=param_sha256(model))
