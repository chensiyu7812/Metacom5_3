#!/usr/bin/env python3
from pathlib import Path
import argparse
from metacom_pm.config import load_config, endpoint_from_config
from metacom_pm.sweep import run_action_sweep
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--config',type=Path,default=ROOT/'configs/experiment.yaml');p.add_argument('--endpoint',default='generator');p.add_argument('--runtime',type=Path,default=ROOT/'data/synthetic/runtime_states.jsonl');p.add_argument('--backend',type=Path,default=ROOT/'data/synthetic/memory_backend.jsonl');p.add_argument('--strategy-bank',type=Path,default=ROOT/'data/strategy/strategy_cards.jsonl');p.add_argument('--out-dir',type=Path,default=ROOT/'outputs/synthetic_sweep');p.add_argument('--max-cards',type=int);p.add_argument('--overwrite',action='store_true');a=p.parse_args();a.out_dir.mkdir(parents=True,exist_ok=True);ep=endpoint_from_config(load_config(a.config),a.endpoint)
print(run_action_sweep(a.runtime,a.backend,a.strategy_bank,a.out_dir/'action_outcomes.jsonl',a.out_dir/'raw_api_calls.jsonl',a.out_dir/'summary.json',endpoint=ep,max_cards=a.max_cards,overwrite=a.overwrite))
