#!/usr/bin/env python3
"""One bounded 16-slot interface regression after the fixed P1 experiment.

The +16 local G calls are an explicit execution-plan deviation, not silently
charged as technical retries or as additional independent efficacy samples.
"""
import argparse
from functools import lru_cache
import json
from pathlib import Path
import sys

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.schema import EpisodeSpec,Resource,digest
from metacom_pm.rl1.evidence import prefix_from_dict
from metacom_pm.rl1.env import ResourceEnv
from metacom_pm.rl1.representation_direct import DirectReplyRenderer

P1=PROJECT/'outputs/pm_rl1/completion_20260930_v2/P1'
MODEL=Path('/opt/tokkio-data0/tokkio_models/huggingface/hub/models--NousResearch--Meta-Llama-3.1-8B-Instruct/snapshots/d10aef7999a2b5ba950ab3974312feeedbfe0b77')


def main(parent):
    from transformers import AutoTokenizer,AutoConfig
    out=parent/'interface_repair_v3';out.mkdir(exist_ok=True)
    if (out/'renderer_freeze.json').exists():raise RuntimeError('repair already frozen')
    original_run=Path(json.loads((parent/'diagnostic_pointer.json').read_text())['run_dir'])
    results=json.loads((original_run/'summary.json').read_text())
    if results['status']!='COMPLETE' or len(results['rows'])!=72:
        raise RuntimeError('finish all original diagnostic slots before follow-up')
    original_freeze=json.loads((parent/'renderer_freeze.json').read_text())
    for name,h in original_freeze['files'].items():
        if sha256_file(parent/name)!=h:raise ValueError('parent input changed')
    tok=AutoTokenizer.from_pretrained(MODEL,local_files_only=True)
    @lru_cache(maxsize=32768)
    def count(text):return len(tok.encode(text,add_special_tokens=False))
    renderer=DirectReplyRenderer(count_text=count,
        count_chat=lambda m:len(tok.apply_chat_template(m,tokenize=True,add_generation_prompt=True)),
        tokenizer_identity=original_freeze['tokenizer_identity'],
        context_limit=AutoConfig.from_pretrained(MODEL,local_files_only=True).max_position_embeddings)
    specs=[EpisodeSpec(**dict(s,prefix=prefix_from_dict(s['prefix']),
        inventory=tuple(tuple(Resource(**dict(r,source_ids=tuple(r['source_ids']))) for r in h) for h in s['inventory'])))
        for s in json.loads((parent/'episode_specs_private.json').read_text())]
    capacities=json.loads((parent/'capacity_prefix_private.json').read_text());changed=[]
    for i,s in enumerate(specs):
        if list(ResourceEnv(s,renderer).observe().initial_plan_mask)!=capacities[i]['initial_plan_mask']:changed.append(i)
    assert not changed,'context feasibility changed; do not inherit capacity silently'
    manifest=json.loads((parent/'diagnostic_manifest.json').read_text())
    risks=[i for i in manifest['selected_indices'] if any(t.role=='supporter' and
           ('my mother' in t.content.lower() or 'my mom' in t.content.lower()) for t in specs[i].prefix.turns)]
    assert len(risks)==1
    chosen=[c for c in manifest['conditions'] if c['representation']=='new' and (c['condition']=='OFF' or c['index']==risks[0])]
    assert len(chosen)==8
    conditions=[]
    for c in chosen:
        messages=renderer.messages(specs[c['index']],tuple(c['counts']))
        conditions.append(dict(c,representation='direct_v3',messages=messages,
            messages_identity=digest(messages),renderer_identity=renderer.identity))
    def save(name,value):
        with (out/name).open('x') as f:f.write(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    save('diagnostic_manifest.json',dict(version='p1-direct-user-interface-repair-v3',
        conditions=conditions,response_slots=16,executors=['base','old_lora_epoch3'],missing=[],
        selection='All six original prefixes OFF; known mother-role prefix also original RS/MEMORY; both original executors',
        interpretation='Adaptive development repair after a visible interface defect; not independent confirmation'))
    save('capacity.json',dict(prefixes=len(specs),same_reachable_masks_as_parent=True,total_reachable=sum(c['reachable'] for c in capacities)))
    save('plan_deviation.json',dict(reason='V2 JSON current-user wrapping elicited third-person transcript analysis in completed diagnostic responses.',
        parent_summary_sha256=sha256_file(original_run/'summary.json'),
        original_slots=72,extra_local_G_slots=16,new_P1_G_upper_bound=88,
        semantic_prompt_revisions_this_repair=1,additional_J_calls=0,additional_human_tasks=0,additional_API_usd=0,
        no_further_prompt_search=True,original_responses_preserved=True,
        accounting='Explicit +16 generation slots to prior plan; not a technical retry or unchanged original budget.'))
    sources=dict(original_freeze['source_files'])
    for p in (parent/'renderer_freeze.json',parent/'episode_specs_private.json',
              PROJECT/'src/metacom_pm/rl1/representation_direct.py',Path(__file__)):
        sources[str(p.relative_to(PROJECT))]=sha256_file(p)
    save('renderer_freeze.json',dict(status='ONE_BOUNDED_INTERFACE_REPAIR_FROZEN',
        new_renderer_identity=renderer.identity,retrieval=original_freeze['retrieval'],
        files={name:sha256_file(out/name) for name in ('diagnostic_manifest.json','capacity.json','plan_deviation.json')},
        source_files=sources,role='Latest turn native user message; historical speakers remain attributed context',
        next_step='Run script77 with this directory; retain failure if this bounded repair is insufficient'))
    print(json.dumps(dict(out=str(out),slots=16,total_P1_slots=88,capacity_unchanged=True)))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,default=P1);main(p.parse_args().parent)
