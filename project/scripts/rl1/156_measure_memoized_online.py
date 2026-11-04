#!/usr/bin/env python3
"""14 bounded real requests comparing exact legacy/memoized sequential paths."""
import argparse
from collections import Counter
from dataclasses import asdict
import json
import os
from pathlib import Path
import random
import statistics
import sys
import time

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.rl1.client_latency import ReferenceStreamClient,validate_trace
from metacom_pm.rl1.durable import save_json_once
from metacom_pm.rl1.latency_serving import RequestVectors,prepare_online,stream_generate,streaming_identity,stage
from metacom_pm.rl1.local_backend import check_static,load_generator
from metacom_pm.rl1.local_gpu_guard import LocalGPUCheck
from metacom_pm.rl1.memoized_online import RequestRenderer,MemoizedHeadSession
from metacom_pm.rl1.observation_features import make_actor_critic
from metacom_pm.rl1.online_materials import load_materials,read
from metacom_pm.rl1.organized_encoding import LoadedBGEBlocks
from metacom_pm.rl1.organized_features import FullTextFeatures
from metacom_pm.rl1.organized_feedback import generation_request
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.supervised_learning import save_json,file_sha

BASE=PROJECT/'outputs/pm_rl1'
PARENT=BASE/'client_latency_pilot_20261104_v1'
TRAIN=BASE/'organized_initial_training_20261103_v2'
VALIDATION=BASE/'memoized_online_validation_20261104_v1'
ACTIONS=[3,3,3,3,3,3,0]


def prepare(output):
    if output.exists(): raise ValueError('new output required')
    old=read(PARENT/'PROTOCOL.json')
    for root in (PARENT,VALIDATION):
        for name,h in read(root/'OUTPUT_MANIFEST.json').items():
            if file_sha(root/name)!=h: raise ValueError('parent validation changed')
    sources=dict(old['sources'])
    for name in ('memoized_online','online_materials'):
        f=PROJECT/'src/metacom_pm/rl1'/(name+'.py');sources[str(f.resolve())]=file_sha(f)
    for f in (Path(__file__),VALIDATION/'OUTPUT_MANIFEST.json',PARENT/'OUTPUT_MANIFEST.json'):
        sources[str(f.resolve())]=file_sha(f)
    for path,h in sources.items():
        if file_sha(path)!=h: raise ValueError('bound source changed')
    schedule=[dict(case=cid,path='memoized',repeat=-1,warmup=True) for cid in old['cases']]
    rng=random.Random(29)
    for repeat in range(3):
        cases=list(old['cases']);rng.shuffle(cases)
        for cid in cases:
            paths=['legacy','memoized'];rng.shuffle(paths)
            schedule.extend(dict(case=cid,path=path,repeat=repeat,warmup=False) for path in paths)
    for i,row in enumerate(schedule):row['slot']=f'memo_latency_{i:03d}'
    regime=dict(old['regime'],prior_warmups=2,repetitions_per_case_arm=3,
        renderer_cache='request-local exact-input memoization for memoized arm; legacy uncached; caches empty each request',
        stopped_observation='memoized arm reuses unchanged next-item metadata after STOP',
        memoized_code=sources[str((PROJECT/'src/metacom_pm/rl1/memoized_online.py').resolve())])
    body=dict(version='pmrl1-memoized-online-pilot-20261104-v1',cases=old['cases'],schedule=schedule,
        regime=regime,regime_identity=digest(regime),sources=sources,
        max_G_calls=14,max_BGE_batches=98,max_policy_forwards=98,G_loads=1,BGE_loads=1,
        output_directory=str(output.resolve()),ledger_sha256=old['ledger_sha256'],
        authorization='Current conversation 2026-11-04: 好的，按计划继续推进。综合考虑不同情况的收益最大化平衡点。',
        scope='free exact-semantics latency comparison only; no scorer or optimizer')
    output.mkdir(parents=True,mode=0o700);save_json(output/'PROTOCOL.json',dict(body,identity=digest(body)))
    print(json.dumps(dict(status='PREPARED',G_calls_upper=14,measured=12,warmups=2,API_cost_usd=0)),flush=True)


def run(output):
    p=read(output/'PROTOCOL.json')
    if p['identity']!=digest({k:v for k,v in p.items() if k!='identity'}) or p['output_directory']!=str(output.resolve()):
        raise ValueError('bound stage changed')
    for path,h in p['sources'].items():
        if file_sha(path)!=h: raise ValueError('source changed: '+path)
    if (output/'LOAD_STARTED.json').exists():raise ValueError('already entered; no automatic reload')
    if any(os.environ.get(k)!='1' for k in ('HF_HUB_OFFLINE','TRANSFORMERS_OFFLINE')):raise ValueError('offline loading required')
    c=read(TRAIN/'CONFIG.json');check_static(read(BASE/'organized_initial_generation_20261103_v2/PROTOCOL.json'))
    guard=LocalGPUCheck(c['gpu_uuid'],c['runtime'],output/'gpu_checks',latest_snapshot=True);guard.check()
    save_json_once(output/'LOAD_STARTED.json',dict(protocol_identity=p['identity'],unix_seconds=time.time()))
    import torch
    torch.set_num_threads(1);start=time.monotonic();generator=load_generator(c['runtime'])
    if digest(dict(generator.manifest,identity=generator.identity))!=digest(c['runtime']):raise ValueError('G runtime changed')
    save_json(output/'G_LOADED.json',dict(seconds=time.monotonic()-start,identity=generator.identity))
    from metacom_pm.paper1.embeddings.bge_m3 import FROZEN_BGE_M3_BINDING,_load_model
    guard.check(own_pid=os.getpid());start=time.monotonic();model,runtime=_load_model(FROZEN_BGE_M3_BINDING)
    if asdict(runtime)!=c['bge_runtime'] or asdict(FROZEN_BGE_M3_BINDING)!=c['bge_binding']:raise ValueError('BGE changed')
    bge=LoadedBGEBlocks(model,binding=FROZEN_BGE_M3_BINDING,runtime=runtime,expected_tokenizer_identity=c['bge_tokenizer_identity'])
    if bge.identity!=c['encoder_identity']:raise ValueError('encoder identity changed')
    save_json(output/'BGE_LOADED.json',dict(seconds=time.monotonic()-start,identity=bge.identity))
    _,catalogs,renderer=load_materials(TRAIN,prefix_ids=p['cases'].values(),tokenizer=generator.tokenizer)
    bt=model.tokenizer
    planner=FullTextFeatures(encode_tokens=lambda s:bt.encode(s,add_special_tokens=False,truncation=False),
        add_special_tokens=bt.build_inputs_with_special_tokens,native_window=8192,
        special_tokens=bt.num_special_tokens_to_add(pair=False),tokenizer_identity=c['bge_tokenizer_identity'],
        encoder_identity=bge.identity,dimension=1024)
    if planner.identity!=c['feature_identity']:raise ValueError('planner changed')
    with torch.random.fork_rng(devices=[]):torch.manual_seed(17);actor=make_actor_critic(planner.feature_dimension).eval()
    expected=read(PARENT/'EXPECTED_PRIVATE.json');history=read(BASE/'organized_initial_generation_20261103_v2/RESPONSES_PRIVATE.json')
    counters=Counter();entered=set();slots={r['slot']:r for r in p['schedule']}
    def encode(blocks):
        if counters['BGE_batches']>=p['max_BGE_batches']:raise ValueError('BGE scope exhausted')
        counters['BGE_batches']+=1;return bge(blocks)
    def decide(values,mask,planned):
        if counters['policy_forwards']>=p['max_policy_forwards']:raise ValueError('policy scope exhausted')
        counters['policy_forwards']+=1
        with torch.inference_mode():dist,value=actor(torch.tensor(values,dtype=torch.float32),torch.tensor(mask))
        if not torch.isfinite(value) or not mask[planned]:raise ValueError('invalid actor computation')
        return planned
    def service(row,emit):
        if row!=slots.get(row['slot']) or row['slot'] in entered:raise ValueError('unbound/repeated request')
        entered.add(row['slot']);view=RequestVectors(planner,encode);catalog=catalogs[p['cases'][row['case']]]
        if row['path']=='legacy':
            req,events=prepare_online(catalog,renderer,actions=ACTIONS,sequential_view=view,decide=decide,
                executor_identity=streaming_identity(generator.identity),draw_identity=row['slot']);cache_stats=None
        else:
            events=[];memo=RequestRenderer(renderer)
            with stage(events,'initial_observation'):session=MemoizedHeadSession(catalog,memo);obs=session.observe()
            for planned in ACTIONS:
                with stage(events,'online_encoding'):values,mask=view.sequential(obs)
                with stage(events,'actor_forward_scripted_action'):action=decide(values,mask,planned)
                with stage(events,'retrieval_and_observation'):obs=session.step(action)
            with stage(events,'terminal_render'):terminal=session.terminal(executor_identity=streaming_identity(generator.identity),draw_identity=row['slot'])
            with stage(events,'request_binding'):req=generation_request(terminal)
            cache_stats=memo.stats
        old=expected[row['case']+'/MS6_sequential_replay']
        if req['messages']!=old['messages'] or req['provenance']!=old['provenance']:raise ValueError('actual selected source changed')
        if counters['G_calls']>=p['max_G_calls']:raise ValueError('G scope exhausted')
        counters['G_calls']+=1
        with stage(events,'G_tokenize_transfer_stream_decode'):raw=stream_generate(generator,req,emit)
        previous=history[old['request_id']]
        return dict(raw,request=req,stages=events,cache_stats=cache_stats,online_BGE_batches=view.calls,
            historical_reply_identical=raw['text']==previous['text'],historical_token_ids_identical=raw['output_token_ids']==previous['output_token_ids'])
    client=ReferenceStreamClient(service,regime_identity=p['regime_identity'],technical_timeout_seconds=900.)
    try:
        for row in p['schedule']:
            guard.check(own_pid=os.getpid());save_json_once(output/(row['slot']+'.started.json'),row)
            trace,raw=client.measure(row,trace_id=row['slot'])
            save_json_once(output/(row['slot']+'.result.private.json'),dict(schedule=row,trace=trace,raw=raw))
            print(json.dumps(dict(slot=row['slot'],case=row['case'],path=row['path'],warmup=row['warmup'],status=trace['status'],
                ttft=trace['ttft_seconds'],completion=trace['completion_seconds'])),flush=True)
            if trace['status']!='natural_stop':raise RuntimeError('incomplete retained; no retry')
    finally:
        client.close();save_json_once(output/'COUNTERS.json',dict(counters))
    rows=[read(output/(r['slot']+'.result.private.json')) for r in p['schedule']]
    for r in rows:
        validate_trace(r['trace'])
        if not r['raw']['historical_reply_identical'] or not r['raw']['historical_token_ids_identical']:raise ValueError('reply drift retained')
    groups={};paired={}
    for cid in p['cases']:
        for path in ('legacy','memoized'):
            xs=[r for r in rows if r['schedule']['case']==cid and r['schedule']['path']==path and not r['schedule']['warmup']]
            groups[cid+'/'+path]={k:statistics.median(r['trace'][k] for r in xs) for k in ('ttft_seconds','completion_seconds')}
            groups[cid+'/'+path]['median_stage_seconds']={k:statistics.median(sum(e['seconds'] for e in r['raw']['stages'] if e['stage']==k) for r in xs) for k in {e['stage'] for e in xs[0]['raw']['stages']}}
        lookup={(r['schedule']['repeat'],r['schedule']['path']):r for r in rows if r['schedule']['case']==cid and not r['schedule']['warmup']}
        paired[cid]={k:statistics.median(lookup[(i,'memoized')]['trace'][k]-lookup[(i,'legacy')]['trace'][k] for i in range(3)) for k in ('ttft_seconds','completion_seconds')}
    summary=dict(status='COMPLETE',G_calls=14,measured_requests=12,warmups=2,groups=groups,paired_memoized_minus_legacy=paired,
        counters=dict(counters),all_historical_replies_and_tokens_identical=True,regime_identity=p['regime_identity'],
        API_cost_usd=0,natural_updates=0,population_p95_established=False)
    save_json(output/'SUMMARY.json',summary);save_json(output/'OUTPUT_MANIFEST.json',{str(f.relative_to(output)):file_sha(f) for f in output.rglob('*') if f.is_file()})
    print(json.dumps(summary),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=['prepare','run']);parser.add_argument('--output',type=Path,required=True)
    a=parser.parse_args();(prepare if a.mode=='prepare' else run)(a.output)
