#!/usr/bin/env python3
"""Encode 24 already-visible train observations with real frozen BGE-M3.

No generator/judge calls, terminal feedback or policy learning.
"""
from dataclasses import asdict
import json
from pathlib import Path
import sys
import time

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.io import sha256_file
from metacom_pm.paper1.embeddings.bge_m3 import BgeM3Encoder
from metacom_pm.rl1.schema import Observation,PublicTurn,AcquiredText,CandidateMetadata,digest
from metacom_pm.rl1.observation_features import ObservedFeatureEncoder,make_actor_critic

OUT=PROJECT/'outputs/pm_rl1/measurement_resolution_20260929_v1'
PILOT=PROJECT/'outputs/pm_rl1/measurement_pilot_20260928_v1'


def observation(raw):
    return Observation(**(raw|dict(current_prefix=tuple(PublicTurn(**t) for t in raw['current_prefix']),
        acquired=tuple(AcquiredText(**a) for a in raw['acquired']),counts=tuple(raw['counts']),
        remaining_items=tuple(raw['remaining_items']),metadata=tuple(tuple(CandidateMetadata(**m) if m else None for m in h) for h in raw['metadata']),
        action_mask=tuple(raw['action_mask']),initial_plan_mask=tuple(raw['initial_plan_mask']))))


def main():
    import numpy as np
    import torch
    started=time.monotonic();dest=OUT/'public_observation_feature_probe.json'
    if dest.exists():raise RuntimeError('preserve existing feature probe')
    if not torch.cuda.is_available() or torch.cuda.device_count()!=1 or 'A4500' not in torch.cuda.get_device_name(0):
        raise RuntimeError('bind free A4500 for this embedding probe')
    if torch.cuda.mem_get_info(0)[0]<6*1024**3:raise RuntimeError('insufficient free encoder memory')
    specs=json.loads((PILOT/'episode_specs_private.json').read_text())
    assert all(s['prefix']['split']=='train' for s in specs)
    traces=json.loads((PILOT/'mechanical_traces.json').read_text());assert len(traces)==12
    bge=BgeM3Encoder();load_started=time.monotonic();runtime=asdict(bge.runtime_identity)
    load_seconds=time.monotonic()-load_started;calls=[]
    def encode(texts):
        calls.append(dict(text_hashes=[digest(t) for t in texts],count=len(texts)))
        return bge.encode(texts)
    encoder=ObservedFeatureEncoder(encode,embedding_dimension=1024,
        text_encoder_identity=digest(dict(binding=asdict(bge.binding),runtime=runtime)),resource_budget=2048)
    rows=[];features=[];masks=[];encoding_started=time.monotonic()
    for trace in traces:
        for index,raw in enumerate(trace['observations']):
            obs=observation(raw);tick=time.monotonic();r=encoder.encode(obs);torch.cuda.synchronize()
            features.append(r.values);masks.append(r.action_mask)
            rows.append(dict(pilot_index=trace['pilot_index'],state_index=index,counts=list(obs.counts),
                visible_acquired_items=len(obs.acquired),feature_identity=digest(r.values),
                feature_dimension=len(r.values),encoding_seconds=time.monotonic()-tick))
    encoding_seconds=time.monotonic()-encoding_started
    # A cached acquired vector must not affect the same initial observation.
    first=encoder.encode(observation(traces[0]['observations'][0]))
    assert first.values==features[0]
    torch.manual_seed(17);model=make_actor_critic(encoder.feature_dimension)
    with torch.no_grad():distribution,values=model(torch.tensor(features),torch.tensor(masks))
    assert torch.isfinite(values).all() and (distribution.probs[~torch.tensor(masks)]==0).all()
    array_path=OUT/'public_observation_features.npy';np.save(array_path,np.asarray(features,dtype=np.float32),allow_pickle=False)
    result=dict(status='REAL_PUBLIC_OBSERVATION_ENCODER_PROBE_NOT_TRAINED_PM',rows=rows,
        observations=len(rows),embedding_texts=sum(c['count'] for c in calls),encoder_calls=len(calls),
        text_call_audit=calls,encoder_identity=encoder.identity,bge_binding=asdict(bge.binding),bge_runtime=runtime,
        gpu=torch.cuda.get_device_name(0),load_seconds=load_seconds,encoding_seconds=encoding_seconds,
        total_process_seconds=time.monotonic()-started,feature_dimension=encoder.feature_dimension,
        actor_parameter_count=sum(p.numel() for p in model.parameters()),all_masked_probabilities_zero=True,
        acquired_vector_cache_does_not_change_initial_features=True,parameter_updates=0,
        formal_feature_freeze=False,LLM_generation_calls=0,judge_calls=0,API_usd=0,
        feature_sha256=sha256_file(array_path),trace_sha256=sha256_file(PILOT/'mechanical_traces.json'),
        module_sha256=sha256_file(PROJECT/'src/metacom_pm/rl1/observation_features.py'),runner_sha256=sha256_file(Path(__file__)))
    dest.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('observations','embedding_texts','load_seconds','encoding_seconds','feature_dimension','actor_parameter_count','parameter_updates')}))


if __name__=='__main__':main()
