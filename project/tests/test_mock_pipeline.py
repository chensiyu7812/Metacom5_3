from __future__ import annotations

import json,re
from pathlib import Path

from metacom_pm.api import CallResult,Endpoint
from metacom_pm.contracts import (
    MemoryOmissionJudgment,MemoryOpportunityItem,MemoryOpportunityJudgment,
    MemorySource,MemoryUseJudgment,ResponsePairJudgment,SourceUseAssessment,
    StrategyUseJudgment,StrategyOmissionJudgment,
)
from metacom_pm.io import iter_jsonl,read_json,write_json
from metacom_pm.sweep import run_action_sweep
from metacom_pm.judging import run_judging
from metacom_pm.pilot_analysis import analyze_judge_pilot

ROOT=Path(__file__).resolve().parents[1]

class FakeClient:
    def __init__(self,endpoint): self.endpoint=endpoint
    def close(self): pass
    def chat(self,messages,*,response_schema=None,**kwargs):
        content='\n'.join(x['content'] for x in messages)
        result=CallResult(text='A calm supportive response.',raw_response={'mock':True},usage={'prompt_tokens':10,'completion_tokens':5,'total_tokens':15},latency_ms=1.0,request_hash='mock')
        if response_schema is None: return result,None
        if response_schema is ResponsePairJudgment:
            lower=content.lower()
            # Pull response fields when the prompt uses JSON.
            try:
                obj=json.loads(messages[-1]['content']);a=obj.get('response_A','');b=obj.get('response_B','')
            except Exception: a=b=''
            if a==b: pref='tie'
            elif 'work harder' in a.lower() or 'calm down' in a.lower() or 'breakup last september' in a.lower(): pref='B'
            elif 'work harder' in b.lower() or 'calm down' in b.lower() or 'breakup last september' in b.lower(): pref='A'
            else: pref='tie'
            parsed=ResponsePairJudgment(preference=pref,empathy=pref,contextual_fit=pref,guidance_fit=pref,non_intrusiveness=pref,coherence=pref,reason='mock consistent judgment')
        elif response_schema is MemoryOpportunityJudgment:
            ids=sorted(set(re.findall(r'mem_[0-9a-f]{12,64}',content)))
            parsed=MemoryOpportunityJudgment(items=[MemoryOpportunityItem(memory_id=x,current_relevance=1,potential_helpfulness=1,stale=False,conflicts_with_newer_information=False,intrusive_if_mentioned=False) for x in ids],reason='mock opportunity')
        elif response_schema is MemoryUseJudgment:
            sources=[]
            for src in ('MP','MS','ME'):
                if re.search(rf'"source"\s*:\s*"{src}"',content): sources.append(MemorySource(src))
            unsupported=1 if 'always freeze' in content.lower() else 0
            utilization=1 if ('previous project update' in content.lower() or sources) else 0
            parsed=MemoryUseJudgment(source_assessments=[SourceUseAssessment(source=s,utilization=utilization,unused_retrieval=0,unnecessary_exposure=0,stale_or_conflicting_use=0,unsupported_personal_claim=unsupported) for s in sources],overall_source_set_appropriateness=2,reason='mock use')
        elif response_schema is MemoryOmissionJudgment:
            missed=2 if ('five steps' in content.lower() or 'usually works for me' in content.lower()) else 0
            parsed=MemoryOmissionJudgment(omission_appropriateness=0 if missed else 2,missed_memory_opportunity_severity=missed,unsupported_personal_claim=0,reason='mock omission')
        elif response_schema is StrategyUseJudgment:
            premature=2 if ('spreadsheet' in content.lower() or 'six steps' in content.lower()) else 0
            parsed=StrategyUseJudgment(strategy_relevance=2,strategy_utilization=2,over_structuring=premature,premature_advice=premature,reason='mock strategy')
        elif response_schema is StrategyOmissionJudgment:
            missed=0 if 'calm supportive response' in content.lower() else 1
            parsed=StrategyOmissionJudgment(strategy_omission_appropriateness=2-missed,missed_strategy_opportunity_severity=missed,premature_or_overstructured_without_strategy=0,reason='mock strategy omission')
        else: raise AssertionError(response_schema)
        result.text=parsed.model_dump_json()
        return result,parsed

def test_mock_sweep_judge_gate(tmp_path,monkeypatch):
    import metacom_pm.sweep as sweep_mod,metacom_pm.judging as judge_mod
    monkeypatch.setattr(sweep_mod,'OpenAICompatibleClient',FakeClient)
    monkeypatch.setattr(judge_mod,'OpenAICompatibleClient',FakeClient)
    ep=Endpoint('http://mock','mock','MOCK_KEY')
    monkeypatch.setenv('MOCK_KEY','x')
    sweep=tmp_path/'sweep';sweep.mkdir()
    run_action_sweep(ROOT/'data/synthetic/runtime_states.jsonl',ROOT/'data/synthetic/memory_backend.jsonl',ROOT/'data/strategy/strategy_cards.jsonl',sweep/'action_outcomes.jsonl',sweep/'raw.jsonl',sweep/'summary.json',endpoint=ep,max_cards=3)
    pilot=tmp_path/'pilot'
    run_judging(ROOT/'data/synthetic/runtime_states.jsonl',ROOT/'data/synthetic/memory_backend.jsonl',sweep/'action_outcomes.jsonl',ROOT/'data/synthetic/pair_graph.jsonl',pilot,endpoint=ep,mode='pilot',max_cards=3)
    gate=analyze_judge_pilot(pilot,ROOT/'data/synthetic/pair_graph_audit.json',pilot/'gate.json',min_repeat_consistency=0.0,min_dual_order_agreement=0.0,_diagnostic_min_reversal_consistency=0.0,_diagnostic_max_position_bias=1.0)
    assert gate['checks']['judging_complete']
    assert gate['checks']['m1_complete'] and gate['checks']['m0_complete'] and gate['checks']['m2_complete'] and gate['checks']['strategy_complete']
