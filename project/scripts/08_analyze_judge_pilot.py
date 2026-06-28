#!/usr/bin/env python3
from pathlib import Path
import argparse
from metacom_pm.pilot_analysis import analyze_judge_pilot
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--pilot-dir',type=Path,default=ROOT/'outputs/judge_pilot');p.add_argument('--out',type=Path,default=ROOT/'outputs/judge_pilot/pilot_gate.json');a=p.parse_args();print(analyze_judge_pilot(a.pilot_dir,ROOT/'data/synthetic/pair_graph_audit.json',a.out))
