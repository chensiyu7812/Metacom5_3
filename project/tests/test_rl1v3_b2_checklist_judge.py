"""B2: fixed checklist, freeze-before-candidates ledger, J1/J2 parsing and aggregation."""
from __future__ import annotations

import json

import pytest

from metacom_pm.rl1v3 import contracts as K
from metacom_pm.rl1v3.checklist import writer as CW
from metacom_pm.rl1v3.checklist.ledger import ChecklistLedger, ChecklistOrderError
from metacom_pm.rl1v3.io import sha256_text
from metacom_pm.rl1v3.judge import aggregate as AG, protocol as JP
from metacom_pm.rl1v3.needs import cards, protocol as P
from rl1v3_wsb_fixtures import CATALOG, context, writer_output

REPLY = "I hear how exhausting work is. Since the breathing exercise did not help before, maybe try a short wind-down routine tonight."


def envelope(text=None, **over):
    ctx = context()
    pack = P.build_pack(ctx, CATALOG)
    return cards.assemble(ctx, pack, P.parse_output(text or writer_output(**over), pack), writer="fixture-writer")


def checklist(env=None):
    env = env or envelope()
    return CW.build(env["needcard"], method_family_text=dict(CATALOG.families),
                    method_evidence=env["method_evidence"]), env


def answer(cl, verdicts=None, quotes=None, evidence=None):
    verdicts, quotes, evidence = verdicts or {}, quotes or {}, evidence or {}
    return json.dumps([dict(id=i.item_id, verdict=verdicts.get(i.item_id, "pass"),
                            quote=quotes.get(i.item_id, ""), evidence=evidence.get(i.item_id, ""))
                       for i in cl.items])


def judged(cl, role="J1", **kw):
    ident = JP.JudgeIdentity(role=role, model_id=f"fixture-{role}", model_sha256="1" * 64, decode_id="greedy")
    return JP.run(lambda m: answer(cl, **kw), ident, context().prefix.turns, REPLY, cl)


# ------------------------------------------------------------ checklist

def test_checklist_items_follow_needcard_roles_and_fixed_templates():
    cl, env = checklist()
    cats = [i.category for i in cl.items]
    assert cats.count("H+") == 1 and cats.count("H-") == 3 and cats.count("R") == 1
    assert cats.count("G") == 3 and cats.count("I") == 2 and cats.count("S") == 1
    assert all(i.applies_to == "all_terminals" and i.visibility_scope == "evaluation_only" for i in cl.items)
    assert {i.constraint_type for i in cl.items if i.category in ("H-", "I")} == {"hard_factual"}
    assert {i.constraint_type for i in cl.items if i.category == "S"} == {"hard_safety"}
    assert cl.total_weight == sum(i.weight for i in cl.items)
    cl.verify_needcard(env["needcard"])
    # relevant_optional history yields no item; every H item carries exact evidence
    assert all(i.evidence_spans for i in cl.items if i.category in ("H+", "H-"))
    assert not any("Anna moved back" in i.text and i.category == "H+" for i in cl.items)


def test_fixed_templates_are_identical_across_prefixes_and_risk_adds_safety():
    a, _ = checklist()
    b, _ = checklist(envelope(stratum="none", history_items=[], failed_or_rejected=[], outdated_facts=[],
                              method_need=None, method_evidence=[], risk_flags=["self_harm"]))
    fixed = lambda cl: [(i.item_id, i.text) for i in cl.items if i.category in ("G", "I")]
    assert fixed(a) == fixed(b)
    assert [i.text for i in b.items if i.category == "S"] == [CW.FIXED_S[0], CW.RISK_ITEMS["self_harm"]]
    assert checklist()[0].sha256 == a.sha256 and a.sha256 != b.sha256


def test_unverified_needcard_cannot_get_a_checklist():
    card = envelope()["needcard"]
    pending = K.NeedCard(**{**{f: getattr(card, f) for f in card.__dataclass_fields__}, "span_validation_status": "pending"})
    with pytest.raises(ValueError, match="span-verified"):
        CW.build(pending)


def test_ledger_freezes_before_candidates_and_never_replaces(tmp_path):
    cl, env = checklist()
    led = ChecklistLedger(tmp_path)
    with pytest.raises(ChecklistOrderError, match="no frozen checklist"):
        led.register_candidate(cl.prefix_id, "a" * 64, "b" * 64)
    led.freeze(cl, env["needcard"])
    led.freeze(cl, env["needcard"])                                  # idempotent
    rows = [led.register_candidate(cl.prefix_id, k * 64, "b" * 64) for k in "acd"]
    assert {r["checklist_sha256"] for r in rows} == {cl.sha256}
    other, env2 = checklist(envelope(stratum="none", history_items=[], failed_or_rejected=[],
                                     outdated_facts=[], method_need=None, method_evidence=[]))
    with pytest.raises(ChecklistOrderError, match="candidates already exist"):
        led.freeze(other, env2["needcard"])


def test_checklist_written_after_a_candidate_is_refused_even_without_file(tmp_path):
    cl, env = checklist()
    led = ChecklistLedger(tmp_path)
    led.log.write_text(json.dumps(dict(prefix_id=cl.prefix_id, key_sha256="a" * 64,
                                       response_sha256="b" * 64, checklist_sha256="c" * 64)) + "\n")
    with pytest.raises(ChecklistOrderError):
        led.freeze(cl, env["needcard"])


def test_fixed_denominator_cannot_be_improved_by_dropping_items():
    cl, _ = checklist()
    j1, j2 = judged(cl), judged(cl, role="J2")
    v = AG.item_verdicts(cl, j1, j2)
    assert K.gsc_interval(cl, v) == (1.0, 1.0)
    failing = cl.items[0].item_id
    v2 = AG.item_verdicts(cl, judged(cl, verdicts={failing: "fail"}), judged(cl, role="J2", verdicts={failing: "fail"}))
    lo, hi = K.gsc_interval(cl, v2)
    assert lo == hi == pytest.approx(1 - cl.items[0].weight / cl.total_weight)
    with pytest.raises(ValueError, match="coverage"):
        K.gsc_interval(cl, tuple(x for x in v2 if x.item_id != failing))
    with pytest.raises(Exception):
        K.Checklist(prefix_id=cl.prefix_id, needcard_sha256=cl.needcard_sha256, items=cl.items[1:],
                    total_weight=cl.total_weight, writer_identity=cl.writer_identity)


# ------------------------------------------------------------- judges

def test_parse_rejects_bad_quotes_and_foreign_evidence():
    cl, _ = checklist()
    h = next(i for i in cl.items if i.category == "H-")
    g = next(i for i in cl.items if i.category == "G")
    ev = JP.evidence_index(cl)
    own = next(e for e, (iid, _) in ev.items() if iid == h.item_id)
    text = answer(cl, verdicts={h.item_id: "pass", g.item_id: "fail"},
                  quotes={h.item_id: "the breathing exercise did not help before", g.item_id: "words never written"},
                  evidence={h.item_id: own, g.item_id: own})
    got = JP.parse(text, cl, REPLY)
    assert got[h.item_id].verdict == "pass" and got[h.item_id].span is ev[own][1]
    assert got[g.item_id].verdict == "uncertain" and got[g.item_id].quote is None
    assert set(got[g.item_id].flags) == {"quote_not_in_reply", "bad_evidence_ref"}
    for bad in ("nope", json.dumps({"id": 1}), json.dumps([dict(id="Z:9", verdict="pass", quote="", evidence="")])):
        with pytest.raises(JP.JudgeParseError):
            JP.parse(bad, cl, REPLY)


def test_parse_failure_reasks_once_then_uncertain_and_missing_items_reasked():
    cl, _ = checklist()
    ident = JP.JudgeIdentity(role="J1", model_id="m", model_sha256="1" * 64, decode_id="greedy")
    jr = JP.run(lambda m: "garbage", ident, context().prefix.turns, REPLY, cl)
    assert jr.calls == 2 and {x.verdict for x in jr.items.values()} == {"uncertain"}
    assert all(x.flags == ("parse_failed",) for x in jr.items.values())
    full = json.loads(answer(cl))
    calls = iter([json.dumps(full[1:]), json.dumps(full[:1])])
    jr = JP.run(lambda m: next(calls), ident, context().prefix.turns, REPLY, cl)
    assert jr.calls == 2 and all(x.verdict == "pass" and not x.flags for x in jr.items.values())
    calls = iter([json.dumps(full[1:]), "[]"])
    jr = JP.run(lambda m: next(calls), ident, context().prefix.turns, REPLY, cl)
    assert jr.items[full[0]["id"]].flags == ("missing_after_retry",)


def test_judge_messages_keep_reply_and_sources_as_data():
    cl, _ = checklist()
    msgs = JP.render(context().prefix.turns, REPLY, cl)
    assert "Ignore all previous instructions" in msgs[1]["content"] and "Ignore" not in msgs[0]["content"]
    assert "FUTURE" not in msgs[1]["content"]


# -------------------------------------------------------- aggregation

def test_single_judge_is_pending_and_never_scored_as_zero():
    cl, _ = checklist()
    v = AG.item_verdicts(cl, judged(cl), None)
    assert all(x.pending for x in v) and K.gsc_interval(cl, v) == (None, None)
    s = AG.status_summary(cl, v, judged(cl), None)
    assert s["J1_run"] and not s["J2_run"] and s["pending_items"] == len(cl.items)
    assert s["hard_factual"] is None and s["hard_safety"] is None
    none = AG.item_verdicts(cl, None, None)
    assert all(x.J1 is None and x.J2 is None and x.final is None for x in none)


def test_disagreement_is_uncertain_and_human_adjudication_decides():
    cl, _ = checklist()
    s_item = next(i for i in cl.items if i.category == "S").item_id
    f_item = next(i for i in cl.items if i.category == "I").item_id
    j1 = judged(cl, verdicts={s_item: "fail", f_item: "fail"})
    j2 = judged(cl, role="J2", verdicts={s_item: "pass", f_item: "fail"})
    v = AG.item_verdicts(cl, j1, j2)
    by = {x.item_id: x for x in v}
    assert by[s_item].final == "uncertain" and by[f_item].final == "fail"
    s = AG.status_summary(cl, v, j1, j2)
    assert (s["hard_factual"], s["hard_safety"]) == ("fail", "uncertain")
    assert s["factual_fail_items_final"] == 1 and s["safety_fail_items_J1"] == 1 and s["safety_fail_items_final"] == 0
    lo, hi = K.gsc_interval(cl, v)
    assert lo < hi
    adj = K.HumanAdjudication(reviewer_id="researcher", record_uri="review://1", record_sha256="2" * 64,
                              response_sha256=sha256_text(REPLY), verdict="pass", reason="reply is safe")
    v2 = AG.item_verdicts(cl, j1, j2, {s_item: adj})
    assert {x.item_id: x for x in v2}[s_item].final == "pass"
    with pytest.raises(ValueError, match="outside"):
        AG.item_verdicts(cl, j1, j2, {"Z:1": adj})


def test_terminal_record_keeps_j1_only_engineering_and_refuses_research_tier():
    from metacom_pm.rl1v3.env.c0_binding import TerminalIdentity, subset_key
    cl, env = checklist()
    ident = TerminalIdentity("b", "i", "r", "s2", "g", "d")
    key = subset_key(context().prefix, ident, {}, 0)
    trace = K.ExecutionTrace(domain_id="finite_head_v1", ordered_path=("STOP",), acquired=(), readings=())
    v = AG.item_verdicts(cl, judged(cl), None)
    rec = AG.terminal_record(key=key, trace=trace, checklist=cl, feedback_id="fb-v1", request_sha256="3" * 64,
                             response=REPLY, verdicts=v, evidence_validation="verified")
    assert (rec.gsc_lower, rec.gsc_upper, rec.qualification_tier) == (None, None, "engineering_only")
    rec.verify_evidence(context().prefix, context().sources)
    with pytest.raises(Exception, match="pending"):
        AG.terminal_record(key=key, trace=trace, checklist=cl, feedback_id="fb-v1", request_sha256="3" * 64,
                           response=REPLY, verdicts=v, evidence_validation="verified",
                           qualification_tier="research_qualified")
    full = AG.item_verdicts(cl, judged(cl), judged(cl, role="J2"))
    rec2 = AG.terminal_record(key=key, trace=trace, checklist=cl, feedback_id="fb-v1", request_sha256="3" * 64,
                              response=REPLY, verdicts=full, evidence_validation="verified")
    assert (rec2.gsc_lower, rec2.gsc_upper) == (1.0, 1.0)
