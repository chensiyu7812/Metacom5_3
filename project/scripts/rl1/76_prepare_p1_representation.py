#!/usr/bin/env python3
"""Freeze P1 train/dev inputs and 72 diagnostic slots; no G/J or training.

Run with the existing paper1 Python environment and CUDA_VISIBLE_DEVICES=0.
Memory retrieval is rebuilt after source exclusions; old RS ranking is retained.
"""
import argparse
from collections import Counter, defaultdict
from dataclasses import asdict
from functools import lru_cache
import json
from pathlib import Path
import sys
import time

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.io import sha256_file
from metacom_pm.paper1.data.memory_source import load_sanitized_runtime_users
from metacom_pm.paper1.multi_view_memory import load_accepted_multi_view_units
from metacom_pm.paper1.embeddings.bge_m3 import BgeM3Encoder
from metacom_pm.rl1.data import ranked_memory
from metacom_pm.rl1.evidence import prefix_from_dict
from metacom_pm.rl1.schema import EpisodeSpec,Resource,HEADS,PLANS,digest
from metacom_pm.rl1.source_repair import repaired_as_of_memory,validate_overlay
from metacom_pm.rl1.render import Renderer
from metacom_pm.rl1.representation import AttributedRenderer,attributed_resource
from metacom_pm.rl1.env import ResourceEnv

OUT=PROJECT/'outputs/pm_rl1/completion_20260930_v2/P1'
MODEL=Path('/opt/tokkio-data0/tokkio_models/huggingface/hub/models--NousResearch--Meta-Llama-3.1-8B-Instruct/snapshots/d10aef7999a2b5ba950ab3974312feeedbfe0b77')


def save(out,name,value):
    path=out/name
    with path.open('x') as f:f.write(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def main(out):
    import torch
    from transformers import AutoTokenizer,AutoConfig
    start=time.monotonic()
    if (not torch.cuda.is_available() or torch.cuda.device_count()!=1 or
            'A4500' not in torch.cuda.get_device_name(0)):
        raise RuntimeError('bind A4500 alone for the existing frozen retrieval encoder')
    if (out/'renderer_freeze.json').exists():raise RuntimeError('P1 inputs already frozen')
    source=PROJECT/'data/paper1_public_memory/es_memeval_public_sanitized_runtime_artifact_v1.json'
    units_path=PROJECT/'data/paper1_public_memory/es_memeval_public_multi_view_session_results_v1.jsonl'
    prior=PROJECT/'outputs/pm_rl1/executor_coverage_20260929_v1/episode_specs_private.json'
    original=json.loads(prior.read_text());assert len(original)==114
    assert {s['prefix']['split'] for s in original}=={'train','dev'}
    overlay=json.loads((out/'source_overlay_private.json').read_text())
    registry=json.loads((out/'source_review_registry.json').read_text())
    assert registry['source_sha256']==sha256_file(units_path) and registry['raw_sha256']==sha256_file(source)
    users=load_sanitized_runtime_users(source);user_map={u.owner_id:u for u in users}
    raw_users={u['owner_id']:u for u in json.loads(source.read_text())['users']}
    units=load_accepted_multi_view_units(units_path,users=users)
    validate_overlay(overlay,units=units,users=user_map)
    unit_map={u.memory_id:u.model_dump(mode='json') for u in units};by_owner=defaultdict(list)
    for u in units:by_owner[u.owner_id].append(u)
    me_reviews={r['unit_id']:r for r in registry['me']}
    tok=AutoTokenizer.from_pretrained(MODEL,local_files_only=True)
    @lru_cache(maxsize=32768)
    def count(text):return len(tok.encode(text,add_special_tokens=False))
    renderer_args=dict(count_text=count,
        count_chat=lambda messages:len(tok.apply_chat_template(messages,tokenize=True,add_generation_prompt=True)),
        tokenizer_identity=digest(dict(tokenizer=sha256_file(MODEL/'tokenizer.json'),template=tok.chat_template)),
        context_limit=AutoConfig.from_pretrained(MODEL,local_files_only=True).max_position_embeddings)
    old_renderer=Renderer(**renderer_args);new_renderer=AttributedRenderer(**renderer_args)
    prefixes=[prefix_from_dict(s['prefix']) for s in original]
    projections=[repaired_as_of_memory(p,user=user_map[p.owner_id],units=by_owner[p.owner_id],
        token_counter=count,overlay=overlay) for p in prefixes]
    unique={c.candidate_id:c for group,_ in projections for rows in group.values() for c in rows}
    print(json.dumps(dict(stage='retrieval',prefixes=len(prefixes),candidate_documents=len(unique))),flush=True)
    encoder=BgeM3Encoder();ids=sorted(unique)
    # BgeM3Encoder.encode checks untruncated lengths and fails above 8192.
    text_batches=[[unique[i].content for i in ids],[p.query for p in prefixes]]
    vectors=dict(zip(ids,encoder.encode(text_batches[0])));queries=encoder.encode(text_batches[1])
    retrieval=dict(version='pm-rl1-p1-source-repaired-fixed-bge-v1',
        binding=asdict(encoder.binding),runtime=asdict(encoder.runtime_identity),
        old_RS_inventory_sha256=sha256_file(prior),source_overlay_identity=digest(overlay),
        document_encoding='old canonical content for stable ranking; new attributed delivery after ranking',
        ranking='frozen cosine/candidate_id; filter before ranking; no ancestor fallback',
        representation_code_sha256=sha256_file(PROJECT/'src/metacom_pm/rl1/representation.py'))
    specs=[];old_delivery=[];capacities=[];changes=[]
    for index,(p,(group,receipt),query,previous) in enumerate(zip(prefixes,projections,queries,original)):
        inventory=ranked_memory(p,group,vectors,query)
        inventory['RS']=tuple(Resource(**dict(r,source_ids=tuple(r['source_ids']))) for r in previous['inventory'][0])
        raw_inventory=tuple(tuple(inventory[h][:4]) for h in HEADS)
        attributed=[]
        sessions={s['session_id']:s for s in raw_users[p.owner_id]['sessions']}
        for items in raw_inventory:
            head=[]
            for r in items:
                u=unit_map[r.source_ids[0]] if r.head in ('MP','ME') else None
                s=sessions[u['source_session_id']] if u else None
                head.append(attributed_resource(r,unit=u,session=s,
                    me_review=me_reviews.get(u['memory_id']) if u else None,count_text=count))
            attributed.append(tuple(head))
        args=dict(prefix=p,retrieval_identity=digest(retrieval),executor_identity='P1_NOT_LOADED',
            judge_identity='P1_NO_REWARD',draw_identity='p1-diagnostic-v1')
        spec=EpisodeSpec(inventory=tuple(attributed),**args)
        old=EpisodeSpec(inventory=raw_inventory,**args)
        specs.append(asdict(spec));old_delivery.append(asdict(old))
        new_mask=ResourceEnv(spec,new_renderer).observe().initial_plan_mask
        old_mask=ResourceEnv(old,old_renderer).observe().initial_plan_mask
        plans=[v for v,ok in zip(PLANS,new_mask) if ok]
        capacities.append(dict(index=index,owner=p.owner_id,split=p.split,prefix_identity=p.identity,
            inventory=[len(h) for h in attributed],reachable=len(plans),old_delivery_reachable=sum(old_mask),
            initial_plan_mask=list(new_mask),old_initial_plan_mask=list(old_mask),
            three=sum(sum(v)==3 for v in plans),four=sum(sum(v)==4 for v in plans),
            same_head_repeat=sum(max(v)>1 for v in plans),
            all_four_heads=(1,1,1,1) in plans,
            first_head_reachable={h:tuple(int(j==i) for j in range(4)) in plans for i,h in enumerate(HEADS)},
            resource_costs=[dict(counts=v,tokens=new_renderer.cost(spec,v)) for v in plans]))
        changes.append(dict(index=index,prefix_identity=p.identity,projection=receipt,
            old_candidate_ids=[[r['candidate_id'] for r in h] for h in previous['inventory']],
            new_candidate_ids=[[r.candidate_id for r in h] for h in raw_inventory]))
    # Two per dev owner; known role-risk case first, then content-independent hash.
    selected=[]
    for owner in sorted({p.owner_id for p in prefixes if p.split=='dev'}):
        choices=[i for i,p in enumerate(prefixes) if p.split=='dev' and p.owner_id==owner]
        risk=[i for i in choices if any(t.role=='supporter' and ('my mother' in t.content.lower() or 'my mom' in t.content.lower()) for t in prefixes[i].turns)]
        ordered=sorted(choices,key=lambda i:digest(['p1-dev-diagnostics-v1',prefixes[i].identity]))
        selected.extend((sorted(risk)[:1]+[i for i in ordered if i not in risk])[:2])
    assert len(selected)==6
    conditions=[];missing=[]
    for index in selected:
        cap=capacities[index];raw=old_delivery[index];p=prefixes[index]
        common={v for v,a,b in zip(PLANS,cap['initial_plan_mask'],cap['old_initial_plan_mask']) if a and b}
        memory=[(raw['inventory'][i][0]['similarity'],i) for i in (1,2,3)
                if raw['inventory'][i] and tuple(int(j==i) for j in range(4)) in common]
        best=min(memory,key=lambda x:(-x[0],x[1]))[1] if memory else None
        plans={'OFF':(0,0,0,0),'RS':(1,0,0,0),
               'MEMORY':tuple(int(j==best) for j in range(4)) if best is not None else None}
        for condition,plan in plans.items():
            if plan is None or plan not in common:
                missing.append(dict(index=index,condition=condition,reason='no_common_legal_plan'));continue
            for label,entry,renderer in [('old',raw,old_renderer),('new',specs[index],new_renderer)]:
                spec=EpisodeSpec(**dict(entry,prefix=p,inventory=tuple(tuple(Resource(**dict(r,source_ids=tuple(r['source_ids']))) for r in h) for h in entry['inventory'])))
                messages=renderer.messages(spec,plan)
                conditions.append(dict(index=index,prefix_identity=p.identity,owner=p.owner_id,
                    condition=condition,counts=plan,representation=label,messages=messages,
                    messages_identity=digest(messages),renderer_identity=renderer.identity,
                    resource_tokens=renderer.cost(spec,plan),candidate_ids=[r.candidate_id for h,n in zip(spec.inventory,plan) for r in h[:n]]))
    assert len(conditions)*2<=72
    summary=dict(prefixes=len(specs),total_reachable=sum(c['reachable'] for c in capacities),
        prefixes_with_three=sum(c['three']>0 for c in capacities),prefixes_with_four=sum(c['four']>0 for c in capacities),
        prefixes_with_same_head_repeat=sum(c['same_head_repeat']>0 for c in capacities),
        all_four_heads_prefixes=sum(c['all_four_heads'] for c in capacities),
        first_head_unreachable={h:sum(not c['first_head_reachable'][h] for c in capacities) for h in HEADS},
        counts_by_split=dict(Counter(p.split for p in prefixes)),
        note='New actual token costs; not efficacy. Old-delivery comparison uses the same repaired candidate inventory.')
    for name,obj in [('episode_specs_private.json',specs),('old_delivery_specs_private.json',old_delivery),
        ('source_projection_private.json',changes),('capacity_prefix_private.json',capacities),('capacity.json',summary),
        ('diagnostic_manifest.json',dict(version='p1-fixed-72-representation-diagnostic-v1',
            selection='two per dev owner; include known mother-role risk, remaining SHA256; no response selection',
            selected_indices=selected,memory_selection='highest frozen top1 similarity among common-legal MP/MS/ME; head-order tie',
            conditions=conditions,missing=missing,executors=['base','old_lora_epoch3'],
            response_slots=len(conditions)*2,interpretation='combined role/RS/source-representation development regression, not independent generalization'))]:save(out,name,obj)
    files={name:sha256_file(out/name) for name in ('episode_specs_private.json','old_delivery_specs_private.json',
        'source_projection_private.json','capacity_prefix_private.json','capacity.json','diagnostic_manifest.json',
        'source_overlay_private.json','source_review_registry.json')}
    save(out,'renderer_freeze.json',dict(status='P1_INPUTS_FROZEN_DIAGNOSTICS_PENDING',
        new_renderer_identity=new_renderer.identity,old_renderer_identity=old_renderer.identity,
        tokenizer_identity=renderer_args['tokenizer_identity'],resource_budget=2048,max_gets=4,
        retrieval=retrieval,files=files,source_files={str(p.relative_to(PROJECT)):sha256_file(p) for p in (source,units_path,prior)},
        feature_encoder='PlanAwareFeatureEncoder; V1 preserved; +70 public mask values',
        me_review_policy='24 source-grounded changes only in train/dev; all unreviewed action stages/results unknown',
        test_scope='No test semantic review or generated test responses; test projection not built in P1',
        seconds=time.monotonic()-start,generator_calls=0,judge_calls=0,api_usd=0))
    print(json.dumps(dict(stage='frozen',**summary,diagnostic_slots=len(conditions)*2)),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,default=OUT)
    main(parser.parse_args().out)
