"""WS-A compatibility tests, with B0 data only; no copied B business code.
The authoritative WS-B acceptance filename is exclusively owned by WS-B.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from metacom_pm.rl1v3 import contracts as K
from metacom_pm.rl1v3 import io as IO

import gzip
from metacom_pm.rl1v3.sources.asset_reuse import session_family
_FIXTURE = Path(__file__).parent / "fixtures/rl1v3/b0_reference"

PROJECT = Path(__file__).resolve().parents[1]
B0_ROWS = _FIXTURE / "prefix_census.jsonl.gz"
ARTIFACT = PROJECT / "data/paper1_public_memory/es_memeval_public_sanitized_runtime_artifact_v1.json"
HEADS = ("RS", "MP", "ME", "MS")
KEY = dict(domain_id="finite_head_v1", owner_id="p1", prefix_id="0"*64, prefix_context_sha256="1"*64, bank_version="bank-v0", index_version="idx-v0", renderer_id="r",
           step2_id="s", g_id="g", decode_id="d")


def _prefix(turns=(("seeker", "hi"),)):
    return K.PrefixSpec.create( owner_id="p1", session_id="p1_conv_2", cut_turn=len(turns) - 1,
                        turns=tuple(K.SourceTurn(turn_index=i, role=r, text=t)
                                    for i, (r, t) in enumerate(turns)),
                        cutoff_rank=1, timestamp="2024-01-01", dataset="evo",
                        family_id="evoemo_owner:p1", ancestor_family_ids=("evoemo_owner:p1",), fold=2, stratum="history")


def _avail(n=1):
    return tuple(K.HeadAvailability(head=h, available=n > 0, count=n) for h in HEADS)


# ------------------------------------------------------------ relied-upon guarantees

def test_visible_prefix_drops_routing_and_evaluation_fields():
    vis = _prefix().visible()
    names = {f.name for f in dataclasses.fields(vis)}
    assert names == {"schema_version", "turns", "timestamp"}


def test_observation_and_reading_view_carry_no_private_identity():
    forbidden = {"record_id", "owner_id", "session_id", "prefix_id", "fold", "stratum", "split",
                 "family_id", "score", "rank", "need", "label", "reward", "source_refs"}
    for cls in (K.Observation, K.ReadingView, K.HeadAvailability, K.VisiblePrefix):
        assert not forbidden & {f.name for f in dataclasses.fields(cls)}, cls.__name__


def test_observation_rejects_unknown_fields_on_decode():
    obs = K.Observation(domain_id="finite_head_v1", history_sessions=1, prefix=_prefix().visible(), acquired=(), availability=_avail(),
                        action_mask=("STOP", "GET_RS"), input_tokens=3)
    raw = json.loads(IO.canonical_json(obs))
    raw["record_id"] = "leak"
    with pytest.raises(Exception):
        IO.decode_contract(K.Observation, json.dumps(raw))


def test_terminal_key_hash_changes_with_every_field():
    base = K.TerminalKey(ordered_path=("GET_MP", "STOP"), acquired=(("m1",),), **KEY)
    variants = dict(KEY, ordered_path=("GET_MP", "STOP"), acquired=(("m1",),))
    for name, value in [("prefix_id", "2"*64), ("bank_version", "b1"), ("index_version", "i1"),
                        ("renderer_id", "r1"), ("step2_id", "s1"), ("g_id", "g1"),
                        ("decode_id", "d1"), ("acquired", (("m2",),)),
                        ("ordered_path", ("GET_ME", "STOP"))]:
        other = K.TerminalKey(**dict(variants, **{name: value}))
        assert other.sha256 != base.sha256, name


def test_off_terminal_is_stop_only_and_empty():
    K.TerminalKey(ordered_path=("STOP",), acquired=(), **KEY)
    with pytest.raises(Exception):
        K.TerminalKey(ordered_path=("STOP",), acquired=(("x",),), **KEY)


def test_b0_hash_is_byte_identical_to_c0_object_sha256():
    obj = {"b": [1, "é"], "a": {"z": None, "y": True}}
    vector = json.loads((_FIXTURE / "PROVENANCE.json").read_text())["canonical_hash_vector"]
    assert vector["value"] == obj
    assert vector["expected"] == IO.object_sha256(obj)


def test_every_b0_census_row_builds_a_c0_prefixspec():
    users = {u["owner_id"]: u for u in json.loads(ARTIFACT.read_text())["users"]}
    n = 0
    with gzip.open(B0_ROWS, "rt", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            sessions = users[r["owner_id"]]["sessions"]
            current = next(s for s in sessions if s["session_id"] == r["session_id"])
            assert current["chronological_rank"] == r["cutoff_rank"]
            assert current["timestamp"] == r["timestamp"]
            turns = current["turns"][:r["cut_turn"]+1]
            assert current["turns"][r["cut_turn"]+1]["role"] == "supporter"
            spec = K.PrefixSpec(
                prefix_id=r["prefix_id"], owner_id=r["owner_id"], session_id=r["session_id"],
                cut_turn=r["cut_turn"], cutoff_rank=r["cutoff_rank"], timestamp=r["timestamp"],
                turns=tuple(K.SourceTurn(turn_index=i, role=t["role"], text=t["content"])
                            for i, t in enumerate(turns)),
                dataset=r["dataset"], family_id=r["eval_only"]["family_id"],
                ancestor_family_ids=tuple(sorted({session_family(r["owner_id"], session["session_id"])
                    for session in sessions if session["chronological_rank"] <= r["cutoff_rank"]})),
                fold=r["assignment"]["fold"])
            assert IO.object_sha256([[t.role, t.text] for t in spec.turns]) == r["prefix_sha256"]
            n += 1
    assert n == 4119


# ----------------------------------------------------- requested before B5 freeze

def test_r1_finite_head_terminal_is_order_invariant():
    a = K.TerminalKey(ordered_path=("GET_MP", "GET_RS", "STOP"), acquired=(("m1",),("r1",)),
                      **KEY)
    b = K.TerminalKey(ordered_path=("GET_RS", "GET_MP", "STOP"), acquired=(("r1",),("m1",)),
                      **KEY)
    assert a.sha256 == b.sha256


def test_r2_get_without_delivered_record_is_rejected():
    with pytest.raises(Exception):
        K.TerminalKey(ordered_path=("GET_MP", "STOP"), acquired=(), **KEY)


def test_r3_action_mask_parameterises_expand():
    rv = K.ReadingView(head="MS", view="sum", expandable=True, ordinal=1, reading_text="sum", reported_at=None, tokens=3)
    K.Observation(domain_id="adaptive_v1", history_sessions=1, prefix=_prefix().visible(), acquired=(rv,), availability=_avail(),
                  action_mask=("STOP", "EXPAND_MS(1)"), input_tokens=3)
    with pytest.raises(Exception):
        K.Observation(domain_id="adaptive_v1", history_sessions=1, prefix=_prefix().visible(), acquired=(rv,), availability=_avail(),
                      action_mask=("STOP", "EXPAND_MS"), input_tokens=3)


def test_r4_checklist_container_binds_prefix_and_total_weight():
    assert hasattr(K, "Checklist")
    names = {f.name for f in dataclasses.fields(K.Checklist)}
    assert {"prefix_id", "items", "total_weight", "needcard_sha256"} <= names
    rec = {f.name for f in dataclasses.fields(K.TerminalRecord)}
    assert {"checklist_sha256", "feedback_id"} <= rec


def test_r5_item_verdict_evidence_and_optional_second_judge():
    names = {f.name for f in dataclasses.fields(K.ItemVerdict)}
    assert {"J1_quote", "J1_source_span", "J2_quote", "J2_source_span"} <= names
    K.ItemVerdict(item_id="i", J1="pass", J2=None, final="pass")


def test_r6_hard_constraints_can_be_pending():
    from dataclasses import replace
    from test_rl1v3_contracts import examples
    base = examples()["TerminalRecord"]
    pending = tuple(replace(v, J1=None, J2=None, final=None) for v in base.item_verdicts)
    rec = replace(base, key=replace(base.key, ordered_path=("STOP",), acquired=()),
                  execution=K.ExecutionTrace(domain_id="finite_head_v1", ordered_path=("STOP",), acquired=(), readings=()),
                  item_verdicts=pending, gsc_lower=None, gsc_upper=None, hard_factual=None, hard_safety=None)
    assert rec.hard_factual is None and rec.hard_safety is None
    assert rec.gsc_lower is None and rec.gsc_upper is None
    with pytest.raises(ValueError):
        replace(rec, qualification_tier="research_qualified")
