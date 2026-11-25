#!/usr/bin/env python3
"""Build 12×3 source-only representation candidates; tokenizer CPU only."""
import argparse,json
from pathlib import Path
from metacom_pm.rl1v3.journal.representations import build
from metacom_pm.rl1v3.sources import source_registry as S
from metacom_pm.rl1v3.retrieve.native_tokens import NativeTokenizer
from metacom_pm.rl1v3.generator.g0e_port import PromptTokenizer
p=argparse.ArgumentParser()
p.add_argument('--root',type=Path,required=True)
p.add_argument('--audit',type=Path,required=True)
p.add_argument('--runtime',type=Path,required=True)
p.add_argument('--baseline',type=Path,required=True)
p.add_argument('--out',type=Path,required=True)
a=p.parse_args()
r=S.load(a.root/'project/outputs/pm_rl1/v3/A1_preparation/final/registry')
t=PromptTokenizer(NativeTokenizer('/opt/tokkio-data0/tokkio_models/gemma-4-12B-it-707f0a3',a.root/'project/outputs/pm_rl1/v3/A1_reuse/ASSET_REUSE_MANIFEST.json'))
b=json.loads(a.baseline.read_text())
report=build(registry=r,audit_path=a.audit,runtime_path=a.runtime,tokenizer=t,baseline_sha256=b['binding_sha256'],out=a.out)
print(json.dumps(report,ensure_ascii=False,indent=2))
