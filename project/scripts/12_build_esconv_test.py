#!/usr/bin/env python3
from pathlib import Path
import argparse
from metacom_pm.esconv import build_esconv_test_runtime
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--esconv',type=Path,default=ROOT/'data/external/ESConv.json');p.add_argument('--out-dir',type=Path,default=ROOT/'data/esconv_test');a=p.parse_args();a.out_dir.mkdir(parents=True,exist_ok=True)
print(build_esconv_test_runtime(a.esconv,ROOT/'data/strategy/esconv_split_manifest.jsonl',a.out_dir/'runtime_states.jsonl',a.out_dir/'memory_backend.jsonl',a.out_dir/'audit_only.jsonl'))
