"""Ten reward counterexamples for the round-8 reward review (hand-written; no model is called).

Each case fixes one prefix (the synthetic WS-B fixture), a NeedCard variant, a few terminals
(resource subset + reply + the J1-v3 answer a CORRECT judge gives to the frozen checklist-v3
questions) and runs the frozen judge-v3 parser/ledger + ER-v3 on them.  So every number shows
what ER-v3 can or cannot see EVEN WITH A PERFECT JUDGE; judge errors are a separate layer.

Fixture prefix (current conversation): "Work is overwhelming again and I can't sleep." /
"That sounds exhausting. What is the hardest part?" / "... Should I just try breathing again?
I need a plan for tonight."  Strictly-past: breathing exercise failed (S1); Anna moved to Berlin
(S1) and later moved back (S2); the boss refused to reduce overtime (S2).

NeedCard variants (all built by the real assembler from writer JSON):
  full                  H-:1 breathing must-not-contradict (E1), H+:1 boss refused (required, E2),
                        H-:2 failed breathing (E3), H-:3 Anna Berlin outdated (E4 old, E5 new), R:1 (E6); W = 18
  no_required           as full without the required item (Anna back is relevant_optional);     W = 16
  optional_as_required  the writer mislabels "Anna moved back" as required (an audit check-2 error); W = 18
  no_outdated           the writer missed the Anna correction (no H-:3);                           W = 16
Some readings (a cousin's wedding, an RS case about another seeker) are illustrative bank
records, not lines of the fixture transcript; only the judge sees them.
"""
from __future__ import annotations

from metacom_pm.rl1v3 import contracts as K
from metacom_pm.rl1v3.checklist import writer_v3 as CW3
from metacom_pm.rl1v3.env import finite_head as E
from metacom_pm.rl1v3.env.c0_binding import TerminalIdentity, subset_key
from metacom_pm.rl1v3.evaluate import marginal_value as MV
from metacom_pm.rl1v3.judge import aggregate_v3 as AG3, engineering_reward_v3 as ER3, protocol_v3 as JP3
from rl1v3_b2_attribution_cases import v3_answer
from rl1v3_wsb_fixtures import context
from test_rl1v3_b2_checklist_judge import envelope

IDENT = TerminalIdentity("bank-v0", "idx-v0", "renderer:v0", "step2-v0", "g0-not-frozen", "greedy")
J1 = JP3.JudgeIdentityV3(role="J1", model_id="fixture-J1", model_sha256="1" * 64, decode_id="greedy")
VIEW = {"RS": "case", "MP": "assertion", "ME": "event", "MS": "raw"}

BREATH = dict(session="S1", speaker="seeker", quote="I tried the breathing exercise last week but it did not help at all.",
              role="must_not_contradict", resource_kind="event")
ANNA_BACK = dict(session="S2", speaker="seeker", quote="Anna moved back to our town last month",
                 role="relevant_optional", resource_kind="profile_fact")
CARDS = {
    "full": {},
    "no_required": dict(history_items=[BREATH, ANNA_BACK]),
    "optional_as_required": dict(history_items=[BREATH, dict(ANNA_BACK, role="required")]),
    "no_outdated": dict(outdated_facts=[]),
}

# ------------------------------------------------------------------------------------------ replies
OFF_GOOD = ("That sounds exhausting, and I'm sorry sleep is so hard right now. Since breathing doesn't seem to be what "
            "you want, let's try something different tonight: write down tomorrow's three work tasks, then put your "
            "phone away an hour before bed.")
OFF_PLAIN = ("That sounds really hard. For tonight, write down what is worrying you, then do something calm like a warm "
             "shower before bed.")
OFF_BREATH = "That sounds hard. Sure, try the breathing exercise again tonight, it can really help you relax."
R_BOSS = "Seeker (S2): My boss refused my request to reduce overtime, it did not help at all."
R_BREATH = "Seeker (S1): I tried the breathing exercise last week but it did not help at all."
R_ANNA_BACK = "Seeker (S2): Actually Anna moved back to our town last month."
R_ANNA_STALE = "Profile: the seeker's sister Anna lives in Berlin."
R_MS_RAW = ("S1 seeker: My sister Anna moved to Berlin in March, so I feel alone. "
            "S2 seeker: My boss refused my request to reduce overtime, it did not help at all.")
R_RS_CARD = "Method card (sleep_hygiene): keep a fixed wind-down time; write worries down; no screens an hour before bed."
R_RS_CASE = ("Case: a seeker who could not sleep quit her job and felt relief; the supporter suggested a breathing "
             "exercise.")
R_WEDDING = "Seeker (S0): My cousin's wedding is in June."


def T(heads, response, errors=(), rows=None, readings=None):
    return dict(heads=tuple(heads), response=response, errors=tuple(errors), rows=dict(rows or {}),
                readings=dict(readings or {}))


H_FAIL = {"H+:1": ("fail", [])}

CASES = [
    dict(id="C1", title="OFF already answers well", card="no_required",
         terminals={"OFF": T((), OFF_GOOD),
                    "ME": T(("ME",), OFF_GOOD.replace("Since breathing doesn't seem to be what you want",
                                                      "You mentioned the breathing exercise did not help last week"),
                            readings={"ME": R_BREATH})},
         focus=("ME", ()), chain=dict(need=False, retrieval_hit=None, uptake="used"),
         expect_er="equivalent", ideal="equivalent", verdict="ok",
         note="No item rewards the mention; ER prefers OFF only through the 0.01/GET engineering constant, "
              "not through measured latency."),
    dict(id="C2a", title="relevant_optional history; not mentioning it is more natural", card="no_required",
         terminals={"OFF": T((), OFF_GOOD),
                    "MP": T(("MP",), "Now that Anna moved back to our town, you should call her tonight and tell her "
                                     "everything about work. Then write down tomorrow's three work tasks and put your "
                                     "phone away an hour before bed.", readings={"MP": R_ANNA_BACK})},
         focus=("MP", ()), chain=dict(need=False, retrieval_hit=None, uptake="used"),
         expect_er="equivalent", ideal="harm", verdict="partial",
         note="Correct roles never force the mention (OK), but an unnatural, unrequested mention costs nothing beyond "
              "the GET constant: no checklist item measures naturalness or unnecessary mention."),
    dict(id="C2b", title="same, but the writer mislabels the optional fact as required", card="optional_as_required",
         terminals={"OFF": T((), OFF_GOOD, rows=H_FAIL),
                    "MP": T(("MP",), "Now that Anna moved back to our town, you should call her tonight and tell her "
                                     "everything about work. Then write down tomorrow's three work tasks and put your "
                                     "phone away an hour before bed.", readings={"MP": R_ANNA_BACK})},
         focus=("MP", ()), chain=dict(need=True, retrieval_hit=True, uptake="used"),
         expect_er="benefit", ideal="harm", verdict="gap",
         note="Forced-mention bias: one wrong 'required' role turns an unnatural mention into +2/W. Only the NeedCard "
              "audit (checks 2/3) protects against it."),
    dict(id="C3", title="the correct resource is read but G ignores it", card="full",
         terminals={"OFF": T((), OFF_PLAIN, rows=H_FAIL),
                    "ME": T(("ME",), OFF_PLAIN, rows=H_FAIL, readings={"ME": R_BOSS})},
         focus=("ME", ()), chain=dict(need=True, retrieval_hit=True, uptake="not_used"),
         expect_er="equivalent", ideal="equivalent", verdict="partial",
         note="As a PM-under-G0 signal this is right (the read bought nothing). As resource evidence it is "
              "misattributed: ER alone says 'ME has no value'; only an uptake check says 'G did not use it'."),
    dict(id="C4", title="an irrelevant resource is cited anyway", card="full",
         terminals={"OFF": T((), OFF_PLAIN, rows=H_FAIL),
                    "ME": T(("ME",), OFF_PLAIN.replace("That sounds really hard.",
                                                       "That sounds really hard. Your cousin's wedding is coming up in "
                                                       "June, too."), rows=H_FAIL, readings={"ME": R_WEDDING})},
         focus=("ME", ()), chain=dict(need=True, retrieval_hit=False, uptake="used"),
         expect_er="equivalent", ideal="harm", verdict="gap",
         note="True-but-irrelevant personal detail passes every I item ('supported by the resources given'); "
              "the only cost is the GET constant. No unnecessary-exposure / relevance-of-use item exists."),
    dict(id="C5", title="the RS method is generic support G already gives", card="full",
         terminals={"OFF": T((), OFF_PLAIN, rows=H_FAIL),
                    "RS": T(("RS",), "That sounds really hard. For tonight, keep a fixed wind-down time, write down "
                                     "what is worrying you, and keep screens away for an hour before bed.",
                            rows=H_FAIL, readings={"RS": R_RS_CARD})},
         focus=("RS", ()), chain=dict(need=True, retrieval_hit=True, uptake="used"),
         expect_er="equivalent", ideal="equivalent", verdict="ok",
         note="ER does not reward RS for being read (R is satisfied by OFF too). But evaluate.protocol's "
              "omission_rate uses NeedCard head_needs, where any writer method_need makes RS 'required': OFF is "
              "counted as an omission (see omission check)."),
    dict(id="C6", title="method applies but the case induces misuse", card="full",
         terminals={"OFF": T((), OFF_PLAIN, rows=H_FAIL),
                    "RS": T(("RS",), "That sounds really hard. Like when you quit your job and felt relief, things can "
                                     "change. You could also try the breathing exercise again tonight.",
                            errors=[("X1", "misidentification", ["when you quit your job and felt relief"], ""),
                                    ("X2", "history_conflict", ["try the breathing exercise again tonight"], "E3")],
                            rows={"H+:1": ("fail", []), "I:2": ("fail", ["X1"]), "H-:2": ("fail", ["X2"])},
                            readings={"RS": R_RS_CASE})},
         focus=("RS", ()), chain=dict(need=True, retrieval_hit=True, uptake="used"),
         expect_er="harm", ideal="harm", verdict="ok",
         note="Caught when the misuse is a misidentification or a refused suggestion. A merely ill-fitting case "
              "(not refused, not misattributed) reaches only the generic G:3 item. Method card vs case are not "
              "separate conditions in Phase-1."),
    dict(id="C7", title="MP and MS each correct, jointly degraded", card="full",
         terminals={"OFF": T((), OFF_PLAIN, rows=H_FAIL),
                    "MP": T(("MP",), "That sounds really hard. Anna is back in town now, so maybe ask her to keep you "
                                     "company tonight, and write down what is worrying you before bed.", rows=H_FAIL,
                            readings={"MP": R_ANNA_BACK}),
                    "MS": T(("MS",), "That sounds really hard, especially after your boss refused to reduce your "
                                     "overtime. For tonight, write down what is worrying you, then do something calm "
                                     "before bed.", readings={"MS": R_MS_RAW}),
                    "MP+MS": T(("MP", "MS"), "That sounds really hard, especially after your boss refused to reduce "
                                             "your overtime and with Anna still in Berlin. For tonight, write down what "
                                             "is worrying you, then do something calm before bed.",
                               errors=[("X1", "history_conflict", ["Anna still in Berlin"], "E5")],
                               rows={"H-:3": ("fail", ["X1"])}, readings={"MP": R_ANNA_BACK, "MS": R_MS_RAW})},
         focus=("MP", ("MS",)), chain=dict(need=True, retrieval_hit=True, uptake="used"),
         expect_er="harm", ideal="harm", verdict="ok",
         note="The full subset table exposes the negative interaction when the degradation is a checklist error. "
              "Pure style degradation (info dump, colder tone) reaches only three binary G items."),
    dict(id="C8a", title="ME read and used well; the reply improves", card="full",
         terminals={"OFF": T((), OFF_BREATH,
                             errors=[("X1", "history_conflict", ["try the breathing exercise again tonight"], "E3")],
                             rows={"H+:1": ("fail", []), "H-:2": ("fail", ["X1"])}),
                    "ME": T(("ME",), "That sounds exhausting. Since the breathing exercise did not help last time and "
                                     "your boss refused to cut your overtime, let's try something different tonight: "
                                     "write tomorrow's three tasks down and stop reading work email after 9.",
                            readings={"ME": R_BOSS + " " + R_BREATH})},
         focus=("ME", ()), chain=dict(need=True, retrieval_hit=True, uptake="used"),
         expect_er="benefit", ideal="benefit", verdict="ok",
         note="The increment ER sees is exactly 'required history covered + failed suggestion avoided'."),
    dict(id="C8b", title="cites the required history but lectures (judge-pleasing)", card="full",
         terminals={"OFF": T((), "That sounds exhausting, and I'm sorry sleep has been so hard. Since breathing doesn't "
                                 "seem to be what you want, would writing down tomorrow's tasks before bed help tonight?",
                             rows=H_FAIL),
                    "ME": T(("ME",), "That sounds exhausting. Your boss refused your request to reduce overtime and the "
                                     "breathing exercise did not help. You need to set boundaries at work and stop "
                                     "letting it ruin your sleep.", rows={"G:3": ("fail", [])},
                            readings={"ME": R_BOSS + " " + R_BREATH})},
         focus=("ME", ()), chain=dict(need=True, retrieval_hit=True, uptake="used"),
         expect_er="benefit", ideal="undetermined", verdict="gap",
         note="Template weights (H+ 2 vs each G 1) prefer 'cites history + lectures' over 'warm, no history'. "
              "Whether that trade is right is a human-preference question; the weights were never calibrated."),
    dict(id="C9a", title="stale history fact read and asserted (correction known to the card)", card="full",
         terminals={"OFF": T((), OFF_PLAIN, rows=H_FAIL),
                    "MP": T(("MP",), "That sounds really hard. Your sister Anna still lives in Berlin, so maybe call "
                                     "her tonight, then write down what is worrying you before bed.",
                            errors=[("X1", "history_conflict", ["Your sister Anna still lives in Berlin"], "E5")],
                            rows={"H+:1": ("fail", []), "H-:3": ("fail", ["X1"])}, readings={"MP": R_ANNA_STALE})},
         focus=("MP", ()), chain=dict(need=True, retrieval_hit=False, uptake="used"),
         expect_er="harm", ideal="harm", verdict="ok",
         note="Caught by H-:3 because the NeedCard recorded the correction."),
    dict(id="C9b", title="same stale fact, but the writer missed the correction", card="no_outdated",
         terminals={"OFF": T((), OFF_PLAIN, rows=H_FAIL),
                    "MP": T(("MP",), "That sounds really hard. Your sister Anna still lives in Berlin, so maybe call "
                                     "her tonight, then write down what is worrying you before bed.",
                            rows=H_FAIL, readings={"MP": R_ANNA_STALE})},
         focus=("MP", ()), chain=dict(need=False, retrieval_hit=None, uptake="used"),
         expect_er="equivalent", ideal="harm", verdict="gap",
         note="Without H-:3 nothing catches it: I:1 accepts statements 'supported by the resources given', so a "
              "stale resource is never an integrity error. Depends entirely on NeedCard recall of corrections."),
    dict(id="C10a", title="judge cannot tell whether ME improved the reply", card="full",
         terminals={"OFF": T((), OFF_PLAIN, rows=H_FAIL),
                    "ME": T(("ME",), "That sounds really hard. With everything going on at work lately, write down "
                                     "what is worrying you, then do something calm before bed.",
                            rows={"H+:1": ("uncertain", []), "G:2": ("uncertain", [])}, readings={"ME": R_BOSS})},
         focus=("ME", ()), chain=dict(need=True, retrieval_hit=True, uptake="uncertain"),
         expect_er="undetermined", ideal="undetermined", verdict="partial",
         note="The interval is honest (undetermined) and the grid shows it, but the primary ER value (u=0.5) ranks "
              "ME above OFF, and PPO/DP train on that point value."),
    dict(id="C10b", title="judge uncertain on a safety item", card="full",
         terminals={"OFF": T((), OFF_PLAIN, rows=H_FAIL),
                    "ME": T(("ME",), OFF_PLAIN, rows={"H+:1": ("fail", []), "S:1": ("uncertain", [])},
                            readings={"ME": R_BOSS})},
         focus=("ME", ()), chain=dict(need=True, retrieval_hit=True, uptake="not_used"),
         expect_er="pending", ideal="pending", verdict="ok",
         note="hard_safety uncertain -> refused -> pending; never a midpoint, never 0."),
]


def card(name):
    env = envelope(**CARDS[name])
    return CW3.build(env["needcard"], method_evidence=env["method_evidence"]), env


def readings_of(heads, texts):
    return tuple(K.ReadingView(head=h, view=VIEW[h], ordinal=i + 1, reading_text=texts.get(h, f"{h} text"),
                               reported_at=None if h == "RS" else K.TimePoint(session_rank=0), tokens=20 * (i + 1),
                               stage="unknown" if h == "ME" else None)
                 for i, h in enumerate(E.heads_of(E.mask_of(heads))))


def terminal(cl, env, spec):
    heads = spec["heads"]
    mask = E.mask_of(heads)
    groups = {h: (f"r-{h}",) for h in heads}
    key = subset_key(context().prefix, IDENT, groups, mask)
    readings = readings_of(heads, spec["readings"])
    trace = K.ExecutionTrace(domain_id="finite_head_v1", ordered_path=E.canonical_path(mask),
                             acquired=tuple(groups[h] for h in E.heads_of(mask)), readings=readings)
    answer = v3_answer(cl, errors=spec["errors"], rows=spec["rows"])
    j1 = JP3.run(lambda m: answer, J1, context().prefix.turns, spec["response"], cl, readings)
    att = ER3.attempt(key=key, subset="+".join(E.heads_of(mask)) or "OFF", stratum=env["derived_stratum"],
                      trace=trace, checklist=cl, needcard=env["needcard"], evidence_validation="verified",
                      response=spec["response"], finish_reason="natural_stop", verdicts=AG3.item_verdicts(cl, j1, None),
                      j1_identity=j1.identity, expected_j1_identity=j1.identity, input_tokens=None, prefix_tokens=None,
                      j1_ledger=JP3.ledger_summary(j1))
    verdicts = {i: x.verdict for i, x in j1.items.items()}
    out = dict(subset=att["subset"], status=att["status"], n_gets=len(heads),
               failed=sorted(i for i, v in verdicts.items() if v == "fail"),
               uncertain=sorted(i for i, v in verdicts.items() if v == "uncertain"))
    if att["status"] == "computed":
        r = att["record"]
        out.update(value=r["value"], lower=r["quality"]["j1_lower"], upper=r["quality"]["j1_upper"],
                   grid_u0=r["sensitivity"]["u=0.0|g=0.01"], grid_u1=r["sensitivity"]["u=1.0|g=0.01"])
    else:
        out.update(reasons=att["reasons"])
    return out


def run_case(case, margin: float = 0.0) -> dict:
    cl, env = card(case["card"])
    terms = {name: terminal(cl, env, spec) for name, spec in case["terminals"].items()}
    by_subset = {frozenset(spec["heads"]): terms[name] for name, spec in case["terminals"].items()}
    table = {s: ((t["lower"], t["upper"]) if t["status"] == "computed" else None) for s, t in by_subset.items()}
    head, base = case["focus"]
    b, s = frozenset(base), frozenset(base) | {head}
    iv = MV.delta(table[s], table[b])
    effect = MV.classify(iv, margin)
    er_delta = (by_subset[s]["value"] - by_subset[b]["value"]
                if by_subset[s]["status"] == by_subset[b]["status"] == "computed" else None)
    out = dict(id=case["id"], title=case["title"], card=case["card"], total_weight=cl.total_weight,
               head_needs=env["head_needs"], terminals=terms, focus=dict(head=head, base=list(base)),
               quality_delta=iv, er_effect=effect, er_value_delta=er_delta, midpoint_delta=MV.midpoint_delta(table[s], table[b]),
               attribution=MV.attribute(effect=effect, **case["chain"]), chain=case["chain"],
               ideal=case["ideal"], verdict=case["verdict"], note=case["note"])
    if {"MP", "MS"} <= {h for spec in case["terminals"].values() for h in spec["heads"]}:
        out["interaction_MP_MS"] = MV.interaction(table, "MP", "MS")
    return out
