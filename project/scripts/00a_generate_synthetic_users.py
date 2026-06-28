#!/usr/bin/env python3
from pathlib import Path
import argparse
from metacom_pm.config import load_config,endpoint_from_config
from metacom_pm.synthetic_generation import generate_longitudinal_source
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--config',type=Path,default=ROOT/'configs/experiment.yaml');p.add_argument('--endpoint',default='synthetic_generator');p.add_argument('--n-users',type=int,default=60);p.add_argument('--seed',type=int,default=90210);p.add_argument('--out-dir',type=Path,default=ROOT/'outputs/new_synthetic_source');a=p.parse_args();a.out_dir.mkdir(parents=True,exist_ok=True)
print(generate_longitudinal_source(a.out_dir/'source_cards.jsonl',a.out_dir/'raw_api_calls.jsonl',a.out_dir/'summary.json',endpoint=endpoint_from_config(load_config(a.config),a.endpoint),n_users=a.n_users,seed=a.seed))
