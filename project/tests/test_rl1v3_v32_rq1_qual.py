"""V3.2 RQ1 resource-effect qualification candidate (CPU): channels, strata, statistics, exposure, gates."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from metacom_pm.rl1v3.evaluate import resource_effect_v32q as Q
from metacom_pm.rl1v3.io import object_sha256

PROJECT = Path(__file__).resolve().parents[1]
P0P2 = PROJECT / "outputs/pm_rl1/v3/V32_WSB_P0P2"


# ------------------------------------------------------------------ frozen inputs stay as they are
def test_frozen_p2_v1_unchanged():
    v1 = json.loads((P0P2 / "p2/P2_PROTOCOL_FROZEN.json").read_text())
    body = {k: v for k, v in v1.items() if k != "protocol_sha256"}
    assert v1["protocol_sha256"] == object_sha256(body) == \
        "2b6057c8dde4b443c08fd3ff281cb6c22c3ebd1f4d1a02eab8ac948a7bd4c81f"


def test_old54_joint_eligibility_and_eligible_subsets():
    e = json.loads((P0P2 / "p2/ELIGIBILITY_54.json").read_text())
    rows = [r for r in e["rows"] if r["plan_job_id"]]
    assert len(rows) == 54
    assert Counter(r["joint_eligibility"] for r in rows) == {"ELIGIBLE": 16, "LEGACY_DIAGNOSTIC": 24, "BLOCKED": 14}
    assert Counter(r["subset"] for r in rows if r["joint_eligibility"] == "ELIGIBLE") == {"OFF": 8, "MS": 8}


def test_candidate_is_not_adopted_and_supersedes_nothing():
    f = Q.freeze(dict(x=1))
    assert f["status"] == "PROPOSED_NOT_ADOPTED"
    assert "unchanged" in f["supersedes"]
    assert f["protocol_sha256"] == object_sha256({k: v for k, v in f.items() if k != "protocol_sha256"})


# ------------------------------------------------------------------ channels
def test_q0_hides_history_and_readings():
    s = Q.review_spec()
    hidden = " ".join(s["Q0"]["hides"])
    assert "历史背景" in hidden and "读取内容" in hidden and "J1" in hidden


def test_qh_packet_is_arm_independent():
    r = Q.QH_PACKET_RULE
    assert r["same_for_all_conditions"] is True
    assert any("并集" in x for x in r["forbidden"])
    assert any("排名" in x for x in r["forbidden"])
    assert "不看任何资源臂" in r["built_by"]
    assert "生成之前冻结" in r["frozen"]


def test_qh_does_not_show_q0_answers_and_channels_stay_separate():
    s = Q.review_spec()
    assert any("Q0" in x for x in s["QH"]["hides"])
    assert any("不事后加权" in x for x in s["independence"])


def test_f_rules_optional_history_not_error_and_evidence_required():
    s = Q.review_spec()["F"]
    assert any("没有提及可选历史不是错误" in x for x in s["rules"])
    assert any("合法证据" in x for x in s["rules"])
    assert set(Q.F_ITEMS) >= {"F1_subject_confusion", "F2_stage_error", "F3_stale_as_current",
                              "F4_repeats_rejected_or_failed", "F5_fabricated_history", "F6_forced_unneeded_recall",
                              "F7_inappropriate_advice", "F8_safety"}
    assert s["attribution_step"]["blind"] is False


# ------------------------------------------------------------------ pair rules and statistics
@pytest.mark.parametrize("labels,pos,score,cat", [
    (["A_better", "A_better"], "A", 1.0, "win"),
    (["A_better", "tie"], "A", 0.5, "win"),
    (["A_better", "B_better"], "A", 0.0, "tie"),
    (["B_better", "uncertain"], "A", -1.0, "loss"),
    (["uncertain", "uncertain"], "A", None, "uncertain"),
    (["tie", "tie"], "B", 0.0, "tie"),
])
def test_pair_outcome(labels, pos, score, cat):
    o = Q.pair_outcome(labels, pos)
    assert o["score"] == score and o["category"] == cat


def test_split_is_flagged():
    assert Q.pair_outcome(["A_better", "B_better"], "A")["split"] is True


def test_unknown_label_rejected():
    with pytest.raises(ValueError):
        Q.rater_score("better", "A")


def test_owner_groups_merge_shared_family():
    g = Q.owner_groups([f"p{i}" for i in range(1, 19)], [["p13", "p18"]])
    assert len(g) == 17 and g["p13+p18"] == ["p13", "p18"]


def test_uncertain_never_zero_only_bounds():
    gof = {"p1": "p1", "p2": "p2"}
    pairs = [dict(owner_id="p1", **Q.pair_outcome(["A_better", "A_better"], "A")),
             dict(owner_id="p2", **Q.pair_outcome(["uncertain", "uncertain"], "A"))]
    est = Q.cluster_estimate(pairs, gof)
    assert est["estimate"] == 1.0 and est["groups"] == 1 and est["uncertain_pairs"] == 1
    b = Q.uncertainty_bounds(pairs, gof)
    assert b == dict(lower=0.0, upper=1.0)


def test_equal_weight_per_owner_group():
    gof = {"p1": "p1", "p2": "p2"}
    pairs = [dict(owner_id="p1", score=1.0, category="win") for _ in range(9)] + \
            [dict(owner_id="p2", score=-1.0, category="loss")]
    assert Q.cluster_estimate(pairs, gof)["estimate"] == 0.0


def test_sign_flip_exact():
    assert Q.sign_flip_p([1.0, 1.0, 1.0]) == pytest.approx(2 / 8)
    assert Q.sign_flip_p([0.0]) == 1.0


def test_holm_stepdown():
    h = Q.holm(dict(a=0.01, b=0.04, c=0.03))
    assert h["a"]["reject"] and not h["c"]["reject"] and not h["b"]["reject"]


def test_precision_monotone():
    a = Q.half_width(groups=17, per_group=2, decisive=0.5, icc=0.1)
    b = Q.half_width(groups=17, per_group=4, decisive=0.5, icc=0.1)
    c = Q.half_width(groups=8, per_group=4, decisive=0.5, icc=0.1)
    assert b < a and c > b
    assert Q.required_per_group(groups=17, target_half_width=0.2, decisive=0.5, icc=0.1) == 4


# ------------------------------------------------------------------ strata and draw
def test_prefix_candidates_s7_and_cues():
    f = Q.prefix_candidates(cutoff_rank=0, past_cues=[], surface={}, mp_changed_slots=0, me_old_ongoing=0)
    assert f["S7"] and not f["explicit_reference_cue"]
    g = Q.prefix_candidates(cutoff_rank=3, past_cues=[dict(supporter_suggestions=1, seeker_third_party_lines=0,
                                                         rejection_after_suggestion=1)],
                            surface=dict(back_reference=True), mp_changed_slots=1, me_old_ongoing=0)
    assert not g["S7"] and g["explicit_reference_cue"] and g["S3_slot_changed_before_cutoff"]
    assert g["S5_rejection_after_suggestion"] and not g["S6_past_third_party"]


def _frame():
    rows = []
    for o in ("p1", "p2"):
        for i in range(10):
            rows.append(dict(prefix_id=f"{o}-{i}", owner_id=o,
                             flags=dict(S7=i == 0, explicit_reference_cue=i in (1, 2, 3))))
    return rows


def test_screening_draw_deterministic_quota_and_exclusion():
    a = Q.screening_draw(_frame(), salt="s", exclude={"p1-1"})
    b = Q.screening_draw(_frame(), salt="s", exclude={"p1-1"})
    assert a["draw_sha256"] == b["draw_sha256"]
    assert all(d["prefix_id"] != "p1-1" for d in a["drawn"])
    c = Counter((d["owner_id"], d["stratum"]) for d in a["drawn"])
    assert c[("p1", "cue")] == 2 and c[("p2", "cue")] == 3 and c[("p1", "S7_rank0")] == 1 and c[("p1", "other")] == 4
    assert Q.screening_draw(_frame(), salt="t")["draw_sha256"] != Q.screening_draw(_frame(), salt="s")["draw_sha256"]


def test_draw_uses_no_reply_or_score_fields():
    rows = _frame()
    for r in rows:
        r["reply"] = "x"
        r["score"] = 1.0
    plain = Q.screening_draw(_frame(), salt="s")
    assert Q.screening_draw(rows, salt="s")["draw_sha256"] == plain["draw_sha256"]


def test_need_labels_partition_and_needcard_map():
    assert Q.NEED_LABELS == ("S1", "S2", "S0", "unclear")
    assert set(Q.NEEDCARD_ROLE_MAP) == {"S1", "S2", "S0"}


# ------------------------------------------------------------------ exposure, executability, gates
def test_exposure_is_recorded_not_excluding():
    assert "不自动排除" in Q.EXPOSURE_RULE and "result lock" in Q.EXPOSURE_RULE
    assert set(Q.EXPOSURE_KINDS) == {"inspection", "design", "outcome_other_contrast", "outcome_same_contrast"}


def _facts(**kw):
    f = dict(g0_identity=False, raters_scheduled=False, primary_metric_approved=False, screen_labels=False,
             qh_packets=False, wsa_8owner_evidence=False, eligible_16_is_8off_8ms=True, identity_54_unchanged=True,
             materials={})
    f.update(kw)
    return f


def test_nothing_executable_without_g0():
    rows = Q.executability(_facts())
    assert rows and not any(r["executable_now"] for r in rows)
    assert all(any("G0 identity" in b for b in r["blockers"]) for r in rows)


def test_executable_only_when_every_prerequisite_holds():
    full = dict(g0_identity=True, raters_scheduled=True, primary_metric_approved=True, screen_labels=True,
                qh_packets=True, materials={"DP-MP": True, "DP-ME": True, "DP-MS": True, "RS-METHOD": True,
                                            "bounded_renderer": True, "RET-MS-asof": True})
    rows = Q.executability(_facts(**full))
    assert all(r["executable_now"] for r in rows if not r["family"].startswith("M5"))


def test_gates_blocked_now():
    g = Q.gate_list(_facts())
    assert g["gate1"]["state"] == "BLOCKED" and g["gate2"]["state"] == "BLOCKED"
    assert {i["state"] for i in g["gate1"]["items"]} <= {"PASS", "BLOCKED", "PENDING"}
    assert g["gate1"]["items"][0]["state"] == "PASS"


def test_stats_plan_forbids_post_hoc_changes_and_scopes_claims():
    p = Q.stats_plan()
    assert any("after viewing" in x for x in p["not_allowed"])
    assert "independent users" in " ".join(p["not_allowed"])
    assert "not a gate" in p["claim_levels"]["generalization"]
