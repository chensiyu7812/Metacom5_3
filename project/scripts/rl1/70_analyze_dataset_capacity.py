#!/usr/bin/env python3
"""Recompute reachable actions from frozen train/dev inventories; tokenizer only."""
import argparse
from collections import Counter
from functools import lru_cache
import importlib.util
import json
from pathlib import Path
import sys

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.rl1.env import ResourceEnv
from metacom_pm.rl1.evidence import prefix_from_dict
from metacom_pm.rl1.render import Renderer
from metacom_pm.rl1.schema import EpisodeSpec,Resource,PLANS,HEADS

def main(output=None):
    sp=importlib.util.spec_from_file_location('census69',Path(__file__).with_name('69_analyze_dataset_features.py'))
    mod=importlib.util.module_from_spec(sp);sp.loader.exec_module(mod)
    out=output or mod.OUT
    out.mkdir(parents=True,exist_ok=True)
    if (out/'capacity.json').exists(): raise RuntimeError('Completed capacity census exists')
    from transformers import AutoConfig,AutoTokenizer
    model=Path('/opt/tokkio-data0/tokkio_models/huggingface/hub/models--NousResearch--Meta-Llama-3.1-8B-Instruct/snapshots/d10aef7999a2b5ba950ab3974312feeedbfe0b77')
    tok=AutoTokenizer.from_pretrained(model,local_files_only=True)
    @lru_cache(maxsize=8192)
    def count(text): return len(tok.encode(text,add_special_tokens=False))
    renderer=Renderer(count_text=count,count_chat=lambda m:len(tok.apply_chat_template(m,tokenize=True,add_generation_prompt=True)),
        tokenizer_identity='analysis-only-local-pinned-Llama-3.1-tokenizer',context_limit=AutoConfig.from_pretrained(model,local_files_only=True).max_position_embeddings)
    rows=[];plans=[]
    for i,raw in enumerate(mod.read(mod.PATHS['specs'])):
        spec=EpisodeSpec(**dict(raw,prefix=prefix_from_dict(raw['prefix']),
            inventory=tuple(tuple(Resource(**dict(r,source_ids=tuple(r['source_ids']))) for r in h) for h in raw['inventory'])))
        env=ResourceEnv(spec,renderer);mask=env.observe().initial_plan_mask
        feasible=[p for p,m in zip(PLANS,mask) if m]
        row=dict(index=i,owner=spec.prefix.owner_id,split=spec.prefix.split,reachable=len(feasible),
            reachable_three=sum(sum(p)==3 for p in feasible),reachable_four=sum(sum(p)==4 for p in feasible),
            reachable_same_head_repeat=sum(max(p)>1 for p in feasible),
            prefix_chat_tokens=renderer.count_chat(renderer.messages(spec,(0,0,0,0))),
            first_MS_raw_tokens=spec.inventory[2][0].raw_tokens if spec.inventory[2] else None)
        for j,h in enumerate(HEADS):
            single=tuple(int(k==j) for k in range(4))
            row[h+'_first_reachable']=single in feasible
        rows.append(row)
        for p in feasible:
            plans.append(dict(index=i,split=spec.prefix.split,counts=p,total=sum(p),resource_tokens=renderer.cost(spec,p),same_head_repeat=max(p)>1))
    owner_rows=[]
    for u in mod.read(mod.PATHS['runtime'])['users']:
        txt='\n'.join(f"[{s['timestamp']}] {s['session_id']}\n"+'\n'.join(t['role']+': '+t['content'] for t in s['turns']) for s in u['sessions'])
        owner_rows.append(dict(owner=u['owner_id'],full_history_text_tokens=count(txt),sessions=len(u['sessions'])))
    summary=dict(prefixes=len(rows),reachable_plans=mod.quantiles(r['reachable'] for r in rows),
        total_reachable=len(plans),by_acquisition_count=dict(Counter(p['total'] for p in plans)),
        prefixes_with_three=sum(r['reachable_three']>0 for r in rows),prefixes_with_four=sum(r['reachable_four']>0 for r in rows),
        prefixes_with_same_head_repeat=sum(r['reachable_same_head_repeat']>0 for r in rows),
        first_head_unreachable={h:sum(not r[h+'_first_reachable'] for r in rows) for h in HEADS},
        full_history_text_tokens=mod.quantiles(r['full_history_text_tokens'] for r in owner_rows),
        note='Reachability recomputed by actual ResourceEnv and full-resource renderer; no G/J calls. Text-only history tokens exclude judge template/replies.',
        tokenizer_json_sha256=mod.sha256((model/'tokenizer.json').read_bytes()).hexdigest())
    mod.write_csv(out,'capacity_prefix_features.csv',rows);mod.write_csv(out,'reachable_plan_features.csv',plans)
    mod.write_csv(out,'owner_history_tokens.csv',owner_rows);mod.write_json(out,'capacity.json',summary)
    print(json.dumps(summary,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path)
    main(parser.parse_args().out)
