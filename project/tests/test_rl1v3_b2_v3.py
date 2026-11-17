"""Checklist v3 + judge v3 (atomic-error ledger) + aggregation v3 + ER-v3 on the attribution
counterexamples and regressions.  Programmatic examples only; no model is called."""
from __future__ import annotations

import json

import pytest

from metacom_pm.rl1v3 import contracts as K
from metacom_pm.rl1v3.checklist import writer_v2 as CW2, writer_v3 as CW3
from metacom_pm.rl1v3.env import finite_head as E
from metacom_pm.rl1v3.env.c0_binding import TerminalIdentity, subset_key
from metacom_pm.rl1v3.io import sha256_text
from metacom_pm.rl1v3.judge import aggregate_v3 as AG3, engineering_reward as ER1, engineering_reward_v2 as ER2
from metacom_pm.rl1v3.judge import engineering_reward_v3 as ER3, protocol_v2 as JP2, protocol_v3 as JP3
from rl1v3_b2_attribution_cases import CASE5, CASES, W, interval, ms_reading, reply, v3_answer, v2_answer, S3A, S3C, S4
from rl1v3_wsb_fixtures import context
from test_rl1v3_b2_checklist_judge import envelope

IDENT = TerminalIdentity("bank-v0", "idx-v0", "renderer:v0", "step2-v0", "g0-not-frozen", "greedy")


def cl3(env=None):
    env = env or envelope()
    return CW3.build(env["needcard"], method_evidence=env["method_evidence"]), env


def ident(role="J1"):
    return JP3.JudgeIdentityV3(role=role, model_id=f"fixture-{role}", model_sha256="1" * 64, decode_id="greedy")


def v3_run(cl, sentence, role="J1", readings=(), answers=None, **ans):
    it = iter(answers) if answers is not None else None
    gen = (lambda m: next(it)) if it is not None else (lambda m: v3_answer(cl, **ans))
    return JP3.run(gen, ident(role), context().prefix.turns, reply(sentence), cl, readings)


def fails(jr):
    return {i for i, x in jr.items.items() if x.verdict == "fail"}


def unc(jr):
    return {i for i, x in jr.items.items() if x.verdict == "uncertain"}


def er_args(cl, env, j1, sentence, *, heads=()):
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
                response=reply(sentence), finish_reason="natural_stop", verdicts=AG3.item_verdicts(cl, j1, None),
                j1_identity=j1.identity, expected_j1_identity=j1.identity, input_tokens=900, prefix_tokens=400,
                j1_ledger=JP3.ledger_summary(j1) if hasattr(j1, "ledger") else None)


# ------------------------------------------------------------------ checklist v3 keeps the fixed structure

def test_checklist_v3_keeps_items_weights_and_categories_of_v2():
    cl, env = cl3()
    v2 = CW2.build(env["needcard"], method_evidence=env["method_evidence"])
    strip = lambda c: [(i.item_id, i.category, i.constraint_type, i.weight, i.evidence_spans, i.applies_to,
                        i.visibility_scope) for i in c.items]
    assert strip(cl) == strip(v2) and cl.total_weight == v2.total_weight == W
    assert {i.category for i in cl.items} == {"H+", "H-", "R", "G", "I", "S"}
    for a, b in zip(cl.items, v2.items):
        assert a.text == b.text if a.category != "I" else b.text.endswith(a.text[1:]) and "Apart from" not in a.text
    assert [k for k, _ in CW3.FIXED_I] == [k for k, _ in CW2.FIXED_I] == list(CW3.I_KINDS)
    assert cl.writer_identity.startswith("pmrl1v3-checklist-template-v3|") and cl.writer_identity != v2.writer_identity
    assert CW3.WEIGHTS == CW2.WEIGHTS and CW3.CONSTRAINT == CW2.CONSTRAINT and len(CW3.ATTRIBUTION_RULES) == 8


# ------------------------------------------------------------------ the five counterexamples under v3

@pytest.mark.parametrize("name", sorted(CASES))
def test_v3_counts_each_true_atomic_error_exactly_once(name):
    cl, env = cl3()
    case = CASES[name]
    readings = ms_reading() if case.get("readings") == "ms" else ()
    j1 = v3_run(cl, case["sentence"], readings=readings, **case["v3"])
    assert fails(j1) == case["truth_fail"] and not unc(j1)
    rec = ER3.compute(**er_args(cl, env, j1, case["sentence"]))
    lo, hi = interval(cl, case["truth_fail"])
    assert rec["quality"]["j1_lower"] == pytest.approx(lo) and rec["quality"]["j1_upper"] == pytest.approx(hi)


def test_case1_and_2_two_errors_in_one_sentence_both_count_with_their_own_owner():
    cl, _ = cl3()
    j1 = v3_run(cl, CASES["1_two_errors_one_sentence"]["sentence"], **CASES["1_two_errors_one_sentence"]["v3"])
    assert {e["id"]: e["owner"] for e in j1.ledger} == {"c1:X1": "H-:3", "c1:X2": "I:1"}
    assert not j1.attributions and "error:c1:X2" in j1.items["I:1"].flags


def test_case3_whole_sentence_same_subclaim_is_attributed_by_error_identity():
    cl, _ = cl3()
    case = CASES["3a_whole_sentence_one_wrong_subclaim"]
    j1 = v3_run(cl, case["sentence"], **case["v3"])
    assert j1.items["I:1"].verdict == "pass" and "attributed_to:H-:3" in j1.items["I:1"].flags
    assert j1.attributions == [dict(item="I:1", attributed_to=["H-:3"], errors=["c1:X1"])]


@pytest.mark.parametrize("sentence", [S3A, S3C])
def test_case3_unsplit_whole_sentence_quotes_become_uncertain_never_merged(sentence):
    """A judge that files two entries but quotes the whole sentence for both: the interval covers
    'one error' and 'two errors' (L5); nothing is silently merged or surely counted twice."""
    cl, _ = cl3()
    j1 = v3_run(cl, sentence, errors=[("X1", "history_conflict", [sentence], "E5"), ("X2", "fabricated_history", [sentence], "")],
                rows={"H-:3": ("fail", ["X1"]), "I:1": ("fail", ["X2"])})
    assert fails(j1) == {"H-:3"} and unc(j1) == {"I:1"}
    assert "overlap_ambiguous" in j1.items["I:1"].flags and "ambiguous_with:c1:X1" in j1.items["I:1"].flags
    assert interval(cl, fails(j1), unc(j1)) == pytest.approx((1 - 3 / W, 1 - 2 / W))


def test_identical_quotes_with_different_ids_are_not_merged_either():
    cl, _ = cl3()
    q = "Anna still lives in Berlin"
    j1 = v3_run(cl, S3A, errors=[("X1", "history_conflict", [q], "E5"), ("X2", "fabricated_history", [q], "")],
                rows={"H-:3": ("fail", ["X1"]), "I:1": ("fail", ["X2"])})
    assert fails(j1) == {"H-:3"} and unc(j1) == {"I:1"}


def test_case4_i_kind_citing_h_minus_evidence_is_owned_by_that_h_minus_item():
    cl, _ = cl3()
    j1 = v3_run(cl, S4, errors=[("X1", "history_conflict", ["Your sister Anna still lives in Berlin"], "E5"),
                                ("X2", "misidentification", ["her in Berlin"], "E5")],
                rows={"H-:3": ("fail", ["X1"]), "I:2": ("fail", ["X2"])})
    assert {e["id"]: e["owner_rule"] for e in j1.ledger} == {"c1:X1": "L2:h_minus_evidence",
                                                             "c1:X2": "L2:i_kind_cites_h_minus_evidence"}
    assert fails(j1) == {"H-:3"} and j1.items["I:2"].verdict == "pass"


def test_case4_residual_undeclared_duplicate_without_evidence_is_visible_in_the_ledger():
    """Documented limit: if the judge files the repeat as a separate I error, cites no evidence and the
    quotes are disjoint, no rule can tell it is the same error; it counts, and the ledger shows both
    entries for the B2 development audit (and J2 disagreement)."""
    cl, _ = cl3()
    j1 = v3_run(cl, S4, errors=[("X1", "history_conflict", ["Your sister Anna still lives in Berlin"], "E5"),
                                ("X2", "misidentification", ["her in Berlin"], "")],
                rows={"H-:3": ("fail", ["X1"]), "I:2": ("fail", ["X2"])})
    assert fails(j1) == {"H-:3", "I:2"}
    assert JP3.ledger_summary(j1)["owners"] == {"c1:X1": "H-:3", "c1:X2": "I:2"}


def test_case5_ownership_swap_between_judges_waits_for_human_adjudication():
    cl, _ = cl3()
    j1 = v3_run(cl, CASE5["sentence"], **CASE5["v3"]["J1"])
    j2 = v3_run(cl, CASE5["sentence"], role="J2", **CASE5["v3"]["J2"])
    assert fails(j1) == {"H-:3"} and fails(j2) == {"I:2"}
    d = AG3.attribution_disputes(cl, j1, j2)
    assert d and d[0]["items"] == ["H-:3", "I:2"] and d[0]["j1_only_fail"] == ["H-:3"]
    v = AG3.item_verdicts(cl, j1, j2)
    assert AG3.gsc_admission(cl, v, d)["status"] == "pending_adjudication"
    assert AG3.gsc_interval(cl, v, d) == (None, None)          # pending, never 0 and never the C0 [lo, 1.0]
    resp = reply(CASE5["sentence"])
    adj = lambda verdict: K.HumanAdjudication(reviewer_id="fixture-reviewer", record_uri="fixture://adj/1",
                                              record_sha256="2" * 64, response_sha256=sha256_text(resp),
                                              verdict=verdict, reason="one error: outdated fact owned by H-:3")
    v = AG3.item_verdicts(cl, j1, j2, human={"H-:3": adj("fail"), "I:2": adj("pass")})
    assert AG3.gsc_admission(cl, v, d)["status"] == "admissible"
    assert AG3.gsc_interval(cl, v, d) == pytest.approx(interval(cl, CASE5["truth_fail"]))


def test_existence_disagreement_without_swap_keeps_the_v1_rule():
    cl, _ = cl3()
    j1 = v3_run(cl, CASE5["sentence"], **CASE5["v3"]["J1"])
    j2 = v3_run(cl, CASE5["sentence"], role="J2")
    assert AG3.attribution_disputes(cl, j1, j2) == []
    v = AG3.item_verdicts(cl, j1, j2)
    assert AG3.gsc_interval(cl, v, []) == pytest.approx((1 - 2 / W, 1.0))


# ------------------------------------------------------------------ ledger rules L2/L6 and parsing

def test_fail_without_valid_error_is_uncertain():
    cl, _ = cl3()
    j1 = v3_run(cl, S3A, errors=[("X1", "history_conflict", ["Anna still lives in Berlin"], "")],   # no H- evidence
                rows={"H-:3": ("fail", ["X1"]), "I:4": ("fail", []), "I:1": ("fail", ["X9"])})
    assert j1.ledger[0]["invalid"] == "history_conflict_without_h_minus_evidence"
    assert unc(j1) == {"H-:3", "I:4", "I:1"} and not fails(j1)
    assert "unknown_error_ref:c1:X9" in j1.items["I:1"].flags


def test_owned_error_with_pass_row_is_uncertain_and_bad_quotes_invalidate_entries():
    cl, _ = cl3()
    j1 = v3_run(cl, S3C, errors=[("X1", "fabricated_history", ["you quit your job yesterday"], ""),
                                 ("X2", "unsupported_inference", ["not in the reply"], "")],
                rows={"I:4": ("fail", ["X2"])})
    assert j1.items["I:1"].verdict == "uncertain" and "ledger_row_conflict" in j1.items["I:1"].flags
    assert j1.ledger[1]["invalid"] == "quote_not_in_reply" and j1.items["I:4"].verdict == "uncertain"


def test_errors_on_other_categories_are_ignored_and_flagged():
    cl, _ = cl3()
    g = next(i.item_id for i in cl.items if i.category == "G")
    j1 = v3_run(cl, S3A, rows={g: ("fail", ["X1"])})
    assert j1.items[g].verdict == "fail" and "errors_on_non_integrity_item" in j1.items[g].flags


def test_structure_errors_reask_then_uncertain_and_reask_ids_are_namespaced():
    cl, _ = cl3()
    bad = json.dumps([dict(id="H-:1", verdict="pass", quote="", evidence="")])          # v2 shape
    j1 = v3_run(cl, S3A, answers=[bad, bad])
    assert j1.calls == 2 and all("parse_failed" in x.flags for x in j1.items.values())
    first = json.loads(v3_answer(cl, errors=[("X1", "history_conflict", ["Anna still lives in Berlin"], "E5")],
                                 rows={"H-:3": ("fail", ["X1"])}))
    first["items"] = [r for r in first["items"] if r["id"] != "I:1"]
    second = v3_answer(cl, errors=[("X1", "fabricated_history", ["work has been overwhelming"], "")],
                       rows={"I:1": ("fail", ["X1"])}, only={"I:1"})
    j1 = v3_run(cl, S3A, answers=[json.dumps(first), second])
    assert j1.calls == 2 and {e["id"] for e in j1.ledger} == {"c1:X1", "c2:X1"}
    assert fails(j1) == {"H-:3", "I:1"}                     # the re-ask's X1 is a different error, not an alias


def test_judge_v3_sees_resources_and_identity_binds_the_ledger_rules():
    cl, _ = cl3()
    msgs = JP3.render(context().prefix.turns, reply(S3A), cl, readings=ms_reading())
    data = json.loads(msgs[1]["content"].split("\n", 1)[1])
    assert data["RESOURCES_GIVEN_TO_REPLY"][0]["head"] == "MS" and "ERRORS" in msgs[0]["content"]
    assert "Apart from" not in msgs[1]["content"]
    i3, i2 = ident(), JP2.JudgeIdentityV2(role="J1", model_id="fixture-J1", model_sha256="1" * 64, decode_id="greedy")
    assert "|pmrl1v3-itemjudge-v3|" in i3.id and i3.id != i2.id


# ------------------------------------------------------------------ ER-v3 binding

def test_er_v3_equals_er_v2_computation_on_a_clean_terminal():
    cl, env = cl3()
    j1 = v3_run(cl, S3A)
    rec = ER3.compute(**er_args(cl, env, j1, S3A, heads=("MP", "ME")))
    assert rec["value"] == pytest.approx(1 - 0.02) and rec["is_gsc"] is False and rec["protocol"] == ER3.PROTOCOL
    assert rec["get_penalty"]["label"] == ER2.GET_PENALTY_LABEL and len(rec["sensitivity"]) == 12
    assert ER3.SENSITIVITY_GRID == ER2.SENSITIVITY_GRID and ER3.PRIMARY == ER2.PRIMARY
    assert ER3.ERConfigV3().max_uncertain_weight == ER2.ERConfigV2().max_uncertain_weight
    assert rec["j1_ledger"]["errors"] == 0
    assert ER3.preregistration()["sha256"] != ER2.preregistration()["sha256"]


def test_versions_do_not_mix():
    cl, env = cl3()
    j1 = v3_run(cl, S3A)
    # ER-v2 refuses a v3 checklist (its binding), ER-v3 refuses v2 checklists and v2 judge runs
    with pytest.raises(ER1.RewardUnavailable) as e:
        args = er_args(cl, env, j1, S3A)
        args.pop("j1_ledger")
        ER2.compute(**args, j1_attributions=())
    assert "checklist_protocol_not_v2" in e.value.reasons
    cl2 = CW2.build(env["needcard"], method_evidence=env["method_evidence"])
    j2run = JP2.run(lambda m: v2_answer(cl2), JP2.JudgeIdentityV2(role="J1", model_id="m", model_sha256="1" * 64,
                                                                   decode_id="g"), context().prefix.turns, reply(S3A), cl2)
    with pytest.raises(ER1.RewardUnavailable) as e:
        ER3.compute(**dict(er_args(cl2, env, j2run, S3A), j1_ledger=None))
    assert {"checklist_protocol_not_v3", "j1_protocol_not_v3"} <= set(e.value.reasons)
    with pytest.raises(ValueError, match="only ER-v3"):
        ER3.to_outcome(dict(ER3.compute(**er_args(cl, env, j1, S3A)), protocol=ER2.PROTOCOL))


def test_er_v3_keeps_hard_safety_uncertain_refusal_and_safety_floor():
    cl, env = cl3()
    s = next(i.item_id for i in cl.items if i.category == "S")
    with pytest.raises(ER1.RewardUnavailable) as e:
        ER3.compute(**er_args(cl, env, v3_run(cl, S3A, rows={s: ("uncertain", [])}), S3A))
    assert "hard_safety_uncertain" in e.value.reasons
    rec = ER3.compute(**er_args(cl, env, v3_run(cl, S3A, rows={s: ("fail", [])}), S3A, heads=("RS",)))
    assert rec["value"] == -1.0 and set(rec["sensitivity"].values()) == {-1.0}
    out = ER3.to_outcome(ER3.compute(**er_args(cl, env, v3_run(cl, S3A), S3A)))
    assert out.detail["protocol"] == ER3.PROTOCOL
