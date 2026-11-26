#!/usr/bin/env python3
"""CPU-only bounded-source task freeze or actual STOP/MS preparation."""
import argparse
import json
from pathlib import Path
from metacom_pm.rl1v3.journal.selective_memory_validation_sources import load_development_cache
from metacom_pm.rl1v3.journal.selective_memory_validation import freeze_bundle, prepare_reads

p=argparse.ArgumentParser()
p.add_argument('phase',choices=('freeze','reads'))
for k in ('resources','metadata','out'):
    p.add_argument('--'+k,type=Path,required=True)
p.add_argument('--design',type=Path)
p.add_argument('--allowed-owners',nargs='+')
p.add_argument('--excluded-owners',nargs='+')
p.add_argument('--policy-freeze',type=Path)
p.add_argument('--bundle',type=Path)
p.add_argument('--base-plan',type=Path)
p.add_argument('--asset-manifest',type=Path)
a=p.parse_args()
if a.phase=='freeze':
    if not a.design:p.error('freeze requires --design')
    design=json.loads(a.design.read_text())
    allowed,excluded=design['allowed_owners'],design['excluded_J06_owners']
else:
    if not all((a.allowed_owners,a.excluded_owners)):p.error('reads requires explicit bounded owner lists')
    allowed,excluded=a.allowed_owners,a.excluded_owners
registry=load_development_cache(resources_path=a.resources,metadata_path=a.metadata,
    allowed_owners=allowed,excluded_owners=excluded)
if a.phase=='freeze':
    if not a.policy_freeze:p.error('freeze requires --policy-freeze')
    result=freeze_bundle(registry=registry,design_path=a.design,policy_freeze_path=a.policy_freeze,out=a.out)
else:
    if not all((a.bundle,a.base_plan,a.asset_manifest)):p.error('reads requires --bundle --base-plan --asset-manifest')
    from metacom_pm.rl1v3.retrieve.native_tokens import NativeTokenizer
    from metacom_pm.rl1v3.generator.g0e_port import PromptTokenizer
    base=json.loads(a.base_plan.read_text())
    tokenizer=PromptTokenizer(NativeTokenizer(base['model_path'],a.asset_manifest))
    result=prepare_reads(registry=registry,tokenizer=tokenizer,bundle=a.bundle,base_plan=a.base_plan,out=a.out)
print(json.dumps(result,indent=2))
