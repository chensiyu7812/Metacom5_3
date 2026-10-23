#!/usr/bin/env python3
"""Freeze the shared 24-train/18-dev x 15-plan menu without executor outputs."""
from collections import Counter
from functools import lru_cache
import json
from pathlib import Path
import sys

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.schema import EpisodeSpec,Resource,PLANS,digest
from metacom_pm.rl1.evidence import prefix_from_dict
from metacom_pm.rl1.representation_direct import DirectReplyRenderer
ROOT=PROJECT/'outputs/pm_rl1/completion_20260930_v2'
MODEL=Path('/opt/tokkio-data0/tokkio_models/huggingface/hub/models--NousResearch--Meta-Llama-3.1-8B-Instruct/snapshots/d10aef7999a2b5ba950ab3974312feeedbfe0b77')


def read(p):return json.loads(p.read_text())


def main():
    from transformers import AutoTokenizer,AutoConfig
    p1=ROOT/'P1';p2=ROOT/'P2';out=p2/'common_pool';out.mkdir(exist_ok=True)
    if (out/'input_freeze.json').exists():raise RuntimeError('shared inputs already frozen')
    contract_path=PROJECT/'docs/pm_rl1_completion_20260930_v2/execution_contract.json'
    contract=read(contract_path)['shared_pool'];plans=[tuple(p) for p in contract['fixed_plans']]
    assert len(plans)==len(set(plans))==15 and contract['selection_seed']==17
    freeze=read(p1/'renderer_freeze.json');active=read(p1/'phase_closeout.json')
    for name,h in freeze['files'].items():assert sha256_file(p1/name)==h,name
    specs=[EpisodeSpec(**dict(s,prefix=prefix_from_dict(s['prefix']),
        inventory=tuple(tuple(Resource(**dict(r,source_ids=tuple(r['source_ids']))) for r in h) for h in s['inventory'])))
        for s in read(p1/'episode_specs_private.json')]
    tok=AutoTokenizer.from_pretrained(MODEL,local_files_only=True)
    @lru_cache(maxsize=32768)
    def count(s):return len(tok.encode(s,add_special_tokens=False))
    renderer=DirectReplyRenderer(count_text=count,
        count_chat=lambda m:len(tok.apply_chat_template(m,tokenize=True,add_generation_prompt=True)),
        tokenizer_identity=freeze['tokenizer_identity'],context_limit=AutoConfig.from_pretrained(MODEL,local_files_only=True).max_position_embeddings)
    assert renderer.identity==active['active_renderer_identity']
    capacities=read(p1/'capacity_prefix_private.json');selected=[]
    for owner in sorted({s.prefix.owner_id for s in specs if s.prefix.split=='train'}):
        choices=[i for i,s in enumerate(specs) if s.prefix.owner_id==owner and s.prefix.split=='train']
        selected.extend(sorted(choices,key=lambda i:digest(['p2-common-train-prefix-v1',17,specs[i].prefix.identity]))[:2])
    assert len(selected)==24
    selected.extend(i for i,s in enumerate(specs) if s.prefix.split=='dev');assert len(selected)==42
    rows=[];missing=[]
    for i in selected:
        s=specs[i]
        for pi,plan in enumerate(plans):
            base=dict(index=i,owner=s.prefix.owner_id,split=s.prefix.split,prefix_identity=s.prefix.identity,
                plan_index=pi,counts=plan,slot_id=digest(['p2-common-pool',s.prefix.identity,plan,renderer.identity]))
            if not capacities[i]['initial_plan_mask'][PLANS.index(plan)]:
                missing.append(dict(base,reason='not_reachable',generation=False,fixed_dev_scoring='OFF fallback, included in aggregate'));continue
            assert renderer.fits(s,plan)
            messages=renderer.messages(s,plan)
            rows.append(dict(base,messages=messages,messages_identity=digest(messages),resource_tokens=renderer.cost(s,plan),
                candidate_ids=[r.candidate_id for head,n in zip(s.inventory,plan) for r in head[:n]]))
    def save(n,v):
        with (out/n).open('x') as f:f.write(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
    save('slots_private.json',dict(rows=rows,unavailable=missing))
    save('summary.json',dict(status='INPUTS_FROZEN_EXECUTOR_PENDING',prefixes=42,train_prefixes=24,dev_prefixes=18,
        plan_menu_size=15,nominal_slots=630,legal_slots=len(rows),unavailable_slots=len(missing),
        legal_by_split=dict(Counter(r['split'] for r in rows)),
        unavailable_by_split=dict(Counter(r['split'] for r in missing)),
        selection='Two train prefixes per owner by seed17/prefix SHA256; all dev; no response-quality selection',
        generation_calls=0,reward_measurements=0,API_usd=0))
    guards=[contract_path,p1/'renderer_freeze.json',p1/'episode_specs_private.json',p1/'phase_closeout.json',
        p1/'capacity_prefix_private.json',PROJECT/'src/metacom_pm/rl1/representation_direct.py',Path(__file__)]
    save('input_freeze.json',dict(status='INPUTS_FROZEN_EXECUTOR_PENDING',renderer_identity=renderer.identity,
        executor_identity=None,judge_identity=None,files={n:sha256_file(out/n) for n in ('slots_private.json','summary.json')},
        source_files={str(p.relative_to(PROJECT)):sha256_file(p) for p in guards},
        next='Bind selected/reloaded executor before generation; bind calibrated scorer before using any reward.'))
    print(json.dumps(read(out/'summary.json'),ensure_ascii=False))


if __name__=='__main__':main()
