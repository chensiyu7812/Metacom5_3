"""G0e binding addendum helpers: payload leak checks and future-text rules (fixtures; WS-A G0e not needed)."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

from rl1v3_wsb_fixtures import FUTURE, context, future_session

spec = importlib.util.spec_from_file_location(
    "g0e_addendum", Path(__file__).resolve().parents[1] / "scripts/rl1v3/B6e_g0e_binding_addendum.py")
A = importlib.util.module_from_spec(spec)
spec.loader.exec_module(A)


def payload(*texts):
    return dict(messages=[dict(role="user", content=t) for t in texts], input_ids=[1, 2], decode={})


def test_payload_leak_checks_cover_keys_ids_future_text_and_evaluation_markers():
    p = context().prefix
    ok = payload(*(t.text for t in p.turns))
    assert A.payload_leaks(ok, prefix=p, private_ids={p.prefix_id}, future_texts=[FUTURE[0][1]], markers=["NeedCard"]) == []
    assert A.payload_leaks(dict(ok, key="x"), prefix=p, private_ids=set(), future_texts=[], markers=[])[0].startswith("payload_keys")
    bad = payload("hello " + p.prefix_id, FUTURE[0][1], "per the NeedCard you need")
    found = A.payload_leaks(bad, prefix=p, private_ids={p.prefix_id}, future_texts=[FUTURE[0][1]], markers=["NeedCard"])
    assert {f.split(":")[0] for f in found} == {"private_id", "future_text", "evaluation_marker"}
    markers = A.forbidden_markers()
    assert any("NOT validated" in m or "METHOD_LABELS" in m for m in markers) and "checklist" in markers


def test_future_text_identical_to_legal_text_is_counted_not_flagged():
    ctx = context()
    p = ctx.prefix
    greeting = "Hey there, how are you doing today my friend?"
    cur = ctx.current
    turns = (SimpleNamespace(turn_index=0, role="supporter", text=greeting),
             SimpleNamespace(turn_index=9, role="seeker", text="FUTURE: something said after the cut in this session."))
    fut = future_session()
    entries = [SimpleNamespace(source=SimpleNamespace(owner_id=p.owner_id, session_id=cur.session_id,
                                                      chronological_rank=p.cutoff_rank, turns=turns)),
               SimpleNamespace(source=SimpleNamespace(owner_id=p.owner_id, session_id=fut.session_id,
                                                      chronological_rank=p.cutoff_rank + 1,
                                                      turns=(SimpleNamespace(text=greeting),) + tuple(fut.turns)))]
    reg = SimpleNamespace(entries=entries, entry=lambda o, s: next(e for e in entries if e.source.session_id == s))
    port = SimpleNamespace(bank=SimpleNamespace(registry=reg))
    prefix = SimpleNamespace(owner_id=p.owner_id, session_id=cur.session_id, cut_turn=0, cutoff_rank=p.cutoff_rank,
                             turns=(SimpleNamespace(text=greeting),))
    check, shared = A.future_texts_of(port, prefix)
    assert shared == 1 and greeting not in check
    assert "FUTURE: something said after the cut in this session." in check and FUTURE[0][1] in check
