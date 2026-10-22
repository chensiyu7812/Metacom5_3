#!/usr/bin/env python3
"""Local-only opt-in batch backend for the explicitly selected P3 protocol.

Adapted from 98's fixed vLLM loop; old 98 and its runtime identity are preserved.
No automatic retries, alternate models, paid fallback, human labels or training.
"""
import argparse
from collections import Counter
import importlib.util
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import time

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.calibration_workflow import verify_identity,require_freeze,stamp
from metacom_pm.rl1 import judge_completion_candidate as proposed


def workflow():
    spec=importlib.util.spec_from_file_location('p3_workflow',Path(__file__).with_name('107_p3_acceptance_workflow.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def configure(context,out,use_proposed):
    w=workflow();c,inputs=w.load_inputs(context)
    out=out.resolve();out.mkdir(parents=True,exist_ok=False)
    protocol={k:v for k,v in inputs['protocol'].items() if k!='identity'}
    if use_proposed:
        if protocol['semantic_revisions_after_human_labels']!=0 or c['revision_events']:
            raise ValueError('cannot apply another semantic revision')
        protocol.update(version=proposed.VERSION,rubric=proposed.RUBRIC,rubric_identity=proposed.RUBRIC_ID,
            status='POST_HUMAN_CANDIDATE_FOR_DEVELOPMENT_NOT_QUALIFIED',semantic_revisions_after_human_labels=1)
    protocol=stamp(protocol)
    runtime={k:v for k,v in inputs['runtime'].items() if k!='identity'}
    runtime.update(protocol_identity=protocol['identity'],runner_sha256=sha256_file(Path(__file__)))
    runtime=stamp(runtime)
    w.save(out/'protocol.json',protocol);w.save(out/'runtime.json',runtime)
    events=c['revision_events']
    if use_proposed:events=[dict(state='applied',from_protocol_identity=inputs['protocol']['identity'],
        to_protocol_identity=protocol['identity'],reason='Explicit selection of reviewed development candidate')]
    prior=Path(c['runtime']).parent/'summary.json'
    new_context=dict(c,protocol=str(out/'protocol.json'),runtime=str(out/'runtime.json'),revision_events=events,
        prior_run_summaries=list(dict.fromkeys(c.get('prior_run_summaries',[])+[str(prior)])))
    new_context.pop('development_score_review',None)
    w.save(out/'context.json',new_context)
    print(json.dumps(dict(context=str(out/'context.json'),model_calls=0,semantic_revision_selected=use_proposed)))


def execute(plan_path,execute_local):
    w=workflow();plan=w.read(plan_path);verify_identity(plan)
    c,inputs=w.load_inputs(plan['context'])
    if plan['bindings']!={k:digest(v) for k,v in inputs.items()}:raise ValueError('batch inputs/code changed')
    if plan['phase']=='validation':require_freeze(w.read(plan['freeze_path']),inputs)
    protocol=inputs['protocol'];runtime=inputs['runtime'];cfg=protocol['runtime'];decode=protocol['decode']
    if runtime['runner_sha256']!=sha256_file(Path(__file__)):
        raise ValueError('configure a new runtime for this backend; never reuse the old 98 runtime')
    scorer=w.select_scorer(protocol);jobs={j['job_id']:j for j in inputs['jobs']}
    expected={j['job_id'] for j in jobs.values() if j['group'] in (
        ('development','recheck_probe') if plan['phase']=='development' else ('validation','repeat'))}
    if len(plan['requests'])!=len(expected) or {r['job_id'] for r in plan['requests']}!=expected:
        raise ValueError('fixed phase job coverage mismatch')
    for entry in plan['requests']:
        req={k:v for k,v in entry.items() if k!='job_id'};job=jobs[entry['job_id']]
        if req['request_id']!=digest({k:v for k,v in req.items() if k!='request_id'}):raise ValueError('request identity mismatch')
        messages,schema=scorer.messages_and_schema(job['evidence'],job['reply'],recheck=job['recheck'])
        if (req['messages']!=messages or req['json_schema']!=schema or req['seed']!=job['seed']
                or req['draw_identity']!=job['draw_id'] or req['executor_identity']!=runtime['identity']
                or req['attempt']!=0):raise ValueError('job request mismatch')
    run_root=Path(c['protocol']).parent/'runs';out=run_root/plan['phase']
    if out.exists():raise ValueError('phase output already exists; preserve attempts, explicit recovery review required')
    previous_paths=list(map(Path,c.get('prior_run_summaries',[])))+list(run_root.glob('*/summary.json'))
    observed_calls=sum(w.read(p)['physical_calls_this_invocation'] for p in previous_paths)
    if plan['previous_calls']<observed_calls or plan['previous_calls']+len(expected)>plan['request_limit']:
        raise ValueError('call allowance/accounting mismatch')
    if not execute_local:
        print(json.dumps(dict(status='OFFLINE_BINDING_CHECK_ONLY',requests=len(expected),model_calls=0,
                              tokenizer_loaded=False,output=str(out))));return
    # No imports below this line execute during an offline check.
    if {p:importlib.metadata.version(p) for p in protocol['packages']}!=protocol['packages']:
        raise ValueError('frozen package versions differ')
    import torch
    from transformers import AutoTokenizer
    from vllm import LLM, SamplingParams
    from vllm.sampling_params import StructuredOutputsParams
    if (torch.cuda.device_count()!=1 or torch.cuda.get_device_name(0)!=runtime['gpu']
            or torch.version.cuda!=runtime['cuda_version']
            or os.environ.get('CUDA_VISIBLE_DEVICES')!=runtime['cuda_visible_devices']
            or os.environ.get('CUDA_DEVICE_ORDER')!=runtime['cuda_device_order']
            or torch.cuda.mem_get_info(0)[0]<44*1024**3):
        raise RuntimeError('frozen free A6000/runtime required; no device fallback')
    model=Path(protocol['model'])
    for name,h in protocol['model_files'].items():
        if sha256_file(model/name)!=h:raise ValueError('checkpoint file changed: '+name)
    tokenizer=AutoTokenizer.from_pretrained(model,local_files_only=True)
    prepared=[]
    for entry in plan['requests']:
        req={k:v for k,v in entry.items() if k!='job_id'}
        ids=tokenizer.apply_chat_template(req['messages'],tokenize=True,add_generation_prompt=True,
            return_dict=False,enable_thinking=decode['thinking'])
        if not 0<len(ids)<cfg['native_context']:raise ValueError('full input exceeds native context; no truncation')
        prepared.append((jobs[entry['job_id']],req,ids))
    out.mkdir(parents=True,exist_ok=False)
    w.save(out/'plan.json',plan);w.save(out/'runtime.json',runtime)
    for _,req,_ in prepared:w.save(out/(req['request_id']+'.request.json'),req)
    start=time.monotonic()
    llm=LLM(model=str(model),dtype=cfg['dtype'],max_model_len=cfg['serving_context'],
        gpu_memory_utilization=cfg['gpu_memory_utilization'],max_num_seqs=cfg['concurrency'],
        max_num_batched_tokens=cfg['max_num_batched_tokens'],enforce_eager=cfg['enforce_eager'],
        enable_prefix_caching=cfg['enable_prefix_caching'],seed=cfg['engine_seed'],
        language_model_only=cfg['language_model_only'],reasoning_parser=cfg['reasoning_parser'])
    engine=llm.llm_engine;loaded=time.monotonic();rows=[];active={};started=0;failed=False
    queue=prepared[:4];deferred=prepared[4:];smoke_checked=False
    def summary(status):
        value=dict(status=status,planned=len(prepared),rows=rows,physical_calls_this_invocation=started,
            unattempted=len(prepared)-started,load_seconds=loaded-start,
            engine_wall_seconds=time.monotonic()-loaded,API_usd=0,
            statuses=dict(Counter(r['measurement_status'] for r in rows)),reward_qualified=False)
        tmp=out/'summary.tmp';tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');tmp.replace(out/'summary.json')
    while queue or active or not smoke_checked:
        if not queue and not active and not smoke_checked:
            smoke_checked=True;queue=[] if failed else deferred
        if failed:queue=[];smoke_checked=True
        while queue and len(active)<cfg['concurrency'] and not failed:
            job,req,ids=queue.pop(0)
            params=SamplingParams(**{k:v for k,v in decode.items() if k!='thinking'},
                max_tokens=cfg['native_context']-len(ids),seed=job['seed'],
                structured_outputs=StructuredOutputsParams(json=req['json_schema']))
            started+=1;summary('RUNNING_NOT_QUALIFIED')
            engine.add_request(req['request_id'],{'prompt_token_ids':ids},params)
            active[req['request_id']]=(job,req,len(ids),time.monotonic())
        if not active:continue
        for output in engine.step():
            if output.request_id not in active or not output.outputs:continue
            job,req,n,t0=active[output.request_id];a=output.outputs[0];elapsed=time.monotonic()-t0
            ids=list(a.token_ids);reason=None
            if output.finished:reason='natural_stop' if a.finish_reason=='stop' else 'context_exhausted' if a.finish_reason=='length' else str(a.finish_reason)
            elif elapsed>=cfg['technical_timeout_seconds']:reason='technical_timeout'
            elif len(ids)>=128 and all(ids[-32:]==ids[-32*(i+1):-32*i] for i in range(1,4)):reason='repetition_guard'
            if reason is None:continue
            if not output.finished:engine.abort_request([output.request_id])
            raw=dict(request_id=req['request_id'],runtime_identity=runtime['identity'],text=a.text,
                finish_reason=reason,model_finish_reason=a.finish_reason,model_stop_reason=a.stop_reason,
                input_tokens=n,output_tokens=len(ids),output_token_ids=ids,seconds=elapsed,API_usd=0)
            measured=scorer.parse_completion(raw['text'],evidence=job['evidence'],reply=job['reply'],
                runtime_identity=runtime['identity'],draw_id=job['draw_id'],finish_reason=reason)
            w.save(out/(req['request_id']+'.raw.json'),raw);w.save(out/(req['request_id']+'.measurement.json'),measured)
            rows.append(dict(job_id=job['job_id'],request_id=req['request_id'],group=job['group'],cache_hit=False,
                finish_reason=reason,measurement_status=measured['measurement_status'],q=measured['q'],m=measured['m'],
                utility=measured['candidate_utility'],input_tokens=n,output_tokens=len(ids),seconds=elapsed))
            failed |= measured['measurement_status'] not in ('measured_candidate','semantic_uncertainty')
            del active[output.request_id];summary('RUNNING_NOT_QUALIFIED')
    summary('STOPPED_TECHNICAL_FAILURE' if failed else 'BATCH_COMPLETE_NOT_QUALIFIED')
    print(json.dumps(dict(output=str(out),physical_calls=started,reward_qualified=False)))


if __name__=='__main__':
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    s=sub.add_parser('configure');s.add_argument('--context',required=True);s.add_argument('--out',type=Path,required=True)
    s.add_argument('--use-proposed-revision',action='store_true')
    s=sub.add_parser('run');s.add_argument('--plan',required=True);s.add_argument('--execute-local',action='store_true')
    a=p.parse_args()
    if a.command=='configure':configure(a.context,a.out,a.use_proposed_revision)
    else:execute(a.plan,a.execute_local)
