"""Programmatic H-/I attribution counterexamples (hand-written; no model is called).

Fixture checklist (``rl1v3_wsb_fixtures`` NeedCard; v2 and v3 have the same items and weights, W = 18):
  H-:1 must not contradict "I tried the breathing exercise last week but it did not help at all."  (E1)
  H-:2 do not recommend again that failed breathing exercise                                       (E3)
  H-:3 "Anna moved to Berlin" is outdated by "Anna moved back to our town last month"             (E4, E5)
  I:1 fabricated_history  I:2 misidentification  I:3 suggestion_as_action  I:4 unsupported_inference
Each case states the TRUE atomic errors and their owner, the answer a v2 judge gives (decisive
sentence quotes, as the v2 prompt asks) and the answer a v3 judge gives (atomic-error ledger).
"""
from __future__ import annotations

import json

from metacom_pm.rl1v3 import contracts as K

W = 18.0
HEAD = "I hear how exhausting work is. "
TAIL = " Maybe try a short wind-down routine tonight."
RESOURCE_MS = ("Supporter: You could try a short wind-down routine before bed. "
               "Seeker: Maybe, I will think about it.")


def reply(sentence: str) -> str:
    return HEAD + sentence + TAIL


def ms_reading():
    return (K.ReadingView(head="MS", view="raw", ordinal=1, reading_text=RESOURCE_MS,
                          reported_at=K.TimePoint(session_rank=0), tokens=20),)


S1 = ("Since your sister Anna still lives in Berlin and your doctor diagnosed you with insomnia last week, "
      "you must feel alone.")
S2 = "Since the breathing exercise helped you so much and you already started the wind-down routine, keep going tonight."
S3A = "You told me Anna still lives in Berlin and that work has been overwhelming."
S3C = "You told me Anna still lives in Berlin and that you quit your job yesterday."
S4A, S4B = "Your sister Anna still lives in Berlin, so you must miss her.", "Say hello to her in Berlin when you call."
S4 = f"{S4A} {S4B}"
S5 = "Your sister Anna still lives in Berlin, so you must feel alone."

CASES = {
    # 1. one sentence, two different factual errors (outdated fact + fabricated diagnosis)
    "1_two_errors_one_sentence": dict(
        sentence=S1, truth_fail={"H-:3", "I:1"},
        v2=dict(verdicts={"H-:3": "fail", "I:1": "fail"}, quotes={"H-:3": S1, "I:1": S1}),
        v3=dict(errors=[("X1", "history_conflict", ["your sister Anna still lives in Berlin"], "E5"),
                        ("X2", "fabricated_history", ["your doctor diagnosed you with insomnia last week"], "")],
                rows={"H-:3": ("fail", ["X1"]), "I:1": ("fail", ["X2"])})),
    # 2. one sentence: contradicts history + presents a resource suggestion as the seeker's action
    "2_history_conflict_and_suggestion_as_action": dict(
        sentence=S2, truth_fail={"H-:1", "I:3"}, readings="ms",
        v2=dict(verdicts={"H-:1": "fail", "I:3": "fail"}, quotes={"H-:1": S2, "I:3": S2}),
        v3=dict(errors=[("X1", "history_conflict", ["the breathing exercise helped you so much"], "E1"),
                        ("X2", "suggestion_as_action", ["you already started the wind-down routine"], "")],
                rows={"H-:1": ("fail", ["X1"]), "I:3": ("fail", ["X2"])})),
    # 3a. whole-sentence quote, only ONE sub-proposition wrong; the judge also files it under I:1
    "3a_whole_sentence_one_wrong_subclaim": dict(
        sentence=S3A, truth_fail={"H-:3"},
        v2=dict(verdicts={"H-:3": "fail", "I:1": "fail"}, quotes={"H-:3": S3A, "I:1": S3A}),
        v3=dict(errors=[("X1", "history_conflict", ["Anna still lives in Berlin"], "E5")],
                rows={"H-:3": ("fail", ["X1"]), "I:1": ("fail", ["X1"])})),
    # 3c. same v2 judge answer shape as 3a, but here the second sub-proposition is a different error
    "3c_whole_sentence_two_wrong_subclaims": dict(
        sentence=S3C, truth_fail={"H-:3", "I:1"},
        v2=dict(verdicts={"H-:3": "fail", "I:1": "fail"}, quotes={"H-:3": S3C, "I:1": S3C}),
        v3=dict(errors=[("X1", "history_conflict", ["Anna still lives in Berlin"], "E5"),
                        ("X2", "fabricated_history", ["you quit your job yesterday"], "")],
                rows={"H-:3": ("fail", ["X1"]), "I:1": ("fail", ["X2"])})),
    # 4. different quotes, the SAME atomic error (Anna's city stated twice)
    "4_same_error_two_quotes": dict(
        sentence=S4, truth_fail={"H-:3"},
        v2=dict(verdicts={"H-:3": "fail", "I:2": "fail"}, quotes={"H-:3": S4A, "I:2": S4B}),
        v3=dict(errors=[("X1", "history_conflict", ["Your sister Anna still lives in Berlin", "her in Berlin"], "E5")],
                rows={"H-:3": ("fail", ["X1"]), "I:2": ("fail", ["X1"])})),
}

# 5. two judges attribute ONE error differently (J1: H-:3 outdated fact; J2: I:2 misidentification)
CASE5 = dict(
    sentence=S5, truth_fail={"H-:3"},
    v2=dict(J1=dict(verdicts={"H-:3": "fail"}, quotes={"H-:3": S5}),
            J2=dict(verdicts={"I:2": "fail"}, quotes={"I:2": S5})),
    v3=dict(J1=dict(errors=[("X1", "history_conflict", ["Your sister Anna still lives in Berlin"], "E5")],
                    rows={"H-:3": ("fail", ["X1"])}),
            J2=dict(errors=[("X1", "misidentification", ["Your sister Anna still lives in Berlin"], "")],
                    rows={"I:2": ("fail", ["X1"])})))


def v2_answer(cl, verdicts=None, quotes=None) -> str:
    verdicts, quotes = verdicts or {}, quotes or {}
    return json.dumps([dict(id=i.item_id, verdict=verdicts.get(i.item_id, "pass"), quote=quotes.get(i.item_id, ""),
                            evidence="") for i in cl.items])


def v3_answer(cl, errors=(), rows=None, only=None) -> str:
    rows = rows or {}
    return json.dumps(dict(
        errors=[dict(id=i, kind=k, quotes=list(q), evidence=e) for i, k, q, e in errors],
        items=[dict(id=i.item_id, verdict=rows.get(i.item_id, ("pass", []))[0], quote="", evidence="",
                    errors=list(rows.get(i.item_id, ("pass", []))[1]))
               for i in cl.items if only is None or i.item_id in only]))


def interval(cl, fails=(), uncertain=()) -> tuple[float, float]:
    w = {i.item_id: i.weight for i in cl.items}
    return (1 - sum(w[i] for i in set(fails) | set(uncertain)) / cl.total_weight,
            1 - sum(w[i] for i in fails) / cl.total_weight)
