#!/usr/bin/env python3
"""Local, nonthinking weak-example author. Does not judge or admit its answers."""
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import time

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT/'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.cache import AttemptCache
OUT = PROJECT/'outputs/pm_rl1/executor_pilot_20260929_v1'

def save(path, obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp'); temp.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n'); temp.replace(path)

def repeated(ids):
    return len(ids)>=128 and all(ids[-32:] == ids[-32*(i+1):-32*i] for i in range(1,4))

def main():
    import torch
    from vllm import LLM, SamplingParams
    start=time.monotonic()
    if torch.cuda.device_count()!=1 or 'A6000' not in torch.cuda.get_device_name(0) or torch.cuda.mem_get_info(0)[0]<44*1024**3:
        raise RuntimeError('bind the free A6000 explicitly; no fallback')
    contract_path=OUT/'condition_contract_private.json'
    contract=json.loads(contract_path.read_text()); author=contract['author']; model=Path(author['model'])
    context=json.loads((model/'config.json').read_text())['text_config']['max_position_embeddings']
    runtime=dict(protocol='pm-rl1-r05-example-author-v1', model=str(model),
        files={p.name:sha256_file(p) for p in sorted(model.iterdir()) if p.is_file() and p.suffix in ('.json','.safetensors','.jinja','.txt')},
        packages={p:importlib.metadata.version(p) for p in ('torch','transformers','vllm')},
        gpu=torch.cuda.get_device_name(0),cuda_visible_devices=os.environ.get('CUDA_VISIBLE_DEVICES'),cuda_version=torch.version.cuda,
        dtype='bfloat16',backend='vllm',native_context=context,decode=author,
        concurrency=4,gpu_memory_utilization=.88,max_num_batched_tokens=4096,enforce_eager=True,
        enable_prefix_caching=False,language_model_only=True,engine_seed=17,
        contract_sha256=sha256_file(contract_path),runner_sha256=sha256_file(Path(__file__)))
    identity=digest(runtime); run=OUT/'author'/identity
    save(run/'runtime.json',dict(**runtime,identity=identity))
    save(OUT/'author_pointer.json',dict(run_dir=str(run),runtime_identity=identity))
    cache=AttemptCache(run/'attempts.sqlite'); queue=[]; active={}; results=[]
    for c in contract['conditions']:
        assert c['split'] in ('train','dev') and c['messages_identity']==digest(c['messages'])
        for seed in contract['seeds']:
            job=dict(index=c['index'],condition=c['condition'],split=c['split'],seed=seed,prefix_identity=c['prefix_identity'])
            payload=dict(messages=c['messages'],executor_identity=identity,seed=seed,
                draw_identity=digest([c['prefix_identity'],seed]),renderer_identity=contract['renderer_identity'])
            req=dict(**payload,request_id=digest(payload))
            save(run/(req['request_id']+'.request.json'),req); queue.append((job,req))
    # Smoke is part of the planned batch; purely technical success, never quality.
    smoke=queue[:3]; deferred=queue[3:]; queue=smoke; checked=False
    save(run/'jobs.json',[dict(**j,request_id=r['request_id']) for j,r in smoke+deferred])
    print(json.dumps(dict(stage='loading',identity=identity,calls=108)),flush=True)
    load=time.monotonic()
    llm=LLM(model=str(model),dtype='bfloat16',max_model_len=context,gpu_memory_utilization=.88,
        max_num_seqs=4,max_num_batched_tokens=4096,enforce_eager=True,enable_prefix_caching=False,seed=17,language_model_only=True)
    load_seconds=time.monotonic()-load; tokenizer=llm.get_tokenizer(); engine=llm.llm_engine; engstart=time.monotonic()
    def finish(j,r,raw,hit):
        save(run/(r['request_id']+'.raw.json'),raw)
        results.append(dict(**j,request_id=r['request_id'],cache_hit=hit,finish_reason=raw['finish_reason'],
            input_tokens=raw['input_tokens'],output_tokens=raw['output_tokens'],seconds=raw['seconds']))
        save(run/'summary.json',dict(status='AUTHOR_OUTPUTS_UNREVIEWED',rows=results,load_seconds=load_seconds,
            engine_wall_seconds=time.monotonic()-engstart,total_seconds=time.monotonic()-start,api_cost_usd=0,planned_calls=108))
        print(json.dumps(results[-1]),flush=True)
    while queue or active or not checked:
        if not queue and not active and not checked:
            checked=True
            if len(results)!=3 or any(r['finish_reason']!='natural_stop' for r in results):
                raise RuntimeError('technical smoke failed; do not revise author based on answers')
            queue=deferred
            save(run/'smoke.json',dict(ok=True,request_ids=[r['request_id'] for r in results],quality_admission=False))
        while queue and len(active)<4:
            j,r=queue.pop(0)
            ids=tokenizer.apply_chat_template(r['messages'],tokenize=True,add_generation_prompt=True,return_dict=False,enable_thinking=False)
            if len(ids)>=context: raise RuntimeError('input over native context; no truncation')
            cached=cache.claim(r)
            if cached is not None: finish(j,r,cached,True); continue
            params=SamplingParams(temperature=.7,top_p=.8,top_k=20,min_p=0.,presence_penalty=1.5,
                repetition_penalty=1.,max_tokens=context-len(ids),seed=j['seed'])
            engine.add_request(r['request_id'],{'prompt_token_ids':ids},params)
            active[r['request_id']]=dict(job=j,request=r,start=time.monotonic(),input_tokens=len(ids))
        if not active: continue
        for o in engine.step():
            if o.request_id not in active or not o.outputs: continue
            a=o.outputs[0]; state=active[o.request_id]; elapsed=time.monotonic()-state['start']; reason=None
            if o.finished: reason='natural_stop' if a.finish_reason=='stop' else 'context_exhausted' if a.finish_reason=='length' else str(a.finish_reason)
            elif elapsed>=300: reason='technical_timeout'
            elif repeated(list(a.token_ids)): reason='repetition_guard'
            if reason is None: continue
            if not o.finished: engine.abort_request([o.request_id])
            raw=dict(request_id=o.request_id,runtime_identity=identity,text=a.text,finish_reason=reason,
                model_finish_reason=a.finish_reason,model_stop_reason=a.stop_reason,input_tokens=state['input_tokens'],
                output_tokens=len(a.token_ids),output_token_ids=list(a.token_ids),seconds=elapsed,api_cost_usd=0)
            cache.finish(o.request_id,raw); finish(state['job'],state['request'],raw,False); del active[o.request_id]

if __name__=='__main__': main()
