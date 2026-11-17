"""Portable C0 contracts: real serialization/identity/isolation, no models."""
from dataclasses import FrozenInstanceError, asdict, fields, replace
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from metacom_pm.rl1v3.contracts import (
    Checklist, ExecutionTrace, HumanAdjudication, OutdatedFact, ReadSuccess, ReadFailure,
    CONTRACT_TYPES, ChecklistItem, HeadAvailability, HistoryItem, IndexManifest,
    ItemVerdict, NeedCard, Observation, PairwiseQuality, PrefixSpec, RankedCandidate,
    ReadingView, Rejection, ResourceRecord, RetrievalResult, RetrievalTrace,
    ScoreComponent, SourceSession, SourceSpan, SourceTurn, TemporalClaim,
    TemporalRelation, TerminalKey, TerminalRecord, TimePoint, VisiblePrefix, json_schema,
)
from metacom_pm.rl1v3.io import (
    SCHEMA_VERSION, build_manifest, canonical_json, decode_contract, object_sha256,
    parse_json, sha256_text, verify_manifest, write_json_once,
)

SHA = sha256_text("fixture")


def examples():
    t = SourceTurn(turn_index=0, role="seeker", text="我打算搬家。")
    time = TimePoint(session_rank=0)
    s = SourceSession(owner_id="p1", session_id="s1", chronological_rank=0, date=None,
                      turns=(t,), raw_sha256=SHA, dataset="fixture", family_id="f1",
                      license="test_fixture", provenance_version="v1", source_uri="fixture:s1",
                      source_split="train", transcript_sha256=object_sha256([(t.role, t.text)]))
    span = SourceSpan(source_key="fixture:p1:s1:0", owner_id="p1", session_id="s1",
                      source_rank=0, turn_index=0, speaker="seeker", start_char=0,
                      end_char=len(t.text), exact_quote=t.text, raw_turn_sha256=t.raw_turn_sha256)
    p = PrefixSpec.create( owner_id="p1", session_id="s2", cut_turn=0,
                   turns=(t,), cutoff_rank=1, timestamp=None, dataset="fixture", family_id="f2", ancestor_family_ids=("f1","f2"))
    resource = ResourceRecord(record_id="me1", bank_version="v0", head="ME", view="event",
        owner_id="p1", source_refs=(span,), reported_at=time, event_time=None, valid_from=None,
        invalid_at=None, stage="intended", body='{"legacy":true}', reading_text=t.text,
        index_keys=("move",), review_status="unverified", writer_identity="fixture-v1",
        source_rank=0, ready_at=time, origin_dataset="fixture", family_id="f1",
        original_raw_identity=SHA, evidence_status="exact_span_verified", epistemic_status="reported_intention")
    claim = TemporalClaim(claim_id="c1", head="ME", subject_id="user", predicate="plans",
        object="moving", reported_at=time, source_rank=0, event_time=None, valid_from=None,
        valid_to=None, invalidated_knowledge_rank=None, epistemic_status="reported_intention",
        evidence_spans=(span,), semantic_support="unverified", version_group="vg1")
    relation = TemporalRelation(edge_id="e1", relation_type="updates", left_id="c2", right_id="c1",
        direction="left_to_right", evidence_spans=(), reported_at=TimePoint(session_rank=2),
        derivation_identity="fixture-v1", review_status="unverified", semantic_support="unverified")
    view = ReadingView(head="ME", view="event", ordinal=1, reading_text=t.text, reported_at=time, tokens=7, stage="intended")
    availability = HeadAvailability(head="ME", available=True, count=1)
    obs = Observation(domain_id="finite_head_v1", history_sessions=1, prefix=p.visible(), acquired=(view,), availability=(availability,),
                      action_mask=("STOP",), input_tokens=10)
    component = ScoreComponent(name="bm25", score=0.5, rank=1)
    ranked = RankedCandidate(record_id="me1", score=0.5, components=(component,))
    result = RetrievalResult(head="ME", ranked=(ranked,), query_identity=SHA,
        filters_applied=("owner", "strict_past"), bank_version="v0", index_version="i0")
    index = IndexManifest(index_version="i0", bank_version="v0", bank_sha256=SHA, head="ME",
        encoder_id="BGE-M3-dense", encoder_revision="revision", encoder_sha256=SHA,
        encoder_dimension=1024, encoder_max_tokens=8192, sparse_method="bm25", sparse_identity="bm25-v1",
        normalization="l2", pooling="cls", chunker_identity="sentence-v1", records_sha256=SHA,
        vectors_sha256=SHA, built_at="2026-11-17T00:00:00Z")
    rejection = Rejection(record_id="future1", reason="future_source")
    trace = RetrievalTrace(prefix_sha256=p.sha256, query_identity=SHA, query_text="moving",
        query_mode="static", acquired_view_sha256=(), bank_version="v0", index_version="i0",
        result=result, rejected=(rejection,), elapsed_ms=0.1, retrieval_identity="bm25-v1")
    history = HistoryItem(record_id="me1", spans=(span,), role="relevant_optional", source_role="seeker", source_rank=0)
    need = NeedCard(prefix_id=p.prefix_id, stratum="history", history_items=(history,),
        failed_or_rejected=(), outdated_facts=(), method_need=None, risk_flags=(),
        writer_identity="fixture-v1", input_sha256=SHA, span_validation_status="pending")
    item = ChecklistItem(item_id="i1", category="H-", constraint_type="hard_factual",
        text="Does not claim the planned move already happened", evidence_spans=(span,),
        weight=1.0, applies_to="all_terminals", visibility_scope="evaluation_only", review_status="unverified")
    checklist = Checklist(prefix_id=p.prefix_id, needcard_sha256=need.sha256, items=(item,), total_weight=1.0, writer_identity="fixture-v1")
    key = TerminalKey.for_prefix(p, domain_id="finite_head_v1", bank_version="v0", index_version="i0",
        ordered_path=("GET_ME", "STOP"), acquired=(("me1",),), renderer_id="r0",
        step2_id="noplan", g_id="G0-candidate", decode_id="greedy-seed0-v1")
    verdict = ItemVerdict(item_id="i1", J1="uncertain", J2="uncertain", final="uncertain")
    pair = PairwiseQuality(comparator_key_sha256=SHA, verdict="uncertain", judge_identity="not_run", qualification_tier="engineering_only")
    execution = ExecutionTrace(domain_id=key.domain_id, ordered_path=key.ordered_path, acquired=key.acquired, readings=(view,))
    terminal = TerminalRecord(key=key, execution=execution, checklist=checklist, checklist_sha256=checklist.sha256, feedback_id="fixture-feedback-v1", request_sha256=SHA, response="", response_sha256=sha256_text(""),
        item_verdicts=(verdict,), gsc_lower=0.0, gsc_upper=1.0, hard_factual="uncertain",
        hard_safety="uncertain", soft_quality_pairwise=(pair,), qualification_tier="engineering_only",
        misuse_flags=(), latency_pred=None, latency_measured=None)
    old = OutdatedFact(old_span=span, new_span=replace(span, source_rank=1))
    human = HumanAdjudication(reviewer_id="fixture-human", record_uri="fixture:adjudication", record_sha256=SHA, response_sha256=sha256_text(""), verdict="uncertain", reason="fixture only")
    success = ReadSuccess(reading=view, record_ids=("me1",), input_tokens_before=10, input_tokens_after=17, native_context_tokens=128, output_reserve_tokens=32, elapsed_ms=1.0)
    failure = ReadFailure(reason="empty", detail="no legal records", input_tokens_unchanged=10, elapsed_ms=0.1)
    return {type(x).__name__: x for x in (time,t,s,span,p,p.visible(),resource,claim,relation,view,
        availability,obs,component,ranked,result,index,rejection,trace,history,need,item,key,verdict,pair,terminal,checklist,execution,old,human,success,failure)}


@pytest.mark.parametrize("cls", CONTRACT_TYPES, ids=lambda c:c.__name__)
def test_positive_roundtrip_and_json_schema(cls):
    example = examples()[cls.__name__]
    wire = canonical_json(example)
    Draft202012Validator.check_schema(json_schema(cls))
    Draft202012Validator(json_schema(cls)).validate(json.loads(wire))
    decoded = decode_contract(cls, wire)
    assert decoded == example
    assert decoded.sha256 == example.sha256
    with pytest.raises(FrozenInstanceError):
        decoded.schema_version = "changed"


NEGATIVES = [
    ("TimePoint", {"date":None, "session_rank":None}),
    ("TimePoint", {"date":"2026-02-30"}),
    ("SourceTurn", {"turn_index":-1}),
    ("SourceTurn", {"role":"system"}),
    ("SourceSession", {"transcript_sha256":"0"*64}),
    ("SourceSession", {"raw_sha256":"bad"}),
    ("SourceSpan", {"start_char":5, "end_char":2}),
    ("SourceSpan", {"exact_quote":"different"}),
    ("PrefixSpec", {"cut_turn":1}),
    ("ResourceRecord", {"owner_id":None}),
    ("ResourceRecord", {"view":"assertion"}),
    ("ResourceRecord", {"epistemic_status":"supporter_suggestion", "stage":"completed"}),
    ("ResourceRecord", {"evidence_status":"semantically_supported"}),
    ("ResourceRecord", {"invalidated_knowledge_rank":2}),
    ("TemporalClaim", {"source_rank":1}),
    ("TemporalRelation", {"semantic_support":"supported"}),
    ("TemporalRelation", {"relation_type":"causes_cure"}),
    ("TemporalRelation", {"direction":"symmetric"}),
    ("ReadingView", {"tokens":True}),
    ("ReadingView", {"stage":None}),
    ("ReadingView", {"record_id":"hidden"}),
    ("HeadAvailability", {"count":0}),
    ("Observation", {"need_card":"hidden"}),
    ("ScoreComponent", {"rank":0}),
    ("RetrievalTrace", {"index_version":"different"}),
    ("NeedCard", {"visibility_scope":"runtime"}),
    ("ChecklistItem", {"weight":0}),
    ("ChecklistItem", {"applies_to":"ON_only"}),
    ("TerminalKey", {"ordered_path":["STOP","GET_ME"]}),
    ("TerminalRecord", {"response_sha256":"0"*64}),
    ("TerminalRecord", {"gsc_lower":0.9,"gsc_upper":0.2}),
    ("TerminalRecord", {"gsc_lower":None}),
    ("TerminalRecord", {"latency_measured":-1}),
]


@pytest.mark.parametrize("name,change", NEGATIVES, ids=[f"{n}-{i}" for i,(n,_) in enumerate(NEGATIVES)])
def test_negative_contracts_fail_closed(name, change):
    original = examples()[name]
    raw = asdict(original)
    raw.update(change)
    with pytest.raises(ValueError):
        decode_contract(type(original), canonical_json(raw))


@pytest.mark.parametrize("cls", CONTRACT_TYPES, ids=lambda c:c.__name__)
def test_every_schema_rejects_private_extra_fields(cls):
    raw = asdict(examples()[cls.__name__]); raw["unread_candidate_text"] = "hidden"
    assert list(Draft202012Validator(json_schema(cls)).iter_errors(raw))


def test_source_span_verification_checks_identity_offsets_role_hash():
    ex = examples(); source = ex["SourceSession"]; span = ex["SourceSpan"]
    span.verify(source)
    for changes in ({"owner_id":"p2"}, {"source_key":"unmapped"}, {"speaker":"supporter"},
                    {"raw_turn_sha256":"0"*64}, {"turn_index":1}, {"source_rank":1},
                    {"exact_quote":"他打算搬家。"}):
        with pytest.raises(ValueError):
            replace(span, **changes).verify(source)


def test_correction_time_is_not_fact_validity_end():
    ex=examples(); r=ex["ResourceRecord"]
    corrected=replace(r, invalid_at=TimePoint(session_rank=3), invalidated_knowledge_rank=3,
                      invalidation_source_refs=(replace(ex["SourceSpan"], source_rank=3),))
    assert corrected.valid_to is None
    future_plan=replace(r, event_time=TimePoint(date="2030-01-01"))
    assert future_plan.stage == "intended" and future_plan.reported_at.date is None


def test_unknown_relationship_is_stored_but_never_claims_support():
    edge=examples()["TemporalRelation"]
    assert edge.semantic_support == "unverified" and not edge.evidence_spans


def test_whitelist_projection_hides_routing_and_labels():
    p=replace(examples()["PrefixSpec"], stratum="history", fold=3, split="test")
    raw=asdict(p.visible())
    assert set(raw) == {"schema_version", "turns", "timestamp"}
    for private in ("owner_id", "session_id", "prefix_id", "family_id", "stratum", "fold", "split"):
        assert private not in canonical_json(p.visible())
    assert "record_id" not in canonical_json(examples()["Observation"])


def test_legacy_prefix_adapter_preserves_cut_and_turns():
    from metacom_pm.rl1.schema import PrefixSpec as Legacy, PublicTurn
    old=Legacy("p1", "s2", 1, 0, "2026-01-01", "train", (PublicTurn("seeker","hello"),))
    new=PrefixSpec.from_legacy(old,dataset="fixture",family_id="f2")
    assert new.cut_turn == old.cut_after_turn_index
    assert new.prefix_id == old.identity and new.turns[0].text == "hello"


@pytest.mark.parametrize("name", [f.name for f in fields(TerminalKey) if f.name != "schema_version"])
def test_every_terminal_key_field_invalidates_cache(name):
    key=examples()["TerminalKey"]
    changes = {"ordered_path":("GET_MP","STOP"), "acquired":(("me2",),), "domain_id":"adaptive_v1", "prefix_id":"1"*64, "prefix_context_sha256":"2"*64}
    changed=replace(key, **{name:changes.get(name, getattr(key,name)+"-changed" if isinstance(getattr(key,name),str) else ())})
    assert changed.sha256 != key.sha256


def test_terminal_schema_version_changes_hash_and_cannot_load_as_current():
    raw=asdict(examples()["TerminalKey"]); old=object_sha256(raw)
    raw["schema_version"]="pmrl1v3-contracts-next"
    assert object_sha256(raw) != old
    with pytest.raises(ValueError): decode_contract(TerminalKey,canonical_json(raw))


def test_canonical_json_preserves_source_unicode_and_refuses_ambiguous_numbers():
    assert canonical_json({"b":1,"a":"é"}) == canonical_json({"a":"é","b":1})
    assert sha256_text("é") != sha256_text("e\u0301")
    for x in (float("nan"),float("inf")):
        with pytest.raises(ValueError): canonical_json({"x":x})
    with pytest.raises(TypeError): canonical_json({1:"coerced key"})
    with pytest.raises(ValueError): parse_json('{"x":1,"x":2}')
    with pytest.raises(ValueError): parse_json('{"x":NaN}')


def test_version_is_mandatory_in_wire_contract():
    raw=asdict(examples()["ReadingView"]); del raw["schema_version"]
    with pytest.raises(ValueError): decode_contract(ReadingView,canonical_json(raw))


def test_manifest_detects_tampering_and_output_resume_is_immutable(tmp_path):
    source=tmp_path/"source.json"; result=tmp_path/"result.json"; code=tmp_path/"code.py"
    write_json_once(source,{"original":True}); write_json_once(result,{"rows":1}); code.write_text("# code\n")
    manifest=build_manifest(task="C0",root=tmp_path,inputs={"source":source},outputs=[result],code=[code],code_sha="base")
    verify_manifest(manifest,root=tmp_path)
    write_json_once(result,{"rows":1})
    with pytest.raises(FileExistsError): write_json_once(result,{"rows":2})
    result.write_text("changed")
    with pytest.raises(ValueError): verify_manifest(manifest,root=tmp_path)


def test_checked_in_schemas_match_contracts():
    root=Path(__file__).resolve().parents[1]/"schemas"/"rl1v3"
    for cls in CONTRACT_TYPES:
        assert json.loads((root/f"{cls.__name__}.schema.json").read_text()) == json_schema(cls)


def test_nested_contract_version_is_required():
    raw=asdict(examples()["ReadingView"]); del raw["reported_at"]["schema_version"]
    with pytest.raises(ValueError): decode_contract(ReadingView,canonical_json(raw))


def test_invalidation_evidence_cannot_come_from_old_or_other_owner_source():
    ex=examples()
    for span in (ex["SourceSpan"], replace(ex["SourceSpan"],owner_id="p2",source_rank=3)):
        with pytest.raises(ValueError):
            replace(ex["ResourceRecord"],invalid_at=TimePoint(session_rank=3),
                    invalidated_knowledge_rank=3,invalidation_source_refs=(span,))
