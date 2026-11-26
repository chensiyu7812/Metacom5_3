#!/usr/bin/env python3
"""Actual sources/native-tokenizer GE2 transport fixture; NEVER a model result.

Every fixture completion is explicitly synthetic transport text, not an answer
or judge. Loads no weights, touches no CUDA and writes only a new private path.
"""
import argparse
import json
import os
from pathlib import Path

os.environ['CUDA_VISIBLE_DEVICES']=''
os.environ['PYTHONDONTWRITEBYTECODE']='1'

from metacom_pm.rl1v3.io import object_sha256, file_sha256, write_json_once, write_jsonl_once
from metacom_pm.rl1v3.journal.ge2_factory import GE2Factory, DirectProvider
from metacom_pm.rl1v3.journal.ge2_retrieval import RetrievalConfig
from metacom_pm.rl1v3.journal.ge2_runtime import execute, terminal_slots
from metacom_pm.rl1v3.journal.ge2_worker import validate_generate_request, WorkerCallBudget
from metacom_pm.rl1v3.journal.pomdp_dynamic_run import read, rows
from metacom_pm.rl1v3.journal.pomdp_latency import MonotonicClock
from metacom_pm.rl1v3.retrieve.native_tokens import NativeTokenizer
from metacom_pm.rl1v3.generator.g0e_port import PromptTokenizer


class Fixture:
    kind='cpu_fixture_not_a_model'
    def __init__(self, spec, native, tasks, slots, clock, inject_protocol_failure=False):
        self.scope_sha256=object_sha256(['GE2 CPU fixture', [t['task_id'] for t in tasks]])
        self.spec,self.native,self.clock=spec,native,clock
        self.inject=inject_protocol_failure
        self.budget=WorkerCallBudget({t['task_id']:object_sha256(t) for t in tasks},self.scope_sha256,
            {'terminal':len(slots),'oneshot':2,'agent':10},slots)
    def generate(self,request,seconds):
        self.budget.claim(request)
        role,ids,decode=validate_generate_request(request,self.spec,self.native,
            boot_id=self.clock.boot_id,now_ns=self.clock.now_ns(),deadline_ns=request['binding']['deadline_ns'])
        if role=='terminal':
            text='CPU_TRANSPORT_FIXTURE_NOT_A_MODEL_REPLY'
        else:
            obs=json.loads(request['payload']['messages'][1]['content'])
            assessment={'status':'unassessed','information_gap':'CPU transport fixture, no semantic judgment'}
            if self.inject and role=='oneshot':
                text='{"invalid":"CPU injected protocol failure"}'
            elif role=='oneshot':
                value={'evidence_state':assessment,'actions':[{'action':'SEARCH','query':obs['query'],'unread_only':True}]+
                    [{'action':'EXPAND','from_search':0,'hit_rank':i,'scope':'parent'} for i in range(4)]+[{'action':'STOP'}]}
                text=json.dumps(value,separators=(',',':'))
            else:
                used=obs['access_budget']['used']
                if used==0:
                    action={'action':'SEARCH','query':obs['query'],'unread_only':True}
                elif used<5 and obs['hits']:
                    # A deliberately mechanical test sequence uses actual handles.
                    initial=[h['handle'] for h in obs['hits'] if h['scope']=='window']
                    action={'action':'EXPAND','handle':initial[min(used-1,len(initial)-1)],'scope':'parent'}
                else: action={'action':'STOP'}
                text=json.dumps({'evidence_state':assessment,'action':action},separators=(',',':'))
        output=self.native.encode(text,add_special_tokens=False)+[decode['eos_token_id'][0]]
        if len(output)>decode['max_new_tokens']:
            raise ValueError('fixture exceeds real controller output cap')
        self.budget.settle(request,output)
        return dict(token_ids=output,text=text,finish_reason='eos',seconds=0.,input_tokens=len(ids),
                    request_sha256=object_sha256(request),fixture_only=True,semantic_evaluation_allowed=False)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--bundle',required=True)
    p.add_argument('--original-plan',required=True)
    p.add_argument('--out',required=True)
    a=p.parse_args()
    out=Path(a.out);out.mkdir(parents=True,exist_ok=False)
    bundle=Path(a.bundle);old=read(a.original_plan)
    baseline=read(old['baseline_path']);source=read(bundle/'SOURCE_CONFIG_PRIVATE.json')
    asset=read(old['source_config_path'])['asset_manifest_path'];source['asset_manifest_path']=asset
    tokenizer=PromptTokenizer(NativeTokenizer(old['model_path'],asset))
    tasks=rows(bundle/'TASKS.runtime.jsonl')
    envelopes={r['task_id']:r for r in rows(bundle/'TASK_ENVELOPES.private.jsonl')}
    recipes=rows(bundle/'DIRECT_SOURCE_RECIPE_PRIVATE.jsonl')
    ids=[r['task_id'] for r in recipes]
    factory=GE2Factory(source_config=source,envelopes=envelopes,tokenizer=tokenizer,baseline=baseline,
        ledger_root=out/'ledgers',retrieval_config=RetrievalConfig(backend='bm25'))
    prep=factory.prepare(tasks)
    factory.direct_provider=DirectProvider(recipes)
    clock=MonotonicClock();results=[];summaries=[]
    for index in range(4):
        selected=tasks[2*index:2*index+2];slots=terminal_slots(selected,ids);events=[]
        backend=Fixture(baseline['spec'],tokenizer.native.tokenizer,selected,slots,clock)
        result=execute(tasks=selected,factory=factory,backend=backend,slots=slots,
            emit=lambda event,**kw:events.append(dict(event=event,**kw)),clock=clock,deadline_ns=clock.now_ns()+1200*10**9)
        write_jsonl_once(out/('fixture-%d.private.jsonl'%index),events)
        write_json_once(out/('fixture-%d.result.private.json'%index),result)
        if result['status']!='FINISHED' or result['pending']:
            raise AssertionError((index,result['status'],result['reason']))
        if any(r['real_model_output'] or r['formal_reward'] is not None or r['status']!='cpu_fixture_transport_only' for r in result['results']):
            raise AssertionError('fixture promoted to model/semantic result')
        results+=result['results']
        summaries.append(dict(batch=index+1,fixture_requests=result['physical_calls'],
            endpoint_slots=len(result['results']),all_native_payloads_revalidated=True))
    selected=tasks[:2];slots=terminal_slots(selected,ids);events=[]
    backend=Fixture(baseline['spec'],tokenizer.native.tokenizer,selected,slots,clock,inject_protocol_failure=True)
    isolated=execute(tasks=selected,factory=factory,backend=backend,slots=slots,
        emit=lambda event,**kw:events.append(dict(event=event,**kw)),clock=clock,deadline_ns=clock.now_ns()+1200*10**9)
    write_jsonl_once(out/'protocol-isolation.private.jsonl',events)
    write_json_once(out/'protocol-isolation.result.private.json',isolated)
    assert isolated['status']=='FINISHED' and not isolated['pending']
    assert sum(r['fallback_executed'] for r in isolated['results'])==2
    assert len({r['request_id'] for r in isolated['results']})==len(isolated['results'])
    receipt=dict(protocol='ge2-native-source-cpu-fixture-v1',new_model_calls=0,model_loads=0,
        generator_weights_loaded=False,device_access=False,task_count=8,terminal_fixture_slots=len(results),
        source_startup=prep,batches=summaries,protocol_failure_isolated_to_path=True,
        fallback_terminal_count=2,fallback_has_no_extra_terminal_call=True,
        later_independent_slots_completed=True,model_quality_or_real_inference_latency_claim=False,
        bundle_manifest_sha256=file_sha256(bundle/'MANIFEST_PRIVATE.json'),
        checked_code_sha256={str(Path(m.__file__).resolve()):file_sha256(m.__file__) for m in
            __import__('sys').modules.copy().values() if getattr(m,'__name__','').startswith('metacom_pm.rl1v3.journal.ge2_') and getattr(m,'__file__',None)})
    write_json_once(out/'CPU_CHECK_PUBLIC.json',receipt)
    print(json.dumps({k:v for k,v in receipt.items() if k!='checked_code_sha256'},indent=2))


if __name__=='__main__':main()
