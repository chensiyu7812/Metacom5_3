"""V3.2.1 admission candidate: gates split by purpose, review spec v2, statistics, 90 screen, PP1."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from metacom_pm.rl1v3.evaluate import resource_effect_v321 as V
from metacom_pm.rl1v3.evaluate import resource_effect_v32q as Q

PROJECT = Path(__file__).resolve().parents[1]
DRAW = PROJECT / "outputs/pm_rl1/v3/V32_WSB_RQ1Q/coverage/SCREENING_DRAW.json"
ELIG = PROJECT / "outputs/pm_rl1/v3/V32_WSB_P0P2/p2/ELIGIBILITY_54.json"


def _facts(**kw):
    f = {k: False for k in ("g0e_identity", "a0_measured", "requests_checked", "output_policy", "gpu_auth",
                            "pp1_qh_backgrounds", "pp1_screen_labels", "raters", "pp1_protocol_approved", "instrument",
                            "formal_protocol", "screen_labels", "formal_qh", "pp1_done", "single_renderer",
                            "dp_ms_formal", "ret_ms_asof", "license_scope", "mp_semantic", "me_semantic",
                            "rs_reviewed", "fc_results", "j1_validated", "decode_cap", "r1_r5_fixed")}
    f.update(kw)
    return f


def _by(gates):
    return {g["gate"]: g for g in gates}


# ------------------------------------------------------------------ gates
def test_gates_have_states_reasons_and_owners():
    for g in V.gates_v321(_facts()):
        assert g["state"] in V.STATE
        for i in g["items"]:
            assert i["state"] in V.STATE
            if i["state"] != "PASS":
                assert i["reason"] and i["unblock_owner"]


def test_fc_ms_does_not_need_rs_mp_me_and_g_eng_does_not_need_pp1():
    g = _by(V.gates_v321(_facts()))
    assert "RS METHOD 卡" in g["FC-MS"]["not_required"] and "MP/ME 语义审核" in g["FC-MS"]["not_required"]
    assert "PP1 结果" in g["G-ENG"]["not_required"] and "PP1" not in " ".join(g["G-ENG"]["depends_on"])
    ids = " ".join(i["evidence"] for i in g["FC-MS"]["items"])
    assert "METHOD" not in ids and "语义审核" not in ids


def test_everything_ready_except_people_gives_pending_not_blocked():
    ready = _facts(**{k: True for k in _facts()})
    ready.update(gpu_auth=False)
    g = _by(V.gates_v321(ready))
    assert g["G-ENG"]["state"] == "PENDING"
    full = _by(V.gates_v321(_facts(**{k: True for k in _facts()})))
    assert all(x["state"] == "PASS" for x in full.values())


def test_current_state_blocked_and_pp1_backgrounds_counted():
    g = _by(V.gates_v321(_facts(output_policy=True, pp1_qh_backgrounds=True)))
    assert g["G-ENG"]["state"] == "BLOCKED" and g["PP1"]["state"] == "BLOCKED"
    assert {i["id"]: i["state"] for i in g["PP1"]["items"]}["P2"] == "PASS"


# ------------------------------------------------------------------ review spec v2
def test_labels_hidden_from_every_rater_and_fa_on_audit_side():
    s = V.review_spec_v2()
    for ch in ("Q0", "QH", "F"):
        assert any("需要标签" in h for h in s[ch]["hides"]) and any("模型分数" in h for h in s[ch]["hides"])
        assert any("条件名" in h for h in s[ch]["hides"])
    assert "audit" in s and s["audit"]["F_A"]["after"].startswith("所有")
    assert "F_A" not in s["F"] and "attribution_step" not in s["F"]


def test_qh_background_is_complete_raw_without_roles_or_excerpts():
    s = V.review_spec_v2()["QH"]
    assert any("完整 as-of RAW" in x for x in s["shows"])
    assert any("摘录与 span 角色" in x for x in s["hides"])
    assert "必须" not in s["instruction"] and "不是评判标准" in s["instruction"]


def test_audit_ledger_never_shown_to_raters():
    r = V.AUDIT_LEDGER_RULE
    assert {"Q0", "QH"} <= set(r["never_shown_to"]) and any("依据回复质量修改标签" in x for x in r["forbidden"])


# ------------------------------------------------------------------ statistics
def test_t_table_against_scipy_when_available():
    st = pytest.importorskip("scipy.stats")
    for q in (0.975, 0.95, 0.80):
        for df in (5, 7, 16, 30):
            assert V.t_quantile(q, df) == pytest.approx(st.t.ppf(q, df), abs=2e-3)


def test_ni_minus_010_unreachable_on_17_groups_with_icc():
    assert V.required_per_group_for_margin(0.10, groups=17, decisive=0.5, icc=0.1) is None
    assert V.required_per_group_for_margin(0.10, groups=17, decisive=0.5, icc=0.05) is None
    m0 = V.required_per_group_for_margin(0.10, groups=17, decisive=0.5, icc=0.0)
    assert 20 <= m0 <= 35
    assert V.required_per_group_for_margin(0.30, groups=17, decisive=0.5, icc=0.1) is not None


def test_precision_anchor_and_monotone():
    a = V.precision_row(17, 2, 0.5, 0.1)
    b = V.precision_row(17, 4, 0.5, 0.1)
    assert 0.25 < a["half_width_95"] < 0.30 and b["mde_80"] < a["mde_80"]


def test_clopper_pearson_rule_of_three_and_needed_replies():
    assert V.cp_upper(0, 34) == pytest.approx(1 - 0.025 ** (1 / 34), abs=1e-6)
    assert V.cp_upper(0, 34) > 0.05
    n = V.replies_needed_for_bound(0.05, 0, 1.0)
    assert 70 <= n <= 75 and V.cp_upper(0, n) < 0.05 <= V.cp_upper(0, n - 1)
    assert V.paired_harm_detectable() == 6


def test_classify_never_turns_not_significant_into_non_inferior():
    assert V.classify(-0.3, 0.2, None) == ["inconclusive"]
    assert V.classify(-0.3, 0.2, 0.10) == ["inconclusive"]
    assert V.classify(-0.05, 0.2, 0.10) == ["non_inferior"]
    assert set(V.classify(0.05, 0.4, 0.10)) == {"superior", "non_inferior"}
    st = V.stats_v321()
    assert any("不显著不得解释为非劣" in x for x in st["reading_rules"])
    assert "-0.10（Q0 非劣界）" in st["not_gates"]


# ------------------------------------------------------------------ screen
def test_initial_screen_is_2_2_1_per_owner_from_frozen_draw():
    draw = json.loads(DRAW.read_text())
    s = V.initial_screen(draw)
    assert len(s["rows"]) == 90 and s["owners"] == 18
    c = Counter((r["owner_id"], r["stratum"]) for r in s["rows"])
    assert set(c.values()) == {1, 2} and all(c[(o, "S7_rank0")] == 1 for o in {r["owner_id"] for r in s["rows"]})
    assert {r["prefix_id"] for r in s["rows"]} <= {d["prefix_id"] for d in draw["drawn"]}
    assert all(r["order"] < 2 for r in s["rows"]) and all(0 < r["inclusion_probability"] <= 1 for r in s["rows"])
    assert V.initial_screen(draw)["screen_sha256"] == s["screen_sha256"]


def test_expansion_uses_labels_only_and_is_deterministic():
    draw = json.loads(DRAW.read_text())
    s = V.initial_screen(draw)
    screened = {r["prefix_id"] for r in s["rows"]}
    gof = {o: ("p13+p18" if o in ("p13", "p18") else o) for o in {d["owner_id"] for d in draw["drawn"]}}
    labels = {r["prefix_id"]: ("S1" if r["stratum"] == "cue" else "S0") for r in s["rows"] if r["stratum"] != "S7_rank0"}
    a = V.expansion_next(draw, screened, labels, gof)
    b = V.expansion_next(draw, screened, dict(labels), gof)
    assert a == b and all(set(d) == {"S2"} for d in a["deficit"].values())
    assert all(x["stratum"] == "cue" and x["prefix_id"] not in screened for x in a["next"] if x["prefix_id"])


# ------------------------------------------------------------------ PP1
def test_pp1_has_16_calls_on_8_prefixes_off_and_ret_ms():
    rows = json.loads(ELIG.read_text())["rows"]
    calls = V.pp1_calls(rows)
    assert len(calls) == 16 and len({c["prefix_id"] for c in calls}) == 8
    assert Counter(c["arm"] for c in calls) == {"OFF": 8, "RET-MS": 8}


def test_pp1_separated_and_stop_rules_are_outcome_free():
    p = V.pp1_protocol(json.loads(ELIG.read_text())["rows"])
    assert "不进入正式" in p["purpose"] and "默认不合并" in p["separation"]["pooling"]
    assert any("结果锁定" in x for x in p["stop"]["never"])
    c = p["cost"]
    assert c["calls"]["generator"] == 16 and c["calls"]["judge"] == 0 and c["calls"]["retries"] == 0
    assert c["gpu_seconds"]["upper_bound"] == 240 + 16 * 300
    assert c["human_minutes"]["total_with_overrun"] > c["human_minutes"]["total"] > 0


def test_freeze_marks_candidate_and_keeps_base():
    f = V.freeze(dict(x=1))
    assert f["status"] == "PROPOSED_NOT_ADOPTED" and f["base"]["protocol"] == Q.PROTOCOL
    assert "unchanged" in f["supersedes"]


def test_pp1_cost_reads_full_histories_and_screen_cost_counts_s7_cheaply():
    c = V.pp1_cost([5000] * 8)
    assert c["human_minutes"]["history_read_per_person"] == 160
    assert c["human_minutes"]["per_rater"] == round(8 * 1.5 + 160 + 8 * 3 + 16 * 4)
    s = V.screen_cost([0, 2500])
    assert s["minutes"] == round(1 + 10 + 3)
    f = V.fc_ms_cost(34, 5000)
    assert f["pairs"] == 102 and f["replies"] == 102 and f["total_hours"] > f["per_rater_hours"]


def test_pp1_call_order_follows_b6e_selection():
    sel = json.loads((PROJECT / "outputs/pm_rl1/v3/B6e_plan/v3/SELECTION.json").read_text())["selected_ids"]
    calls = V.pp1_calls(json.loads(ELIG.read_text())["rows"], sel)
    assert [c["prefix_id"] for c in calls[::2]] == sel and [c["arm"] for c in calls[:2]] == ["OFF", "RET-MS"]
