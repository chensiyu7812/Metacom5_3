#!/usr/bin/env python3
"""Freeze CPU-only two-batch plan after actual source/read/request preparation."""
import argparse,json
from metacom_pm.rl1v3.journal.selective_memory_validation_packages import prepare
p=argparse.ArgumentParser()
for name in ('base-plan','bundle','requests','read-checks','measurements','repo','out'):
    p.add_argument('--'+name,required=True)
p.add_argument('--evaluation-preparation')
a=p.parse_args();print(json.dumps(prepare(**vars(a)),indent=2))
