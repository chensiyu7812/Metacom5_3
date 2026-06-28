#!/usr/bin/env python3
from pathlib import Path
import argparse
from metacom_pm.pairgraph import build_pair_graph
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--runtime',type=Path,default=ROOT/'data/synthetic/runtime_states.jsonl');p.add_argument('--out-dir',type=Path,default=ROOT/'data/synthetic');p.add_argument('--max-cards',type=int);p.add_argument('--seed',type=int,default=3201);a=p.parse_args()
print(build_pair_graph(a.runtime,a.out_dir/'pair_graph.jsonl',a.out_dir/'pair_graph_audit.json',seed=a.seed,max_cards=a.max_cards))
