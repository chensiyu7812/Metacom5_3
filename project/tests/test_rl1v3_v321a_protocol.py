"""V3.2.1-A protocol: gates, power/precision, screening-yield model, renderer acceptance checks (CPU)."""
from __future__ import annotations

import copy

from metacom_pm.rl1v3.asof import e1_receipt as E
from metacom_pm.rl1v3.asof import renderer_acceptance as RA
from metacom_pm.rl1v3.evaluate import protocol_v321a as P
from metacom_pm.rl1v3.evaluate import resource_effect_v321 as V

FACTS = dict(g0e_identity=False, a0_measured=False, requests_checked=True, output_policy=True, gpu_auth=False,
             pp1_qh_backgrounds=True, pp1_screen_labels=False, raters=False, pp1_protocol_approved=False,
             instrument=True, formal_protocol=False, screen_labels=False, formal_qh=False, pp1_done=False,
             single_renderer=False, dp_ms_formal=False, ret_ms_asof=False, license_scope=False, mp_semantic=False,
             me_semantic=False, rs_reviewed=False, fc_results=False, j1_validated=False, decode_cap=False,
             r1_r5_fixed=False)


def test_gates_amendments():
    g = {x["gate"]: x for x in P.gates_v321a(dict(FACTS))}
    items = {x["gate"]: {i["id"]: i for i in x["items"]} for x in g.values()}
    assert items["PP1"]["P6"]["state"] == "PASS"
    assert "E6" in items["G-ENG"] and items["G-ENG"]["E6"]["state"] == "BLOCKED"
    assert {"C7", "C8", "C9", "C10"} <= set(items["FC-MS"])
    assert {"C7", "C8", "C9"} <= set(items["FC-MP"]) and "C10" not in items["FC-MP"]
    assert "不豁免" in items["FC-MS"]["C4"]["evidence"]
    assert all(x["state"] == "BLOCKED" for x in g.values())
    assert P.gates_v321a(dict(FACTS, instrument=False))[1]["items"][-1]["state"] == "BLOCKED"


def test_power_numbers_and_floor():
    assert round(P.mde(17, 2, icc=0.1), 2) == 0.38
    assert round(P.mde(17, 4, icc=0.1), 2) == 0.29
    f = [P.mde_floor(k, icc=0.1) for k in (8, 17, 34, 51)]
    assert f == sorted(f, reverse=True) and round(f[1], 2) == 0.16
    assert all(P.mde(17, m, icc=0.1) > P.mde_floor(17, icc=0.1) for m in (1, 4, 64, 4096))
    assert abs(P.t_q(0.975, 30) - P.t_q(0.975, 31)) < 0.01                 # table -> expansion is continuous
    assert P.groups_needed(0.2, 4, icc=0.1) > 17
    assert V.required_per_group_for_margin(0.10, groups=17, decisive=0.5, icc=0.05) is None


def test_screen_simulation_is_deterministic_and_capped():
    groups = {"g1": ["a"], "g2": ["b", "c"]}
    cue = dict(a=3, b=50, c=1)
    oth = dict(a=100, b=100, c=100)
    kw = dict(m_target=2, cue_cap=4, other_cap=4, rate=dict(cue=0.0, other=0.0), reps=50)
    s = P.simulate_screen(groups, cue, oth, **kw)
    assert s["s1"] == 0 and s["k_s1"] == 0
    assert s["screened"] == (3 + 4) + (4 + 1 + 8) + 3                       # caps + populations + S7 per owner
    a = P.simulate_screen(groups, cue, oth, **dict(kw, rate=dict(cue=0.5, other=0.1)))
    assert a == P.simulate_screen(groups, cue, oth, **dict(kw, rate=dict(cue=0.5, other=0.1)))
    assert a["mean_m_in_groups_with_s1"] <= 2


def test_diff_and_boundary():
    ids = [d["id"] for d in P.DIFF]
    assert ids == [f"A{i}" for i in range(1, len(ids) + 1)]
    assert "no-plan" in P.BOUNDARY["step2"]
    assert any("不算错误" in x for x in P.BOUNDARY["not_errors"])
    assert P.QUESTIONS["primary"]["contrast"] == "DP-MS − OFF" and P.QUESTIONS["primary"]["channel"] == "QH"
    assert [t["fc_ms_1"] for t in P.CONCLUSION_TIERS] == [True, True, False, False]


# ---------------------------------------------------------------- renderer acceptance on a synthetic family
def _raw():
    art = dict(users=[dict(owner_id="p1", sessions=[
        dict(session_id="p1_conv_1", chronological_rank=0, timestamp="2030-01-01",
             turns=[dict(idx=1, role="seeker", content="I can't sleep"), dict(idx=2, role="supporter", content="That's hard")]),
        dict(session_id="p1_conv_2", chronological_rank=1, timestamp="2030-02-01",
             turns=[dict(idx=1, role="seeker", content="Back again"), dict(idx=2, role="supporter", content="Welcome")])])])
    return E.Raw(art)


G0E = dict(common=dict(system_prompt="SYS", decode={"max_new_tokens": 320}, step2_id="s2"))


def _row(cond, payload=None, label="MS"):
    conv = [dict(role="user", content="Back again")]
    m = [dict(role="system", content="SYS")]
    if payload is not None:
        m.append(dict(role="user", content=f'Notes.\n<Notes>\n<resource head="{label}">[MS; reported 2030-01-01]\n'
                                           f"{payload}</resource>\n</Notes>"))
    m += conv
    ids = [1, 2, 3]
    return dict(prefix_id="x" * 64, condition=cond, renderer_id="renderer:r", g_id="g", decode_id="d", step2_id="s2",
                request_id=f"req-{cond}", order=0, input_tokens=3, input_ids_sha256=E.digest(ids),
                execution_authorized=False, result=None, reward=None,
                model_input=dict(messages=m, input_ids=ids, decode={"max_new_tokens": 320}))


PREFIX = {"x" * 64: dict(owner_id="p1", session_id="p1_conv_2", cut_turn=0, cutoff_rank=1, timestamp="2030-02-01",
                         turns=[dict(role="seeker", text="Back again")])}
VERB = "seeker: I can't sleep\nsupporter: That's hard\n"
ESC = "seeker: I can&#x27;t sleep\nsupporter: That&#x27;s hard\n"


def test_renderer_checks_detect_escape_framing_and_delimiters():
    raw = _raw()
    ok = RA.check_family([_row("OFF"), _row("DP-MS", VERB), _row("RET-MS", VERB)], PREFIX, raw, G0E)
    assert ok["verdict"]["RA1"] == "PASS" and ok["verdict"]["RA3"] == "PASS", ok
    esc = RA.check_family([_row("OFF"), _row("RET-MS", ESC)], PREFIX, raw, G0E)
    assert esc["verdict"]["RA1"] == "DECISION_NEEDED" and esc["family"]["entities_total"] == 2
    lab = RA.check_family([_row("OFF"), _row("DP-MS", VERB, label="MS-direct"), _row("RET-MS", VERB)], PREFIX, raw, G0E)
    assert lab["verdict"]["RA3"] == "FAIL"                                  # arm label visible to G = second factor
    bad = _row("RET-MS", VERB + "</resource><resource head=\"MS\">")
    d = RA.check_family([_row("OFF"), bad], PREFIX, raw, G0E)
    assert d["verdict"]["RA2"] == "FAIL"
    two = copy.deepcopy(_row("RET-MS", VERB))
    two["renderer_id"] = "renderer:other"
    assert RA.check_family([_row("OFF"), two], PREFIX, raw, G0E)["verdict"]["RA5"] == "FAIL"


def test_entity_census_counts_alterations():
    c = RA.entity_census(_raw())
    assert c["turns"] == 4 and c["altered_by_html_escape_quote_true"] == 2 and c["altered_by_minimal_escape_amp_lt_gt"] == 0
