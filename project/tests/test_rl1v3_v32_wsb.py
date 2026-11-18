"""WS-B V3.2 P0-P2 CPU tests: as-of audit/checker, bindings, visibility, research env, P2 protocol,
reward qualification, baselines fairness and latency schema.  Real preserved snapshots + fixtures;
no model, tokenizer download, GPU or network."""
from __future__ import annotations

import ast
import copy
import dataclasses
import json
from pathlib import Path

import numpy as np
import pytest

from metacom_pm.rl1v3.asof import binding as AB, check as CK, legacy_audit as LA, visibility as VIS
from metacom_pm.rl1v3.bank.v0_port import PrefixPort, load_bank
from metacom_pm.rl1v3.env import finite_head as E, research_v32 as RV
from metacom_pm.rl1v3.env.c0_binding import C0FiniteHeadEnv, TerminalIdentity, TerminalTable
from metacom_pm.rl1v3.evaluate import baselines_v32 as BL, latency_v1 as LT, resource_value_v32 as P2
from metacom_pm.rl1v3.io import canonical_json, object_sha256
from metacom_pm.rl1v3.judge import reward_qualification_v1 as RQ
from metacom_pm.rl1v3.render.v0 import messages

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "project"
ROWS = PROJECT / "data/paper1_public_memory/es_memeval_public_multi_view_session_results_v1.jsonl"
CENSUS = PROJECT / "outputs/pm_rl1/v3/B0/prefix_census.jsonl"
AB3D17 = "ab3d17407ca4f1c4b00d5532406ffcc74fa0732fd5ffeef4fd764099ea463f6e"


class TestTokenizer:
    __test__ = False
    identity = "test-only-codepoints-v32"
    native_context_tokens = 200000

    def count(self, text):
        return len(text)

    def prompt_tokens(self, prefix, readings):
        return len(canonical_json(messages(prefix, readings)))


def jl(p):
    return [json.loads(x) for x in Path(p).read_text().splitlines()]


@pytest.fixture(scope="module")
def world():
    bank, _ = load_bank(ROOT)
    rows = jl(ROWS)
    pools = LA.MPPools(rows, bank)
    census = {c["prefix_id"]: c for c in jl(CENSUS)}
    return bank, rows, pools, census


def prefix_of(world, pid):
    bank, _, _, census = world
    c = census[pid]
    return bank.registry.prefix(c["owner_id"], c["session_id"], c["cut_turn"])


def owner_cut_prefixes(world, owner):
    bank, _, _, census = world
    first = {}
    for c in census.values():
        if c["owner_id"] == owner and (c["session_id"] not in first or c["cut_turn"] < first[c["session_id"]]["cut_turn"]):
            first[c["session_id"]] = c
    return [bank.registry.prefix(owner, c["session_id"], c["cut_turn"])
            for c in sorted(first.values(), key=lambda c: c["cutoff_rank"])]


def env_for(world, prefix, ident=None):
    bank = world[0]
    port = PrefixPort(bank, prefix, TestTokenizer(), g_id="test-g", decode_id="not-run")
    ident = ident or TerminalIdentity(**{k: port.identity[k] for k in
                                         ("bank_version", "index_version", "renderer_id", "step2_id", "g_id", "decode_id")})
    env = C0FiniteHeadEnv(prefix=prefix, history_sessions=prefix.cutoff_rank, availability=dict(port.availability()),
                          read=lambda h, acquired, p=port: p.read(h, acquired=acquired), identity=ident,
                          table=TerminalTable({}, table_id="t"), prefix_tokens=port.base_tokens,
                          read_takes_acquired=True, dynamic_mask=port.action_mask)
    return env, port


def legacy_binding(world, prefix, env):
    return AB.legacy_bank_v0_binding(world[0].registry, prefix, identity=dataclasses.asdict(env.identity),
                                     snapshot_sha256="0" * 64, external_snapshot="esconv-train",
                                     visibility_policy=VIS.whitelist_manifest()["sha256"])


# ------------------------------------------------------------------ legacy as-of audit
def test_compiler_inputs_were_strictly_past(world):
    bank, rows, _, _ = world
    r = LA.compiler_frontier(rows, bank.registry)
    assert r["sessions"] == 401 and r["reproduced"] == 401 and not r["mismatches"]
    assert r["unit_session_or_rank_mismatch"] == 0


def test_bank_v0_mp_pool_is_a_subset_of_the_asof_pool(world):
    _, _, pools, census = world
    for c in list(census.values())[::97]:
        assert pools.legacy(c["owner_id"], c["cutoff_rank"]) <= pools.asof(c["owner_id"], c["cutoff_rank"])


def test_prefix_extension_breaks_the_legacy_projection_not_the_asof_rule(world):
    bank, rows, pools, _ = world
    changed = 0
    for c in range(1, 23):
        changed += pools.legacy_at_horizon("p11", c, c) != pools.legacy_at_horizon("p11", c, 99)
        # the as-of pool from a writer that never saw sessions >= c is identical
        truncated = [r for r in rows if r["owner_id"] == "p11"
                     and bank.registry.entry("p11", r["session_id"]).source.chronological_rank < c]
        assert LA.asof_pool(LA.slots_of(truncated), pools.moved_to_me, "p11", c) == pools.asof("p11", c)
    assert changed > 0


def test_ab3d17_mp_is_only_unreachable_under_the_legacy_projection(world):
    x = LA.counterfactual_top1(world[2], world[0], prefix_of(world, AB3D17))
    assert x["legacy_pool"] == 0 and x["asof_pool"] > 0 and x["top1"] == "legacy_has_no_candidate"


# ------------------------------------------------------------------ exchange checker
@pytest.fixture(scope="module")
def p11_exchanges(world):
    bank, _, pools, _ = world
    ps = owner_cut_prefixes(world, "p11")[:12]
    return ps, CK.build_exchange("legacy_bank_v0", pools, bank, ps), CK.build_exchange("reference_chronological", pools, bank, ps)


def test_controls_negative_and_positive(world, p11_exchanges):
    _, leg, ref = p11_exchanges
    r_leg, r_ref = CK.run(leg, world[0].registry), CK.run(ref, world[0].registry)
    assert any(p.startswith("X5a") for p in r_leg["prefix_extension_problems"]) and not r_leg["passed"]
    assert r_ref["passed"] and r_ref["cutoffs_passed"] == r_ref["cutoffs"]


def _first_mem(cut):
    return next(r for r in cut["records"] if r["head"] == "ME")


@pytest.mark.parametrize("mutation,code", [
    ("future_span", "X2_span_future"), ("known_early", "X3_known_before_report"), ("event_time", "X4_event_time"),
    ("frontier", "X1_frontier_not_exact"), ("snapshot", "X6_snapshot_sha_not_reproduced"),
    ("stream_batch", "X6_stream_batch_differ"), ("rs_owner", "X7_rs_has_owner"), ("span_text", "X2_span_text"),
])
def test_checker_rejects_mechanical_violations(world, p11_exchanges, mutation, code):
    bank = world[0]
    _, _, ref = p11_exchanges
    ex = copy.deepcopy(ref)
    cut = ex["cutoffs"][-1]
    rec = _first_mem(cut)
    if mutation == "future_span":
        later = next(e.source for e in bank.registry.entries if e.source.owner_id == "p11"
                     and e.source.chronological_rank > cut["cutoff_rank"])
        rec["source_refs"][0].update(session_id=later.session_id, source_rank=later.chronological_rank)
    elif mutation == "known_early":
        rec["known_rank"] = rec["source_refs"][0]["source_rank"] - 1
    elif mutation == "event_time":
        rec["event_time"] = "2024-03"
    elif mutation == "frontier":
        cut["source_frontier"] = cut["source_frontier"][:-1]
    elif mutation == "snapshot":
        cut["snapshot_sha256"] = "f" * 64
    elif mutation == "stream_batch":
        cut.update(batch_snapshot_sha256="a" * 64, stream_snapshot_sha256="b" * 64)
    elif mutation == "rs_owner":
        cut["records"].append(dict(record_id="rs::x", head="RS", owner_id="p11", content_sha256="0", source_refs=[],
                                   known_rank=0, ready_rank=0))
    elif mutation == "span_text":
        rec["source_refs"][0]["exact_quote"] += " (paraphrased)"
    if mutation not in ("snapshot", "stream_batch"):
        cut["snapshot_sha256"] = CK.snapshot_sha256(cut["records"])
    res = CK.run(ex, bank.registry)
    probs = [p for r in res["rows"] for p in r["problems"]]
    assert any(p.startswith(code) for p in probs), probs


def test_rewritten_past_and_vanished_records_are_detected(world, p11_exchanges):
    _, _, ref = p11_exchanges
    ex = copy.deepcopy(ref)
    last = ex["cutoffs"][-1]
    _first_mem(last)["content_sha256"] = "rewritten"                 # an early-ready record changed later
    assert any(p.startswith("X5b") for p in CK.prefix_extension(ex["cutoffs"]))
    ex = copy.deepcopy(ref)
    last = ex["cutoffs"][-1]
    victim = next(r for r in ex["cutoffs"][-3]["records"] if r["head"] == "MP")
    last["records"] = [r for r in last["records"] if r["record_id"] != victim["record_id"]]
    for r in last["records"]:
        r["supersedes"] = [x for x in (r.get("supersedes") or ()) if x != victim["record_id"]]
    assert any(p.startswith("X5c") for p in CK.prefix_extension(ex["cutoffs"]))


# ------------------------------------------------------------------ bindings
def test_legacy_binding_is_valid_but_cannot_be_promoted(world):
    prefix = prefix_of(world, AB3D17)
    env, _ = env_for(world, prefix)
    b = legacy_binding(world, prefix, env)
    assert AB.validate(b, world[0].registry, prefix) == []
    probs = AB.validate(dataclasses.replace(b, tier="research_candidate"), world[0].registry, prefix)
    assert "legacy_writer_cannot_be_research" in probs and "research_tier_requires_chronological_writer" in probs
    assert any(p.startswith("placeholder_identity:decode_id") for p in probs)


def test_binding_frontier_must_be_exact_and_strictly_past(world):
    prefix = prefix_of(world, AB3D17)
    env, _ = env_for(world, prefix)
    b = legacy_binding(world, prefix, env)
    cur = world[0].registry.entry(prefix.owner_id, prefix.session_id)
    bad = dataclasses.replace(b, source_frontier=b.source_frontier + (AB.FrontierEntry(
        cur.source_id, prefix.session_id, prefix.cutoff_rank, None, cur.source.transcript_sha256, prefix.cutoff_rank + 1),))
    probs = AB.validate(bad, world[0].registry, prefix)
    assert any(p.startswith("frontier_not_exact") for p in probs)
    assert "frontier_contains_current_session" in probs and any(p.startswith("frontier_future") for p in probs)
    assert AB.validate(dataclasses.replace(b, source_frontier=b.source_frontier[:-1]), world[0].registry, prefix)


def test_composite_key_isolates_writer_and_snapshot(world):
    prefix = prefix_of(world, AB3D17)
    env, _ = env_for(world, prefix)
    b = legacy_binding(world, prefix, env)
    b2 = dataclasses.replace(b, writer_identity="chrono-writer-v1", writer_kind="chronological_asof")
    b3 = dataclasses.replace(b, tier_reason="relabelled only")
    k = "1" * 64
    assert AB.asof_terminal_key_sha256(k, b) != AB.asof_terminal_key_sha256(k, b2)
    assert AB.asof_terminal_key_sha256(k, b) == AB.asof_terminal_key_sha256(k, b3)   # tier text is not identity
    assert b.sha256 != dataclasses.replace(b, snapshot_sha256="1" * 64).sha256


# ------------------------------------------------------------------ visibility
def test_scan_flags_keys_ids_hashes_and_future_text():
    obs = dict(domain_id="finite_head_v1", acquired=[dict(head="MP", reading_text="seeker: I moved to Osaka last spring.",
                                                         record_id="resource:" + "a" * 64)])
    r = VIS.scan(obs, VIS.PM_OBSERVATION, private_tokens=["p11_conv_3"],
                 future_texts=["I moved to Osaka last spring.", "Hello! How are you feeling today?"],
                 legal_texts=["supporter: Hello! How are you feeling today?"])
    assert not r["ok"] and "acquired[].record_id" in r["forbidden_keys"][0] + r["non_whitelisted_paths"][0]
    assert r["future_text_hits"] and r["future_texts_identical_to_legal_text"] == 1 and r["private_hash_like"] >= 1
    clean = VIS.scan(dict(domain_id="finite_head_v1", action_mask=["STOP"]), VIS.PM_OBSERVATION)
    assert clean["ok"]
    assert "acquired[].reading_text" not in VIS.PM_OBSERVATION_NOTEXT


def test_real_observations_pass_and_notext_drops_only_text(world):
    prefix = prefix_of(world, AB3D17)
    env, _ = env_for(world, prefix)
    ep = RV.BoundEpisode(env, legacy_binding(world, prefix, env))
    s = ep.reset()
    for a in (E.GET["RS"], E.GET["MS"]):
        s, info = ep.try_step(s, a)
        assert not isinstance(info, RV.Invalid), info
    bank = world[0]
    private = sorted({r.record_id for r in bank.records} | {e.source_id for e in bank.registry.entries} | {prefix.prefix_id})
    full = ep.observe(s, private_tokens=private)
    nt = ep.observe(s, notext=True, private_tokens=private)
    assert [r["head"] for r in full["acquired"]] == ["RS", "MS"] and all("reading_text" in r for r in full["acquired"])
    assert all("reading_text" not in r for r in nt["acquired"])
    assert {k: v for k, v in full.items() if k != "acquired"} == {k: v for k, v in nt.items() if k != "acquired"}


# ------------------------------------------------------------------ research env
def test_invalid_get_is_typed_and_leaves_state(world):
    prefix = prefix_of(world, AB3D17)
    env, _ = env_for(world, prefix)
    ep = RV.BoundEpisode(env, legacy_binding(world, prefix, env))
    s0 = ep.reset()
    s1, info = ep.try_step(s0, "GET_MP")                                 # MP: no legal candidate in bank-v0
    assert isinstance(info, RV.Invalid) and info.reason == "no_legal_candidates" and s1 == s0
    s2, _ = ep.try_step(s0, "GET_RS")
    s3, info = ep.try_step(s2, "GET_RS")
    assert info.reason == "already_read" and s3 == s2 and len(s3.readings) == 1
    assert ep.try_step(s0, "EXPAND_MS(1)")[1].reason == "unknown_action"
    done = dataclasses.replace(s2, done=True)
    assert ep.try_step(done, "GET_ME")[1].reason == "after_stop"
    assert [i.reason for i in ep.invalid_log] == ["no_legal_candidates", "already_read", "unknown_action", "after_stop"]


def test_read_changes_state_and_terminal_is_pending_not_zero(world):
    prefix = prefix_of(world, AB3D17)
    env, _ = env_for(world, prefix)
    ep = RV.BoundEpisode(env, legacy_binding(world, prefix, env))
    s0 = ep.reset()
    s1, info = ep.try_step(s0, "GET_ME")
    assert s1.order == ("ME",) and s1.input_tokens > s0.input_tokens and info["record_ids"]
    assert ep.observe(s1)["acquired"][0]["ordinal"] == 1
    v = ep.stop_value(s1)
    assert v.status == "pending" and v.lower is None and v.upper is None
    k = ep.composite_key(s1)
    ep.intervals[k] = RV.Interval("partial", 0.2, 0.6, ("uncertain",))
    assert ep.stop_value(s1) == RV.Interval("partial", 0.2, 0.6, ("uncertain",))
    with pytest.raises(ValueError):
        RV.Interval("pending", 0.0, 0.0)
    with pytest.raises(ValueError):
        RV.Interval("complete", 0.1, 0.2)


def test_bound_episode_refuses_mismatched_identity(world):
    prefix = prefix_of(world, AB3D17)
    env, _ = env_for(world, prefix)
    b = legacy_binding(world, prefix, env)
    with pytest.raises(RV.BindingMismatch):
        RV.BoundEpisode(env, dataclasses.replace(b, g_id="G0e:other"))
    with pytest.raises(RV.BindingMismatch):
        RV.BoundEpisode(env, dataclasses.replace(b, prefix_context_sha256="0" * 64))


def test_replay_cache_never_crosses_identities(world):
    prefix = prefix_of(world, AB3D17)
    env, _ = env_for(world, prefix)
    b = legacy_binding(world, prefix, env)
    new = dataclasses.replace(b, writer_identity="chrono-v1", writer_kind="chronological_asof", tier="research_candidate")
    cache = RV.ReplayCache()
    cache.put("2" * 64, b, dict(response_sha256="r1"))
    assert cache.get("2" * 64, b)["binding_tier"] == "legacy_engineering"
    assert cache.get("2" * 64, new) is None
    assert cache.get("2" * 64, dataclasses.replace(b, decode_id="decode:other")) is None
    with pytest.raises(ValueError):
        cache.put("2" * 64, b, dict(response_sha256="r2"))
    with pytest.raises(PermissionError):
        cache.migrate(b, new)


def test_pm_side_modules_do_not_import_evaluation_artefacts():
    for f in ("env/research_v32.py", "asof/binding.py", "asof/visibility.py"):
        tree = ast.parse((PROJECT / "src/metacom_pm/rl1v3" / f).read_text())
        mods = [n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        mods += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
        assert not [m for m in mods if any(x in m for x in ("needs", "checklist", "judge", "evaluate"))], (f, mods)


# ------------------------------------------------------------------ P2 protocol
def _facts(mp="mp_same", mp_pool=3, rs_score=.3, third=0, sugg=0, rej=0, ago=2):
    base = lambda h, status, n: dict(legal_candidates=n, review_status="unverified", sessions_ago=None if h == "RS" else ago,
                                     slot_versions_before_cutoff=1, top1=dict(score=rs_score, source_session_id=f"s{h}"),
                                     asof=dict(status=status, legacy_pool=n, asof_pool=n + 1),
                                     cues=dict(third_party=third, supporter_suggestion=sugg,
                                               seeker_rejection_or_failure=rej, case_self_disclosure=0))
    return dict(RS=base("RS", "external_snapshot", 5), MP=base("MP", mp, mp_pool), ME=base("ME", "registry_rules", 4),
                MS=base("MS", "registry_rules", 2))


def test_assess_job_rules():
    off = P2.assess_job(dict(subset="OFF"), _facts(), {})
    assert off["eligibility"] == "ELIGIBLE" and off["research_role"] == "off_baseline"
    assert P2.assess_job(dict(subset="MP"), _facts(mp="mp_differs"), {})["eligibility"] == "LEGACY_DIAGNOSTIC"
    assert P2.assess_job(dict(subset="MP+MS"), _facts(mp="mp_tie_dependent"), {})["eligibility"] == "LEGACY_DIAGNOSTIC"
    blk = P2.assess_job(dict(subset="MP"), _facts(mp="mp_unreachable_legacy_reachable_asof", mp_pool=0), {})
    assert blk["eligibility"] == "BLOCKED" and blk["research_role"] == "not_run_not_zero"
    rs = P2.assess_job(dict(subset="RS"), _facts(rs_score=.05), {"back_reference": True})
    assert rs["eligibility"] == "ELIGIBLE" and rs["research_role"].startswith("rs_case_v0_reference")
    assert {"S2_legal_but_maybe_not_needed", "S6_third_party_as_user", "S1_history_may_supply_needed_info"} <= set(rs["candidate_situations"])
    me = P2.assess_job(dict(subset="ME"), _facts(third=2, sugg=1, rej=1, ago=6), {})
    assert {"S3_possibly_outdated", "S4_may_induce_inappropriate_advice", "S5_rejected_or_failed_suggestion",
            "S6_third_party_as_user"} <= set(me["candidate_situations"])
    assert me["questions"]["generator_uses_or_ignores_correctly"] == "not_answerable_before_generation"
    assert me["questions"]["worth_reading_now"] == "pending_human"


def test_review_pairs_positions_are_seeded_and_complete():
    jobs = [dict(prefix_id=p, subset=s) for p in ("a" * 64, "b" * 64) for s in ("OFF", "MP", "MS", "MP+MS")]
    pairs = P2.review_pairs(jobs)
    assert len(pairs) == 2 * (3 + 2)
    assert all(pr["y"] in ("OFF", "MP", "MS") for pr in pairs)
    p1, p2 = P2.assign_positions(pairs, "x" * 64), P2.assign_positions(pairs, "x" * 64)
    assert p1 == p2 and P2.assign_positions(pairs, "y" * 64) != p1
    many = P2.assign_positions(P2.review_pairs([dict(prefix_id=f"{i:064d}", subset=s) for i in range(30)
                                                for s in ("OFF", "RS")]), "z" * 64)
    assert 0 < sum(r["A"] == "OFF" for r in many) < len(many)


def test_family_design_isolates_factors():
    jobs = [dict(prefix_id="a" * 64, subset=s) for s in ("OFF", "RS", "MP", "ME", "MS", "MP+MS", "ME+MS")]
    d = P2.family_design(jobs, {"a" * 64: ["OFF", "RS", "MP", "RS+MP", "RS+MP+ME+MS"]})
    assert d["never_mixed"] == ["resource content", "retriever/ranker", "renderer/packaging", "generator"]
    assert set(d["families"]["EXP_RS"]["arms"]) == {"R0", "F_resident", "METHOD", "METHOD_PLUS_CASE"}
    assert "never called OFF" in d["families"]["EXP_RS"]["arms"]["F_resident"]
    assert d["families"]["EXP_RS"]["new_inputs"] == 3


# ------------------------------------------------------------------ reward qualification
def test_relevant_optional_never_creates_a_requirement():
    import rl1v3_reward_review_cases as RC
    full_opt, _ = RC.card("no_required")
    mislabel, _ = RC.card("optional_as_required")
    hp = lambda cl: [i for i in cl.items if i.category == "H+"]
    assert len(hp(mislabel)) == len(hp(full_opt)) + 1
    assert mislabel.total_weight - full_opt.total_weight == 2.0
    assert not any("Anna moved back" in i.text for i in hp(full_opt))         # optional item: no H+ requirement
    assert any("Anna moved back" in i.text for i in hp(mislabel))


def test_call_and_terminal_status_keep_failure_kinds_apart():
    assert RQ.classify_call(finish_reason="length", parsed=False) == "truncated"
    assert RQ.classify_call(finish_reason="stop", parsed=False) == "parse_failed"
    assert RQ.classify_call(finish_reason=None, parsed=False, blocked=True) == "pre_call_blocked"
    assert RQ.item_status("pass", ("bad_evidence_ref:E9",)) == "bad_evidence_ref"
    assert RQ.item_status(None) == "missing"
    w = {"G:1": 1.0, "I:1": 1.0, "S:1": 1.0, "H+:1": 2.0}
    done = RQ.terminal_status(["ok"], {"G:1": "pass", "I:1": "fail", "S:1": "pass", "H+:1": "pass"}, weights=w)
    assert done["status"] == "complete" and done["lower"] == done["upper"] == 0.8
    part = RQ.terminal_status(["ok"], {"G:1": "pass", "I:1": "uncertain", "S:1": "pass", "H+:1": "pass"}, weights=w)
    assert part["status"] == "pending" and part["lower"] == 0.8 and part["upper"] == 1.0 and not part["filled_with_zero"]
    trunc = RQ.terminal_status(["truncated"], {k: "missing" for k in w}, weights=w)
    assert trunc["status"] == "refused_pending" and trunc["lower"] == 0.0 and trunc["upper"] == 1.0
    assert "truncated" in trunc["reasons"] and "missing" in trunc["reasons"]
    safety = RQ.terminal_status(["ok"], {"G:1": "pass", "I:1": "pass", "S:1": "uncertain", "H+:1": "pass"},
                                weights=w, safety_items=("S:1",))
    assert safety["status"] == "refused_pending"


def test_decode_budget_candidate():
    assert RQ.decode_budget(800, input_tokens=1000) == dict(budget=1024, raw_budget=1024, blocked=False, reasons=[])
    big = RQ.decode_budget(7000, input_tokens=1000)
    assert big["blocked"] and "budget_over_cap" in big["reasons"]
    assert RQ.decode_budget(100, input_tokens=32700)["reasons"] == ["context_over_operational_limit"]
    assert RQ.DECODE_CANDIDATE["status"] == "PROPOSED_NOT_ADOPTED"


def test_isolation_rules():
    ok = dict(train_reward=dict(judge_family="qwen", judge_prompt_sha="a", qualified=False), claim_tier="engineering_only",
              final_eval=dict(judge_family="mistral", judge_prompt_sha="b", human=True),
              train_owners=["p1"], final_owners=["p2"], selection_split="dev",
              arms={"PPO": dict(reward_id="r", budget=10, prefixes=["x"]), "BC": dict(reward_id="r", budget=10, prefixes=["x"])})
    assert RQ.check_isolation(ok) == []
    bad = copy.deepcopy(ok)
    bad.update(final_eval=dict(judge_family="qwen", judge_prompt_sha="b"), final_owners=["p1"], pending_as_zero=True,
               claim_tier="research", selection_split="final")
    bad["arms"]["BC"]["budget"] = 20
    assert set(RQ.check_isolation(bad)) == {"R1", "R2/R4", "R3", "R5", "R7", "R8"}


# ------------------------------------------------------------------ baselines
def test_fairness_contract():
    base = dict(prefixes=["a", "b"], binding_sha256="b", bank_version="bk", index_version="ix", g_id="g", decode_id="d",
                step2_id="s", evaluator_id="e", split_rule="fold6", fold_rule="owner", renderer_id="r0", feedback_terminals=10)
    runs = {a: dict(base) for a in ("OFF", "ALL", "PPO", "BC-union")}
    runs["F-resident"] = dict(base, renderer_id="r-F")
    assert BL.check_fair(runs) == []
    r2 = copy.deepcopy(runs)
    r2["ALL"]["renderer_id"] = "r1"
    r2["F-resident"]["renderer_id"] = "r0"
    r2["BC-union"]["feedback_terminals"] = 99
    r2["PPO"]["g_id"] = "g2"
    p = BL.check_fair(r2)
    assert {"renderer_differs_outside_F_resident", "F_resident_must_have_its_own_renderer",
            "BC-union_feedback_not_matched_to_PPO", "PPO:g_id"} <= set(p)


def test_fixed_arms_on_fixture_tables():
    rng = np.random.default_rng(0)
    full = lambda: {m: float(rng.normal()) for m in range(E.N_SUBSETS)}
    train = [full() for _ in range(20)]
    test = [dict(table=full(), cues=dict(advice_request=True), history_sessions=1) for _ in range(20)]
    r = BL.evaluate_fixed_arms(test, train, k_random=1, seed=3)
    assert all(r["means"]["Oracle(diagnostic)"] >= v for v in r["means"].values())
    test[0]["table"][3] = None
    with pytest.raises(ValueError):
        BL.evaluate_fixed_arms(test, train, k_random=1, seed=3)
    assert set(BL.ARMS) == {"OFF", "ALL", "Fixed-best", "F-resident", "Rule", "Random", "OneShot", "Seq-BC",
                            "BC-union", "PPO", "PPO-NoText"}


# ------------------------------------------------------------------ latency
def _row(i, cond, ev, **fl):
    return dict(request_id=f"r{i}", condition=cond, binding_sha256="b", g_id="g", decode_id="d", hardware_id="A6000",
                events_ms=ev, flags=fl)


def test_latency_schema_and_percentiles():
    rows = [_row(i, "OFF", dict(request_end=0, first_token=100 + i, first_visible_valid_text=150 + i, complete_text=900 + i))
            for i in range(20)]
    rows.append(_row(99, "OFF", dict(request_end=0), failed=True))
    s = LT.summarise(rows)["groups"]["OFF|warm"]
    assert s["n"] == 21 and s["failure_rate"] == 1 / 21 and s["ttfv_ms"]["n"] == 20
    assert s["ttfv_ms"]["p50"] == pytest.approx(159.5) and s["ttfv_ms"]["p95"] == pytest.approx(168.05)
    assert LT.validate_online(_row(1, "OFF", dict(request_end=0, first_token=50, first_visible_valid_text=40,
                                                   complete_text=60))) == ["visible_before_first_token"]
    off = dict(_row(2, "OFF", dict(request_end=0, complete_text=5)), judge_ms=3000)
    assert "offline_cost_in_online_row" in LT.validate_online(off)
    with pytest.raises(LT.LedgerMix):
        LT.summarise([off])
    with pytest.raises(LT.LedgerMix):
        LT.offline_row("pm_decision", wall_s=1, gpu_s=1, identity="x")
    assert LT.offline_row("judge_j1", wall_s=1, gpu_s=1, identity="x")["user_latency"] is False


def test_manifests_are_stable():
    for m in (VIS.whitelist_manifest(), RQ.manifest(), BL.manifest(), LT.manifest()):
        body = {k: v for k, v in m.items() if k != "sha256"}
        assert m["sha256"] == object_sha256(body)
