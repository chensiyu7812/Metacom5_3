#!/usr/bin/env python3
from pathlib import Path
import argparse
from metacom_pm.preparation import prepare_synthetic_counterfactuals

ROOT = Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser()
p.add_argument('--source', type=Path, default=ROOT/'data/source/synthetic_v31_source.jsonl')
p.add_argument('--out-dir', type=Path, default=ROOT/'data/synthetic')
p.add_argument('--max-states', type=int)
p.add_argument('--variant-mode', choices=['balanced9','all'], default='balanced9')
a=p.parse_args(); a.out_dir.mkdir(parents=True, exist_ok=True)
result=prepare_synthetic_counterfactuals(a.source,a.out_dir/'runtime_states.jsonl',a.out_dir/'memory_backend.jsonl',a.out_dir/'audit_only.jsonl',a.out_dir/'preparation_summary.json',max_states=a.max_states,variant_mode=a.variant_mode)
print(result)
