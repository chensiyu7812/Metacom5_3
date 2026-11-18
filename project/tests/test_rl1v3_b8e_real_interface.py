"""B6e -> B8e interface on REAL bank-v0 terminals (WS-A PrefixPort; test-only char tokenizer).

TerminalKeys / ExecutionTraces come from the real bank-v0 read path and are checked against the B5
replay of the same prefix.  NeedCard, checklist, J1 answers and therefore every ER value here are
FIXTURES (labelled), never G0 terminals; training runs are a few steps to show the interface only.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from metacom_pm.rl1v3 import contracts as K
from metacom_pm.rl1v3.checklist import writer_v3 as CW3
from metacom_pm.rl1v3.checklist.ledger import ChecklistLedger, ChecklistOrderError
from metacom_pm.rl1v3.env import finite_head as E
from metacom_pm.rl1v3.env.bank_replay_v2 import replay_prefix
from metacom_pm.rl1v3.env.c0_binding import C0FiniteHeadEnv, TerminalIdentity, TerminalTable
from metacom_pm.rl1v3.evaluate import terminal_registry as TR
from metacom_pm.rl1v3.io import sha256_text
from metacom_pm.rl1v3.judge import aggregate_v3 as AG3, engineering_reward_v2 as ER2, engineering_reward_v3 as ER3
from metacom_pm.rl1v3.judge import protocol_v3 as JP3
from metacom_pm.rl1v3.policies.encoder import ObservationEncoder
from metacom_pm.rl1v3.train import ppo as PPO, real_instances as RI, supervised as S
from metacom_pm.rl1v3.train.common import JsonlLog, param_sha256, seed_everything
from rl1v3_b2_attribution_cases import v3_answer
from test_rl1v3_b5_bank_replay_v2 import CFG, CharTokenizer

ROOT = Path(__file__).resolve().parents[2]
R16, MP8 = "01c44f464e0e", "ab3d17407ca4"           # B6e-v3 selections: all heads / MP without legal candidates
PLAN = dict(g_id="g0-FIXTURE-not-a-real-G0", decode_id="greedy-fixture")
REPLY = "That sounds really hard. What feels most pressing tonight?"


@pytest.fixture(scope="module")
def world():
    from metacom_pm.rl1v3.bank import v0_port as AP
    from metacom_pm.rl1v3.env import a1b_port as P
    bank = P.load_bank(ROOT, **CFG)
    cov = {r["prefix_id"][:12]: r for r in map(json.loads, (ROOT / "project/outputs/pm_rl1/v3/B1/coverage_sample_v1.jsonl").read_text().splitlines())}
    out = {}
    for short in (R16, MP8):
        prefix = P.prefix_for(bank.registry, cov[short])
        fa = AP.PortFactory(bank, CharTokenizer(), dict(g_id="g-test-not-frozen", decode_id="not_run",
                                                        step2_id="none-v0-read-replay", output_reserve_tokens=320))
        rep = replay_prefix(lambda f=fa, p=prefix: f.for_prefix(p))
        assert rep["passed"], rep["failures"]
        out[short] = dict(prefix=prefix, factory=lambda f=fa, p=prefix: f.for_prefix(p), rep=rep,
                          binding=TR.ReplayBinding.from_report(rep))
    return out


def plan_identity(rep):
    i = rep["identity"]
    return TerminalIdentity(i["bank_version"], i["index_version"], i["renderer_id"], i["step2_id"], **PLAN)


def keygen_env(w, ident):
    port = w["factory"]()
    return C0FiniteHeadEnv(prefix=port.prefix, history_sessions=port.prefix.cutoff_rank,
                           availability=dict(port.availability()), read=lambda h, acquired: port.read(h, acquired=acquired),
                           identity=ident, table=TerminalTable({}, table_id="keygen"), prefix_tokens=port.base_tokens,
                           read_takes_acquired=True, dynamic_mask=port.action_mask)


def terminals(w, ident):
    env = keygen_env(w, ident)
    for m in w["binding"].reachable:
        s = RI._replay(env, m)
        yield m, env.terminal_key(s), env.execution_trace(s), s


def fixture_card(prefix):
    card = K.NeedCard(prefix_id=prefix.prefix_id, stratum="none", history_items=(), failed_or_rejected=(),
                      outdated_facts=(), method_need=None, risk_flags=(), writer_identity="FIXTURE-not-a-writer",
                      input_sha256="0" * 64, span_validation_status="verified")
    return card, CW3.build(card)


def er_attempt(w, card, cl, key, trace, s, rows=None):
    jid = JP3.JudgeIdentityV3(role="J1", model_id="FIXTURE-judge", model_sha256="1" * 64, decode_id="greedy")
    j1 = JP3.run(lambda m: v3_answer(cl, rows=rows or {}), jid, w["prefix"].turns, REPLY, cl, env_readings(s))
    return ER3.attempt(key=key, subset=TR.subset_name(s.mask), stratum=card.stratum, trace=trace, checklist=cl,
                       needcard=card, evidence_validation="verified", response=REPLY, finish_reason="natural_stop",
                       verdicts=AG3.item_verdicts(cl, j1, None), j1_identity=j1.identity, expected_j1_identity=jid.id,
                       input_tokens=s.input_tokens, prefix_tokens=0, j1_ledger=JP3.ledger_summary(j1))


def env_readings(s):
    return tuple(r.public_view for r in s.readings)


def build(tmp_path, w, *, skip=(), refuse=(), floor=()):
    ident = plan_identity(w["rep"])
    reg = TR.TerminalRegistry(identity=ident, ledger=ChecklistLedger(tmp_path / w["prefix"].prefix_id[:8]),
                              table_tag="FIXTURE")
    reg.bind_prefix(w["prefix"], w["binding"])
    card, cl = fixture_card(w["prefix"])
    reg.ledger.freeze(cl, card)
    s_item = next(i.item_id for i in cl.items if i.category == "S")
    for m, key, trace, s in terminals(w, ident):
        if m in skip:
            continue
        reg.register(w["prefix"].prefix_id, key, trace, sha256_text(REPLY))
        rows = {s_item: ("uncertain", [])} if m in refuse else {s_item: ("fail", [])} if m in floor else None
        reg.add_er(w["prefix"].prefix_id, er_attempt(w, card, cl, key, trace, s, rows))
    table, rep = reg.table(w["prefix"].prefix_id)
    return reg, RI.RealInstance(instance_id=w["prefix"].prefix_id[:12], port_factory=w["factory"], identity=ident,
                                table=table, report=rep, reachable=w["binding"].reachable)


# ------------------------------------------------------------------ real keys / traces and the registry

def test_real_keys_match_the_formal_replay_and_reachability(world):
    assert len(world[R16]["binding"].reachable) == 16 and len(world[MP8]["binding"].reachable) == 8
    for w in world.values():
        ident = plan_identity(w["rep"])
        for m, key, trace, _ in terminals(w, ident):
            trace.verify_key(key)
            assert key.g_id == PLAN["g_id"] and key.sha256 != w["rep"]["key_by_subset"][TR.subset_name(m)]
            assert w["binding"].replay_key_sha(w["prefix"], key) == w["rep"]["key_by_subset"][TR.subset_name(m)]


def test_candidates_need_a_frozen_checklist_and_a_replay_matching_key(world, tmp_path):
    w = world[R16]
    ident = plan_identity(w["rep"])
    reg = TR.TerminalRegistry(identity=ident, ledger=ChecklistLedger(tmp_path / "l"))
    reg.bind_prefix(w["prefix"], w["binding"])
    m, key, trace, s = next(terminals(w, ident))
    with pytest.raises(ChecklistOrderError):
        reg.register(w["prefix"].prefix_id, key, trace, "r" * 64)
    card, cl = fixture_card(w["prefix"])
    reg.ledger.freeze(cl, card)
    other = TerminalIdentity(**dict(ident.__dict__, g_id="another-G0"))
    _, k2, t2, _ = next(terminals(w, other))
    with pytest.raises(TR.RegistryError, match="identity"):
        reg.register(w["prefix"].prefix_id, k2, t2, "r" * 64)
    _, kb, _, _ = list(terminals(w, ident))[3]
    with pytest.raises(TR.RegistryError, match="reproduce"):
        reg.register(w["prefix"].prefix_id, kb, trace, "r" * 64)
    reg.register(w["prefix"].prefix_id, key, trace, "r" * 64)
    with pytest.raises(TR.RegistryError, match="write-once"):
        reg.register(w["prefix"].prefix_id, key, trace, "r" * 64)


def test_only_er_v3_engineering_records_enter_and_gsc_never(world, tmp_path):
    w = world[R16]
    ident = plan_identity(w["rep"])
    reg = TR.TerminalRegistry(identity=ident, ledger=ChecklistLedger(tmp_path / "l"))
    reg.bind_prefix(w["prefix"], w["binding"])
    card, cl = fixture_card(w["prefix"])
    reg.ledger.freeze(cl, card)
    m, key, trace, s = next(terminals(w, ident))
    reg.register(w["prefix"].prefix_id, key, trace, "r" * 64)
    good = er_attempt(w, card, cl, key, trace, s)
    for bad in (dict(good, record=dict(good["record"], protocol=ER2.PROTOCOL)),
                dict(good, record=dict(good["record"], gsc_lower=0.5)),
                dict(good, record=dict(good["record"], is_gsc=True))):
        with pytest.raises(TR.RegistryError, match="ER-v3"):
            reg.add_er(w["prefix"].prefix_id, bad)
    with pytest.raises(TR.RegistryError, match="GSC"):
        reg.add_er(w["prefix"].prefix_id, object())
    with pytest.raises(TR.RegistryError, match="unregistered"):
        reg.add_er(w["prefix"].prefix_id, dict(good, key_sha256="0" * 64))
    reg.add_er(w["prefix"].prefix_id, good)
    table, rep = reg.table(w["prefix"].prefix_id)
    assert rep["computed"] == 1 and rep["complete"] is False and table.table_id.endswith("partial")
    assert rep["is_gsc"] is False and rep["missing_or_refused_filled_with_zero"] is False


# ------------------------------------------------------------------ pending / partial tables in B8e

def test_refused_and_missing_terminals_stay_pending_and_partial_is_not_an_oracle(world, tmp_path):
    w = world[MP8]
    refuse, skip = w["binding"].reachable[1], w["binding"].reachable[2]
    reg, inst = build(tmp_path, w, refuse=(refuse,), skip=(skip,))
    assert inst.report["refused"] == 1 and inst.report["refusal_reasons"] == {"hard_safety_uncertain": 1}
    assert inst.report["missing"] == [TR.subset_name(skip)] and not inst.complete
    env = RI.make_env(inst)
    with pytest.raises(E.PendingTerminal):
        env.step(RI._replay(env, refuse), E.STOP)
    with pytest.raises(E.PendingTerminal):
        env.step(RI._replay(env, skip), E.STOP)
    for f in (RI.oracle_dp, RI.feasible_subsets):
        with pytest.raises(RI.IncompleteTable):
            f(inst)
    kept, excluded = RI.trainable([inst], "PPO")
    assert kept == [] and excluded[0]["reason"] == "partial_terminal_table"


def test_complete_tables_run_bc_oneshot_ppo_and_notext_through_the_real_env(world, tmp_path):
    insts = []
    for name, w in world.items():
        floor = (w["binding"].reachable[-1],) if name == R16 else ()
        insts.append(build(tmp_path / name, w, floor=floor)[1])
    assert all(i.complete for i in insts)
    r16 = insts[0]
    assert r16.report["safety_floor"] == 1 and r16.rewards[r16.reachable[-1]] == -1.0
    assert np.isnan(insts[1].rewards[E.mask_of(("MP",))])                     # unreachable: NaN, masked, never 0
    dp = RI.oracle_dp(r16)
    assert dp.root_value == pytest.approx(1.0) and dp.optimal_terminals == (0,)  # fixture: every GET costs 0.01
    text = RI.HashingTextEncoder()
    log = JsonlLog(tmp_path / "curves.jsonl")
    for arm, use_text in (("Seq-BC", True), ("Seq-BC-NoText", False)):
        kept, excluded = RI.trainable(insts, arm)
        assert len(kept) == 2 and not excluded
        enc = ObservationEncoder(text, text.dim, use_text=use_text)
        g = seed_everything(17)
        bc, _, info = S.train_bc(kept, kept, RI.make_env, enc, RI.oracle_dp, gen=g, epochs=1, lr=1e-3, batch=8,
                                 log=log, method=arm)
        init = param_sha256(bc)
        res = PPO.train_ppo(bc, kept, kept, RI.make_env, enc,
                            PPO.PPOConfig(rounds=1, steps_per_round=8, n_envs=2, epochs=1, minibatch=8, eval_every=1,
                                          ckpt_every=1), gen=g, rng=np.random.default_rng(17), log=log, ckpt_dir=None,
                            method="PPO" + arm[6:])
        assert res["optimizer_steps"] >= 1 and res["final_param_sha256"] != init     # PPO stepped the real env
    enc = ObservationEncoder(text, text.dim)
    m, _, info = S.train_oneshot(insts, insts, RI.make_env, enc, RI.feasible_subsets, gen=seed_everything(17),
                                 epochs=1, lr=1e-3, batch=8, log=log)
    assert info["optimizer_steps"] >= 1
