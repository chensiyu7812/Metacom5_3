#!/usr/bin/env python3
"""Freeze six treatment categories per train/dev prefix before P2 generation.

CPU tokenizer only. These are authoring inputs, not accepted SFT targets or
measured rewards. Plan selection uses legal inventory and a fixed hash only.
"""
import argparse
from collections import Counter
from functools import lru_cache
import json
from pathlib import Path
import sys

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.schema import EpisodeSpec, Resource, PLANS, digest
from metacom_pm.rl1.evidence import prefix_from_dict
from metacom_pm.rl1.env import ResourceEnv
from metacom_pm.rl1.representation_direct import DirectReplyRenderer

ROOT=PROJECT/'outputs/pm_rl1/completion_20260930_v2'
MODEL=Path('/opt/tokkio-data0/tokkio_models/huggingface/hub/models--NousResearch--Meta-Llama-3.1-8B-Instruct/snapshots/d10aef7999a2b5ba950ab3974312feeedbfe0b77')
CATEGORIES=('OFF','single','cross_two','same_two','three','four')


def in_category(plan, category):
    total=sum(plan)
    return {'OFF':total==0,'single':total==1,
        'cross_two':total==2 and max(plan)==1,'same_two':total==2 and max(plan)==2,
        'three':total==3,'four':total==4}[category]


def main(root):
    from transformers import AutoTokenizer,AutoConfig
    p1=root/'P1';out=root/'P2';out.mkdir(exist_ok=True)
    if (out/'slot_freeze.json').exists():raise RuntimeError('P2 slots already frozen')
    closeout=json.loads((p1/'phase_closeout.json').read_text())
    assert closeout['status']=='COMPLETE_WITH_DISCLOSED_LIMITS'
    freezes=[p1/'renderer_freeze.json',p1/'interface_repair_v3/renderer_freeze.json']
    for path in freezes:
        assert sha256_file(path)==closeout['input_freezes'][str(path.relative_to(PROJECT))]
        freeze=json.loads(path.read_text())
        for name,value in freeze['files'].items():assert sha256_file(path.parent/name)==value,name
        for name,value in freeze['source_files'].items():assert sha256_file(PROJECT/name)==value,name
    tok=AutoTokenizer.from_pretrained(MODEL,local_files_only=True)
    @lru_cache(maxsize=32768)
    def count(text):return len(tok.encode(text,add_special_tokens=False))
    original_freeze=json.loads(freezes[0].read_text())
    renderer=DirectReplyRenderer(count_text=count,
        count_chat=lambda m:len(tok.apply_chat_template(m,tokenize=True,add_generation_prompt=True)),
        tokenizer_identity=original_freeze['tokenizer_identity'],
        context_limit=AutoConfig.from_pretrained(MODEL,local_files_only=True).max_position_embeddings)
    assert renderer.identity==closeout['active_renderer_identity']
    capacities=json.loads((p1/'capacity_prefix_private.json').read_text())
    specs=[EpisodeSpec(**dict(s,prefix=prefix_from_dict(s['prefix']),
        inventory=tuple(tuple(Resource(**dict(r,source_ids=tuple(r['source_ids']))) for r in h) for h in s['inventory'])))
        for s in json.loads((p1/'episode_specs_private.json').read_text())]
    slots=[];missing=[]
    for index,spec in enumerate(specs):
        assert spec.prefix.split in ('train','dev')
        mask=ResourceEnv(spec,renderer).observe().initial_plan_mask
        assert list(mask)==capacities[index]['initial_plan_mask']
        plans=[p for p,ok in zip(PLANS,mask) if ok];used=set()
        for category in CATEGORIES:
            choices=[p for p in plans if in_category(p,category)]
            if not choices:
                missing.append(dict(index=index,category=category,reason='no_legal_plan'));continue
            plan=min(choices,key=lambda p:digest(['pm-rl1-p2-executor-slot-v1',17,spec.prefix.identity,category,p]))
            if plan in used:
                missing.append(dict(index=index,category=category,reason='duplicate_plan'));continue
            used.add(plan)
            # Derive a real reachable path, including possible non-monotone token costs.
            paths={(0,0,0,0):()}
            for p in plans[1:]:
                predecessors=[(i,tuple(v-int(j==i) for j,v in enumerate(p))) for i in range(4) if p[i]]
                valid=[(i,prev) for i,prev in predecessors if prev in paths]
                if valid:
                    i,prev=min(valid);paths[p]=paths[prev]+(i+1,)
            env=ResourceEnv(spec,renderer)
            for action in paths[plan]:env.step(action,expected_state_hash=env.state_hash)
            assert env.observe().counts==plan
            messages=renderer.messages(spec,plan)
            slots.append(dict(slot_id=digest([spec.prefix.identity,plan,renderer.identity]),
                index=index,owner=spec.prefix.owner_id,split=spec.prefix.split,
                prefix_identity=spec.prefix.identity,category=category,counts=plan,
                acquisition_path=paths[plan],resource_tokens=renderer.cost(spec,plan),
                messages_identity=digest(messages),messages=messages,
                candidate_ids=[r.candidate_id for h,n in zip(spec.inventory,plan) for r in h[:n]]))
    # Twelve fixed behavior inputs: two per category and four per dev owner.
    # Include the known source-confirmed attribution failure; select the rest by hash.
    dev=[s for s in slots if s['split']=='dev'];owners=sorted({s['owner'] for s in dev})
    known=[s for s in dev if s['index']==102 and s['category']=='OFF']
    assert len(known)==1 and len(owners)==3
    selected=known.copy();owner_n=Counter([known[0]['owner']]);category_n=Counter(['OFF'])
    for category in CATEGORIES:
        while category_n[category]<2:
            candidates=[s for s in dev if s['category']==category and owner_n[s['owner']]<4 and s not in selected]
            chosen=min(candidates,key=lambda s:(owner_n[s['owner']],digest(['p2-behavior-input-v1',17,s['slot_id']])))
            selected.append(chosen);owner_n[chosen['owner']]+=1;category_n[category]+=1
    assert len(selected)==12 and set(owner_n.values())=={4}
    summary=dict(status='INPUTS_FROZEN_AUTHORING_NOT_STARTED',slots=len(slots),
        slots_by_split=dict(Counter(s['split'] for s in slots)),missing=missing,
        coverage=[dict(split=split,category=category,
            prefixes=len({s['prefix_identity'] for s in slots if s['split']==split and s['category']==category}),
            owners=len({s['owner'] for s in slots if s['split']==split and s['category']==category}))
            for split in ('train','dev') for category in CATEGORIES],
        acquired_units_by_head={head:sum(s['counts'][i] for s in slots) for i,head in enumerate(('RS','MP','MS','ME'))},
        behavioral_regression_inputs=12,behavior_inputs_by_owner=dict(owner_n),
        generator_calls=0,judge_calls=0,API_usd=0,accepted_targets=0,
        note='Coverage is input availability, not accepted targets, source correctness or executor efficacy.')
    def save(name,obj):
        with (out/name).open('x') as f:f.write(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
    save('authoring_slots_private.json',dict(version='p2-six-category-inputs-v1',slots=slots))
    save('behavior_inputs_private.json',dict(version='p2-behavior-inputs-v1',slots=selected,
        selection='Known historical-speaker failure OFF + deterministic category/owner-balanced hash; development only'))
    save('slot_summary.json',summary)
    sources=[p1/'phase_closeout.json',p1/'episode_specs_private.json',*freezes,
        PROJECT/'src/metacom_pm/rl1/representation_direct.py',Path(__file__),
        PROJECT/'docs/pm_rl1_completion_20260930_v2/execution_contract.json']
    save('slot_freeze.json',dict(status=summary['status'],renderer_identity=renderer.identity,
        plan_selection='Legal candidates, seed17 prefix/category/plan SHA256; no quality-dependent selection',
        expected_author_initial_slots=684,actual_author_initial_slots=len(slots),
        author_repair_reserve=dict(train=80,dev=16),teacher='NOT_BOUND',validator='NOT_BOUND',
        inference_started=False,training_started=False,
        files={name:sha256_file(out/name) for name in ('authoring_slots_private.json','behavior_inputs_private.json','slot_summary.json')},
        source_files={str(p.relative_to(PROJECT)):sha256_file(p) for p in sources},
        next_step='Bind local author and source-grounded acceptance procedure; generate once per slot; freeze accepted targets before one LoRA run.'))
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=ROOT);main(p.parse_args().root)
