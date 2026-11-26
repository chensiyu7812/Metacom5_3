#!/usr/bin/env python3
"""Prepare the single fixed Top4 proposal on CPU. Never load model weights."""
import argparse,json
from pathlib import Path
from metacom_pm.rl1v3.journal.selective_memory_validation_sources import load_development_cache
from metacom_pm.rl1v3.journal.selective_memory_validation_top4 import prepare
from metacom_pm.rl1v3.retrieve.native_tokens import NativeTokenizer
from metacom_pm.rl1v3.generator.g0e_port import PromptTokenizer
p=argparse.ArgumentParser()
for k in ('resources','metadata','bundle','base-plan','selection-freeze','asset-manifest','out'):p.add_argument('--'+k,type=Path,required=True)
p.add_argument('--allowed-owners',nargs='+',required=True);p.add_argument('--excluded-owners',nargs='+',required=True)
a=p.parse_args();registry=load_development_cache(resources_path=a.resources,metadata_path=a.metadata,
    allowed_owners=a.allowed_owners,excluded_owners=a.excluded_owners)
base=json.loads(a.base_plan.read_text());tokenizer=PromptTokenizer(NativeTokenizer(base['model_path'],a.asset_manifest))
print(json.dumps(prepare(registry=registry,tokenizer=tokenizer,bundle=a.bundle,base_plan=a.base_plan,
    selection_freeze=a.selection_freeze,out=a.out),indent=2))
