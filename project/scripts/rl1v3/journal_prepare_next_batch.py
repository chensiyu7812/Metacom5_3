#!/usr/bin/env python3
"""Prepare one complete-pair CPU proposal; never execute requests."""
import argparse
import json
from metacom_pm.rl1v3.journal.batch_proposal import prepare

p=argparse.ArgumentParser()
for name in ('requests','smoke','measurements','a0-measurements','repo','out'):
    p.add_argument('--'+name,required=True)
a=p.parse_args()
print(json.dumps(prepare(**vars(a)),ensure_ascii=False,indent=2))
