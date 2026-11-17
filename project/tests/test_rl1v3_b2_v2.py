"""Checklist v2 (I = Resource Misuse / Integrity), judge v2 attribution, ER-v2 and eval protocol v2.

Programmatic examples only (hand-written NeedCard, reply and judge answers); no model is called.
"""
from __future__ import annotations

import json

import pytest

from metacom_pm.rl1v3 import contracts as K
from metacom_pm.rl1v3.checklist import writer as CW1, writer_v2 as CW2
from metacom_pm.rl1v3.env import finite_head as E
from metacom_pm.rl1v3.env.c0_binding import TerminalIdentity, subset_key
from metacom_pm.rl1v3.evaluate import protocol_v2 as EV
from metacom_pm.rl1v3.judge import aggregate as AG, engineering_reward as ER1, engineering_reward_v2 as ER
from metacom_pm.rl1v3.judge import protocol_v2 as JP
from test_rl1v3_b2_checklist_judge import envelope
from rl1v3_wsb_fixtures import context

IDENT = TerminalIdentity("bank-v0", "idx-v0", "renderer:v0", "step2-v0", "g0-not-frozen", "greedy")
S_OLD = "Since your sister Anna still lives in Berlin, you must feel alone."
S_NEW = "Your doctor told you last week that you have insomnia."
REPLY = f"I hear how exhausting work is. {S_OLD} {S_NEW} Maybe try a short wind-down routine tonight."


def cl2(env=None):
    env = env or envelope()
    return CW2.build(env["needcard"], method_evidence=env["method_evidence"]), env


def ids(cl, cat):
    return [i.item_id for i in cl.items if i.category == cat]


def outdated_item(cl):
    return next(i.item_id for i in cl.items if i.category == "H-" and "still current" in i.text)


def answer(cl, verdicts=None, quotes=None):
    verdicts, quotes = verdicts or {}, quotes or {}
    return json.dumps([dict(id=i.item_id, verdict=verdicts.get(i.item_id, "pass"), quote=quotes.get(i.item_id, ""),
                            evidence="") for i in cl.items])


def judged(cl, role="J1", readings=(), **kw):
    ident = JP.JudgeIdentityV2(role=role, model_id=f"fixture-{role}", model_sha256="1" * 64, decode_id="greedy")
    return JP.run(lambda m: answer(cl, **kw), ident, context().prefix.turns, REPLY, cl, readings)


def er_args(cl, env, j1, *, heads=()):
    groups = {h: (f"r-{h}",) for h in heads}
    mask = E.mask_of(heads)
    key = subset_key(context().prefix, IDENT, groups, mask)
    order = E.heads_of(mask)
    readings = tuple(K.ReadingView(head=h, view={"RS": "case", "MP": "assertion", "ME": "event", "MS": "raw"}[h],
                                   ordinal=i + 1, reading_text=f"{h} text", reported_at=None if h == "RS" else
                                   K.TimePoint(session_rank=0), tokens=10 * (i + 1),
                                   stage="unknown" if h == "ME" else None) for i, h in enumerate(order))
    trace = K.ExecutionTrace(domain_id="finite_head_v1", ordered_path=E.canonical_path(mask),
                             acquired=tuple(groups[h] for h in order), readings=readings)
    return dict(key=key, trace=trace, checklist=cl, needcard=env["needcard"], evidence_validation="verified",
                response=REPLY, finish_reason="natural_stop", verdicts=AG.item_verdicts(cl, j1, None),
                j1_identity=j1.identity, expected_j1_identity=j1.identity, input_tokens=900, prefix_tokens=400,
                j1_attributions=j1.attributions)


# ------------------------------------------------------------------ checklist v2

def test_checklist_v2_defines_I_as_resource_misuse_with_scope_and_keeps_v1():
    cl, env = cl2()
    I = [i for i in cl.items if i.category == "I"]
    assert len(I) == 4 and all(i.text.startswith("Apart from any statement already judged under an H- item")
                               for i in I)
    assert [CW2.i_kind(i.item_id) for i in I] == ["fabricated_history", "misidentification",
                                                  "suggestion_as_action", "unsupported_inference"]
    assert {i.constraint_type for i in I} == {"hard_factual"} and {i.weight for i in I} == {1.0}
    r = [i for i in cl.items if i.category == "R"]
    assert len(r) == 1 and r[0].text == CW2.R_TEXT and "sleep_hygiene" not in r[0].text and r[0].evidence_spans
    v1 = CW1.build(env["needcard"], method_family_text={}, method_evidence=env["method_evidence"])
    assert sum(i.category == "I" for i in v1.items) == 2 and CW1.CHECKLIST_PROTOCOL.endswith("-v1")
    assert cl.writer_identity.startswith("pmrl1v3-checklist-template-v2|") and cl.sha256 != v1.sha256
    assert cl.total_weight == v1.total_weight + 2.0


def test_r_item_requires_verified_method_evidence():
    env = envelope()
    with pytest.raises(ValueError, match="R item needs"):
        CW2.build(env["needcard"], method_evidence=())


# ------------------------------------------------------------------ attribution (conflict tests)

def test_same_atomic_error_counts_once_under_H_minus():
    cl, env = cl2()
    h, i1 = outdated_item(cl), "I:1"
    j1 = judged(cl, verdicts={h: "fail", i1: "fail"}, quotes={h: S_OLD, i1: S_OLD})
    assert j1.pre_attribution[i1].verdict == "fail"
    assert j1.items[i1].verdict == "pass" and f"attributed_to:{h}" in j1.items[i1].flags
    assert j1.attributions == [dict(item=i1, attributed_to=h, quote_sha256=j1.attributions[0]["quote_sha256"])]
    rec = ER.compute(**er_args(cl, env, j1))
    assert rec["quality"]["j1_lower"] == pytest.approx(1 - 2 / cl.total_weight)     # H- weight only, not H- + I
    assert rec["j1_attributions"][0]["attributed_to"] == h


def test_partial_quote_overlap_is_the_same_atomic_error():
    cl, env = cl2()
    h = outdated_item(cl)
    j1 = judged(cl, verdicts={h: "fail", "I:2": "fail"}, quotes={h: S_OLD, "I:2": "your sister Anna still lives in Berlin"})
    assert j1.items["I:2"].verdict == "pass" and j1.attributions[0]["item"] == "I:2"


def test_distinct_errors_both_count():
    cl, env = cl2()
    h = outdated_item(cl)
    j1 = judged(cl, verdicts={h: "fail", "I:4": "fail"}, quotes={h: S_OLD, "I:4": S_NEW})
    assert j1.items["I:4"].verdict == "fail" and not j1.attributions
    rec = ER.compute(**er_args(cl, env, j1))
    assert rec["quality"]["j1_lower"] == pytest.approx(1 - 3 / cl.total_weight)


def test_I_error_counts_when_no_H_minus_item_exists():
    env = envelope(stratum="none", history_items=[], failed_or_rejected=[], outdated_facts=[], method_need=None,
                   method_evidence=[])
    cl, _ = cl2(env)
    assert not ids(cl, "H-")
    j1 = judged(cl, verdicts={"I:1": "fail"}, quotes={"I:1": S_OLD})
    assert j1.items["I:1"].verdict == "fail" and not j1.attributions


def test_fail_without_reply_quote_is_uncertain_only_for_H_minus_and_I():
    cl, _ = cl2()
    h, g = outdated_item(cl), ids(cl, "G")[0]
    j1 = judged(cl, verdicts={h: "fail", "I:3": "fail", g: "fail"})
    assert j1.items[h].verdict == "uncertain" and "fail_without_quote" in j1.items[h].flags
    assert j1.items["I:3"].verdict == "uncertain" and j1.items[g].verdict == "fail"


def test_attribution_is_per_judge_and_disagreement_stays_uncertain():
    cl, _ = cl2()
    h = outdated_item(cl)
    j1 = judged(cl, verdicts={h: "fail", "I:1": "fail"}, quotes={h: S_OLD, "I:1": S_OLD})
    j2 = judged(cl, role="J2", verdicts={"I:1": "fail"}, quotes={"I:1": S_OLD})       # J2 did not fail H-
    v = {x.item_id: x for x in AG.item_verdicts(cl, j1, j2)}
    assert v["I:1"].J1 == "pass" and v["I:1"].J2 == "fail" and v["I:1"].final == "uncertain"
    assert v[h].final == "uncertain"


def test_judge_sees_terminal_readings_while_checklist_is_identical():
    cl, _ = cl2()
    rv = lambda h, o: K.ReadingView(head=h, view={"MP": "assertion", "MS": "raw"}[h], ordinal=o, reading_text=f"{h} body",
                                    reported_at=K.TimePoint(session_rank=0), tokens=3)
    msgs = JP.render(context().prefix.turns, REPLY, cl, readings=(rv("MS", 1), rv("MP", 2)))
    data = json.loads(msgs[1]["content"].split("\n", 1)[1])
    assert [r["head"] for r in data["RESOURCES_GIVEN_TO_REPLY"]] == ["MP", "MS"]
    assert "judge it only under that H- item" in msgs[0]["content"]
    off = json.loads(JP.render(context().prefix.turns, REPLY, cl)[1]["content"].split("\n", 1)[1])
    assert off["ITEMS"] == data["ITEMS"] and off["RESOURCES_GIVEN_TO_REPLY"] == []


# ------------------------------------------------------------------ ER-v2

def test_er_v2_primary_value_penalty_and_tokens_reported_separately():
    cl, env = cl2()
    rec = ER.compute(**er_args(cl, env, judged(cl), heads=("MP", "ME")))
    assert rec["value"] == pytest.approx(1 - 0.02) and rec["is_gsc"] is False
    assert rec["get_penalty"] == dict(n_gets=2, per_get=0.01, total=pytest.approx(0.02),
                                      label="engineering_constant_not_a_cost_model")
    assert rec["cost_report"]["reading_tokens_by_head"] == {"MP": 10, "ME": 20}
    assert rec["cost_report"]["input_tokens"] == 900 and rec["cost_report"]["reading_tokens_total"] == 30
    assert len(rec["sensitivity"]) == 12 and rec["sensitivity"]["u=0.5|g=0.01"] == pytest.approx(rec["value"])
    assert rec["sensitivity"]["u=0.0|g=0.0"] == pytest.approx(rec["quality"]["j1_lower"])


def test_er_v2_sensitivity_bounds_follow_uncertain_value():
    cl, env = cl2()
    g = ids(cl, "G")
    rec = ER.compute(**er_args(cl, env, judged(cl, verdicts={g[0]: "uncertain"})))
    W = cl.total_weight
    assert rec["sensitivity"]["u=0.0|g=0.0"] == pytest.approx(1 - 1 / W)
    assert rec["sensitivity"]["u=1.0|g=0.0"] == pytest.approx(1.0)
    assert rec["sensitivity"]["u=0.5|g=0.0"] == pytest.approx(1 - 0.5 / W)


def test_hard_safety_uncertain_is_refused_not_midpointed():
    cl, env = cl2()
    s = ids(cl, "S")[0]
    with pytest.raises(ER1.RewardUnavailable) as e:
        ER.compute(**er_args(cl, env, judged(cl, verdicts={s: "uncertain"})))
    assert "hard_safety_uncertain" in e.value.reasons


def test_safety_fail_floors_every_grid_point():
    cl, env = cl2()
    s = ids(cl, "S")[0]
    rec = ER.compute(**er_args(cl, env, judged(cl, verdicts={s: "fail"}), heads=("RS",)))
    assert rec["value"] == -1.0 and set(rec["sensitivity"].values()) == {-1.0}


def test_v1_checklist_is_refused_and_versions_do_not_mix():
    _, env = cl2()
    v1 = CW1.build(env["needcard"], method_family_text={}, method_evidence=env["method_evidence"])
    j1 = judged(v1)
    with pytest.raises(ER1.RewardUnavailable) as e:
        ER.compute(**er_args(v1, env, j1))
    assert "checklist_protocol_not_v2" in e.value.reasons
    cl, env = cl2()
    rec = ER.compute(**er_args(cl, env, judged(cl)))
    with pytest.raises(ValueError):
        ER1.to_outcome(rec)
    assert ER.to_outcome(rec).reward == pytest.approx(rec["value"])
    with pytest.raises(ValueError):
        ER.to_outcome(dict(rec, protocol=ER1.PROTOCOL))


def test_preregistration_is_frozen_and_distinct_from_v1():
    p = ER.preregistration()
    assert p["sha256"] == ER.preregistration()["sha256"]
    assert p["grid"] == dict(uncertain_value=(0.0, 0.5, 1.0), get_penalty=(0.0, 0.005, 0.01, 0.02))
    assert "hard_safety_uncertain" in p["refusal_reasons"] and ER.ERConfigV2().sha256 != ER1.ERConfig().sha256


def test_attempts_feed_refusal_report_by_subset_and_stratum():
    cl, env = cl2()
    s = ids(cl, "S")[0]
    ok = er_args(cl, env, judged(cl), heads=("MP",))
    bad = er_args(cl, env, judged(cl, verdicts={s: "uncertain"}), heads=("MS",))
    attempts = [ER.attempt(subset="MP", stratum="history", **ok), ER.attempt(subset="MS", stratum="none", **bad),
                ER.attempt(subset="MP", stratum="history", **ok)]
    rep = EV.refusal_report(attempts)
    assert rep["overall"] == dict(n=3, refused=1, rate=pytest.approx(1 / 3))
    assert rep["by_subset"]["MS"]["rate"] == 1.0 and rep["by_stratum"]["history"]["rate"] == 0.0
    assert rep["by_reason"] == {"hard_safety_uncertain": 1}
    assert rep["mix"]["stratum"]["max_abs_share_shift"] == pytest.approx(1 / 3)


# ------------------------------------------------------------------ eval protocol v2

def rows(n_owner=6, per=10, owner_effect=True, shared=()):
    out = []
    for o in range(n_owner):
        for k in range(per):
            fam = [f"esconv:{o}"] + ([f"esconv:shared"] if o in shared else [])
            out.append(dict(prefix_id=f"p{o}-{k}", owner_id=f"o{o}", session_id=f"s{o}-{k % 3}", family_ids=fam,
                            er_value=(o / n_owner if owner_effect else 0.5) + (0.01 * (k % 2)),
                            natural_weight=1.0 + o, subset=("MP",), stratum="none", get_penalty=0.01,
                            j1_lower=0.4, j1_upper=0.6,
                            reading_tokens_total=100, er_sensitivity={"u=0.5|g=0.01": 0.5, "u=0.0|g=0.0": 0.4}))
    return out


def test_clusters_merge_owners_sharing_a_family():
    cl = EV.clusters(rows(shared=(1, 2)))
    assert cl["o1"] == cl["o2"] and len(set(cl.values())) == 5


def test_cluster_bootstrap_is_deterministic_and_wider_than_iid_under_owner_effects():
    r = rows()
    a, b = EV.cluster_bootstrap(r), EV.cluster_bootstrap(r)
    assert a == b and a["n_clusters"] == 6 and a["n_prefixes"] == 60 and a["n_sessions"] == 18
    m = EV.arm_metrics(r)
    assert m["er_value_cluster_se"]["value"] > 2 * m["er_value_se"]["value"]
    assert "comparison only" in m["er_value_se"]["note"] and a["warning"] == "fewer than 10 clusters: interval is unreliable"
    w = EV.cluster_bootstrap(r, weight_key="natural_weight")
    assert w["value"] > a["value"]                 # natural weights move the estimate; they are not ignored


def test_report_v2_lists_every_metric_and_sensitivity_ranking():
    off = rows(owner_effect=False)
    allr = [dict(e, er_value=e["er_value"] + 0.1, er_sensitivity={"u=0.5|g=0.01": 0.6, "u=0.0|g=0.0": 0.45})
            for e in off]
    names = {a.name for a in EV.REQUIRED_ARMS} - {"OFF", "ALL"}
    rep = EV.build_report({"OFF": off, "ALL": allr}, missing_arms={n: "not run in this unit test" for n in names})
    assert rep["protocol"] == "pmrl1v3-eval-protocol-v2"
    for arm in ("OFF", "ALL"):
        assert set(rep["arms"][arm]["metrics"]) == set(EV.METRICS)
        assert rep["arms"][arm]["metrics"]["er_refusal_rate"]["status"] == "not_available"
    assert rep["sensitivity_ranking"]["primary"] == ["ALL", "OFF"] and rep["sensitivity_ranking"]["stable"]
