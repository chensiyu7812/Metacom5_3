"""B8e-preflight: programmatic task correctness, isolation and real learning."""
from __future__ import annotations

import ast
import dataclasses
from pathlib import Path

import numpy as np
import pytest
import torch

from metacom_pm.rl1v3.env import finite_head as E
from metacom_pm.rl1v3.env import programmatic as P
from metacom_pm.rl1v3.evaluate import rollout as RO
from metacom_pm.rl1v3.policies.encoder import ObservationEncoder
from metacom_pm.rl1v3.policies.mlp import ActorCritic
from metacom_pm.rl1v3.train import ppo as PPO
from metacom_pm.rl1v3.train import supervised as S
from metacom_pm.rl1v3.train.common import JsonlLog, param_sha256, seed_everything

SRC = Path(P.__file__)


def enc(use_text=True):
    return ObservationEncoder(P.SyntheticTextEncoder(), P.TEXT_DIM, use_text=use_text)


def inst(need="hist_ME", cue="cue_event", avail=(1, 1, 1, 1), tokens=200, k=0):
    return P.Instance(instance_id=f"t:{need}:{cue}:{tokens}:{avail}", cue=cue, need=need,
                      prefix_text=P.paraphrase(cue, k), prefix_tokens=tokens, availability=avail,
                      reading_texts=tuple(P.paraphrase(P.reading_symbol(h, need), k)
                                          for h in E.HEADS),
                      rewards=tuple(P.terminal_reward(m, need) for m in range(E.N_SUBSETS)))


# ------------------------------------------------------- task correctness

def test_reward_formula_by_hand():
    assert P.terminal_reward(0, "hist_ME") == 0.5
    assert P.terminal_reward(E.mask_of(["ME"]), "hist_ME") == pytest.approx(0.5 + .4 - .05)
    assert P.terminal_reward(E.mask_of(["ME", "MS"]), "hist_MS") == pytest.approx(
        0.5 + .4 - .05 - .15 - .03)
    assert P.terminal_reward(E.mask_of(["RS"]), "none") == pytest.approx(0.5 - .04 - .03)


def test_capacity_masks_ms_and_budget_masks_all_gets():
    env = P.make_env(inst(tokens=550))
    s = env.reset()
    assert "GET_MS" not in env.legal_actions(s) and "GET_ME" in env.legal_actions(s)
    with pytest.raises(E.IllegalAction):
        env.step(s, "GET_MS")
    env1 = P.make_env(inst(tokens=100), max_gets=1)
    s, _, _, _ = env1.step(env1.reset(), "GET_RS")
    assert env1.legal_actions(s) == ("STOP",)
    with pytest.raises(E.IllegalAction):
        env1.step(s, "GET_MP")


def test_termination_and_reward_only_at_stop():
    env = P.make_env(inst())
    s, r1, d1, _ = env.step(env.reset(), "GET_ME")
    s, r2, d2, info = env.step(s, "STOP")
    assert (r1, d1, d2) == (0.0, False, True)
    assert r2 == pytest.approx(0.85) and info["path"] == ("GET_ME", "STOP")
    with pytest.raises(E.IllegalAction):
        env.step(s, "STOP")


def test_bayes_between_oneshot_best_and_oracle():
    for i in P.generate(400, 7, range(3), "t"):
        ev = P.bayes_expected_value(i)
        post = P.CUE_POSTERIOR[i.cue]
        # upper bound: posterior-weighted privileged oracle over the same visible facts
        oracle_ev = sum(p * P.oracle_dp(dataclasses.replace(
            i, need=n, rewards=tuple(P.terminal_reward(m, n) for m in range(E.N_SUBSETS))
        )).root_value for n, p in post.items())
        assert ev <= oracle_ev + 1e-9
        # lower bound: best fixed subset for the same cue
        fixed = max(sum(p * P.terminal_reward(m, n) for n, p in post.items())
                    for m in P.feasible_subsets(i))
        assert ev >= fixed - 1e-9


def test_sequential_reading_beats_one_shot_on_ambiguous_cue():
    i = inst(cue="cue_event", tokens=200)
    post = P.CUE_POSTERIOR[i.cue]
    oneshot = max(sum(p * P.terminal_reward(m, n) for n, p in post.items())
                  for m in P.feasible_subsets(i))
    assert P.bayes_expected_value(i) == pytest.approx(0.76)
    assert oneshot == pytest.approx(0.67)
    assert P.bayes_action(i, 0, {}) == "GET_ME"
    assert P.bayes_action(i, E.BIT["ME"], {"ME": "me_pointer_session"}) == "GET_MS"
    assert P.bayes_action(i, E.BIT["ME"], {"ME": "me_fact"}) == "STOP"


# ------------------------------------------------------------- isolation

def test_programmatic_module_imports_no_real_data_loader():
    tree = ast.parse(SRC.read_text())
    mods = {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    mods |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not any("paper1" in m or "prefixes" in m or "rl1." in m for m in mods), mods
    assert "open(" not in SRC.read_text() and "read_text" not in SRC.read_text()


def test_observation_independent_of_latent_rewards_and_unread_text():
    a = inst(need="hist_ME")
    b = dataclasses.replace(inst(need="hist_MS"), instance_id=a.instance_id)
    e = enc()
    ea, eb = P.make_env(a), P.make_env(b)
    assert np.array_equal(e(ea.observe(ea.reset())), e(eb.observe(eb.reset())))
    # different terminal table only: identical observations along a fixed path
    c = dataclasses.replace(a, rewards=tuple(9.0 for _ in a.rewards))
    ec = P.make_env(c)
    sa, sc = ea.reset(), ec.reset()
    for act in ("GET_RS", "GET_MP"):
        sa, _, _, _ = ea.step(sa, act)
        sc, _, _, _ = ec.step(sc, act)
        assert np.array_equal(e(ea.observe(sa)), e(ec.observe(sc)))
    obs = ea.observe(sa)
    assert set(obs) == {"prefix", "acquired", "availability", "action_mask", "input_tokens"}
    flat = repr(obs)
    for secret in ("hist_ME", "me_fact", "ms_", "reward", a.instance_id):
        assert secret not in flat
    # reading ME later does reveal the read text, and only then
    sa, _, _, _ = ea.step(sa, "GET_ME")
    assert "me_fact" in repr(ea.observe(sa))


def test_notext_drops_reading_text_but_keeps_flags():
    i = inst()
    env = P.make_env(i)
    s, _, _, _ = env.step(env.reset(), "GET_ME")
    full, nt = enc(True)(env.observe(s)), enc(False)(env.observe(s))
    d = P.TEXT_DIM
    text_block = slice(d + 8 + 4, d + 8 + 4 + 4 * d)
    assert np.abs(full[text_block]).sum() > 0 and np.abs(nt[text_block]).sum() == 0
    assert np.array_equal(np.delete(full, np.r_[text_block]), np.delete(nt, np.r_[text_block]))


# ------------------------------------------------------- real learning

def test_bc_and_oneshot_take_real_optimizer_steps_and_reduce_loss():
    tr = P.generate(300, 11, range(3), "tr")
    dv = P.generate(100, 12, range(3), "dv")
    g = seed_everything(5)
    log = JsonlLog(None)
    m, _, info = S.train_bc(tr, dv, P.make_env, enc(), P.oracle_dp, gen=g, epochs=4, lr=1e-3,
                            batch=64, log=log)
    rows = [r for r in log.rows if r["method"] == "Seq-BC"]
    assert info["optimizer_steps"] > 0 and rows[-1]["train_loss"] < rows[0]["train_loss"]
    m2, _, info2 = S.train_oneshot(tr, dv, P.make_env, enc(), P.feasible_subsets, gen=g,
                                   epochs=4, lr=1e-3, batch=64, log=log)
    rows = [r for r in log.rows if r["method"] == "OneShot"]
    assert info2["optimizer_steps"] > 0 and rows[-1]["train_loss"] < rows[0]["train_loss"]


def test_ppo_learns_solvable_task_from_scratch():
    # profile cue -> GET_MP is clearly optimal; OFF = 0.5, optimum = 0.87
    tr = tuple(dataclasses.replace(i, cue="cue_profile", need="hist_MP",
                                   prefix_text=P.paraphrase("cue_profile", 0),
                                   reading_texts=tuple(P.paraphrase(P.reading_symbol(h, "hist_MP"), 0)
                                                       for h in E.HEADS),
                                   rewards=tuple(P.terminal_reward(m, "hist_MP")
                                                 for m in range(E.N_SUBSETS)),
                                   availability=(1, 1, 1, 1))
               for i in P.generate(64, 3, range(1), "tr"))
    e = enc()
    g = seed_everything(1)
    model = ActorCritic(e.dim)
    cfg = PPO.PPOConfig(rounds=12, steps_per_round=512, n_envs=64, minibatch=128,
                        eval_every=4, lr=1e-3)
    before = float(np.mean([r["ret"] for r in RO.batched_greedy(tr, P.make_env, e,
                                                                 S.greedy_choose(model))]))
    log = JsonlLog(None)
    res = PPO.train_ppo(model, tr, tr, P.make_env, e, cfg, gen=g, rng=np.random.default_rng(1),
                        log=log, ckpt_dir=None, method="PPO")
    after = float(np.mean([r["ret"] for r in RO.batched_greedy(tr, P.make_env, e,
                                                                S.greedy_choose(model))]))
    assert res["optimizer_steps"] > 0
    assert after == pytest.approx(0.87, abs=1e-6), (before, after)


def test_ppo_resume_is_bitwise_identical(tmp_path):
    tr = P.generate(64, 21, range(2), "tr")
    e = enc()
    cfg = PPO.PPOConfig(rounds=4, steps_per_round=256, n_envs=32, minibatch=64,
                        eval_every=4, ckpt_every=2)
    g = seed_everything(9)
    m1 = ActorCritic(e.dim)
    r1 = PPO.train_ppo(m1, tr, tr, P.make_env, e, cfg, gen=g, rng=np.random.default_rng(9),
                       log=JsonlLog(None), ckpt_dir=tmp_path / "a", method="x")
    g = seed_everything(9)
    m2 = ActorCritic(e.dim)
    PPO.train_ppo(m2, tr, tr, P.make_env, e, cfg, gen=g, rng=np.random.default_rng(9),
                  log=JsonlLog(None), ckpt_dir=tmp_path / "b", method="x", stop_after=2)
    g3, rng3, m3 = torch.Generator(), np.random.default_rng(0), ActorCritic(e.dim)
    opt3, start = PPO.resume(tmp_path / "b" / "round_0002.pt", m3, cfg, g3, rng3)
    r3 = PPO.train_ppo(m3, tr, tr, P.make_env, e, cfg, gen=g3, rng=rng3, log=JsonlLog(None),
                       ckpt_dir=None, method="x", start_round=start, opt=opt3)
    assert start == 2 and r1["final_param_sha256"] == r3["final_param_sha256"]


def test_masked_policy_never_samples_illegal_actions():
    e = enc()
    model = ActorCritic(e.dim)
    i = inst(tokens=590, avail=(0, 1, 1, 1))
    env = P.make_env(i)
    obs = env.observe(env.reset())
    x, m = torch.tensor(e(obs))[None], torch.tensor(e.mask(obs))[None]
    probs = model.dist(x, m).probs[0]
    for a, p in zip(E.ACTIONS, probs):
        if a not in obs["action_mask"]:
            assert float(p) == 0.0
