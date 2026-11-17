"""Directed check of the FROZEN v2 H-/I attribution (``judge.protocol_v2.attribute``, A2/A3).

Each test runs the frozen v2 code on a programmatic counterexample and asserts what v2 ACTUALLY
does next to the true atomic errors.  v2 is not modified: the defects shown here are recorded
evidence for the v3 version bump (``checklist.writer_v3`` / ``judge.protocol_v3`` /
``judge.aggregate_v3`` / ER-v3), whose behaviour on the same cases is in ``test_rl1v3_b2_v3.py``.
"""
from __future__ import annotations

import pytest

from metacom_pm.rl1v3 import contracts as K
from metacom_pm.rl1v3.checklist import writer_v2 as CW2
from metacom_pm.rl1v3.judge import aggregate as AG, protocol_v2 as JP2
from rl1v3_b2_attribution_cases import CASE5, CASES, W, interval, ms_reading, reply, v2_answer
from rl1v3_wsb_fixtures import context
from test_rl1v3_b2_checklist_judge import envelope


def cl2():
    env = envelope()
    return CW2.build(env["needcard"], method_evidence=env["method_evidence"])


def v2_run(cl, case, role="J1", **ans):
    ident = JP2.JudgeIdentityV2(role=role, model_id=f"fixture-{role}", model_sha256="1" * 64, decode_id="greedy")
    readings = ms_reading() if case.get("readings") == "ms" else ()
    return JP2.run(lambda m: v2_answer(cl, **ans), ident, context().prefix.turns, reply(case["sentence"]), cl, readings)


def fails(jr):
    return {i for i, it in jr.items.items() if it.verdict == "fail"}


def test_fixture_items_and_weights():
    cl = cl2()
    assert cl.total_weight == W
    assert [i.item_id for i in cl.items if i.category in ("H-", "I")] == ["H-:1", "H-:2", "H-:3", "I:1", "I:2", "I:3", "I:4"]


@pytest.mark.parametrize("name", ["1_two_errors_one_sentence", "2_history_conflict_and_suggestion_as_action",
                                  "3c_whole_sentence_two_wrong_subclaims"])
def test_v2_defect_merges_two_different_errors_that_share_a_sentence(name):
    """Cases 1, 2, 3c: the second (I) error is lost because both decisive quotes are the same sentence."""
    cl, case = cl2(), CASES[name]
    j1 = v2_run(cl, case, **case["v2"])
    assert fails(j1) == case["truth_fail"] - {i for i in case["truth_fail"] if i.startswith("I:")}
    assert len(j1.attributions) == 1 and j1.attributions[0]["item"] in case["truth_fail"]
    assert interval(cl, fails(j1)) != interval(cl, case["truth_fail"])       # quality overstated by 1/18


def test_v2_identical_inputs_for_3a_and_3c_cannot_both_be_right():
    """Case 3: whole-sentence quotes give v2 the same input shape whether the sentence holds one wrong
    sub-proposition (3a, must merge) or two (3c, must not); a span rule is right on at most one."""
    cl = cl2()
    a, c = CASES["3a_whole_sentence_one_wrong_subclaim"], CASES["3c_whole_sentence_two_wrong_subclaims"]
    ja, jc = v2_run(cl, a, **a["v2"]), v2_run(cl, c, **c["v2"])
    assert fails(ja) == fails(jc) == {"H-:3"}
    assert fails(ja) == a["truth_fail"] and fails(jc) != c["truth_fail"]


def test_v2_defect_double_counts_one_error_quoted_twice():
    """Case 4: the same atomic error, quoted from two sentences, fails H-:3 and I:2."""
    cl, case = cl2(), CASES["4_same_error_two_quotes"]
    j1 = v2_run(cl, case, **case["v2"])
    assert fails(j1) == {"H-:3", "I:2"} != case["truth_fail"] and not j1.attributions
    assert interval(cl, fails(j1))[0] == pytest.approx(1 - 3 / W)            # truth: 1 - 2/18


def test_v2_defect_two_judges_with_different_owners():
    """Case 5: C0 sets both items uncertain; the lower bound counts the one error twice and the
    upper bound not at all, although both judges found an error."""
    cl = cl2()
    j1 = v2_run(cl, CASE5, **CASE5["v2"]["J1"])
    j2 = v2_run(cl, CASE5, role="J2", **CASE5["v2"]["J2"])
    v = AG.item_verdicts(cl, j1, j2)
    by = {x.item_id: x.final for x in v}
    assert by["H-:3"] == by["I:2"] == "uncertain"
    lo, hi = K.gsc_interval(cl, v)
    assert lo == pytest.approx(1 - 3 / W) and hi == pytest.approx(1.0)
    assert interval(cl, CASE5["truth_fail"]) == pytest.approx((1 - 2 / W, 1 - 2 / W))


def test_v2_prompt_and_item_text_scope_whole_statements():
    """The v2 I questions and system prompt exclude whole statements judged under H-, so even an
    accurate v2 judge is told to skip a second error inside such a statement (cases 1-3)."""
    cl = cl2()
    assert all(i.text.startswith("Apart from any statement already judged under an H- item")
               for i in cl.items if i.category == "I")
    assert "judge I items only on other statements" in JP2.SYSTEM_PROMPT
