from dataclasses import replace
import pytest

from metacom_pm.rl1.schema import PrefixSpec, PublicTurn, Resource, EpisodeSpec, digest
from metacom_pm.rl1.temporal_evidence_ledger import SourceTurn, TemporalEvidenceLedger
from metacom_pm.rl1.resource_opportunity import capacity, candidate_capacity, measured_contrasts, dominated_same_input
from metacom_pm.rl1.env import ResourceEnv
from metacom_pm.rl1.render import Renderer


def prefix():
    return PrefixSpec("u", "now", 2, 0, "2026-01-03", "train", (PublicTurn("seeker", "mother talk?"),))


def ledger():
    return TemporalEvidenceLedger(prefix(), [SourceTurn("u","old",1,0,"seeker","I intend to talk. 妈妈", "2026-01-02")],
                                  provenance_identity="fixture")


@pytest.mark.parametrize("change",[
    dict(owner_id="other"),dict(session_rank=2),dict(reported_at="2026-01-04"),
    dict(session_id="now",session_rank=2,turn_index=1),dict(speaker="assistant"),dict(turn_index=-1)])
def test_source_scope_fails_closed(change):
    source=SourceTurn("u","old",1,0,"seeker","x","2026-01-02")
    with pytest.raises(ValueError):
        TemporalEvidenceLedger(prefix(),[replace(source,**change)],provenance_identity="x")


def test_test_prefix_and_future_current_suffix_rejected():
    with pytest.raises(ValueError):
        TemporalEvidenceLedger(replace(prefix(),split="test"),[],provenance_identity="x")
    with pytest.raises(ValueError):
        TemporalEvidenceLedger(prefix(),[SourceTurn("u","now",2,0,"seeker","future answer","2026-01-03")],provenance_identity="x")


def test_unicode_offsets_exact_quotes_and_tamper():
    l=ledger()
    text="I intend to talk. 妈妈"
    span=l.span("u/old:0",len(text)-2,len(text),"妈妈")
    assert span["speaker"]=="seeker"
    with pytest.raises(ValueError):l.span("u/old:0",0,2,"妈妈")
    with pytest.raises(ValueError):l.span("u/old:0",True,2," ")
    bad={**span,"speaker":"supporter"}
    with pytest.raises(ValueError):
        l.add_claim(candidate_id="c",head="ME",statement="mother",spans=[bad],input_source_keys=["u/old:0"],
                    derivation_method="fixture",derivation_identity="fixture")


def test_lookup_is_index_not_bge_score_and_no_implicit_truth():
    l=ledger()
    hit=l.lookup("talk")[0]
    assert hit["bge_similarity"] is None and hit["actor_visible"] is False
    assert l.lookup("completed")==[]
    value=l.export()
    assert value["unknown_is_not_false"] and value["session_directory"][0]["summary"] is None
    assert value["identity"]==digest({k:v for k,v in value.items() if k!="identity"})


def test_blinded_position_not_assumed_to_be_original_turn_idx():
    l=ledger()
    span=l.locate_quote("old","seeker",0,17,"I intend to talk.")
    assert span["source_key"]=="u/old:0"
    # Ambiguous occurrences cannot silently choose the first or idx-minus-one.
    t=SourceTurn("u","old",1,0,"seeker","same", "2026-01-02")
    repeated=TemporalEvidenceLedger(prefix(),[t,replace(t,turn_index=1)],provenance_identity="fixture")
    with pytest.raises(ValueError):repeated.locate_quote("old","seeker",0,4,"same")


def test_complete_declared_dependencies_not_just_citations():
    l=ledger()
    s=l.span("u/old:0",0,17,"I intend to talk.")
    kwargs=dict(candidate_id="c",head="ME",statement="intends talk",spans=[s],
                derivation_method="fixture",derivation_identity="fixture")
    with pytest.raises(ValueError):l.add_claim(**kwargs,input_source_keys=["u/old:0","u/future:0"])
    cid=l.add_claim(**kwargs,input_source_keys=["u/old:0"],stage="intention")
    record=l.export()["claims"][cid]
    assert record["outcome"] is None and record["semantic_support"]=="unverified"
    assert record["training_label"] is False
    other=l.add_claim(**{**kwargs,"candidate_id":"d"},input_source_keys=["u/old:0"])
    with pytest.raises(ValueError):
        l.add_relation(kind="updates",left=cid,right=other,spans=[s],input_source_keys=["u/future:0"],
                       derivation_method="fixture",derivation_identity="x")
    rid=l.add_relation(kind="updates",left=cid,right=other,spans=[s],input_source_keys=["u/old:0"],
                       derivation_method="fixture",derivation_identity="x")
    assert l.export()["relations"][rid]["effect"]=="index_only_no_automatic_supersession"
    # Caller mutation cannot poison the index identity or its cached evidence.
    exported=l.export();exported["claims"][cid]["spans"][0]["exact_quote"]="changed"
    assert l.export()["claims"][cid]["spans"][0]["exact_quote"]=="I intend to talk."


def spec():
    return EpisodeSpec(prefix(),((Resource("r1","RS","one",.9,1,None,None,None,"na",("s",)),
                                   Resource("r2","RS","two",.8,1,None,None,None,"na",("t",))),(),(),()),
                       "retrieval","G","J","draw")


def test_capacity_respects_blocking_predecessor_and_matches_environment():
    class NonMonotone(Renderer):
        def cost(self,s,counts):return [0,3000,10][counts[0]]
        def fits(self,s,counts):return self.cost(s,counts)<=s.resource_budget
    r=NonMonotone(count_text=len,count_chat=lambda m:1,tokenizer_identity="test",context_limit=9000)
    s=spec();rows=capacity(s,r)
    assert tuple(x["reachable"] for x in rows)==ResourceEnv(s,r).observe().initial_plan_mask
    # rank2's endpoint fits but cannot jump over rank1.
    two=next(x for x in rows if x["counts"]==[2,0,0,0])
    assert two["fits"] and not two["reachable"]


def terminal(rid,counts,tokens,text="same",g="G",e="source"):
    return dict(request_id=rid,prefix_identity="p",executor_identity=g,renderer_identity="R",
                evidence_identity=e,response_identity=digest(text),counts=counts,resource_tokens=tokens,split="train")


def test_content_dominance_preserves_scope_and_missing_rewards():
    rows=[terminal("a",[0,0,0,0],0),terminal("b",[1,0,0,0],200),
          terminal("otherG",[0,1,0,0],300,g="other"),terminal("otherEvidence",[0,0,1,0],400,e="different")]
    dominated=dominated_same_input(rows)
    assert [r["request_id"] for r in dominated]==["b"]
    assert dominated[0]["assigned_q"] is None


def test_multi_head_changes_not_misattributed_to_one_candidate():
    rows=[terminal("off",[0,0,0,0],0),terminal("two",[1,1,0,0],100)]
    assert measured_contrasts(rows)==[]
    rows.append(terminal("one",[1,0,0,0],60))
    result=measured_contrasts(rows)
    assert {(r["head"],r["rank"]) for r in result}=={("RS",1),("MP",1)}
    assert all(r["quality_effect"] is None for r in result)
    with pytest.raises(ValueError):measured_contrasts(rows+[rows[0]])
