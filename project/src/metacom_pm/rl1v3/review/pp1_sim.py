"""Synthetic PP1 material for the end-to-end acceptance of the review tool.

Every text here is invented and marked SIMULATED; nothing comes from EvoEmo, ESConv or any model output.  The
shape mirrors PP1: 8 cases with an as-of history, one OFF reply and one resource reply per case (conditions are
known only to the audit side), plus one extra rank-0 case for the curator's S7 form.
"""
from __future__ import annotations

SIM_SALT = "SIMULATION-ONLY-NOT-A-SECRET"
SIM_PROTOCOL = dict(id="pmrl1v3-v321a-pp1-sim", sha256="0" * 64, note="simulated acceptance run")

_TOPICS = [
    ("starting a new job at a bakery", "my manager seems strict", "I tried waking up earlier but it did not help"),
    ("moving to a new city", "I still know nobody here", "joining a running club felt awkward last time"),
    ("my sister's wedding planning", "everyone keeps asking me to help", "I said no to organising the music"),
    ("preparing for a driving test", "I failed the parking part once", "practising at night made me more nervous"),
    ("caring for an old dog", "the vet visits are expensive", "a payment plan was rejected by the clinic"),
    ("learning to cook for myself", "I keep burning the rice", "the cooking class was too fast for me"),
    ("a long exam season", "my friends study much faster", "a study group made me feel worse"),
    ("repairing a friendship", "we argued about a trip", "my first apology message got no answer"),
]


def _session(topic, detail, tried, n):
    return [dict(role="seeker", text=f"Simulated session {n}: I want to talk about {topic}."),
            dict(role="supporter", text=f"Simulated supporter: thank you for sharing about {topic}. How are you feeling?"),
            dict(role="seeker", text=f"Simulated: honestly {detail}."),
            dict(role="supporter", text="Simulated supporter: that sounds hard. What have you tried so far?"),
            dict(role="seeker", text=f"Simulated: {tried}.")]


def cases(n_cases: int = 8) -> list[dict]:
    out = []
    for i in range(n_cases):
        topic, detail, tried = _TOPICS[i % len(_TOPICS)]
        hist = [dict(date=f"2030-0{1 + k}-1{i % 9}", turns=_session(topic, detail, tried, k + 1)) for k in range(2 + i % 2)]
        prefix = [dict(role="seeker", text=f"Simulated today: things around {topic} came back this week."),
                  dict(role="supporter", text="Simulated supporter: I am here. What happened?"),
                  dict(role="seeker", text=f"Simulated today: {detail} again and I do not know what to do.")]
        out.append(dict(case_key=f"sim-case-{i + 1}", owner_key=f"sim-owner-{i + 1}", order_key=1,
                        prefix=prefix, history=hist))
    return out


def rank0_case() -> dict:
    return dict(case_key="sim-case-rank0", owner_key="sim-owner-9", order_key=0,
                prefix=[dict(role="seeker", text="Simulated first talk: I just want someone to listen today.")], history=[])


def replies(cs: list[dict]) -> tuple[list[dict], list[tuple], dict]:
    reps, pairs, resources = [], [], {}
    for i, c in enumerate(cs):
        topic, detail, tried = _TOPICS[i % len(_TOPICS)]
        a = dict(reply_key=f"{c['case_key']}:base", case_key=c["case_key"], condition="OFF",
                 text=f"Simulated reply: it makes sense that {detail} feels heavy. Would it help to talk through "
                      f"one small step you could take this week?")
        b = dict(reply_key=f"{c['case_key']}:res", case_key=c["case_key"], condition="RET-MS",
                 text=f"Simulated reply: you mentioned before that {tried}, so let us not repeat that. "
                      f"It makes sense that {detail} feels heavy. What would feel manageable right now?")
        reps += [a, b]
        pairs.append((f"pair:{c['case_key']}", c["case_key"], a["reply_key"], b["reply_key"]))
        resources[b["reply_key"]] = "（模拟材料）" + " / ".join(t["text"] for t in c["history"][0]["turns"])
    return reps, pairs, resources


def translate(text: str) -> str | None:
    """Mock translation for prefix lines only (tests the original/translation mapping, not translation quality)."""
    if text.startswith("Simulated today") or text.startswith("Simulated first talk"):
        return "【模拟译文】" + text.replace("Simulated", "模拟")
    return None
