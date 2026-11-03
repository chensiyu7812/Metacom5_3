#!/usr/bin/env python3
"""One bound real BGE load for a prepared initial pool; no G/J/optimizer.

Uses original CUDA deployment, pinned weights and verified complete token
blocks. This is reusable real policy input preparation, not reward validation.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import sys
import time

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.rl1.schema import digest, PublicTurn
from metacom_pm.rl1.organized_encoding import LoadedBGEBlocks, BlockCache, EncodedHeadView
from metacom_pm.rl1.organized_features import FullTextFeatures
from metacom_pm.rl1.organized_policy_interface import HeadObservation, ReadText, no_text
from metacom_pm.rl1.local_gpu_guard import LocalGPUCheck
from metacom_pm.rl1.supervised_learning import save_json


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def run(package, output):
    manifest=json.loads((package/'PACKAGE_MANIFEST.json').read_text())
    for name,h in manifest.items():
        if Path(name).is_absolute() or '..' in Path(name).parts or sha(package/name)!=h:raise ValueError('prepared package changed')
    config=json.loads((package/'CONFIG.json').read_text())
    blocks=json.loads((package/'BLOCKS_PRIVATE.json').read_text())
    states=json.loads((package/'OBSERVATIONS_PRIVATE.json').read_text())
    from metacom_pm.paper1.embeddings.bge_m3 import FROZEN_BGE_M3_BINDING, _load_model
    if asdict(FROZEN_BGE_M3_BINDING)!=config['bge_binding']:raise ValueError('original BGE binding changed')
    if any(os.environ.get(k)!='1' for k in ('HF_HUB_OFFLINE','TRANSFORMERS_OFFLINE')):raise ValueError('offline loader required')
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    batch_size=4 if max(map(len,blocks.values()))<=2048 else 1
    protocol=dict(package_identity=digest(manifest),script_sha256=sha(__file__),encoder_identity=config['encoder_identity'],
        max_loads=1,blocks_identity=digest(blocks),unique_blocks=len(blocks),batch_size=batch_size,
        operations=['complete_public_token_block_encoding'],G_calls=0,J_calls=0,training_updates=0,
        authorization=dict(source='current conversation 2026-11-03',
            instruction='好，也尽快推进，正确通过检查，开始RL学习',
            interpretation='necessary local real input preparation for the requested RL continuation'))
    save_json(output/'PROTOCOL.json',protocol)
    guard=LocalGPUCheck(config['gpu_uuid'],config['runtime'],output/'gpu_checks',latest_snapshot=True)
    guard.check()
    save_json(output/'LOAD_STARTED.json',dict(protocol_identity=digest(protocol),timestamp=time.time()))
    started=time.monotonic()
    import torch
    with torch.random.fork_rng(devices=[]):model,runtime=_load_model(FROZEN_BGE_M3_BINDING)
    if asdict(runtime)!=config['bge_runtime']:raise ValueError('actual BGE runtime changed')
    loaded=LoadedBGEBlocks(model,binding=FROZEN_BGE_M3_BINDING,runtime=runtime,
        expected_tokenizer_identity=config['bge_tokenizer_identity'])
    if loaded.identity!=config['encoder_identity']:raise ValueError('actual block encoder identity changed')
    save_json(output/'LOAD_COMPLETED.json',dict(binding=asdict(FROZEN_BGE_M3_BINDING),runtime=asdict(runtime),
        encoder_identity=loaded.identity,seconds=time.monotonic()-started))
    print(json.dumps(dict(status='REAL_BGE_LOADED',blocks=len(blocks))),flush=True)
    cache=BlockCache(output/'blocks.sqlite',encoder_identity=loaded.identity,dimension=1024,native_window=8192)
    calls=0
    def invoke(xs):
        nonlocal calls
        guard.check(own_pid=os.getpid());calls+=1
        result=loaded(xs)
        if calls%20==0:print(json.dumps(dict(physical_BGE_batches=calls)),flush=True)
        return result
    vectors,stats=cache.encode(list(blocks.values()),invoke=invoke,encoder_identity=loaded.identity,batch_size=batch_size)
    del vectors
    bt=model.tokenizer
    planner=FullTextFeatures(encode_tokens=lambda s:bt.encode(s,add_special_tokens=False,truncation=False),
        add_special_tokens=bt.build_inputs_with_special_tokens,native_window=8192,
        special_tokens=bt.num_special_tokens_to_add(pair=False),tokenizer_identity=config['bge_tokenizer_identity'],
        encoder_identity=loaded.identity,dimension=1024)
    if planner.identity!=config['feature_identity']:raise ValueError('prepared and actual feature planner differ')
    def cached_only(xs):raise ValueError('feature assembly requested an unplanned block')
    full=EncodedHeadView(planner,cache,invoke=cached_only,encoder_identity=loaded.identity)
    hidden=EncodedHeadView(planner,cache,invoke=cached_only,encoder_identity=loaded.identity,without_text=True)
    features={}
    for key,row in states.items():
        raw=row['observation'];obs=HeadObservation(**(raw|dict(
            current_prefix=tuple(PublicTurn(**t) for t in raw['current_prefix']),
            acquired=tuple(ReadText(**x) for x in raw['acquired']),
            **{k:tuple(raw[k]) for k in ('counts','remaining_items','next_input_tokens','action_mask')})))
        if key!=digest(asdict(obs)) or planner.plan(obs)!=row['plan']:raise ValueError('observation/whole-token plan drift')
        x,mask=full.sequential(obs);nx,nmask=hidden.sequential(no_text(obs))
        if mask!=nmask or any(nx[1024:5120]):raise ValueError('NoText visibility changed')
        features[key]=dict(prefix_identity=row['prefix_identity'],features=x,NoText_features=nx,mask=mask,
            full_view_identity=full.identity,NoText_view_identity=hidden.identity)
    save_json(output/'FEATURES_PRIVATE.json',features)
    result=dict(status='REAL_INITIAL_POLICY_INPUTS_ENCODED',source_package=str(package.resolve()),
        source_package_identity=digest(manifest),real_BGE_loads=1,**stats,observations=len(features),
        feature_dimension=planner.feature_dimension,full_view_identity=full.identity,NoText_view_identity=hidden.identity,
        BGE_identity=loaded.identity,G_calls=0,J_calls=0,BC_checkpoints=0,natural_updates=0,
        no_text_acquired_components_zero=True,all_tokens_preserved=True,seconds=time.monotonic()-started)
    save_json(output/'RESULTS.json',result)
    save_json(output/'OUTPUT_MANIFEST.json',{str(p.relative_to(output)):sha(p) for p in output.rglob('*') if p.is_file()})
    print(json.dumps(result),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--package',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.package,a.output)
