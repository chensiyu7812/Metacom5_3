import json
from dataclasses import replace
from types import SimpleNamespace

import pytest

from metacom_pm.rl1.evidence import legal_evidence
from metacom_pm.rl1.judge import parse_measurement, messages
from metacom_pm.rl1.schema import PrefixSpec, PublicTurn

EVIDENCE = {"current_date": "2025-01-02", "current_prefix": [
    {"id": "C:T000", "role": "seeker", "text": "I want to talk about my dog."}],
    "legal_past_sessions": []}
REPLY = "You mentioned your dog. What feels hardest?"


def good():
    return dict(status="scored", q=3, m=0,
        q_rationale=dict(current_need="talk", response_quote="What feels hardest?",
            evidence=[dict(source_id="C:T000", quote="my dog")], reason="appropriate invitation"),
        claims=[dict(response_quote="You mentioned your dog.", relation="supported", severity=0,
            evidence=[dict(source_id="C:T000", quote="my dog")], reason="explicit")],
        misuse_findings=[], coverage="all personal assertions checked", uncertainty_reasons=[])


def parse(obj, **kwargs):
    return parse_measurement(json.dumps(obj), evidence=EVIDENCE, reply=REPLY,
        runtime_identity="test-runtime", draw_id="draw-0", finish_reason="natural_stop", **kwargs)


def test_binding_and_exact_source_offsets():
    result = parse(good())
    assert result["measurement_status"] == "measured_candidate"
    assert result["q"] == 3 and result["m"] == 0
    assert result["reward_eligible"] is False
    for span in result["exact_span_checks"]:
        raw = REPLY if span.get("response") else EVIDENCE["current_prefix"][0]["text"]
        for pos in span["positions"]:
            assert raw[pos["start"]:pos["end"]] == span["quote"]
    changed = parse_measurement(json.dumps(good()), evidence=EVIDENCE, reply="Unrelated reply",
        runtime_identity="x", draw_id="y", finish_reason="natural_stop")
    assert changed["q"] is None


@pytest.mark.parametrize("change", [
    lambda o: o.update(q=True), lambda o: o.update(m=False),
    lambda o: o["q_rationale"]["evidence"][0].update(source_id="H999:T000"),
    lambda o: o["q_rationale"]["evidence"][0].update(quote="my cat"),
    lambda o: o["claims"][0].update(severity=1), lambda o: o.update(misuse_findings=[True]),
    lambda o: o.update(m=1), lambda o: o.update(uncertainty_reasons=["unresolved"]),
    lambda o: o.update(status="uncertain"),
])
def test_invalid_records_are_missing_not_zero(change):
    obj = good(); change(obj)
    result = parse(obj)
    assert result["measurement_status"] == "parse_or_evidence_failure"
    assert result["q"] is None and result["m"] is None


def test_no_claims_is_na_not_perfect_factual_precision():
    obj = good(); obj["claims"] = []
    result = parse(obj)
    assert result["measurement_status"] == "measured_candidate"
    assert result["factual_precision"] is None


def test_duplicate_json_and_extra_conclusions_rejected():
    raw = json.dumps(good())
    for value in [raw[:-1] + ', "q": 4}', raw + '\n' + raw]:
        result = parse_measurement(value, evidence=EVIDENCE, reply=REPLY,
            runtime_identity="r", draw_id="d", finish_reason="natural_stop")
        assert result["q"] is None


def test_closed_thinking_fence_and_long_reason_are_preserved():
    obj = good(); obj["q_rationale"]["reason"] = "reason " * 200
    result = parse_measurement('Reasoning here</think>\n```json\n' + json.dumps(obj) + '\n```',
        evidence=EVIDENCE, reply=REPLY, runtime_identity="r", draw_id="d", finish_reason="natural_stop")
    assert result["parsed"] == obj
    assert len(result["format_transformations"]) == 2


def test_technical_failure_and_semantic_uncertainty_remain_distinct():
    obj = good(); obj.update(status="uncertain", q=None, m=None, uncertainty_reasons=["ambiguous"])
    assert parse(obj)["measurement_status"] == "semantic_uncertainty"
    result = parse_measurement(json.dumps(good()), evidence=EVIDENCE, reply=REPLY,
        runtime_identity="r", draw_id="d", finish_reason="technical_timeout")
    assert result["measurement_status"] == "technical_failure" and result["q"] is None


def test_cut_evidence_excludes_current_suffix_and_future():
    def session(sid, rank, texts):
        return SimpleNamespace(session_id=sid, chronological_rank=rank, timestamp=f"2025-01-0{rank+1}",
            turns=tuple(SimpleNamespace(role=r, content=t) for r, t in texts))
    sessions = [session("past", 0, [("seeker", "past fact")]),
                session("now", 1, [("seeker", "visible"), ("supporter", "hidden response"), ("seeker", "hidden suffix")]),
                session("future", 2, [("seeker", "future fact")])]
    user = SimpleNamespace(owner_id="p1", sessions=sessions, session_by_id=lambda x: next(s for s in sessions if s.session_id == x))
    prefix = PrefixSpec("p1", "now", 1, 0, "2025-01-02", "train", (PublicTurn("seeker", "visible"),))
    evidence, private = legal_evidence(prefix, user)
    visible = json.dumps(messages(evidence, "Reply"))
    assert "past fact" in visible and "visible" in visible
    assert all(s not in visible for s in ("hidden response", "hidden suffix", "future fact", '"owner_id"', '"resource_budget"'))
    with pytest.raises(ValueError):
        legal_evidence(replace(prefix, turns=(PublicTurn("seeker", "forged"),)), user)
    with pytest.raises(ValueError):
        legal_evidence(replace(prefix, owner_id="p2"), user)


def test_independent_intake_preserves_missing_and_reviewer_provenance():
    from copy import deepcopy
    from metacom_pm.rl1.review import validate_submission
    exam={'items':[{'item_id':'one'}]}
    raw=dict(protocol='pm-rl1-independent-review-v1',source_sha256='bound',reviewer_identity='test model',
        reviewer_kind='model',reviewer_details='test version',items=[dict(item_id='one',q_A='',m_A='uncertain',
        q_B='2',m_B='0',pairwise='uncertain',evidence='source pending',uncertainty='cannot establish fact')])
    result=validate_submission(raw,exam=exam,source_sha256='bound')
    assert result['reviewer_kind']=='model' and result['rows'][0]['q_A'] is None and result['rows'][0]['m_A'] is None
    assert result['rows'][0]['m_B']==0 and result['complete_items']==0 and not result['training_feedback_allowed']
    for edit in [lambda r:r.update(source_sha256='tampered'),lambda r:r['items'].append(r['items'][0]),
                 lambda r:r['items'][0].update(m_A='0.5'),lambda r:r.update(reviewer_details='')]:
        changed=deepcopy(raw);edit(changed)
        with pytest.raises(ValueError):validate_submission(changed,exam=exam,source_sha256='bound')


def test_source_scoped_cache_separates_equal_prompts_but_not_acquisition_order():
    from dataclasses import asdict, replace
    from metacom_pm.rl1.bound_generation import BoundResourceEnv, validate_and_project
    from metacom_pm.rl1.schema import EpisodeSpec, Resource, HEADS
    from metacom_pm.rl1.render import Renderer
    prefix=PrefixSpec('owner','session',2,0,'2025-01-02','train',(PublicTurn('seeker','same visible turn'),))
    inventory=tuple((Resource(h,h,'resource '+h,.8,10,None if h=='RS' else 'owner',
        None if h=='RS' else 0,None if h=='RS' else '2025-01-01','past',('source',)),) for h in HEADS)
    spec=EpisodeSpec(prefix,inventory,'retrieve','runtime','judge','draw',10000)
    renderer=Renderer(count_text=len,count_chat=lambda m:len(json.dumps(m)),tokenizer_identity='counter',context_limit=100000)
    def stopped(s,actions=()):
        env=BoundResourceEnv(s,renderer)
        for a in (*actions,0):env.step(a,expected_state_hash=env.state_hash)
        return env
    first=stopped(spec);same_prompt=stopped(replace(spec,prefix=replace(prefix,session_id='other')))
    a,b=first.generation_request(),same_prompt.generation_request()
    assert a['messages']==b['messages'] and a['request_id']!=b['request_id']
    inventory2=list(inventory);inventory2[0]=(replace(inventory[0][0],source_ids=('other-source',)),)
    assert stopped(replace(spec,inventory=tuple(inventory2))).generation_request()['request_id']!=a['request_id']
    assert stopped(spec,(1,2)).generation_request()==stopped(spec,(2,1)).generation_request()
    projected=validate_and_project(a,'runtime')
    assert 'provenance' not in projected and 'owner' not in json.dumps(asdict(first.observe()))
    tampered=json.loads(json.dumps(a));tampered['provenance']['prefix_identity']='forged'
    with pytest.raises(ValueError):validate_and_project(tampered,'runtime')
    restored=BoundResourceEnv.restore(spec,renderer,first.snapshot())
    assert restored.snapshot()==first.snapshot()


def test_quote_normalization_is_typography_only_and_keeps_original_hash():
    from copy import deepcopy
    from hashlib import sha256
    from metacom_pm.rl1.quote_normalization import matching_original,parse_typographic_view
    assert matching_original('I am sure',"I am not sure") is None
    assert matching_original('I have a dog','I have a cat') is None
    assert matching_original("I'm\nnot sure",'I’m  not sure')=='I’m  not sure'
    assert matching_original("I'm sure",'I’m sure. I\'m sure.')=="I'm sure"  # exact match needs no normalization
    obj=good();obj['q_rationale']['response_quote']='What\nfeels hardest?'
    raw=json.dumps(obj)
    bindings=dict(evidence=EVIDENCE,reply=REPLY,runtime_identity='r',draw_id='d',finish_reason='natural_stop')
    result=parse_typographic_view(raw,**bindings)
    assert result['strict_parser_status']=='parse_or_evidence_failure' and result['measurement_status']=='measured_candidate'
    assert result['raw_output_sha256']==sha256(raw.encode()).hexdigest()
    assert result['quote_transformations'][0]['matched_original']=='What feels hardest?'
    bad=deepcopy(obj);bad['q_rationale']['evidence'][0]['source_id']='FUTURE:T000'
    assert parse_typographic_view(json.dumps(bad),**bindings)['q'] is None
    duplicate=raw[:-1]+',"q":4}'
    assert parse_typographic_view(duplicate,**bindings)['q'] is None


def test_prepared_indexed_contract_resolves_ids_without_inventing_semantics():
    from copy import deepcopy
    from metacom_pm.rl1.judge_indexed import response_units,parse_indexed,messages_and_schema
    units=response_units(REPLY)
    assert all(REPLY[u['start']:u['end']]==u['text'] for u in units)
    obj=dict(status='scored',q=3,m=0,q_rationale=dict(current_need='talk',response_unit_ids=['R002'],
        source_turn_ids=['C:T000'],reason='invites discussion'),claims=[dict(response_unit_id='R001',relation='supported',
        severity=0,source_turn_ids=['C:T000'],reason='seeker stated it')],misuse_findings=[],coverage='all claims',uncertainty_reasons=[])
    bindings=dict(evidence=EVIDENCE,reply=REPLY,runtime_identity='r',draw_id='d',finish_reason='natural_stop')
    result=parse_indexed(json.dumps(obj),**bindings)
    assert result['q']==3 and result['parsed']['claims'][0]['evidence'][0]['quote']==EVIDENCE['current_prefix'][0]['text']
    assert not result['reward_eligible'] and not result['semantic_validation']
    for field,invalid in [('source_turn_ids',['H999:T000']),('response_unit_ids',['R999'])]:
        changed=deepcopy(obj);changed['q_rationale'][field]=invalid
        assert parse_indexed(json.dumps(changed),**bindings)['q'] is None
    changed=deepcopy(obj);changed['m']=1
    assert parse_indexed(json.dumps(changed),**bindings)['q'] is None
