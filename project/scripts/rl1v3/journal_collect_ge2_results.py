#!/usr/bin/env python3
"""Collect only original GE2 completed/stopped jobs; no model or policy change."""
import argparse
import json
from metacom_pm.rl1v3.journal.ge2_results import collect

p=argparse.ArgumentParser()
for key in ('package','root','bundle','out'):p.add_argument('--'+key,required=True)
p.add_argument('--batches',nargs='+',type=int,default=[1,2,3,4])
print(json.dumps(collect(**vars(p.parse_args())),indent=2))
