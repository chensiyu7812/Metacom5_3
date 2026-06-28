#!/usr/bin/env python3
from pathlib import Path
import argparse
from metacom_pm.human_eval import analyze_annotations
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--key',type=Path,default=ROOT/'outputs/human_eval/private_key.jsonl');p.add_argument('--annotations',type=Path,nargs='+',required=True);p.add_argument('--out',type=Path,default=ROOT/'outputs/human_eval/analysis.json');a=p.parse_args();print(analyze_annotations(a.annotations,a.key,a.out))
