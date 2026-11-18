#!/usr/bin/env python3
"""Verify the PP1 preparation package without model imports or GPU access."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'project/src'))
from metacom_pm.rl1v3.compile.ms_pp1 import check_bundle

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    print(json.dumps(check_bundle(args.out,ROOT),ensure_ascii=False,sort_keys=True))
