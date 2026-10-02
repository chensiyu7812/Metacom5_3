#!/usr/bin/env python3
"""One frozen native-interface run per candidate; local only, no automatic retries."""
import argparse
import importlib.metadata
import json
import math
import os
from pathlib import Path
import sys
import time

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.measurement_candidates import parse_native_choice, repeated_tail
OUT=PROJECT/'outputs/pm_rl1/r04b_measurement_20260930_v1'


def read(p):
    return json.loads(p.read_text())


def save(p,x):
    p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n');tmp.replace(p)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--model',choices=['prometheus','skywork'],required=True)
    args=parser.parse_args();start=time.monotonic()
    freeze=read(OUT/'freeze.json')
    for name,expected in freeze['files'].items():
        if sha256_file(Path(name))!=expected:raise ValueError('frozen input/code changed: '+name)
    models=read(OUT/'model_files.json');m=models[args.model];model=Path(m['model_dir'])
    for name,expected in m['files'].items():
        if sha256_file(model/name)!=expected:raise ValueError('model bytes changed: '+name)
    jobs=[j for j in read(OUT/'jobs_private.json') if j['model']==args.model]
    import torch
    if (torch.cuda.device_count()!=1 or 'A6000' not in torch.cuda.get_device_name(0)
            or torch.cuda.mem_get_info(0)[0]<44*1024**3):
        raise RuntimeError('bind the free A6000 explicitly; no device fallback')
    packages=['torch','transformers']+(['vllm'] if args.model=='prometheus' else [])
    runtime=dict(model_identity=digest(m),model=m['repo'],revision=m['revision'],
        packages={k:importlib.metadata.version(k) for k in packages},
        gpu=torch.cuda.get_device_name(0),cuda_version=torch.version.cuda,
        cuda_visible_devices=os.environ.get('CUDA_VISIBLE_DEVICES'),
        protocol_sha256=sha256_file(OUT/'protocol.json'),freeze_sha256=sha256_file(OUT/'freeze.json'),
        runner_sha256=sha256_file(Path(__file__)))
    runtime['identity']=digest(runtime);run=OUT/'runs'/args.model
    if (run/'runtime.json').exists() and read(run/'runtime.json')!=runtime:raise ValueError('runtime changed')
    save(run/'runtime.json',runtime);results=[]

    def finish(j,raw):
        raw=dict(job_id=j['job_id'],runtime_identity=runtime['identity'],input_identity=j['input_identity'],
                 input_tokens=j['input_tokens'],api_cost_usd=0,**raw)
        save(run/(j['job_id']+'.raw.json'),raw)
        row={k:j[k] for k in ('job_id','case_id','draw')}
        if 'side' in j:row['side']=j['side']
        row.update({k:v for k,v in raw.items() if k not in ('text','output_token_ids')})
        results.append(row)
        save(run/'summary.json',dict(status='RUNNING',rows=results,planned=len(jobs),
            total_wall_seconds=time.monotonic()-start,api_cost_usd=0))
        print(json.dumps({k:row.get(k) for k in ('case_id','draw','side','finish_reason','score','output_tokens')}),flush=True)

    queue=[]
    for j in jobs:
        p=run/(j['job_id']+'.raw.json');claim=run/(j['job_id']+'.claim.json')
        if p.exists():
            raw=read(p)
            if raw['runtime_identity']!=runtime['identity'] or raw['input_identity']!=j['input_identity']:raise ValueError('raw identity changed')
            results.append({**{k:j[k] for k in ('case_id','draw','job_id')},**raw})
            continue
        if claim.exists():raise RuntimeError('unresolved prior attempt; no silent resend')
        if j['capacity_status']!='ready':
            finish(j,dict(finish_reason='technical_context_missing',score=None,text='',seconds=0,
                capacity_status=j['capacity_status']))
        else:queue.append(j)
    load=time.monotonic();torch.manual_seed(0)
    if args.model=='prometheus':
        from vllm import LLM,SamplingParams
        llm=LLM(model=str(model),dtype='bfloat16',max_model_len=32768,gpu_memory_utilization=.88,
            max_num_seqs=4,max_num_batched_tokens=4096,enforce_eager=True,enable_prefix_caching=False,seed=0)
        engine=llm.llm_engine;active={};load_seconds=time.monotonic()-load
        while queue or active:
            while queue and len(active)<4:
                j=queue.pop(0);save(run/(j['job_id']+'.claim.json'),dict(job_id=j['job_id'],runtime_identity=runtime['identity']))
                params=SamplingParams(temperature=0,top_p=1,top_k=-1,min_p=0,presence_penalty=0,
                    frequency_penalty=0,repetition_penalty=1,max_tokens=32768-j['input_tokens'],seed=0,
                    ignore_eos=False)
                engine.add_request(j['job_id'],{'prompt_token_ids':j['input_ids']},params)
                active[j['job_id']]=(j,time.monotonic())
            for output in engine.step():
                if output.request_id not in active or not output.outputs:continue
                a=output.outputs[0];j,t0=active[output.request_id];elapsed=time.monotonic()-t0;reason=None
                if output.finished:
                    reason='natural_stop' if a.finish_reason=='stop' else 'context_exhausted' if a.finish_reason=='length' else str(a.finish_reason)
                elif elapsed>=300:reason='technical_timeout'
                elif repeated_tail(list(a.token_ids)):reason='repetition_guard'
                if reason is None:continue
                if not output.finished:engine.abort_request([output.request_id])
                if reason=='natural_stop' and not a.text.strip():reason='empty_output'
                finish(j,dict(text=a.text,output_token_ids=list(a.token_ids),output_tokens=len(a.token_ids),
                    finish_reason=reason,model_finish_reason=a.finish_reason,model_stop_reason=a.stop_reason,
                    parsed=parse_native_choice(a.text,reason),seconds=elapsed))
                del active[output.request_id]
    else:
        from transformers import AutoModelForSequenceClassification
        model_obj=AutoModelForSequenceClassification.from_pretrained(str(model),local_files_only=True,
            torch_dtype=torch.bfloat16,attn_implementation='sdpa',num_labels=1).to('cuda:0').eval()
        load_seconds=time.monotonic()-load
        for j in queue:
            save(run/(j['job_id']+'.claim.json'),dict(job_id=j['job_id'],runtime_identity=runtime['identity']))
            t0=time.monotonic();torch.cuda.reset_peak_memory_stats(0)
            try:
                ids=torch.tensor([j['input_ids']],dtype=torch.long,device='cuda:0')
                with torch.inference_mode():
                    logits=model_obj(input_ids=ids,attention_mask=torch.ones_like(ids),use_cache=False).logits
                torch.cuda.synchronize();score=logits[0,0].float().item()
                if tuple(logits.shape)!=(1,1) or not math.isfinite(score):raise ValueError('nonfinite or wrong-shape score')
                finish(j,dict(score=score,finish_reason='scored',seconds=time.monotonic()-t0,
                    logits_dtype=str(logits.dtype),peak_allocated_bytes=torch.cuda.max_memory_allocated(0)))
            except Exception as exc:
                finish(j,dict(score=None,finish_reason='technical_exception',exception_type=type(exc).__name__,
                    error=str(exc),seconds=time.monotonic()-t0))
                raise RuntimeError('exception retained; no automatic retry or backend change') from exc
    assert len(results)==len(jobs)
    save(run/'summary.json',dict(status='FINITE_CANDIDATE_RUN_COMPLETE',rows=results,planned=len(jobs),
        load_seconds=load_seconds,total_wall_seconds=time.monotonic()-start,api_cost_usd=0,
        maximum_torch_allocated_bytes=torch.cuda.max_memory_allocated(0),no_quality_regeneration=True))


if __name__=='__main__':main()
