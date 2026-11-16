"""CPU/tokenizer only; decode the existing nine dev input specs, no outputs.

Keep the prepared 41-request package immutable. Recompute why its four planned
arm slots are absent, using actual inventory and sequential reachability.
"""
import importlib.util
import json
import os
from pathlib import Path
import sys

OUT=Path(__file__).resolve().parent
B=OUT.parent
P=OUT.parents[3]
C=P/'outputs/pm_rl1/completion_20260930_v2'
sys.path.insert(0,str(P/'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.schema import EpisodeSpec,Resource,PLANS,digest
from metacom_pm.rl1.evidence import prefix_from_dict
from metacom_pm.rl1.representation_direct import DirectReplyRenderer
from metacom_pm.rl1.rs_applicability import RSApplicabilityRenderer
from metacom_pm.rl1.env import ResourceEnv
from metacom_pm.rl1.rs_development import read,save_once


def main():
    os.umask(0o077)
    prep=B/'rs_transfer_preparation_20261019_v1'
    module_spec=importlib.util.spec_from_file_location('projection',prep/'prepare_inputs.py')
    projection=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(projection)
    indexes=set(read(prep/'selection_lock.json')['indexes'])
    assert indexes=={98,99,101,103,106,107,108,110,112}
    spec_path=C/'P1/episode_specs_private.json'
    freeze=read(C/'P1/renderer_freeze.json')
    assert sha256_file(spec_path)==freeze['files'][spec_path.name]
    data=spec_path.read_bytes()
    selected={i:json.loads(data[a:z]) for i,a,z in projection.members(data) if i in indexes}
    assert set(selected)==indexes
    from transformers import AutoTokenizer
    runtime=read(C/'P2/executor_freeze.json')['primary_runtime']
    tok=AutoTokenizer.from_pretrained(runtime['model_dir'],local_files_only=True)
    count=lambda text:len(tok.encode(text,add_special_tokens=False))
    chat=lambda m:len(tok.apply_chat_template(m,tokenize=True,add_generation_prompt=True))
    kwargs=dict(count_text=count,count_chat=chat,tokenizer_identity=freeze['tokenizer_identity'],
        context_limit=runtime['policy']['context_limit'])
    old,new=DirectReplyRenderer(**kwargs),RSApplicabilityRenderer(**kwargs)
    protocol=read(prep/'protocol.json')
    assert old.identity==protocol['renderer_baseline'] and new.identity==protocol['renderer_intervention']
    rows=[]
    for index in sorted(indexes):
        raw=selected[index]
        spec=EpisodeSpec(**dict(raw,prefix=prefix_from_dict(raw['prefix']),
            inventory=tuple(tuple(Resource(**dict(r,source_ids=tuple(r['source_ids']))) for r in h) for h in raw['inventory'])))
        assert spec.prefix.split=='dev'
        before=ResourceEnv(spec,old).observe().initial_plan_mask
        after=ResourceEnv(spec,new).observe().initial_plan_mask
        plans=[]
        for k,plan in enumerate(PLANS):
            deficits={head:dict(required=n,available=len(items)) for head,n,items in zip(('RS','MP','MS','ME'),plan,spec.inventory) if n>len(items)}
            # An infeasible plan is not rendered with truncated/absent resources.
            old_cost=None if deficits else old.cost(spec,plan)
            new_cost=None if deficits else new.cost(spec,plan)
            old_input=None if deficits else chat(old.messages(spec,plan))
            new_input=None if deficits else chat(new.messages(spec,plan))
            plans.append(dict(counts=list(plan),inventory_deficits=deficits,
                old_resource_tokens=old_cost,new_resource_tokens=new_cost,
                old_input_tokens=old_input,new_input_tokens=new_input,
                old_resource_budget_ok=None if deficits else old_cost<=spec.resource_budget,
                new_resource_budget_ok=None if deficits else new_cost<=spec.resource_budget,
                old_reachable=before[k],new_reachable=after[k]))
        row=dict(index=index,inventory_lengths=dict(zip(('RS','MP','MS','ME'),map(len,spec.inventory))),
            resource_budget=spec.resource_budget,prefix_identity=spec.prefix.identity,
            old_reachable_plans=sum(before),new_reachable_plans=sum(after),
            lost_plans=[r for r in plans if r['old_reachable'] and not r['new_reachable']],
            gained_plans=[r for r in plans if not r['old_reachable'] and r['new_reachable']],
            all_four=next(r for r in plans if r['counts']==[1,1,1,1]),plans=plans)
        rows.append(row)
    source=read(prep/'input_requests_private.json')
    for r in source:
        row=next(x for x in rows if x['index']==r['index'])
        p=next(x for x in row['plans'] if x['counts']==r['counts'])
        assert p['old_reachable'] and p['new_reachable']
        assert p['old_resource_tokens']==r['metadata']['resource_tokens']
    report=dict(status='CHECKED_NINE_DEV_CONTEXTS_70_PLANS_EACH',rows=rows,
        original_missing_contexts=[r['index'] for r in rows if not r['all_four']['old_reachable']],
        newly_lost_context_plan_count=sum(len(r['lost_plans']) for r in rows),
        newly_gained_context_plan_count=sum(len(r['gained_plans']) for r in rows),
        all_41_prepared_requests_still_valid=True,protected_source_bodies_decoded=0,
        decoded_dev_specs=9,test_specs_read=0,old_outputs_read=0,generator_calls=0,GPU_used=False,
        full_114_or_162_capacity_certified=False,
        scope='The nine authorized development contexts only; no whole-inventory adoption claim.',
        source_files={str(p):sha256_file(p) for p in [spec_path,Path(__file__),prep/'protocol.json',
            P/'src/metacom_pm/rl1/env.py',P/'src/metacom_pm/rl1/rs_applicability.py']})
    save_once(OUT/'reachability_receipt.json',report)
    print(json.dumps({k:v for k,v in report.items() if k not in ('rows','source_files')},ensure_ascii=False))
    for row in rows:
        print(json.dumps({k:v for k,v in row.items() if k not in ('plans','lost_plans')},ensure_ascii=False))


if __name__=='__main__':main()
