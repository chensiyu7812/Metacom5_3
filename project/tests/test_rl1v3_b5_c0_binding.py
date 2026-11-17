"""B5 bound to C0 0.2.x: full TerminalKey lookup, trace order, isolation.

Uses an in-memory MOCK bank (four fixed reading units), clearly not bank-v0;
the real bank-v0 replay test is added when WS-A A1b delivers ``read``.
Skipped on branches without C0 0.2.x.
"""
from __future__ import annotations

import dataclasses
import itertools
import json

import numpy as np
import pytest

K = pytest.importorskip("metacom_pm.rl1v3.contracts")
IO = pytest.importorskip("metacom_pm.rl1v3.io")
if not str(IO.SCHEMA_VERSION).startswith("pmrl1v3-contracts-0.2"):
    pytest.skip("binding targets C0 0.2.x", allow_module_level=True)

from metacom_pm.rl1v3.env import c0_binding as B  # noqa: E402
from metacom_pm.rl1v3.env import finite_head as E  # noqa: E402
from metacom_pm.rl1v3.policies.encoder import ObservationEncoder  # noqa: E402

VIEW = {"RS": "method", "MP": "assertion", "ME": "event", "MS": "sum"}
GROUPS = {"RS": ("rs:card1",), "MP": ("mp:a", "mp:b"), "ME": ("me:e1",), "MS": ("ms:sum3",)}
ID = B.TerminalIdentity("bank-v0-mock", "idx-mock", "render-1", "step2-none", "g0-mock", "greedy")


def prefix(text="I tried calling my sister but it went badly"):
    turns = (K.SourceTurn(turn_index=0, role="supporter", text="Welcome back."),
             K.SourceTurn(turn_index=1, role="seeker", text=text))
    return K.PrefixSpec.create(owner_id="p1", session_id="p1_conv_3", cut_turn=1, turns=turns,
                               cutoff_rank=2, timestamp="2024-02-01", dataset="evo",
                               family_id="evoemo_owner:p1",
                               ancestor_family_ids=("evoemo_owner:p1", "esconv:esconv_0007"))


def mock_read(calls, fail=()):
    def read(head):
        calls.append(head)
        if head in fail:
            return K.ReadFailure(reason="capacity", detail="mock", input_tokens_unchanged=50,
                                 elapsed_ms=1.0)
        v = K.ReadingView(head=head, view=VIEW[head], ordinal=1, reading_text=f"{head} body",
                          reported_at=None, tokens=5, stage="attempted" if head == "ME" else None)
        return K.ReadSuccess(reading=v, record_ids=GROUPS[head], input_tokens_before=50,
                             input_tokens_after=55, native_context_tokens=8192,
                             output_reserve_tokens=320, elapsed_ms=2.0)
    return read


def table(p, rewards=None, identity=ID, drop=()):
    rewards = rewards or {m: 0.5 + 0.1 * bin(m).count("1") for m in range(E.N_SUBSETS)}
    rows = {B.subset_key(p, identity, GROUPS, m).sha256: E.TerminalOutcome(rewards[m])
            for m in range(E.N_SUBSETS) if m not in drop}
    return B.TerminalTable(rows, table_id="mock")


def env(p=None, calls=None, fail=(), tbl=None, identity=ID, avail=None):
    p = p or prefix()
    return B.C0FiniteHeadEnv(prefix=p, history_sessions=2,
                             availability=avail or {h: 3 for h in E.HEADS},
                             read=mock_read(calls if calls is not None else [], fail),
                             identity=identity, table=tbl or table(p), prefix_tokens=50)


def run(e, actions):
    s, tot, info = e.reset(), 0.0, None
    for a in actions:
        s, r, _, info = e.step(s, a)
        tot += r
    return s, tot, info


def test_same_subset_any_order_hits_one_canonical_key_and_trace_keeps_order():
    e = env()
    s1, r1, i1 = run(e, ["GET_ME", "GET_RS", "STOP"])
    s2, r2, i2 = run(e, ["GET_RS", "GET_ME", "STOP"])
    assert i1["key_sha256"] == i2["key_sha256"] and r1 == r2
    assert e.terminal_key(s1).ordered_path == ("GET_RS", "GET_ME", "STOP")
    assert e.execution_trace(s1).ordered_path == ("GET_ME", "GET_RS", "STOP")
    assert e.execution_trace(s2).ordered_path == ("GET_RS", "GET_ME", "STOP")
    assert e.terminal_key(s1).acquired == (GROUPS["RS"], GROUPS["ME"])


def test_all_65_orders_map_to_16_keys():
    e = env()
    keys, traces = set(), set()
    for k in range(5):
        for seq in itertools.permutations(E.HEADS, k):
            s, _, info = run(e, [E.GET[h] for h in seq] + ["STOP"])
            keys.add(info["key_sha256"])
            traces.add(e.execution_trace(s).sha256)
    assert (len(keys), len(traces)) == (16, 65)


def test_get_reads_only_and_stop_looks_up_once():
    calls = []
    e = env(calls=calls)
    s, _, _ = run(e, ["GET_MP"])
    assert calls == ["MP"] and not s.done
    s, _, _, info = e.step(s, "STOP")
    assert calls == ["MP"] and info["path"] == ("GET_MP", "STOP")


def test_missing_terminal_is_pending_not_zero():
    p = prefix()
    e = env(p=p, tbl=table(p, drop=(E.mask_of(["MS"]),)))
    s, _, _ = run(e, ["GET_MS"])
    with pytest.raises(E.PendingTerminal):
        e.step(s, "STOP")


def test_other_identity_never_reuses_rewards():
    p = prefix()
    other = dataclasses.replace(ID, g_id="g1-mock")
    e = env(p=p, tbl=table(p), identity=other)
    with pytest.raises(E.PendingTerminal):
        e.step(e.reset(), "STOP")
    q = prefix(text="a different current message")
    e2 = env(p=q, tbl=table(p))
    with pytest.raises(E.PendingTerminal):
        e2.step(e2.reset(), "STOP")


def test_read_failure_leaves_state_unchanged():
    e = env(fail=("MS",))
    s0 = e.reset()
    s1, _, _, _ = e.step(s0, "GET_MP")
    with pytest.raises(B.ReadRejected):
        e.step(s1, "GET_MS")
    assert s1.order == ("MP",) and len(s1.readings) == 1 and s1.input_tokens == 55
    s2, _, _, _ = e.step(s1, "GET_RS")
    assert s2.order == ("MP", "RS")


def test_illegal_actions_raise_and_do_not_mutate():
    e = env(avail={"RS": 0, "MP": 1, "ME": 1, "MS": 1})
    s = e.reset()
    for bad in ("GET_RS", "EXPAND_MS(1)", "GET_XX"):
        with pytest.raises(E.IllegalAction):
            e.step(s, bad)
    assert s == e.reset()
    s, _, _ = run(e, ["GET_MP"])
    with pytest.raises(E.IllegalAction):
        e.step(s, "GET_MP")


def test_observation_is_c0_and_contains_only_read_text():
    e = env()
    s = e.reset()
    o0 = e.observe(s)
    assert isinstance(o0, K.Observation) and o0.acquired == ()
    s, _, _ = run(e, ["GET_ME", "GET_MP"])
    o = e.observe(s)
    assert [v.ordinal for v in o.acquired] == [1, 2]
    assert [v.head for v in o.acquired] == ["ME", "MP"]
    wire = IO.canonical_json(o)
    for secret in ("mp:a", "me:e1", "rs:card1", "RS body", "MS body", "bank-v0-mock", "g0-mock"):
        assert secret not in wire
    assert "ME body" in wire and "MP body" in wire
    assert IO.decode_contract(K.Observation, wire) == o
    assert "GET_ME" not in o.action_mask and "GET_MP" not in o.action_mask
    assert all(t.role in ("seeker", "supporter") for t in o.prefix.turns)
    assert o.prefix.turns[-1].text.startswith("I tried")  # prefix ends at the cut


def test_dp_over_c0_table_matches_bruteforce_and_env_execution():
    rng = np.random.default_rng(3)
    p = prefix()
    rewards = {m: float(rng.random()) for m in range(E.N_SUBSETS)}
    e = env(p=p, tbl=table(p, rewards))
    dp = E.solve_dp(rewards)
    best, _ = E.brute_force_best(rewards)
    assert abs(dp.root_value - best) < 1e-12
    s, tot = e.reset(), 0.0
    while not s.done:
        s, r, _, _ = e.step(s, dp.optimal_actions[s.mask][0])
        tot += r
    assert abs(tot - dp.root_value) < 1e-12


def test_encoder_consumes_c0_observation():
    e = env()
    s, _, _ = run(e, ["GET_MS"])
    enc = ObservationEncoder(lambda t: np.full(8, float(len(t) % 7), dtype=np.float32), 8)
    v = enc(e.observe(s))
    assert v.shape == (enc.dim,) and enc.mask(e.observe(s)).sum() == 4
    nt = ObservationEncoder(lambda t: np.ones(8, dtype=np.float32), 8, use_text=False)
    assert nt(e.observe(s))[8 + 8 + 4:8 + 8 + 4 + 32].sum() == 0
