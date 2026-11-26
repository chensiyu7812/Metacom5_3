#!/usr/bin/env python3
"""Real native tokens and real source tools; synthetic model transport only.

Does not load weights or access CUDA. Reports no model-quality result.
"""
import argparse,json
from pathlib import Path
from metacom_pm.rl1v3.io import object_sha256
from metacom_pm.rl1v3.journal import gsws as S
from metacom_pm.rl1v3.journal.gsws_runtime import execute,slots,ROLE_MAP
from metacom_pm.rl1v3.journal.gsws_worker import validate_generate_request
from metacom_pm.rl1v3.journal.ge2_factory import GE2Factory
from metacom_pm.rl1v3.journal.ge2_sources import rows,write_once
from metacom_pm.rl1v3.journal.ge2_retrieval import RetrievalConfig
from metacom_pm.rl1v3.journal.pomdp_latency import MonotonicClock
from metacom_pm.rl1v3.generator.g0e_port import PromptTokenizer
from metacom_pm.rl1v3.retrieve.native_tokens import NativeTokenizer


def run(bundle,old_plan,output):
    b=Path(bundle);out=Path(output);out.mkdir(parents=True,exist_ok=True)
    p=json.loads(Path(old_plan).read_text());baseline=json.loads(Path(p['baseline_path']).read_text())
    cfg=json.loads((b/'SOURCE_CONFIG_PRIVATE.json').read_text());tasks=rows(b/'TASKS.runtime.jsonl')
    tok=PromptTokenizer(NativeTokenizer(p['model_path'],cfg['asset_manifest_path']))
    factory=GE2Factory(source_config=cfg,envelopes={r['task_id']:r for r in rows(b/'TASK_ENVELOPES.private.jsonl')},
        tokenizer=tok,baseline=baseline,ledger_root=out/'ledgers',retrieval_config=RetrievalConfig(backend='bm25'))
    factory.prepare(tasks);clock=MonotonicClock();events=[]
    class FixtureBackend:
        kind='cpu_fixture_no_model';scope_sha256=object_sha256(tasks)
        def generate(self,request,seconds):
            role=request['role'];arm=request['binding']['arm'];obs=request['binding']['observation']
            if role=='terminal':text='CPU wiring fixture only; no semantic conclusion.'
            elif arm=='A1_READING_NOTES':text=json.dumps(dict(notes='CPU fixture; interpret actual evidence later.',evidence_ids=[]))
            else:text=json.dumps(dict(goal_and_boundaries='CPU fixture',claims=[],gaps_or_conflicts='Unknown',response_implications='Pending'))
            if role!='terminal' or arm=='A0_RAW':
                validate_generate_request(request,baseline['spec'],tok.native.tokenizer,
                    boot_id=clock.boot_id,now_ns=clock.now_ns(),deadline_ns=clock.now_ns()+1000000000)
            elif request['binding']['state'] is not None:
                try:validate_generate_request(request,baseline['spec'],tok.native.tokenizer,
                    boot_id=clock.boot_id,now_ns=clock.now_ns(),deadline_ns=clock.now_ns()+1000000000)
                except ValueError as error:assert 'no CPU fixture' in str(error)
                else:raise AssertionError('real worker accepted CPU fixture as actual model state')
            ids=tok.native.tokenizer.encode(text,add_special_tokens=False)+[request['payload']['decode']['eos_token_id'][0]]
            return dict(token_ids=ids,text=text,finish_reason='eos',seconds=0.,input_tokens=len(request['payload']['input_ids']),
                        request_sha256=object_sha256(request),origin='cpu_fixture_not_model')
    summaries=[]
    for n in range(4):
        ts=tasks[2*n:2*n+2]
        result=execute(tasks=ts,factory=factory,backend=FixtureBackend(),slots=slots(ts),
            emit=lambda kind,**kw:events.append(dict(kind=kind,**kw)),clock=clock,deadline_ns=clock.now_ns()+1200*10**9)
        summaries.append({k:v for k,v in result.items() if k!='endpoints'})
    # Complete fixed 48 terminal / 32 interpreter paths with real source tools.
    assert sum(s['backend_calls'] for s in summaries)==80 and sum(s['fixture_terminal_slots'] for s in summaries)==48
    assert all(s['actual_model_calls']==0 for s in summaries)
    write_once(out/'CPU_RUNTIME_EVENTS_NOT_MODEL.private.jsonl',events,jsonl=True)
    report=dict(status='CPU_NATIVE_SOURCE_RUNTIME_PASSED',jobs=summaries,model_loads=0,gpu_access=False,
        actual_model_calls=0,synthetic_backend_calls=80,fixture_endpoints=48,semantic_success=None,
        same_original_evidence_asserted_across_three_arms=True,fixtures_rejected_by_real_terminal_worker=True)
    write_once(out/'CPU_RUNTIME_PUBLIC.json',report);print(json.dumps(report,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--bundle',required=True);p.add_argument('--old-plan',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();run(a.bundle,a.old_plan,a.output)
