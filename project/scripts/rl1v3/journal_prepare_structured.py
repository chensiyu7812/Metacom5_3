#!/usr/bin/env python3
"""CPU-only freeze of 18 paired structured source tasks."""
import argparse,json
from pathlib import Path
from metacom_pm.rl1v3.journal.structured_learning import prepare
from metacom_pm.rl1v3.sources import source_registry as S
from metacom_pm.rl1v3.retrieve.native_tokens import NativeTokenizer
from metacom_pm.rl1v3.generator.g0e_port import PromptTokenizer
p=argparse.ArgumentParser()
for name in ('root','repo','smoke','measurements','seed','out'):p.add_argument('--'+name,type=Path,required=True)
a=p.parse_args();kw=vars(a);root=kw.pop('root')
registry=S.load(root/'project/outputs/pm_rl1/v3/A1_preparation/final/registry')
tokenizer=PromptTokenizer(NativeTokenizer('/opt/tokkio-data0/tokkio_models/gemma-4-12B-it-707f0a3',root/'project/outputs/pm_rl1/v3/A1_reuse/ASSET_REUSE_MANIFEST.json'))
print(json.dumps(prepare(registry=registry,tokenizer=tokenizer,**kw),indent=2))
