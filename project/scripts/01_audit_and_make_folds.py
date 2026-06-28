#!/usr/bin/env python3
from pathlib import Path
import argparse
from metacom_pm.audit import audit_synthetic_release
from metacom_pm.splits import make_grouped_folds
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--data-dir',type=Path,default=ROOT/'data/synthetic');p.add_argument('--folds',type=int,default=5);a=p.parse_args()
print(audit_synthetic_release(a.data_dir/'runtime_states.jsonl',a.data_dir/'memory_backend.jsonl',a.data_dir/'audit_report.json'))
print(make_grouped_folds(a.data_dir/'runtime_states.jsonl',a.data_dir/'folds.jsonl',a.data_dir/'folds_summary.json',n_splits=a.folds))
