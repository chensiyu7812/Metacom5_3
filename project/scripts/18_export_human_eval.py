#!/usr/bin/env python3
from pathlib import Path
import argparse
from metacom_pm.human_eval import export_blinded_pairs
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--comparisons',type=Path,required=True);p.add_argument('--out-dir',type=Path,default=ROOT/'outputs/human_eval');p.add_argument('--n-pairs',type=int,default=120);a=p.parse_args();a.out_dir.mkdir(parents=True,exist_ok=True);print(export_blinded_pairs(a.comparisons,a.out_dir/'blinded_pairs.jsonl',a.out_dir/'private_key.jsonl',n_pairs=a.n_pairs))
