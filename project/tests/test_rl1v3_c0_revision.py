"""Behavioural regression for R1-R6/N1-N7; no model execution or expected failures."""
from dataclasses import asdict, replace
from itertools import permutations
import gzip
import json
from pathlib import Path

import pytest
from pydantic import TypeAdapter

from metacom_pm.rl1v3 import contracts as K, io as IO
from test_rl1v3_contracts import examples


def test_all_65_real_paths_map_to_exactly_16_finite_terminals_and_preserve_order():
    base = examples()["TerminalKey"]
    identities = set()
    traces = set()
    for n in range(5):
        for heads in permutations(K.HEAD_ORDER, n):
            path = tuple("GET_" + h for h in heads) + ("STOP",)
            groups = tuple((h + "-record",) for h in heads)
            views = tuple(K.ReadingView(head=h, view={"RS":"method", "MP":"assertion", "ME":"event", "MS":"sum"}[h],
                ordinal=i+1, reading_text=h, reported_at=None, tokens=1,
                stage="unknown" if h == "ME" else None) for i,h in enumerate(heads))
            trace = K.ExecutionTrace(domain_id=base.domain_id, ordered_path=path, acquired=groups, readings=views)
            key = replace(base, ordered_path=path, acquired=groups)
            trace.verify_key(key)
            assert trace.ordered_path == path
            identities.add(key.sha256); traces.add(trace.sha256)
    assert len(identities) == 16
    assert len(traces) == 65


def test_adaptive_identity_keeps_order_and_isolated_from_finite():
    base=examples()["TerminalKey"]
    a=replace(base,domain_id="adaptive_v1",ordered_path=("GET_MP","GET_ME","STOP"), acquired=(("mp",),("me",)))
    b=replace(a,ordered_path=("GET_ME","GET_MP","STOP"),acquired=(("me",),("mp",)))
    assert len({a.sha256,b.sha256,replace(a,domain_id="finite_head_v1").sha256}) == 3


@pytest.mark.parametrize("path,groups", [
    (("GET_ME","STOP"),()), (("GET_ME","STOP"),((),)),
    (("GET_MP","GET_ME","STOP"),(("a","b"),)),
    (("GET_MP","GET_ME","STOP"),(("a",),("a",))),
    (("GET_ME","GET_ME","STOP"),(("a",),("b",))),
    (("GET_MS","EXPAND_MS(1)","STOP"),(("s",),("raw",)))])
def test_each_finite_get_has_its_own_unique_nonempty_group(path,groups):
    with pytest.raises(ValueError): replace(examples()["TerminalKey"],ordered_path=path,acquired=groups)


def test_multirecord_delivery_group_is_not_flattened():
    base=examples()["TerminalKey"]
    a=replace(base,ordered_path=("GET_MP","GET_ME","STOP"),acquired=(("a","b"),("c",)))
    b=replace(a,acquired=(("a",),("b","c")))
    assert a.sha256 != b.sha256
    assert IO.decode_contract(K.TerminalKey, IO.canonical_json(a)).acquired == (("a","b"),("c",))


def adaptive_observation():
    return K.Observation(domain_id="adaptive_v1", history_sessions=2, prefix=examples()["PrefixSpec"].visible(),
        acquired=(K.ReadingView(head="MS", view="sum", expandable=True,ordinal=1,reading_text="summary",reported_at=None,tokens=2),),
        availability=(K.HeadAvailability(head="MS",available=True,count=7),),action_mask=("STOP","EXPAND_MS(1)"),input_tokens=20)


@pytest.mark.parametrize("action",["EXPAND_MS","EXPAND_MS(0)","EXPAND_MS(2)","EXPAND_MS(-1)","EXPAND_MS(01)"])
def test_expand_mask_rejects_ambiguous_or_unavailable_ordinals(action):
    with pytest.raises(ValueError): replace(adaptive_observation(),action_mask=("STOP",action))


def test_expansion_trace_and_budget_observation():
    obs=adaptive_observation(); summary=obs.acquired[0]
    raw=K.ReadingView(head="MS",view="raw",ordinal=2,expanded_from_ordinal=1,reading_text="source text",reported_at=None,tokens=3)
    trace=K.ExecutionTrace(domain_id="adaptive_v1",ordered_path=("GET_MS","EXPAND_MS(1)","STOP"), acquired=(("sum1",),("raw1",)),readings=(summary,raw))
    assert IO.decode_contract(K.ExecutionTrace,IO.canonical_json(trace)) == trace
    replace(obs,acquired=(summary,raw),action_mask=("STOP","GET_MS"))
    with pytest.raises(ValueError): replace(obs,acquired=(summary,raw))  # cannot expand twice
    with pytest.raises(ValueError): replace(obs,domain_id="finite_head_v1")
    with pytest.raises(ValueError): replace(trace,readings=(replace(summary,expandable=False),raw))
    with pytest.raises(ValueError): replace(trace,readings=(summary,replace(raw,expanded_from_ordinal=None)))


def test_empty_pool_masks_get_and_count_is_not_delivery_count():
    obs=adaptive_observation()
    with pytest.raises(ValueError): replace(obs,availability=(K.HeadAvailability(head="MS",available=False,count=0),),action_mask=("STOP","GET_MS"))
    assert obs.availability[0].count == 7 and len(obs.acquired) == 1
    assert "delivery_tokens" not in asdict(obs)


def test_checklist_is_bound_once_per_prefix_across_all_16_subsets(tmp_path):
    ex=examples(); checklist=ex["Checklist"]; need=ex["NeedCard"]
    for n in range(16):
        IO.bind_checklist(tmp_path,checklist,need)
        assert IO.load_checklist(tmp_path,checklist.prefix_id) == checklist
    assert len(list(tmp_path.iterdir())) == 1
    other=replace(checklist,items=(replace(checklist.items[0],weight=2.0),),total_weight=2.0)
    with pytest.raises(FileExistsError): IO.bind_checklist(tmp_path,other,need)
    with pytest.raises(ValueError): replace(checklist,total_weight=2.0)
    with pytest.raises(ValueError): replace(checklist,items=checklist.items*2,total_weight=2.0)
    with pytest.raises(ValueError): IO.bind_checklist(tmp_path,checklist,replace(need,writer_identity="another"))


def test_feedback_identity_changes_score_record_but_not_response_key():
    record=examples()["TerminalRecord"]
    other=replace(record,feedback_id="new-judge-prompt-parser-aggregation")
    assert record.sha256 != other.sha256 and record.key.sha256 == other.key.sha256
    with pytest.raises(ValueError): replace(record,checklist_sha256="0"*64)
    with pytest.raises(ValueError): replace(record,checklist=replace(record.checklist,prefix_id="0"*64))


@pytest.mark.parametrize("j1,j2",[("pass","fail"),("fail","pass"),("pass","uncertain"),("uncertain","pass")])
def test_disagreement_requires_uncertain_or_explicit_bound_human(j1,j2):
    v=K.ItemVerdict(item_id="i1",J1=j1,J2=j2,final="uncertain")
    with pytest.raises(ValueError): replace(v,final="pass")
    human=replace(examples()["HumanAdjudication"],verdict="pass")
    approved=replace(v,final="pass",human_adjudication=human)
    record=examples()["TerminalRecord"]
    replace(record,item_verdicts=(approved,),gsc_lower=1.0,gsc_upper=1.0)
    with pytest.raises(ValueError): replace(record,item_verdicts=(replace(approved,human_adjudication=replace(human,response_sha256="0"*64)),),gsc_lower=1.0,gsc_upper=1.0)


def test_pending_j2_differs_from_uncertain_and_cannot_receive_zero_score():
    r=examples()["TerminalRecord"]; v=replace(r.item_verdicts[0],J2=None)
    pending=replace(r,item_verdicts=(v,),gsc_lower=None,gsc_upper=None)
    assert K.gsc_interval(r.checklist,(v,)) == (None,None)
    assert K.gsc_interval(r.checklist,r.item_verdicts) == (0.0,1.0)
    with pytest.raises(ValueError): replace(pending,gsc_lower=0.0,gsc_upper=0.0)
    with pytest.raises(ValueError): replace(pending,qualification_tier="research_qualified",evidence_validation="verified")


@pytest.mark.parametrize("field",["hard_factual","hard_safety"])
@pytest.mark.parametrize("state",[None,"uncertain","pass","fail"])
def test_four_hard_constraint_states_roundtrip(field,state):
    r=replace(examples()["TerminalRecord"],**{field:state})
    assert getattr(IO.decode_contract(K.TerminalRecord,IO.canonical_json(r)),field) == state
    if state is None:
        with pytest.raises(ValueError): replace(r,qualification_tier="research_qualified",evidence_validation="verified")


def test_verdict_quotes_and_spans_are_checked_against_legal_sources():
    ex=examples(); span=ex["SourceSpan"]; source=ex["SourceSession"]; prefix=ex["PrefixSpec"]
    v=K.ItemVerdict(item_id="i1",J1="pass",J2=None,final="pass",J1_quote="planning",J1_source_span=span)
    v.verify_evidence("still planning",prefix,(source,))
    with pytest.raises(ValueError): v.verify_evidence("already done",prefix,(source,))
    with pytest.raises(ValueError): replace(v,J1=None)
    with pytest.raises(ValueError): replace(v,J1_source_span=replace(span,source_rank=2)).verify_evidence("planning",prefix,(replace(source,chronological_rank=2),))
    with pytest.raises(ValueError): replace(v,J1_source_span=replace(span,owner_id="p2",source_key="fixture:p2:s1:0")).verify_evidence("planning",prefix,(replace(source,owner_id="p2"),))


def test_fixed_denominator_retains_failed_and_uncertain_items():
    ex=examples(); i=ex["ChecklistItem"]
    checklist=replace(ex["Checklist"],items=(i,replace(i,item_id="i2",weight=2.0),replace(i,item_id="i3",weight=3.0)),total_weight=6.0)
    verdicts=tuple(K.ItemVerdict(item_id="i"+str(n),J1=v,J2=v,final=v) for n,v in enumerate(("pass","fail","uncertain"),1))
    assert K.gsc_interval(checklist,verdicts) == (1/6,4/6)
    with pytest.raises(ValueError): K.gsc_interval(checklist,verdicts[:1])


def test_prefix_identity_ignores_split_but_runtime_identity_binds_time_and_family():
    p=examples()["PrefixSpec"]
    assert replace(p,split="test",fold=9,stratum="both").runtime_sha256 == p.runtime_sha256
    for change in ({"timestamp":"2026-01-01"},{"ancestor_family_ids":("f1","f2","new")},{"cutoff_rank":2}):
        other=replace(p,**change)
        assert other.prefix_id == p.prefix_id and other.runtime_sha256 != p.runtime_sha256
    with pytest.raises(ValueError): replace(p,owner_id="p2")
    with pytest.raises(ValueError): replace(p,ancestor_family_ids=("f1",))
    with pytest.raises(ValueError): replace(p,prefix_id="0"*64)


def test_family_closure_must_cover_all_strict_past_and_no_future():
    ex=examples(); p=ex["PrefixSpec"]; old=ex["SourceSession"]
    turns=p.turns+(K.SourceTurn(turn_index=1,role="supporter",text="response"),)
    current=replace(old,session_id=p.session_id,chronological_rank=1,turns=turns,family_id="f2",transcript_sha256=IO.object_sha256([(t.role,t.text) for t in turns]))
    p.verify_source_context(current,(old,))
    for history in ((),(replace(old,owner_id="p2"),),(old,old)):
        with pytest.raises(ValueError): p.verify_source_context(current,history)
    for families in (("f2",),("f1","f2","future")):
        with pytest.raises(ValueError): replace(p,ancestor_family_ids=families).verify_source_context(current,(old,))


def test_typed_read_failure_cannot_produce_ordinal_or_generator_input():
    success=examples()["ReadSuccess"]; failed=examples()["ReadFailure"]
    for x in (success,failed):
        assert IO.decode_contract(K.ReadResult,IO.canonical_json(x)) == x
    assert not {"reading","ordinal","record_ids"} & set(asdict(failed))
    for change in ({"input_tokens_after":100,"native_context_tokens":101}, {"record_ids":()}, {"input_tokens_after":10}):
        with pytest.raises(ValueError): replace(success,**change)
    raw=asdict(failed); raw["ordinal"]=2
    with pytest.raises(ValueError): IO.decode_contract(K.ReadResult,IO.canonical_json(raw))


def test_packed_candidate_tokens_remain_private_and_bind_delivered_ids():
    r=examples()["RetrievalResult"]
    replace(r,delivery_record_ids=("me1",),delivery_tokens=10)
    for change in ({"delivery_record_ids":("me1",)}, {"delivery_tokens":10}, {"delivery_record_ids":("other",),"delivery_tokens":10}):
        with pytest.raises(ValueError): replace(r,**change)


def test_pinned_b0_reference_is_byte_identical_to_b_branch():
    root=Path(__file__).parents[2]; fixture=Path(__file__).parent/"fixtures/rl1v3/wsb"
    manifest=json.loads((fixture/"PROVENANCE.json").read_text())
    for row in manifest["files"]:
        path=root/row["destination"]
        # Review inputs live in result manifest, while CI needs only portable fixtures.
        if "fixtures/" not in row["destination"]: continue
        assert IO.file_sha256(path) == row["stored_sha256"]
        payload=gzip.decompress(path.read_bytes()) if path.suffix == ".gz" else path.read_bytes()
        assert IO.sha256_bytes(payload) == row["source_sha256"]


def test_public_remaining_budget_and_union_schema():
    from jsonschema import Draft202012Validator
    obs=adaptive_observation()
    assert obs.remaining_gets == 4
    assert examples()["Observation"].remaining_gets == 3
    schema=K.json_schema(K.ReadResult)
    path=Path(__file__).parents[1]/"schemas/rl1v3/ReadResult.schema.json"
    assert json.loads(path.read_text()) == schema
    for name in ("ReadSuccess","ReadFailure"):
        Draft202012Validator(schema).validate(json.loads(IO.canonical_json(examples()[name])))


def test_concurrent_checklist_publication_is_atomic(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    ex=examples()
    def publish(_):
        IO.bind_checklist(tmp_path,ex["Checklist"],ex["NeedCard"])
        return IO.load_checklist(tmp_path,ex["Checklist"].prefix_id).sha256
    with ThreadPoolExecutor(max_workers=8) as pool:
        assert set(pool.map(publish,range(32))) == {ex["Checklist"].sha256}
