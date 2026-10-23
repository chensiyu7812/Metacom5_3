#!/usr/bin/env python3
"""Bound local P2 author/reviewer jobs with natural ends and durable claims.

One exact attempt per job, no quality retry, no API fallback. Review is not RL J.
"""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import time

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.cache import AttemptCache
from metacom_pm.rl1.schema import digest
OUT=PROJECT/'outputs/pm_rl1/completion_20260930_v2/P2'


def read(p):return json.loads(p.read_text())


def save(p,v):
    p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n');tmp.replace(p)


def repeated(ids):
    return len(ids)>=128 and all(ids[-32:]==ids[-32*(i+1):-32*i] for i in range(1,4))


def main(stage,preflight_only):
    start=time.monotonic();freeze=read(OUT/'supervision_freeze.json')
    for n,h in freeze['files'].items():assert sha256_file(OUT/n)==h,n
    for n,h in freeze['source_files'].items():assert sha256_file(PROJECT/n)==h,n
    protocol=read(OUT/'supervision_protocol.json');jobs_path=OUT/(stage+'_jobs_private.json')
    if stage!='author':
        jf=read(OUT/(stage+'_jobs_freeze.json'))
        for n,h in jf['files'].items():assert sha256_file(PROJECT/n)==h,n
    jobs=read(jobs_path)
    assert len({(j['slot_id'],j['attempt']) for j in jobs})==len(jobs)
    assert all(j['split'] in ('train','dev') for j in jobs)
    if stage=='author':assert len(jobs)==684 and all(j['attempt']==0 for j in jobs)
    review=stage.startswith('review');decode=protocol['review_decode'] if review else protocol['author_decode']
    from transformers import AutoTokenizer
    model=Path(protocol['model']);context=protocol['native_context']
    tokenizer=AutoTokenizer.from_pretrained(model,local_files_only=True)
    encoded=[tokenizer.apply_chat_template(j['messages'],tokenize=True,add_generation_prompt=True,
                return_dict=False,enable_thinking=False) for j in jobs]
    assert all(0<len(ids)<context for ids in encoded),'context exhausted; no truncation'
    print(json.dumps(dict(stage=stage,preflight='OK',jobs=len(jobs),max_input_tokens=max(map(len,encoded),default=0))),flush=True)
    if preflight_only:return
    import torch
    from vllm import LLM,SamplingParams
    if torch.cuda.device_count()!=1 or 'A6000' not in torch.cuda.get_device_name(0) or torch.cuda.mem_get_info(0)[0]<44*1024**3:
        raise RuntimeError('bind free A6000; no GPU fallback')
    packages={p:importlib.metadata.version(p) for p in ('torch','transformers','vllm')}
    assert packages==protocol['packages'],'runtime package drift'
    for n,h in protocol['model_files'].items():assert sha256_file(model/n)==h,n
    runtime=dict(protocol='p2-local-jobs-v1',stage=stage,decode=decode,model=str(model),
        model_files=protocol['model_files'],packages=packages,gpu=torch.cuda.get_device_name(0),
        cuda_visible_devices=os.environ.get('CUDA_VISIBLE_DEVICES'),cuda_version=torch.version.cuda,
        dtype='bfloat16',concurrency=4,gpu_memory_utilization=.88,max_num_batched_tokens=4096,
        enforce_eager=True,enable_prefix_caching=False,language_model_only=True,engine_seed=17,native_context=context,
        jobs_sha256=sha256_file(jobs_path),supervision_freeze_sha256=sha256_file(OUT/'supervision_freeze.json'),
        runner_sha256=sha256_file(Path(__file__)))
    identity=digest(runtime);run=OUT/stage/identity
    save(run/'runtime.json',dict(runtime,identity=identity));save(OUT/(stage+'_pointer.json'),dict(run_dir=str(run),runtime_identity=identity))
    queue=[]
    for job,ids in zip(jobs,encoded):
        payload=dict(messages=job['messages'],executor_identity=identity,seed=job['seed'],
            draw_identity=digest(['p2',stage,job['slot_id'],job['attempt'],job['seed']]),
            renderer_identity=job['renderer_identity'])
        request=dict(payload,request_id=digest(payload));save(run/(request['request_id']+'.request.json'),request)
        queue.append((job,ids,request))
    cache=AttemptCache(run/'attempts.sqlite');results=[];active={}
    smoke,deferred=queue[:3],queue[3:];queue=smoke;checked=False
    load=time.monotonic()
    llm=LLM(model=str(model),dtype='bfloat16',max_model_len=context,gpu_memory_utilization=.88,
        max_num_seqs=4,max_num_batched_tokens=4096,enforce_eager=True,enable_prefix_caching=False,
        seed=17,language_model_only=True)
    load_seconds=time.monotonic()-load;engine=llm.llm_engine;engine_start=time.monotonic()
    def finish(job,request,raw,cache_hit):
        save(run/(request['request_id']+'.raw.json'),raw)
        row={k:job[k] for k in ('slot_id','index','category','split','attempt')}
        row.update(request_id=request['request_id'],finish_reason=raw['finish_reason'],cache_hit=cache_hit,
            input_tokens=raw['input_tokens'],output_tokens=raw['output_tokens'],seconds=raw['seconds'])
        results.append(row)
        save(run/'summary.json',dict(status='COMPLETE_UNADMITTED' if len(results)==len(jobs) else 'IN_PROGRESS',
            stage=stage,rows=results,planned=len(jobs),physical_calls=sum(not r['cache_hit'] for r in results),
            load_seconds=load_seconds,engine_wall_seconds=time.monotonic()-engine_start,
            elapsed_seconds=time.monotonic()-start,API_usd=0,RL_reward_calls=0))
        if len(results)%16==0 or len(results)==len(jobs) or len(results)<=3:
            print(json.dumps(dict(stage=stage,done=len(results),total=len(jobs),last_finish=raw['finish_reason'])),flush=True)
    while queue or active or not checked:
        if not queue and not active and not checked:
            checked=True
            if any(r['finish_reason']!='natural_stop' for r in results):raise RuntimeError('technical smoke failed; preserve attempts')
            queue=deferred;save(run/'smoke.json',dict(request_ids=[r['request_id'] for r in results],technical_only=True))
        while queue and len(active)<4:
            job,ids,req=queue.pop(0);cached=cache.claim(req)
            if cached is not None:finish(job,req,cached,True);continue
            params=SamplingParams(temperature=decode['temperature'],top_p=decode['top_p'],top_k=decode['top_k'],
                min_p=decode['min_p'],presence_penalty=decode['presence_penalty'],repetition_penalty=decode['repetition_penalty'],
                max_tokens=context-len(ids),seed=job['seed'])
            engine.add_request(req['request_id'],{'prompt_token_ids':ids},params)
            active[req['request_id']]=dict(job=job,request=req,start=time.monotonic(),input_tokens=len(ids))
        if not active:continue
        for output in engine.step():
            if output.request_id not in active or not output.outputs:continue
            a=output.outputs[0];state=active[output.request_id];elapsed=time.monotonic()-state['start'];reason=None
            if output.finished:reason='natural_stop' if a.finish_reason=='stop' else 'context_exhausted' if a.finish_reason=='length' else str(a.finish_reason)
            elif elapsed>=300:reason='technical_timeout'
            elif repeated(list(a.token_ids)):reason='repetition_guard'
            if reason is None:continue
            if not output.finished:engine.abort_request([output.request_id])
            raw=dict(request_id=output.request_id,runtime_identity=identity,text=a.text,finish_reason=reason,
                model_finish_reason=a.finish_reason,model_stop_reason=a.stop_reason,input_tokens=state['input_tokens'],
                output_tokens=len(a.token_ids),output_token_ids=list(a.token_ids),seconds=elapsed,API_usd=0)
            cache.finish(output.request_id,raw);finish(state['job'],state['request'],raw,False);del active[output.request_id]


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stage',choices=('author','review','repair','review_repair'),required=True)
    p.add_argument('--preflight-only',action='store_true');a=p.parse_args();main(a.stage,a.preflight_only)
