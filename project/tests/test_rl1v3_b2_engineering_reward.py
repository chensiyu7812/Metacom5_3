"""ER-v1: the named engineering reward is computable only from complete J1 and never becomes GSC."""
from __future__ import annotations

import dataclasses

import pytest

from metacom_pm.rl1v3 import contracts as K
from metacom_pm.rl1v3.env import finite_head as E
from metacom_pm.rl1v3.env.c0_binding import TerminalIdentity, TerminalTable, subset_key
from metacom_pm.rl1v3.judge import aggregate as AG, engineering_reward as ER
from test_rl1v3_b2_checklist_judge import REPLY, checklist, envelope, judged
from rl1v3_wsb_fixtures import context

IDENT = TerminalIdentity("bank-v0", "idx-v0", "render-v0", "step2-v0", "g0-unfrozen", "greedy")


def setup(**kw):
    cl, env = checklist()
    key = subset_key(context().prefix, IDENT, {}, 0)
    trace = K.ExecutionTrace(domain_id="finite_head_v1", ordered_path=("STOP",), acquired=(), readings=())
    j1 = judged(cl, **kw)
    v = AG.item_verdicts(cl, j1, None)
    args = dict(key=key, trace=trace, checklist=cl, needcard=env["needcard"], evidence_validation="verified",
                response=REPLY, finish_reason="natural_stop", verdicts=v, j1_identity=j1.identity,
                expected_j1_identity=j1.identity, input_tokens=512)
    return cl, env, args


def test_value_uses_fixed_denominator_midpoint_and_get_cost():
    cl, _, args = setup()
    rec = ER.compute(**args)
    assert rec["value"] == pytest.approx(1.0) and rec["is_gsc"] is False
    assert rec["qualification_tier"] == "engineering_only" and rec["j2_status"] == "not_run"
    g = [i for i in cl.items if i.category == "G"]
    cl2, _, args2 = setup(verdicts={g[0].item_id: "fail", g[1].item_id: "uncertain"})
    rec2 = ER.compute(**args2)
    W = cl2.total_weight
    assert rec2["j1_lower"] == pytest.approx(1 - 2 / W) and rec2["j1_upper"] == pytest.approx(1 - 1 / W)
    assert rec2["q"] == pytest.approx(1 - 1.5 / W) and rec2["value"] == pytest.approx(rec2["q"])


def test_safety_failure_floors_value_and_is_not_traded_against_cost():
    cl, _, args = setup()
    s = next(i for i in cl.items if i.category == "S").item_id
    _, _, args = setup(verdicts={s: "fail"})
    rec = ER.compute(**args)
    assert rec["value"] == ER.ERConfig().unsafe_value and rec["j1_safety_fail_items"] == [s]


@pytest.mark.parametrize("mutate,reason", [
    (lambda a: a.update(evidence_validation="pending"), "evidence_not_verified"),
    (lambda a: a.update(finish_reason="technical_timeout"), "reply_incomplete"),
    (lambda a: a.update(response="   "), "reply_incomplete"),
    (lambda a: a.update(expected_j1_identity="J1|other"), "j1_identity_mismatch"),
    (lambda a: a.update(verdicts=a["verdicts"][1:]), "verdict_coverage_differs_from_checklist"),
    (lambda a: a.update(verdicts=AG.item_verdicts(a["checklist"], None, None)), "j1_incomplete"),
    (lambda a: a.update(needcard=envelope(stratum="none", history_items=[], failed_or_rejected=[], outdated_facts=[],
                                          method_need=None, method_evidence=[])["needcard"]), "checklist_not_bound_to_needcard"),
    (lambda a: a.update(trace=K.ExecutionTrace(domain_id="finite_head_v1", ordered_path=("GET_MP", "STOP"),
                                               acquired=(("r1",),), readings=(K.ReadingView(head="MP", view="assertion",
                                               ordinal=1, reading_text="x", reported_at=None, tokens=1),))),
     "trace_does_not_reproduce_key"),
])
def test_refuses_instead_of_guessing(mutate, reason):
    _, _, args = setup()
    mutate(args)
    with pytest.raises(ER.RewardUnavailable) as e:
        ER.compute(**args)
    assert reason in e.value.reasons


def test_too_uncertain_is_refused():
    cl, _, _ = setup()
    many = {i.item_id: "uncertain" for i in cl.items[:6]}
    _, _, args = setup(verdicts=many)
    with pytest.raises(ER.RewardUnavailable, match="too_uncertain"):
        ER.compute(**args)


def test_j2_does_not_change_er_v1_and_er_never_fills_gsc():
    cl, env, args = setup()
    rec = ER.compute(**args)
    j1 = judged(cl)
    j2 = judged(cl, role="J2", verdicts={cl.items[0].item_id: "fail"})
    rec2 = ER.compute(**dict(args, verdicts=AG.item_verdicts(cl, j1, j2)))
    assert rec2["value"] == rec["value"] and rec2["j2_status"] == "complete"
    t = AG.terminal_record(key=args["key"], trace=args["trace"], checklist=cl, feedback_id="fb", request_sha256="3" * 64,
                           response=REPLY, verdicts=args["verdicts"], evidence_validation="verified")
    assert t.gsc_lower is None and t.gsc_upper is None


def test_engineering_table_drives_env_and_missing_terminals_stay_pending():
    _, _, args = setup()
    rec = ER.compute(**args)
    table = TerminalTable({rec["key_sha256"]: ER.to_outcome(rec)}, table_id="er-v1-fixture")
    assert table.lookup(args["key"]).reward == rec["value"]
    other = subset_key(context().prefix, dataclasses.replace(IDENT, g_id="g0-other"), {}, 0)
    with pytest.raises(E.PendingTerminal):
        table.lookup(other)
    with pytest.raises(ValueError, match="only ER-v1"):
        ER.to_outcome(dict(rec, qualification_tier="research_qualified"))
