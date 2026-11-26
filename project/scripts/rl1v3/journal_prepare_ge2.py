#!/usr/bin/env python3
"""Freeze GE2 on CPU; creates no authorization or real model output."""
import argparse
import json
from metacom_pm.rl1v3.journal.ge2_packages import prepare

p=argparse.ArgumentParser()
for key in ('repo','original-plan','bundle','selection','retrieval-freeze','out'):
    p.add_argument('--'+key, required=True)
p.add_argument('--evaluation-contract')
a=p.parse_args()
print(json.dumps(prepare(**vars(a)),indent=2))
