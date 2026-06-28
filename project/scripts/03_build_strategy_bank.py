#!/usr/bin/env python3
from pathlib import Path
import argparse
from metacom_pm.strategy_bank import build_strategy_bank
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--esconv',type=Path,default=ROOT/'data/external/ESConv.json');p.add_argument('--evoemo',type=Path,default=ROOT/'data/external/evo_emo.json');p.add_argument('--out-dir',type=Path,default=ROOT/'data/strategy');p.add_argument('--seed',type=int,default=13);a=p.parse_args();a.out_dir.mkdir(parents=True,exist_ok=True)
print(build_strategy_bank(a.esconv,a.evoemo,a.out_dir/'strategy_cards.jsonl',a.out_dir/'esconv_split_manifest.jsonl',a.out_dir/'strategy_bank_audit.json',seed=a.seed))
