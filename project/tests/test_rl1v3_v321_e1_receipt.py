"""WS-B independent E1 as-of receipt checker: own canonical hash, own materialisation, tamper detection."""
from __future__ import annotations

import copy
import html
import json

import pytest

from metacom_pm.rl1v3.asof import e1_receipt as E

VECTORS = [  # PR #18 HASH_TEST_VECTORS.json (copied; values are the exchange spec's own examples)
    dict(input={}, canonical_utf8_text="{}", canonical_utf8_hex="7b7d",
         sha256="44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a"),
    dict(input={"b": 2, "a": 1}, canonical_utf8_text='{"a":1,"b":2}', canonical_utf8_hex="7b2261223a312c2262223a327d",
         sha256="43258cff783fe7036d8a43033f830adfc60ec037382473548ac742b888292777"),
    dict(input={"quote": "他曾说\n“未尝试”", "nullable": None, "ordered": ["é", "é"], "flag": False},
         canonical_utf8_text='{"flag":false,"nullable":null,"ordered":["é","é"],"quote":"他曾说\\n“未尝试”"}',
         canonical_utf8_hex="7b22666c6167223a66616c73652c226e756c6c61626c65223a6e756c6c2c226f726465726564223a5b22c3a9222c"
                            "2265cc81225d2c2271756f7465223a22e4bb96e69bbee8afb45c6ee2809ce69caae5b09de8af95e2809d227d",
         sha256="19e2f23728fb5ef4761b44c6df30a7fdaefa338cc115cbbf3240558bbd6031a9"),
    dict(input={"as_of": {"owner_id": "p3", "cutoff_rank": 3}, "snapshot_sha": "excluded"},
         canonical_utf8_text='{"as_of":{"cutoff_rank":3,"owner_id":"p3"}}',
         canonical_utf8_hex="7b2261735f6f66223a7b226375746f66665f72616e6b223a332c226f776e65725f6964223a227033227d7d",
         sha256="1921ba614a5f9deacb9bc3f0b2ad01960732d69e89ce750977d3404091841eea"),
]


def test_own_encoder_reproduces_spec_vectors():
    assert E.check_vectors(VECTORS) == []


@pytest.mark.parametrize("obj", [{"z": [1, "a\u0001\t/"], "a": {"y": None, "x": True}}, [" ", "\\", '"'], 0, "é"])
def test_own_encoder_equals_stdlib_compact_sorted(obj):
    assert E.canon(obj) == json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def test_floats_and_duplicates_rejected():
    with pytest.raises(ValueError):
        E.canon({"a": 1.5})
    with pytest.raises(ValueError):
        E.strict_loads('{"a":1,"a":2}')
    with pytest.raises(ValueError):
        E.strict_loads('{"a":NaN}')


# ------------------------------------------------------------------ synthetic bundle built from B's own rules
def _artifact():
    sess = []
    for r, (sid, date) in enumerate([("esc12", "2024-01-01"), ("p1_conv_1", "2024-02-01"), ("p1_conv_2", "2024-03-01"),
                                     ("p1_conv_3", "2024-04-01")]):
        sess.append(dict(session_id=sid, chronological_rank=r, timestamp=date, turns=[
            dict(idx=1, role="supporter", content=f"Hi there, session {r}."),
            dict(idx=2, role="seeker", content=f"I'm worried about exam {r}, it's hard."),
            dict(idx=3, role="supporter", content=f"That sounds stressful {r}."),
            dict(idx=4, role="seeker", content=f"Yes, my friend Ana said {r} words about the long weekend trip plans.")]))
    other = [dict(session_id="p2_conv_1", chronological_rank=0, timestamp="2024-01-05", turns=[
        dict(idx=1, role="seeker", content="completely different owner text that nobody else ever wrote here")])]
    return dict(users=[dict(owner_id="p1", sessions=sess), dict(owner_id="p2", sessions=other)])


def _record(raw, owner, sid, rank):
    turns = raw.sessions[(owner, sid)]["turns"]
    refs = [dict(owner_id=owner, session_id=sid, turn_index=i, start_char=0, end_char=len(t["text"]),
                 exact_quote=t["text"], speaker=t["role"], raw_turn_sha256=E.text_sha(t["text"]), source_rank=rank,
                 source_key=f"d:{owner}:{sid}:{i}") for i, t in enumerate(turns)]
    r = dict(kind="MS_RAW", owner_id=owner, session_id=sid, review_status="pending", source_refs=refs,
             text="\n".join(f"{t['role']}: {t['text']}" for t in turns),
             reported_at=dict(session_rank=rank), known_at=dict(session_rank=rank + 1),
             ready_at=dict(session_rank=rank + 1), record_id="pending")
    r["record_id"] = "asof-record:" + E.digest(r)
    return r


def _bundle():
    raw = E.Raw(_artifact())
    owner, cutoff, sid, cut = "p1", 3, "p1_conv_3", 1
    cur = raw.sessions[(owner, sid)]
    fam = sorted({f"evoemo_owner:{owner}"} | {s["family_id"] for s in raw.by_owner[owner] if s["rank"] <= cutoff})
    pre = dict(schema_version="x", prefix_id="PID", prefix_protocol="x", identity_scope="v3", owner_id=owner,
               session_id=sid, cut_turn=cut, cutoff_rank=cutoff, timestamp=cur["date"], dataset="d",
               family_id=cur["family_id"], ancestor_family_ids=fam,
               turns=[dict(role=t["role"], text=t["text"], turn_index=i) for i, t in enumerate(cur["turns"][:cut + 1])])
    srcs = []
    for s in raw.legal_past(owner, cutoff, pre["timestamp"]):
        x = dict(owner_id=owner, session_id=s["session_id"], dataset="d", chronological_rank=s["rank"], date=s["date"],
                 family_id=s["family_id"], ancestor_family_ids=[], license="l", complete=True,
                 transcript_sha256=raw.transcript_sha(owner, s["session_id"]))
        x["source_sha256"] = E.digest({k: x[k] for k in E.SOURCE_FIELDS})
        srcs.append(x)
    frontier = dict(as_of=dict(owner_id=owner, cutoff_rank=cutoff), sources=srcs)
    past = [_record(raw, owner, s["session_id"], s["rank"]) for s in raw.legal_past(owner, cutoff, None)]
    future = past + [_record(raw, owner, sid, cutoff)]
    lp = E.materialize(past, cutoff)
    ctx = E.digest({k: pre[k] for k in E.CONTEXT_FIELDS})
    snap = dict(as_of=dict(owner_id=owner, cutoff_rank=cutoff, prefix_context_sha256=ctx), ledger_prefix=lp,
                views=[dict(record=r, disposition="raw_available") for r in lp], source_frontier=frontier,
                source_frontier_sha256=E.digest(frontier))
    snap["snapshot_sha"] = E.digest(snap)
    latest = raw.legal_past(owner, cutoff, None)[-1]
    reading = dict(MS=dict(view="raw", reported_at=dict(session_rank=latest["rank"]),
                           reading_text="Header.\n" + "\n".join(f"{t['role']}: {t['text']}" for t in latest["turns"])),
                   MP=dict(status="unavailable"), ME=dict(status="unavailable"))
    b = dict(prefix_id="PID", prefix_context_sha256=ctx, snapshot_sha=snap["snapshot_sha"],
             source_frontier_sha256=snap["source_frontier_sha256"], raw_record_ids=[r["record_id"] for r in lp],
             selected_raw_id=[r for r in lp if r["session_id"] == latest["session_id"]][0]["record_id"],
             reading_sha256=E.digest(reading["MS"]))
    files = dict(prefix=pre, frontier=frontier, reading=reading, snapshot_past=snap, snapshot_future=copy.deepcopy(snap),
                 ledger_past=past, ledger_future=future)
    census = dict(owner_id=owner, session_id=sid, cut_turn=cut, cutoff_rank=cutoff, timestamp=cur["date"])
    return b, files, raw, census


def test_valid_synthetic_bundle_passes():
    b, f, raw, c = _bundle()
    assert E.check_prefix(b, f, raw, c, {"PID"})["problems"] == []


@pytest.mark.parametrize("tamper,expect", [
    (lambda f: f["ledger_past"][0]["source_refs"][1].update(exact_quote="I am worried"), "M5_record_id"),
    (lambda f: f["snapshot_future"]["ledger_prefix"].reverse(), "M4_snapshot_sha_not_reproduced:future"),
    (lambda f: f["prefix"]["turns"][1].update(text="changed"), "M2_prefix_turns_not_verbatim_raw"),
    (lambda f: f["frontier"]["sources"].pop(), "M3_frontier_not_exact_legal_past"),
    (lambda f: f["reading"]["MS"].update(reading_text="Header.\nsupporter: invented"), "M8_reading_text_not_verbatim_raw"),
])
def test_tampering_is_detected(tamper, expect):
    b, f, raw, c = _bundle()
    tamper(f)
    probs = E.check_prefix(b, f, raw, c, {"PID"})["problems"]
    assert any(p.startswith(expect) for p in probs), probs


def test_future_session_record_never_materialised_at_cutoff():
    b, f, raw, c = _bundle()
    assert len(f["ledger_future"]) == len(f["ledger_past"]) + 1
    assert E.materialize(f["ledger_future"], 3) == E.materialize(f["ledger_past"], 3)


def _g0e():
    return dict(common=dict(system_prompt="SYS", decode=dict(max_new_tokens=320), step2_id="s2"))


def _row(f, arm, inserted=None):
    conv = [dict(role=E.ROLE[t["role"]], content=t["text"]) for t in f["prefix"]["turns"]]
    m = [dict(role="system", content="SYS")] + ([dict(role="user", content=inserted)] if inserted else []) + conv
    ids = list(range(40))
    return dict(request_id="r", arm=arm, preview_messages=m, messages_sha256=E.digest(m), input_ids=ids,
                input_ids_sha256=E.digest(ids), input_tokens=40, output_reserve=320, runtime_context=16384,
                decode=dict(max_new_tokens=320), step2_id="s2", runtime_callable=False, execution_authorized=False,
                reward=None, terminal_result=None)


def _ev(text):
    return '<ExternalEvidence type="MS-RAW-direct">\n' + text + "\n</ExternalEvidence>"


def test_projection_passes_and_flags_future_and_other_owner_text():
    b, f, raw, c = _bundle()
    off = _row(f, "OFF")
    assert E.check_projection(off, f["prefix"], f["reading"]["MS"], raw, _g0e())["problems"] == []
    ms = _row(f, "MS-RAW-direct", _ev(f["reading"]["MS"]["reading_text"]))
    assert E.check_projection(ms, f["prefix"], f["reading"]["MS"], raw, _g0e(), off["preview_messages"])["problems"] == []
    leak = _row(f, "MS-RAW-direct", _ev(f["reading"]["MS"]["reading_text"] + "\nYes, my friend Ana said 3 words about the long weekend. "
                                        "completely different owner text that nobody else ever wrote here"))
    probs = E.check_projection(leak, f["prefix"], f["reading"]["MS"], raw, _g0e())["problems"]
    assert any(p.startswith("P5_future_text") for p in probs) and any(p.startswith("P5_other_owner") for p in probs)


def test_escaped_payload_is_recorded_not_hidden():
    b, f, raw, c = _bundle()
    ms = _row(f, "MS-RAW-direct", _ev(html.escape(f["reading"]["MS"]["reading_text"])))
    r = E.check_projection(ms, f["prefix"], f["reading"]["MS"], raw, _g0e())
    assert r["problems"] == [] and r["html_escaped_payload"] is True
