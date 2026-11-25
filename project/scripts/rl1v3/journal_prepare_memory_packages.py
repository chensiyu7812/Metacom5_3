#!/usr/bin/env python3
"""Prepare fixed Memory/Writer/update requests with local CPU tokenization."""
import argparse,json
from pathlib import Path
from metacom_pm.rl1v3.journal.memory_packages import prepare
from metacom_pm.rl1v3.sources import source_registry as S
from metacom_pm.rl1v3.retrieve.native_tokens import NativeTokenizer
from metacom_pm.rl1v3.generator.g0e_port import PromptTokenizer
p=argparse.ArgumentParser()
for name in ('root','representations','writer8','smoke','measurements','repo','out'):p.add_argument('--'+name,type=Path,required=True)
a=p.parse_args();args=vars(a);root=args.pop('root')
registry=S.load(root/'project/outputs/pm_rl1/v3/A1_preparation/final/registry')
tokenizer=PromptTokenizer(NativeTokenizer('/opt/tokkio-data0/tokkio_models/gemma-4-12B-it-707f0a3',
    root/'project/outputs/pm_rl1/v3/A1_reuse/ASSET_REUSE_MANIFEST.json'))
print(json.dumps(prepare(registry=registry,tokenizer=tokenizer,**args),indent=2,ensure_ascii=False))
