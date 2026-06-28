#!/usr/bin/env python3
from pathlib import Path
import argparse,json
from metacom_pm.release import run_release_preflight
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=ROOT);p.add_argument('--out',type=Path,default=ROOT/'release_preflight.json');p.add_argument('--skip-tests',action='store_true');a=p.parse_args();r=run_release_preflight(a.root,a.out,run_tests=not a.skip_tests);print(json.dumps(r,ensure_ascii=False,indent=2));raise SystemExit(0 if r['status'] in {'API_PILOT_READY','CONFIRMATORY_READY'} else 2)
