#!/usr/bin/env python3
"""Prepare/check offline; execute only an explicitly approved fixed G/BGE stage.

The private package contains four existing train prefixes, no held-out cases.
Neither preparation nor checking loads model weights or contacts a provider.
"""
import argparse
from dataclasses import asdict,replace
from functools import lru_cache
import json
import os
from pathlib import Path
import sys

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.calibration_workflow import stamp,verify_identity
from metacom_pm.rl1.evidence import prefix_from_dict
from metacom_pm.rl1.learning_preparation import TerminalCandidate
from metacom_pm.rl1.local_backend import local_protocol,LOCAL,check_static,authorize
from metacom_pm.rl1.local_integration import select_cases,verify_cases,run_probe
from metacom_pm.rl1.observation_features import PlanAwareFeatureEncoder
from metacom_pm.rl1.representation_direct import DirectReplyRenderer
from metacom_pm.rl1.schema import EpisodeSpec,Resource,digest
from metacom_pm.rl1.supervised_learning import save_json


def read(path):return json.loads(Path(path).read_text())


def spec_from(raw):
    return EpisodeSpec(**dict(raw,prefix=prefix_from_dict(raw['prefix']),inventory=tuple(
        tuple(Resource(**dict(r,source_ids=tuple(r['source_ids']))) for r in h) for h in raw['inventory'])))


def renderer_for(runtime,tokenizer_identity):
    from transformers import AutoTokenizer
    tokenizer=AutoTokenizer.from_pretrained(runtime['model_dir'],local_files_only=True)
    @lru_cache(maxsize=32768)
    def count(text):return len(tokenizer.encode(text,add_special_tokens=False))
    class CachedRenderer(DirectReplyRenderer):
        def __init__(self,**kwargs):super().__init__(**kwargs);self.costs={};self.fit_cache={}
        def cost(self,s,c):
            key=(s.identity,tuple(c))
            if key not in self.costs:self.costs[key]=super().cost(s,c)
            return self.costs[key]
        def fits(self,s,c):
            key=(s.identity,tuple(c))
            if key not in self.fit_cache:self.fit_cache[key]=super().fits(s,c)
            return self.fit_cache[key]
    return CachedRenderer(count_text=count,
        count_chat=lambda ms:len(tokenizer.apply_chat_template(ms,tokenize=True,add_generation_prompt=True)),
        tokenizer_identity=tokenizer_identity,context_limit=runtime['policy']['context_limit'])


def token_preflight(observations,requests,renderer,bge_dir,binding):
    from transformers import AutoTokenizer
    tokenizer=AutoTokenizer.from_pretrained(bge_dir,local_files_only=True)
    batches=[]
    def capture(texts):
        # Only discover public strings using the production projection. These
        # disposable zeros are never saved or offered as measured BGE features.
        batches.append(list(texts));return [[0.]*binding['embedding_dimension'] for _ in texts]
    encoder=PlanAwareFeatureEncoder(capture,embedding_dimension=binding['embedding_dimension'],
        text_encoder_identity='INPUT_DISCOVERY_ONLY')
    for obs in observations:encoder.encode(obs)
    lengths=[len(tokenizer.encode(t,add_special_tokens=True)) for batch in batches for t in batch]
    inputs=[renderer.count_chat(r['messages']) for r in requests]
    if len(batches)>8 or max(lengths)>binding['max_seq_length']:raise ValueError('BGE input exceeds fixed no-truncation scope')
    if max(inputs)>=renderer.context_limit:raise ValueError('G prompt leaves no native generation context')
    return dict(observations=len(observations),embedding_batches=len(batches),embedding_texts=len(lengths),
        BGE_token_lengths=lengths,BGE_max_tokens=max(lengths),BGE_context=binding['max_seq_length'],
        G_prompt_token_lengths=inputs,G_context=renderer.context_limit,
        text_discovery_identity=digest(batches),model_loads=0,model_inference=0,synthetic_vectors_saved=False)


def prepare(root):
    if root.exists():raise ValueError('package already exists; use check, never overwrite a prepared stage')
    q=PROJECT/'outputs/pm_rl1'
    paths=dict(executor=q/'completion_20260930_v2/P2/executor_freeze.json',
        renderer=q/'completion_20260930_v2/P1/renderer_freeze.json',
        specs=q/'completion_20260930_v2/P1/episode_specs_private.json',
        candidates=q/'completion_preparation_20261022/bc_terminal_candidates_private.json',
        static=q/'learning_execution_20261022_v1/LOCAL_BACKEND_STATIC_PREFLIGHT.json',
        runtime_reference=q/'judge_selection_preparation_20261014_v1/four_head_diagnostic_preparation_20261020_v1/protocol.json')
    freeze=read(paths['executor']);rf=read(paths['renderer']);prior=read(paths['static']);ref=read(paths['runtime_reference'])
    if sha256_file(paths['specs'])!=rf['files']['episode_specs_private.json']:raise ValueError('P1 source changed')
    if (sha256_file(paths['executor'])!=prior['executor_freeze_sha256']
            or sha256_file(paths['runtime_reference'])!=prior['diagnostic_reference_sha256']):
        raise ValueError('original runtime metadata changed')
    candidates=[TerminalCandidate(**dict(x,counts=tuple(x['counts']))) for x in read(paths['candidates'])]
    if len(candidates)!=336 or any(c.split!='train' for c in candidates):raise ValueError('original train pool changed')
    renderer=renderer_for(freeze['primary_runtime'],rf['tokenizer_identity'])
    if renderer.identity!=freeze['renderer_identity']:raise ValueError('renderer identity changed')
    wanted={c.prefix_identity for c in candidates};episodes={}
    for raw in read(paths['specs']):
        prefix=prefix_from_dict(raw['prefix'])
        if prefix.identity not in wanted:continue
        s=replace(spec_from(raw),executor_identity=freeze['primary_runtime']['identity'],
            draw_identity=freeze['terminal_draw_identity'])
        episodes[s.prefix.identity]=(s,renderer)
    cases=select_cases(candidates,episodes);observations,requests=verify_cases(cases,episodes)
    preflight=token_preflight(observations,requests,renderer,ref['bge_local_dir'],ref['bge_binding'])
    assets={p:v['sha256'] for p,v in prior['checked_files'].items()}
    source_files=list((PROJECT/'src/metacom_pm/rl1').glob('*.py'))+[Path(__file__),
        PROJECT/'scripts/rl1/92_run_p2_common_pool.py',PROJECT/'src/metacom_pm/paper1/embeddings/bge_m3.py']
    assets.update({str(p.resolve()):sha256_file(p) for p in source_files+list(paths.values())})
    protocol=local_protocol(scope=LOCAL,runtime=freeze['primary_runtime'],bge_binding=ref['bge_binding'],
        bge_runtime=ref['bge_expected_runtime'],assets=assets,packages=prior['package_metadata'],
        gpu_uuid=ref['approval_scope']['gpu_uuid'],request_ids=[r['request_id'] for r in requests],
        max_embedding_batches=8,context_identity=digest(cases))
    checks=check_static(protocol)
    context=dict(specs=[asdict(episodes[c['prefix_identity']][0]) for c in cases],
        tokenizer_identity=rf['tokenizer_identity'],bge_local_dir=ref['bge_local_dir'])
    ready=stamp(dict(status='READY_FOR_SCOPED_LOCAL_APPROVAL_NOT_EXECUTED',protocol_identity=protocol['identity'],
        heads=[c['head'] for c in cases],train_prefixes=4,fixed_requests=8,max_G_loads=1,max_BGE_loads=1,
        max_G_generations=8,max_BGE_batches=8,API_calls=0,API_cost_usd='0',training_updates=0,human_dispatch=0,
        static_checks=checks,token_preflight=preflight,original_runtime=freeze['primary_runtime']['identity'],
        judge_qualification_required=False,judge_qualification_granted=False,
        old_diagnostic_authorization_inherited=False,live_integration_complete=False,
        estimated_generation_watchdog_seconds=8*freeze['primary_runtime']['policy']['timeout_seconds'],
        timing_limit='Cooperative per-generation watchdog; not a hard wall deadline or a 128/384 throughput decision.'))
    root.mkdir(parents=True,mode=0o700)
    files=dict(protocol=protocol,cases=cases,context=context,READY=ready)
    for name,value in files.items():save_json(root/(name+'.json'),value)
    save_json(root/'PACKAGE.json',stamp(dict(protocol_identity=protocol['identity'],
        files={name+'.json':sha256_file(root/(name+'.json')) for name in files})))
    return ready


def load_package(root):
    manifest=read(root/'PACKAGE.json');verify_identity(manifest)
    if set(manifest['files'])!={'protocol.json','cases.json','context.json','READY.json'}:
        raise ValueError('package membership changed')
    for name,sha in manifest['files'].items():
        if sha256_file(root/name)!=sha:raise ValueError('package changed: '+name)
    protocol=read(root/'protocol.json');verify_identity(protocol)
    if manifest['protocol_identity']!=protocol['identity']:raise ValueError('package protocol changed')
    return protocol,read(root/'cases.json'),read(root/'context.json')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['prepare','check','execute'])
    parser.add_argument('--package',type=Path,required=True)
    parser.add_argument('--approval',type=Path)
    args=parser.parse_args()
    if any(os.environ.get(k)!='1' for k in ('HF_HUB_OFFLINE','TRANSFORMERS_OFFLINE')):
        raise ValueError('set both model libraries offline; no download/fallback is allowed')
    if args.mode=='prepare':result=prepare(args.package)
    else:
        protocol,cases,context=load_package(args.package)
        approval=read(args.approval) if args.approval else None
        if args.mode=='execute':authorize(protocol,approval)
        checks=check_static(protocol)
        renderer=renderer_for(protocol['runtime'],context['tokenizer_identity'])
        episodes={s.prefix.identity:(s,renderer) for s in map(spec_from,context['specs'])}
        observations,requests=verify_cases(cases,episodes)
        token_check=token_preflight(observations,requests,renderer,context['bge_local_dir'],protocol['bge_binding'])
        if token_check!=read(args.package/'READY.json')['token_preflight']:raise ValueError('input tokenization changed')
        if args.mode=='check':result=dict(status='OFFLINE_PACKAGE_VERIFIED',protocol_identity=protocol['identity'],**checks)
        else:result=run_probe(protocol,cases,episodes,args.package/'run',approval=approval)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
