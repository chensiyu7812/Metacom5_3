#!/usr/bin/env python3
"""CPU-only package construction, never model execution."""
import argparse,json
from metacom_pm.rl1v3.journal.structured_constrained_packages import prepare
p=argparse.ArgumentParser();p.add_argument('--original',required=True);p.add_argument('--repo',required=True);p.add_argument('--out',required=True)
a=p.parse_args();print(json.dumps(prepare(a.original,a.repo,a.out),indent=2))
