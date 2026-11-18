"""Round-8 reward review: ten counterexamples through the FROZEN checklist-v3 / judge-v3 / ER-v3, plus the
marginal-value proposal (``evaluate.marginal_value``).  Fixtures only; no model is called; no frozen
protocol is changed (asserted against ``outputs/pm_rl1/v3/B2/protocols_v3_frozen.json``)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from metacom_pm.rl1v3.checklist import writer_v3 as CW3
from metacom_pm.rl1v3.evaluate import marginal_value as MV, protocol as EP
from metacom_pm.rl1v3.judge import engineering_reward_v3 as ER3, protocol_v3 as JP3
from rl1v3_reward_review_cases import CASES, card, run_case
from test_rl1v3_b2_checklist_judge import envelope

ROOT = Path(__file__).resolve().parents[1]
RUNS = {c["id"]: run_case(c) for c in CASES}


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_er_v3_behaviour_on_each_counterexample_is_as_documented(case):
    r = RUNS[case["id"]]
    assert r["er_effect"] == case["expect_er"]
    if case["verdict"] == "ok":
        assert case["expect_er"] == case["ideal"]
    if case["verdict"] == "gap":
        assert case["expect_er"] != case["ideal"]


def test_the_frozen_v3_identities_are_untouched():
    frozen = json.loads((ROOT / "outputs/pm_rl1/v3/B2/protocols_v3_frozen.json").read_text())
    assert CW3.writer_identity() == frozen["checklist"]["v3"]
    assert ER3.preregistration()["sha256"] == frozen["engineering_reward"]["v3"]["sha256"]
    assert JP3.JUDGE_PROTOCOL == frozen["judge"]["v3"]


def test_gaps_cost_only_the_get_constant_or_reward_the_wrong_thing():
    W = 18
    assert RUNS["C2b"]["er_value_delta"] == pytest.approx(2 / W - 0.01)          # forced mention via a wrong 'required'
    for cid in ("C2a", "C4", "C9b"):                                             # unnatural / irrelevant / stale use
        assert RUNS[cid]["er_value_delta"] == pytest.approx(-0.01)               # = one GET, nothing else
    me = RUNS["C8b"]["terminals"]["ME"]
    assert me["failed"] == ["G:3"] and RUNS["C8b"]["er_value_delta"] > 0          # lecturing + history beats warm OFF


def test_attribution_separates_generator_and_retrieval_from_resource_value():
    assert RUNS["C3"]["er_effect"] == "equivalent" and RUNS["C3"]["attribution"] == "generator_not_used"
    assert RUNS["C4"]["attribution"] == "retrieval_miss"
    assert RUNS["C8a"]["attribution"] == "realized_value"
    assert RUNS["C1"]["attribution"] == "unneeded_read"


def test_midpoint_ranks_an_undetermined_pair_and_only_the_interval_or_grid_shows_it():
    r = RUNS["C10a"]
    lo, hi = r["quality_delta"]
    assert lo < 0 < hi and r["midpoint_delta"] > 0 and r["er_value_delta"] > 0
    t = r["terminals"]
    assert t["ME"]["grid_u0"] < t["OFF"]["grid_u0"] and t["ME"]["grid_u1"] > t["OFF"]["grid_u1"]
    assert RUNS["C10b"]["terminals"]["ME"]["reasons"] == ["hard_safety_uncertain"] and RUNS["C10b"]["quality_delta"] is None


def test_joint_degradation_is_visible_in_the_subset_table():
    lo, hi = RUNS["C7"]["interaction_MP_MS"]
    assert hi < 0 and RUNS["C7"]["er_effect"] == "harm"


def test_eval_protocol_omission_treats_a_writer_method_label_as_rs_necessity():
    """The frozen eval-protocol omission/unneeded-read metrics read NeedCard head_needs, where any writer
    method_need puts RS in 'required'.  OFF is then an 'omission' although ER finds RS adds nothing (C5)."""
    _, env = card("full")
    assert "RS" in env["head_needs"]["required"]
    assert "RS" not in envelope(method_need=None, method_evidence=[])["head_needs"]["required"]
    t = RUNS["C5"]["terminals"]

    def ep(name, subset):
        return dict(prefix_id="p", subset=subset, er_value=t[name]["value"], j1_lower=t[name]["lower"],
                    j1_upper=t[name]["upper"], required_heads=env["head_needs"]["required"],
                    optional_heads=env["head_needs"]["optional"])
    assert EP.arm_metrics([ep("OFF", ())])["omission_rate"]["value"] == 1.0
    assert t["RS"]["value"] < t["OFF"]["value"]


# ------------------------------------------------------------------ marginal_value proposal

def test_delta_and_classify_never_turn_pending_into_zero():
    assert MV.delta(None, (0.5, 0.6)) is None and MV.classify(None, 0.05) == "pending"
    assert MV.classify((0.06, 0.2), 0.05) == "benefit" and MV.classify((-0.2, -0.06), 0.05) == "harm"
    assert MV.classify((-0.04, 0.03), 0.05) == "equivalent" and MV.classify((-0.04, 0.2), 0.05) == "undetermined"
    with pytest.raises(ValueError):
        MV.classify((0, 0), -0.1)


def test_marginals_skip_unreachable_subsets_and_keep_pending():
    f = frozenset
    table = {f(): (0.8, 0.8), f({"ME"}): (0.9, 0.95), f({"MS"}): None, f({"ME", "MS"}): (0.7, 0.7)}
    rows = {(tuple(r["base"]), r["head"]): r for r in MV.marginals(table, ("ME", "MS", "MP"), 0.0)}
    assert rows[((), "ME")]["effect"] == "benefit" and rows[((), "MS")]["effect"] == "pending"
    assert rows[(("ME",), "MS")]["effect"] == "harm" and rows[(("MS",), "ME")]["effect"] == "pending"
    assert not any("MP" == h or "MP" in b for b, h in rows)                          # MP unreachable: no row, no 0
    assert MV.interaction(table, "ME", "MS") is None


def test_decision_label_follows_the_paper1_rule_and_needs_measured_latency():
    good = dict(quality=(0.1, 0.2), margin=0.05, new_hard_factual_fail=False, safety="pass")
    assert MV.decision_label(**good, added_latency_s=0.4, latency_budget_s=1.5) == "beneficial"
    assert MV.decision_label(**good, added_latency_s=None, latency_budget_s=1.5) == "undetermined"
    assert MV.decision_label(**good, added_latency_s=2.0, latency_budget_s=1.5) == "infeasible"
    assert MV.decision_label(**dict(good, safety="fail"), added_latency_s=0.1, latency_budget_s=1.5) == "infeasible"
    assert MV.decision_label(**dict(good, safety="uncertain"), added_latency_s=0.1, latency_budget_s=1.5) == "pending"
    assert MV.decision_label(**dict(good, quality=(-0.01, 0.02)), added_latency_s=0.1, latency_budget_s=1.5) == "nonbeneficial"


def test_attribute_covers_the_chain():
    a = MV.attribute
    assert a(effect="pending", need=True, retrieval_hit=True, uptake="used") == "pending"
    assert a(effect="benefit", need=None, retrieval_hit=None, uptake="used") == "need_unverified"
    assert a(effect="benefit", need=False, retrieval_hit=None, uptake="used") == "unanticipated_value"
    assert a(effect="harm", need=False, retrieval_hit=None, uptake="used") == "unneeded_read_harm"
    assert a(effect="equivalent", need=True, retrieval_hit=False, uptake="used") == "retrieval_miss"
    assert a(effect="equivalent", need=True, retrieval_hit=True, uptake="not_used") == "generator_not_used"
    assert a(effect="equivalent", need=True, retrieval_hit=True, uptake="used") == "used_no_gain"
    assert a(effect="harm", need=True, retrieval_hit=True, uptake="used") == "misuse_or_harmful_use"
    assert a(effect="benefit", need=True, retrieval_hit=True, uptake="uncertain") == "undetermined"
    assert set(MV.CHAIN) >= {a(effect=e, need=n, retrieval_hit=h, uptake=u)
                             for e in MV.EFFECTS for n in (None, True, False) for h in (None, True, False)
                             for u in (None, "used", "not_used", "uncertain")}
