"""Judge-v3 rejection paths and output-capacity risk before any real J1 call (fixtures only; no model).

Truncation, parse failure, missing items, bad evidence ids and atomic-error conflicts must all end
in uncertain items -> ER-v3 refusal -> pending terminal, never in a guessed verdict, a 0 reward or a
GSC value.  The capacity helper must produce answers the frozen v3 parser accepts.
"""
from __future__ import annotations

import json

import pytest

from metacom_pm.rl1v3.judge import aggregate_v3 as AG3, capacity_v3 as CAP, engineering_reward as ER1
from metacom_pm.rl1v3.judge import engineering_reward_v3 as ER3, protocol_v3 as JP3
from rl1v3_b2_attribution_cases import S1, S3A, reply, v3_answer
from test_rl1v3_b2_v3 import cl3, er_args, v3_run


def test_truncated_answer_twice_ends_pending_not_guessed():
    cl, env = cl3()
    full = v3_answer(cl, errors=[("X1", "history_conflict", ["Anna still lives in Berlin"], "E5")],
                     rows={"H-:3": ("fail", ["X1"])})
    cut = full[: len(full) // 2]                         # a max_new_tokens cut mid-JSON; greedy re-ask repeats it
    j1 = v3_run(cl, S3A, answers=[cut, cut])
    assert j1.calls == 2 and {x.verdict for x in j1.items.values()} == {"uncertain"}
    assert all("parse_failed" in x.flags for x in j1.items.values()) and j1.ledger == []
    with pytest.raises(ER1.RewardUnavailable) as e:
        ER3.compute(**er_args(cl, env, j1, S3A))
    assert {"too_uncertain", "hard_safety_uncertain"} <= set(e.value.reasons)
    att = ER3.attempt(key=er_args(cl, env, j1, S3A)["key"], subset="OFF", stratum="both",
                      **{k: v for k, v in er_args(cl, env, j1, S3A).items() if k != "key"})
    assert att["status"] == "refused" and "record" not in att


def test_missing_items_after_reask_are_uncertain_with_their_flag():
    cl, env = cl3()
    first = json.loads(v3_answer(cl))
    first["items"] = [r for r in first["items"] if r["id"] not in ("I:2", "S:1")]
    j1 = v3_run(cl, S3A, answers=[json.dumps(first), json.dumps(dict(errors=[], items=[]))])
    assert j1.calls == 2
    assert {i for i, x in j1.items.items() if "missing_after_retry" in x.flags} == {"I:2", "S:1"}
    with pytest.raises(ER1.RewardUnavailable) as e:
        ER3.compute(**er_args(cl, env, j1, S3A))
    assert "hard_safety_uncertain" in e.value.reasons


def test_bad_evidence_ids_never_create_a_sure_fail():
    cl, _ = cl3()
    j1 = v3_run(cl, S3A, errors=[("X1", "history_conflict", ["Anna still lives in Berlin"], "E99")],
                rows={"H-:3": ("fail", ["X1"])})
    assert j1.ledger[0]["invalid"] == "bad_evidence_ref" and j1.items["H-:3"].verdict == "uncertain"
    bad_row = json.loads(v3_answer(cl))
    for r in bad_row["items"]:
        if r["id"] == "H+:1":
            r["evidence"] = "E5"                         # E5 belongs to H-:3, not to H+:1
    j1 = v3_run(cl, S3A, answers=[json.dumps(bad_row)])
    assert "bad_evidence_ref" in j1.items["H+:1"].flags and j1.items["H+:1"].span is None


def test_atomic_conflicts_feed_the_uncertain_weight_and_the_refusal_threshold():
    cl, env = cl3()
    q = "your sister Anna still lives in Berlin"
    rows = {"H-:3": ("fail", ["X1"]), "I:1": ("fail", ["X2"]), "I:2": ("pass", []), "I:4": ("fail", ["X9"])}
    j1 = v3_run(cl, S1, errors=[("X1", "history_conflict", [q], "E5"), ("X2", "fabricated_history", [q], ""),
                                ("X3", "misidentification", ["your doctor diagnosed you"], "")], rows=rows)
    flags = {i: j1.items[i].flags for i in ("I:1", "I:2", "I:4")}
    assert "overlap_ambiguous" in flags["I:1"] and "ledger_row_conflict" in flags["I:2"]
    assert "fail_without_valid_error" in flags["I:4"] and "unknown_error_ref:c1:X9" in flags["I:4"]
    rec = ER3.compute(**er_args(cl, env, j1, S1))
    assert rec["quality"]["j1_uncertain_weight"] == pytest.approx(3 / 18)
    assert rec["j1_ledger"]["ambiguous"] == {"c1:X2": ["c1:X1"]}


def test_er_v3_is_never_gsc_and_gsc_stays_pending_without_j2():
    cl, env = cl3()
    j1 = v3_run(cl, S3A)
    rec = ER3.compute(**er_args(cl, env, j1, S3A))
    assert rec["is_gsc"] is False and not {"gsc_lower", "gsc_upper", "final"} & set(rec)
    v = AG3.item_verdicts(cl, j1, None)
    assert AG3.gsc_admission(cl, v, [])["status"] == "pending" and AG3.gsc_interval(cl, v, []) == (None, None)


@pytest.mark.parametrize("scenario", CAP.SCENARIOS)
def test_capacity_answers_are_valid_v3_outputs_for_the_frozen_parser(scenario):
    cl, _ = cl3()
    resp = reply(S1)
    sentences = [s for s in (resp.split(". "))]
    sentences = [s if s.endswith(".") else s + "." for s in sentences if s]
    sentences = [s for s in sentences if s in resp]
    items = [(i.item_id, i.category) for i in cl.items]
    text = CAP.answer(items, sentences, scenario, n_evidence=0, pretty=scenario == "worst")
    rows, cited, ledger = JP3.parse(text, cl, resp)
    assert set(rows) == {i.item_id for i in cl.items}
    assert all(e["invalid"] in (None, "history_conflict_without_h_minus_evidence") for e in ledger)
