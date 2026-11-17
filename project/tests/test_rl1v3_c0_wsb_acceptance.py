"""WS-B executable acceptance of the shared C0 contracts (review of contracts 0.1.0).

Skipped until `metacom_pm.rl1v3.contracts` is present on the branch.  Plain
tests are guarantees WS-B code relies on.  `xfail(strict=True)` tests encode
the concrete changes WS-B requested before B5 freezes on C0; once C0 ships
them the xfail turns into XPASS (a failure), forcing both lines to drop the
marker in a coordinated schema-version commit.  See
project/outputs/pm_rl1/v3/C0_review/C0_REVIEW_WSB_ZH.md.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

K = pytest.importorskip("metacom_pm.rl1v3.contracts")
IO = pytest.importorskip("metacom_pm.rl1v3.io")

from metacom_pm.rl1v3.prefixes import census as C  # noqa: E402

PROJECT = Path(__file__).resolve().parents[1]
B0_ROWS = PROJECT / "outputs/pm_rl1/v3/B0/prefix_census.jsonl"
ARTIFACT = PROJECT / "data/paper1_public_memory/es_memeval_public_sanitized_runtime_artifact_v1.json"
HEADS = ("RS", "MP", "ME", "MS")
KEY = dict(prefix_id="p", bank_version="bank-v0", index_version="idx-v0", renderer_id="r",
           step2_id="s", g_id="g", decode_id="d")


def _prefix(turns=(("seeker", "hi"),)):
    return K.PrefixSpec(prefix_id="p", owner_id="p1", session_id="p1_conv_2", cut_turn=len(turns) - 1,
                        turns=tuple(K.SourceTurn(turn_index=i, role=r, text=t)
                                    for i, (r, t) in enumerate(turns)),
                        cutoff_rank=1, timestamp="2024-01-01", dataset="evo",
                        family_id="evoemo_owner:p1", fold=2, stratum="history")


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
    obs = K.Observation(prefix=_prefix().visible(), acquired=(), availability=_avail(),
                        action_mask=("STOP", "GET_RS"), input_tokens=3)
    raw = json.loads(IO.canonical_json(obs))
    raw["record_id"] = "leak"
    with pytest.raises(Exception):
        IO.decode_contract(K.Observation, json.dumps(raw))


def test_terminal_key_hash_changes_with_every_field():
    base = K.TerminalKey(ordered_path=("GET_MP", "STOP"), acquired_record_ids=("m1",), **KEY)
    variants = dict(KEY, ordered_path=("GET_MP", "STOP"), acquired_record_ids=("m1",))
    for name, value in [("prefix_id", "q"), ("bank_version", "b1"), ("index_version", "i1"),
                        ("renderer_id", "r1"), ("step2_id", "s1"), ("g_id", "g1"),
                        ("decode_id", "d1"), ("acquired_record_ids", ("m2",)),
                        ("ordered_path", ("GET_ME", "STOP"))]:
        other = K.TerminalKey(**dict(variants, **{name: value}))
        assert other.sha256 != base.sha256, name


def test_off_terminal_is_stop_only_and_empty():
    K.TerminalKey(ordered_path=("STOP",), acquired_record_ids=(), **KEY)
    with pytest.raises(Exception):
        K.TerminalKey(ordered_path=("STOP",), acquired_record_ids=("x",), **KEY)


def test_b0_hash_is_byte_identical_to_c0_object_sha256():
    obj = {"b": [1, "é"], "a": {"z": None, "y": True}}
    assert C.digest(obj) == IO.object_sha256(obj)


@pytest.mark.skipif(not (B0_ROWS.exists() and ARTIFACT.exists()), reason="B0 outputs absent")
def test_every_b0_census_row_builds_a_c0_prefixspec():
    users = {u.owner_id: u for u in C.load_users(ARTIFACT)}
    n = 0
    with B0_ROWS.open(encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            turns = C.materialize_prefix(r, users)
            spec = K.PrefixSpec(
                prefix_id=r["prefix_id"], owner_id=r["owner_id"], session_id=r["session_id"],
                cut_turn=r["cut_turn"], cutoff_rank=r["cutoff_rank"], timestamp=r["timestamp"],
                turns=tuple(K.SourceTurn(turn_index=i, role=t.role, text=t.content)
                            for i, t in enumerate(turns)),
                dataset=r["dataset"], family_id=r["eval_only"]["family_id"],
                fold=r["assignment"]["fold"])
            assert IO.object_sha256([[t.role, t.text] for t in spec.turns]) == r["prefix_sha256"]
            n += 1
    assert n == 4119


# ----------------------------------------------------- requested before B5 freeze

@pytest.mark.xfail(strict=True, reason="WS-B R1: Phase-1 terminals must be subset-canonical "
                   "(domain_id + canonical head order) so the 16-terminal table and DP are exact")
def test_r1_finite_head_terminal_is_order_invariant():
    a = K.TerminalKey(ordered_path=("GET_MP", "GET_RS", "STOP"), acquired_record_ids=("m1", "r1"),
                      **KEY)
    b = K.TerminalKey(ordered_path=("GET_RS", "GET_MP", "STOP"), acquired_record_ids=("r1", "m1"),
                      **KEY)
    assert a.sha256 == b.sha256


@pytest.mark.xfail(strict=True, reason="WS-B R2: every GET/EXPAND in ordered_path must bind its "
                   "own non-empty record group; a GET with no delivered record is not a terminal")
def test_r2_get_without_delivered_record_is_rejected():
    with pytest.raises(Exception):
        K.TerminalKey(ordered_path=("GET_MP", "STOP"), acquired_record_ids=(), **KEY)


@pytest.mark.xfail(strict=True, reason="WS-B R3: action_mask must carry parameterised "
                   "EXPAND_MS(j) exactly as TerminalKey.ordered_path does; bare EXPAND_MS is ambiguous")
def test_r3_action_mask_parameterises_expand():
    rv = K.ReadingView(head="MS", ordinal=1, reading_text="sum", reported_at=None, tokens=3)
    K.Observation(prefix=_prefix().visible(), acquired=(rv,), availability=_avail(),
                  action_mask=("STOP", "EXPAND_MS(1)"), input_tokens=3)
    with pytest.raises(Exception):
        K.Observation(prefix=_prefix().visible(), acquired=(rv,), availability=_avail(),
                      action_mask=("STOP", "EXPAND_MS"), input_tokens=3)


@pytest.mark.xfail(strict=True, reason="WS-B R4: checklist items must be bound to one prefix "
                   "with a fixed total weight (fixed GSC denominator across all terminals)")
def test_r4_checklist_container_binds_prefix_and_total_weight():
    assert hasattr(K, "Checklist")
    names = {f.name for f in dataclasses.fields(K.Checklist)}
    assert {"prefix_id", "items", "total_weight", "needcard_sha256"} <= names
    rec = {f.name for f in dataclasses.fields(K.TerminalRecord)}
    assert {"checklist_sha256", "feedback_id"} <= rec


@pytest.mark.xfail(strict=True, reason="WS-B R5: item verdicts keep per-judge evidence and "
                   "distinguish 'J2 not run' (None) from 'uncertain'")
def test_r5_item_verdict_evidence_and_optional_second_judge():
    names = {f.name for f in dataclasses.fields(K.ItemVerdict)}
    assert {"J1_quote", "J1_source_span", "J2_quote", "J2_source_span"} <= names
    K.ItemVerdict(item_id="i", J1="pass", J2=None, final="pass")


@pytest.mark.xfail(strict=True, reason="WS-B R6: unevaluated hard constraints are pending "
                   "(None), never collapsed into 'uncertain' or a zero reward")
def test_r6_hard_constraints_can_be_pending():
    resp = "ok"
    K.TerminalRecord(key=K.TerminalKey(ordered_path=("STOP",), acquired_record_ids=(), **KEY),
                     request_sha256="0" * 64, response=resp, response_sha256=IO.sha256_text(resp),
                     item_verdicts=(), gsc_lower=None, gsc_upper=None, hard_factual=None,
                     hard_safety=None, soft_quality_pairwise=(), qualification_tier="engineering_only",
                     misuse_flags=(), latency_pred=None, latency_measured=None)
