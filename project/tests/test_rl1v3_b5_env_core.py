"""B5 core: deterministic toy environments, exact DP, illegal actions, isolation."""
from __future__ import annotations

import random

import pytest

from metacom_pm.rl1v3.env import finite_head as E


def toy_env(availability=None, rewards=None, capacity=None, unit_tokens=None, calls=None):
    availability = availability or {h: 2 for h in E.HEADS}
    rewards = rewards if rewards is not None else {m: float(bin(m).count("1")) / 10
                                                   for m in range(E.N_SUBSETS)}
    calls = calls if calls is not None else {"read": [], "terminal": []}

    def reader(head):
        calls["read"].append(head)
        return E.ReadUnit(head=head, reading_text=f"text-{head}", tokens=10,
                          record_ids=(f"rec-{head}",), cost_s=0.1)

    def lookup(mask):
        calls["terminal"].append(mask)
        r = rewards.get(mask)
        return None if r is None else E.TerminalOutcome(reward=r, key_sha256=f"k{mask}")

    env = E.FiniteHeadEnv(availability=availability, reader=reader, terminal_lookup=lookup,
                          prefix_tokens=100, token_capacity=capacity, unit_tokens=unit_tokens)
    return env, calls


def run(env, actions):
    s, total = env.reset(), 0.0
    for a in actions:
        s, r, done, info = env.step(s, a)
        total += r
    return s, total, info


# ------------------------------------------------------------------ positives

def test_terminal_depends_only_on_subset():
    env, _ = toy_env()
    s1, r1, i1 = run(env, ["GET_MP", "GET_RS", "STOP"])
    s2, r2, i2 = run(env, ["GET_RS", "GET_MP", "STOP"])
    assert i1["terminal_mask"] == i2["terminal_mask"] and r1 == r2
    assert i1["path"] == ("GET_RS", "GET_MP", "STOP")  # canonical head order


def test_get_calls_reader_only_and_stop_calls_terminal_once():
    env, calls = toy_env()
    run(env, ["GET_ME", "GET_MS", "STOP"])
    assert calls["read"] == ["ME", "MS"] and len(calls["terminal"]) == 1


def test_replay_is_deterministic():
    env, _ = toy_env()
    seq = ["GET_MS", "GET_RS", "STOP"]
    assert run(env, seq) == run(env, seq)


def test_observation_exposes_only_read_text_and_no_private_ids():
    env, _ = toy_env()
    s = env.reset()
    obs0 = env.observe(s)
    assert obs0["acquired"] == () and "STOP" in obs0["action_mask"]
    s, _, _, info = env.step(s, "GET_MP")
    obs1 = env.observe(s)
    flat = repr(obs1)
    assert "rec-MP" not in flat and "reward" not in flat and "key" not in flat
    assert obs1["acquired"][0]["reading_text"] == "text-MP" and obs1["acquired"][0]["ordinal"] == 1
    assert "text-RS" not in flat  # unread text never appears
    assert info["record_ids"] == ("rec-MP",)  # private ids go to the executor only
    assert "GET_MP" not in obs1["action_mask"]


def test_dp_matches_brute_force_on_random_tables():
    rng = random.Random(17)
    for _ in range(300):
        rewards = {m: rng.choice([0.0, 0.25, 0.5, rng.random()]) for m in range(E.N_SUBSETS)}
        avail = rng.randrange(E.N_SUBSETS)
        max_gets = rng.randint(0, 4)
        cost = {h: rng.choice([0.0, 0.01, 0.1]) for h in E.HEADS}
        dp = E.solve_dp(rewards, available=avail, max_gets=max_gets, step_cost=cost)
        best, paths = E.brute_force_best(rewards, available=avail, max_gets=max_gets,
                                         step_cost=cost)
        assert abs(dp.root_value - best) < 1e-9
        assert {E.mask_of(p) for p in paths} == set(dp.optimal_terminals)


def test_dp_hand_table_and_ties():
    r = {m: 0.0 for m in range(E.N_SUBSETS)}
    r[E.mask_of(["MP"])] = 0.8
    r[E.mask_of(["MP", "ME"])] = 0.9
    r[0] = 0.5
    dp = E.solve_dp(r)
    assert dp.root_value == 0.9
    assert set(dp.optimal_actions[0]) == {"GET_MP", "GET_ME"}  # both orders reach {MP,ME}
    assert dp.optimal_actions[E.mask_of(["MP", "ME"])] == ("STOP",)
    assert dp.optimal_terminals == (E.mask_of(["MP", "ME"]),)


def test_dp_respects_availability_and_budget():
    r = {m: float(bin(m).count("1")) for m in range(E.N_SUBSETS)}
    dp = E.solve_dp(r, available=E.mask_of(["RS", "ME"]), max_gets=1)
    assert dp.root_value == 1.0
    assert set(dp.optimal_terminals) == {E.mask_of(["RS"]), E.mask_of(["ME"])}


def test_policy_following_dp_achieves_dp_value_in_env():
    rng = random.Random(29)
    for _ in range(50):
        rewards = {m: rng.random() for m in range(E.N_SUBSETS)}
        env, _ = toy_env(rewards=rewards)
        dp = E.solve_dp(rewards)
        s, total = env.reset(), 0.0
        while not s.done:
            a = dp.optimal_actions[s.mask][0]
            s, r, _, _ = env.step(s, a)
            total += r
        assert abs(total - dp.root_value) < 1e-9


def test_interval_dp_never_claims_exact_optimum_under_overlap():
    lo = {m: 0.0 for m in range(E.N_SUBSETS)}
    hi = {m: 0.0 for m in range(E.N_SUBSETS)}
    lo[0], hi[0] = 0.4, 0.6
    lo[E.mask_of(["MS"])], hi[E.mask_of(["MS"])] = 0.5, 0.7
    out = E.interval_dp(lo, hi, available=E.mask_of(["MS"]), max_gets=1)
    assert out["certainly_optimal"] == ()
    assert set(out["possibly_optimal"]) == {"STOP", "GET_MS"}
    lo[E.mask_of(["MS"])], hi[E.mask_of(["MS"])] = 0.8, 0.9
    out = E.interval_dp(lo, hi, available=E.mask_of(["MS"]), max_gets=1)
    assert out["certainly_optimal"] == ("GET_MS",)


# ------------------------------------------------------------------ negatives

def test_repeated_get_is_illegal_and_state_unchanged():
    env, calls = toy_env()
    s, _, _, _ = env.step(env.reset(), "GET_RS")
    with pytest.raises(E.IllegalAction):
        env.step(s, "GET_RS")
    assert calls["read"] == ["RS"]


def test_empty_head_is_masked_and_illegal():
    env, calls = toy_env(availability={"RS": 0, "MP": 1, "ME": 1, "MS": 1})
    s = env.reset()
    assert "GET_RS" not in env.legal_actions(s)
    with pytest.raises(E.IllegalAction):
        env.step(s, "GET_RS")
    assert calls["read"] == []


def test_over_capacity_get_is_masked():
    env, calls = toy_env(capacity=105, unit_tokens={"MS": 50, "MP": 5})
    s = env.reset()
    assert "GET_MS" not in env.legal_actions(s) and "GET_MP" in env.legal_actions(s)
    with pytest.raises(E.IllegalAction):
        env.step(s, "GET_MS")
    assert calls["read"] == []


def test_action_after_stop_and_unknown_action_are_illegal():
    env, _ = toy_env()
    s, _, done, _ = env.step(env.reset(), "STOP")
    assert done and env.legal_actions(s) == ()
    with pytest.raises(E.IllegalAction):
        env.step(s, "STOP")
    with pytest.raises(E.IllegalAction):
        env.step(env.reset(), "EXPAND_MS(1)")  # Phase-2 only


def test_missing_terminal_is_pending_not_zero():
    env, _ = toy_env(rewards={0: 0.1})
    s, _, _, _ = env.step(env.reset(), "GET_ME")
    with pytest.raises(E.PendingTerminal):
        env.step(s, "STOP")
    with pytest.raises(E.PendingTerminal):
        E.solve_dp({0: 0.1})


def test_reader_without_unit_fails_closed():
    env = E.FiniteHeadEnv(availability={h: 1 for h in E.HEADS}, reader=lambda h: None,
                          terminal_lookup=lambda m: E.TerminalOutcome(0.0), prefix_tokens=1)
    with pytest.raises(E.IllegalAction):
        env.step(env.reset(), "GET_MP")


def test_unknown_head_in_availability_is_rejected():
    with pytest.raises(ValueError):
        E.FiniteHeadEnv(availability={"XX": 1}, reader=lambda h: None,
                        terminal_lookup=lambda m: None, prefix_tokens=1)
