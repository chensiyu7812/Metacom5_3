"""WS-B executable acceptance of the shared C0 contracts (0.2.0).

Skipped until `metacom_pm.rl1v3.contracts` is present on the branch.  The six
WS-B requests R1–R6 raised against 0.1.0 are now ordinary tests; any
regression fails CI.  See
project/outputs/pm_rl1/v3/C0_review/C0_REVIEW_WSB_ZH.md.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

K = pytest.importorskip("metacom_pm.rl1v3.contracts")
IO = pytest.importorskip("metacom_pm.rl1v3.io")
if not str(getattr(IO, "SCHEMA_VERSION", "")).startswith("pmrl1v3-contracts-0.2"):
    pytest.skip("WS-B acceptance targets C0 0.2.x", allow_module_level=True)

from metacom_pm.rl1v3.prefixes import census as C  # noqa: E402

PROJECT = Path(__file__).resolve().parents[1]
B0_ROWS = PROJECT / "outputs/pm_rl1/v3/B0/prefix_census.jsonl"
ARTIFACT = PROJECT / "data/paper1_public_memory/es_memeval_public_sanitized_runtime_artifact_v1.json"
HEADS = ("RS", "MP", "ME", "MS")
SHA = "a" * 64


def prefix(turns=(("seeker", "hi"),), **kw):
    args = dict(owner_id="p1", session_id="p1_conv_2", cut_turn=len(turns) - 1,
                turns=tuple(K.SourceTurn(turn_index=i, role=r, text=t)
                            for i, (r, t) in enumerate(turns)),
                cutoff_rank=1, timestamp="2024-01-01", dataset="evo",
                family_id="evoemo_owner:p1", ancestor_family_ids=("evoemo_owner:p1",),
                fold=2, stratum="history")
    args.update(kw)
    return K.PrefixSpec.create(**args)


def key(path, groups, domain="finite_head_v1", p=None, **kw):
    p = p or prefix()
    base = dict(domain_id=domain, bank_version="bank-v0", index_version="idx-v0",
                ordered_path=tuple(path), acquired=tuple(tuple(g) for g in groups),
                renderer_id="r", step2_id="s", g_id="g", decode_id="d")
    base.update(kw)
    return K.TerminalKey.for_prefix(p, **base)


def view(head, ordinal, **kw):
    args = dict(head=head, view={"RS": "method", "MP": "assertion", "ME": "event",
                                 "MS": "sum"}[head],
                ordinal=ordinal, reading_text=f"{head} text", reported_at=None, tokens=3,
                stage="attempted" if head == "ME" else None)
    args.update(kw)
    return K.ReadingView(**args)


def avail(n=1):
    return tuple(K.HeadAvailability(head=h, available=n > 0, count=n) for h in HEADS)


def obs(acquired=(), mask=("STOP",), domain="finite_head_v1", **kw):
    return K.Observation(domain_id=domain, history_sessions=1, prefix=prefix().visible(),
                         acquired=tuple(acquired), availability=avail(),
                         action_mask=tuple(mask), input_tokens=10, **kw)


def checklist(p=None, weights=(1.0, 2.0)):
    p = p or prefix()
    items = tuple(K.ChecklistItem(item_id=f"i{k}", category="G", constraint_type="soft_support",
                                  text=f"item {k}", evidence_spans=(), weight=w,
                                  applies_to="all_terminals", visibility_scope="evaluation_only",
                                  review_status="unverified") for k, w in enumerate(weights))
    return K.Checklist(prefix_id=p.prefix_id, needcard_sha256=SHA, items=items,
                       total_weight=sum(weights), writer_identity="w")


def record(k, trace, cl, verdicts, response="a reply", tier="engineering_only", **kw):
    lo, hi = K.gsc_interval(cl, verdicts)
    args = dict(key=k, execution=trace, checklist=cl, checklist_sha256=cl.sha256,
                feedback_id="fb", request_sha256=SHA, response=response,
                response_sha256=IO.sha256_text(response), item_verdicts=tuple(verdicts),
                gsc_lower=lo, gsc_upper=hi, hard_factual=None, hard_safety=None,
                soft_quality_pairwise=(), qualification_tier=tier, misuse_flags=(),
                latency_pred=None, latency_measured=None)
    args.update(kw)
    return K.TerminalRecord(**args)


# ------------------------------------------------- B0 compatibility (prefix ids)

@pytest.mark.skipif(not (B0_ROWS.exists() and ARTIFACT.exists()), reason="B0 outputs absent")
def test_b0_prefix_id_is_the_c0_v3_identity_for_every_census_row():
    users = {u.owner_id: u for u in C.load_users(ARTIFACT)}
    n = 0
    with B0_ROWS.open(encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            user = users[r["owner_id"]]
            turns = C.materialize_prefix(r, users)
            fams = {C.session_family(user.owner_id, s)
                    for s in C.strictly_past_sessions(user, r["cutoff_rank"])}
            fams.add(r["eval_only"]["family_id"])
            spec = K.PrefixSpec.create(
                owner_id=r["owner_id"], session_id=r["session_id"], cut_turn=r["cut_turn"],
                cutoff_rank=r["cutoff_rank"], timestamp=r["timestamp"], dataset=r["dataset"],
                turns=tuple(K.SourceTurn(turn_index=i, role=t.role, text=t.content)
                            for i, t in enumerate(turns)),
                family_id=r["eval_only"]["family_id"], ancestor_family_ids=tuple(fams),
                fold=r["assignment"]["fold"])
            assert spec.prefix_id == r["prefix_id"]
            n += 1
    assert n == 4119


def test_prefix_id_independent_of_fold_and_stratum_but_bound_to_content():
    a, b = prefix(fold=1, stratum="none"), prefix(fold=6, stratum="both")
    assert a.prefix_id == b.prefix_id and a.runtime_sha256 == b.runtime_sha256
    assert prefix(turns=(("seeker", "other"),)).prefix_id != a.prefix_id
    with pytest.raises(Exception):
        K.PrefixSpec(**{**{f.name: getattr(a, f.name) for f in dataclasses.fields(a)},
                        "prefix_id": "b" * 64})


# ---------------------------------------- R1: subset-canonical Phase-1 identity

def test_r1_finite_head_terminal_identity_is_order_invariant_and_trace_keeps_order():
    a = key(("GET_MP", "GET_RS", "STOP"), (("m1",), ("r1",)))
    b = key(("GET_RS", "GET_MP", "STOP"), (("r1",), ("m1",)))
    assert a.sha256 == b.sha256 and a.ordered_path == ("GET_RS", "GET_MP", "STOP")
    tr = K.ExecutionTrace(domain_id="finite_head_v1", ordered_path=("GET_MP", "GET_RS", "STOP"),
                          acquired=(("m1",), ("r1",)), readings=(view("MP", 1), view("RS", 2)))
    tr.verify_key(a)
    assert tr.ordered_path == ("GET_MP", "GET_RS", "STOP")


def test_r1_adaptive_identity_keeps_order():
    a = key(("GET_MP", "GET_RS", "STOP"), (("m1",), ("r1",)), domain="adaptive_v1")
    b = key(("GET_RS", "GET_MP", "STOP"), (("r1",), ("m1",)), domain="adaptive_v1")
    assert a.sha256 != b.sha256


def test_r1_terminal_key_hash_changes_with_every_identity_field():
    base = key(("GET_MP", "STOP"), (("m1",),))
    for name, value in [("bank_version", "b1"), ("index_version", "i1"), ("renderer_id", "r1"),
                        ("step2_id", "s1"), ("g_id", "g1"), ("decode_id", "d1"),
                        ("acquired", (("m2",),)), ("ordered_path", ("GET_ME", "STOP"))]:
        assert key(**{"path": ("GET_MP", "STOP") if name != "ordered_path" else value,
                      "groups": (("m1",),) if name != "acquired" else value},
                   **({} if name in ("acquired", "ordered_path") else {name: value})
                   ).sha256 != base.sha256, name
    assert key(("GET_MP", "STOP"), (("m1",),), domain="adaptive_v1").sha256 != base.sha256
    other = prefix(turns=(("seeker", "different"),))
    assert key(("GET_MP", "STOP"), (("m1",),), p=other).sha256 != base.sha256


# ------------------------------------------ R2: each GET bound to real records

def test_r2_get_without_delivered_record_and_group_mismatch_are_rejected():
    with pytest.raises(Exception):
        key(("GET_MP", "STOP"), ())
    with pytest.raises(Exception):
        key(("GET_MP", "STOP"), ((),))
    with pytest.raises(Exception):
        key(("GET_MP", "GET_RS", "STOP"), (("m1",),))
    with pytest.raises(Exception):
        key(("GET_MP", "GET_MP", "STOP"), (("m1",), ("m2",)))  # finite: head once
    with pytest.raises(Exception):
        key(("STOP",), (("x",),))
    key(("STOP",), ())


def test_r2_read_failure_has_no_reading_and_success_needs_records_and_capacity():
    K.ReadFailure(reason="capacity", detail="over", input_tokens_unchanged=10, elapsed_ms=1.0)
    ok = dict(reading=view("MP", 1), record_ids=("m1",), input_tokens_before=10,
              input_tokens_after=13, native_context_tokens=100, output_reserve_tokens=20,
              elapsed_ms=1.0)
    K.ReadSuccess(**ok)
    with pytest.raises(Exception):
        K.ReadSuccess(**{**ok, "record_ids": ()})
    with pytest.raises(Exception):
        K.ReadSuccess(**{**ok, "input_tokens_after": 95})
    with pytest.raises(Exception):
        K.ReadSuccess(**{**ok, "input_tokens_after": 11})  # reading not charged


# --------------------------------------- R3: parameterised EXPAND, domain split

def test_r3_expand_is_parameterised_and_adaptive_only():
    s = view("MS", 1, expandable=True)
    obs([s], mask=("STOP", "EXPAND_MS(1)"), domain="adaptive_v1")
    for bad in (("STOP", "EXPAND_MS"), ("STOP", "EXPAND_MS(2)")):
        with pytest.raises(Exception):
            obs([s], mask=bad, domain="adaptive_v1")
    with pytest.raises(Exception):
        obs([view("MS", 1, expandable=True)], mask=("STOP", "EXPAND_MS(1)"))  # finite
    with pytest.raises(Exception):
        obs([view("MP", 1)], mask=("STOP", "GET_MP"))  # finite: MP already read
    with pytest.raises(Exception):
        view("MP", 1, expandable=True)  # only SUM may advertise expansion
    with pytest.raises(Exception):
        key(("GET_MS", "EXPAND_MS(1)", "STOP"), (("s1",), ("raw1",)))  # finite
    key(("GET_MS", "EXPAND_MS(1)", "STOP"), (("s1",), ("raw1",)), domain="adaptive_v1")
    with pytest.raises(Exception):
        key(("GET_MP", "EXPAND_MS(1)", "STOP"), (("m1",), ("raw1",)), domain="adaptive_v1")


# ---------------------------------------- R4: fixed checklist and denominator

def test_r4_checklist_fixed_denominator_and_binding():
    cl = checklist(weights=(1.0, 3.0))
    with pytest.raises(Exception):
        K.Checklist(prefix_id=cl.prefix_id, needcard_sha256=SHA, items=cl.items, total_weight=3.0,
                    writer_identity="w")
    v = (K.ItemVerdict(item_id="i0", J1="pass", J2="pass", final="pass"),
         K.ItemVerdict(item_id="i1", J1="pass", J2="fail", final="uncertain"))
    assert K.gsc_interval(cl, v) == (0.25, 1.0)
    with pytest.raises(Exception):
        K.gsc_interval(cl, v[:1])  # dropping an item cannot change the denominator
    k = key(("STOP",), ())
    tr = K.ExecutionTrace(domain_id="finite_head_v1", ordered_path=("STOP",), acquired=(),
                          readings=())
    rec = record(k, tr, cl, v)
    assert rec.checklist_sha256 == cl.sha256 and rec.feedback_id == "fb"
    other = checklist(p=prefix(turns=(("seeker", "zzz"),)))
    with pytest.raises(Exception):
        record(k, tr, other, (K.ItemVerdict(item_id="i0", J1="pass", J2="pass", final="pass"),
                              K.ItemVerdict(item_id="i1", J1="pass", J2="pass", final="pass")))


# ------------------------------------- R5: per-judge evidence, J2 not run

def test_r5_judge_evidence_and_unrun_second_judge():
    p = K.ItemVerdict(item_id="i0", J1="pass", J2=None, final="pass", J1_quote="a reply")
    assert p.pending
    with pytest.raises(Exception):
        K.ItemVerdict(item_id="i0", J1="pass", J2=None, final="pass", J2_quote="x")
    with pytest.raises(Exception):
        K.ItemVerdict(item_id="i0", J1="pass", J2="fail", final="pass")
    cl = checklist()
    k = key(("STOP",), ())
    tr = K.ExecutionTrace(domain_id="finite_head_v1", ordered_path=("STOP",), acquired=(),
                          readings=())
    rec = record(k, tr, cl, (p, K.ItemVerdict(item_id="i1", J1="pass", J2="pass",
                                              final="pass")))
    assert (rec.gsc_lower, rec.gsc_upper) == (None, None)  # pending, not zero
    with pytest.raises(Exception):
        record(k, tr, cl, (K.ItemVerdict(item_id="i0", J1="pass", J2="pass", final="pass",
                                         J1_quote="not in reply"),
                           K.ItemVerdict(item_id="i1", J1="pass", J2="pass", final="pass")))


# ------------------------------------- R6: pending hard constraints

def test_r6_pending_hard_constraints_never_certified():
    cl = checklist()
    k = key(("STOP",), ())
    tr = K.ExecutionTrace(domain_id="finite_head_v1", ordered_path=("STOP",), acquired=(),
                          readings=())
    full = (K.ItemVerdict(item_id="i0", J1="pass", J2="pass", final="pass"),
            K.ItemVerdict(item_id="i1", J1="pass", J2="pass", final="pass"))
    rec = record(k, tr, cl, full)
    assert rec.hard_factual is None and rec.hard_safety is None
    with pytest.raises(Exception):
        record(k, tr, cl, full, tier="research_qualified")
    with pytest.raises(Exception):
        record(k, tr, cl, full, tier="research_qualified", hard_factual="pass",
               hard_safety="pass", evidence_validation="pending")


# ------------------------------------------------ Observation isolation

def test_observation_whitelist_and_no_private_fields():
    names = {f.name for f in dataclasses.fields(K.Observation)}
    assert names == {"schema_version", "domain_id", "history_sessions", "prefix", "acquired",
                     "availability", "action_mask", "input_tokens"}
    rv = {f.name for f in dataclasses.fields(K.ReadingView)}
    assert rv == {"schema_version", "head", "view", "expandable", "expanded_from_ordinal",
                  "ordinal", "reading_text", "reported_at", "tokens", "stage"}
    forbidden = {"record_id", "record_ids", "owner_id", "session_id", "prefix_id", "fold",
                 "stratum", "split", "family_id", "score", "need", "label", "reward", "gsc",
                 "source_refs", "key", "checklist"}
    for cls in (K.Observation, K.ReadingView, K.HeadAvailability, K.VisiblePrefix):
        assert not forbidden & {f.name for f in dataclasses.fields(cls)}, cls.__name__


def test_observation_decode_rejects_injected_private_field():
    raw = json.loads(IO.canonical_json(obs(mask=("STOP", "GET_RS"))))
    raw["record_id"] = "leak"
    with pytest.raises(Exception):
        IO.decode_contract(K.Observation, json.dumps(raw))
    raw = json.loads(IO.canonical_json(obs([view("MP", 1)], mask=("STOP",))))
    raw["acquired"][0]["score"] = 0.9
    with pytest.raises(Exception):
        IO.decode_contract(K.Observation, json.dumps(raw))


def test_visible_prefix_has_no_post_cut_turns():
    p = prefix(turns=(("supporter", "hello"), ("seeker", "I feel low")))
    assert [t.text for t in p.visible().turns] == ["hello", "I feel low"]
    with pytest.raises(Exception):
        prefix(turns=(("seeker", "a"), ("supporter", "future reply")))  # must end on seeker
