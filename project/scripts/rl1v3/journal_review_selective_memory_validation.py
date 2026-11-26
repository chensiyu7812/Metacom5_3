#!/usr/bin/env python3
"""Freeze unrun evaluation records and report actual source delivery only."""
import argparse,json
from pathlib import Path
from metacom_pm.rl1v3.journal.selective_memory_validation_review import prepare
p=argparse.ArgumentParser()
for k in ('bundle','requests-dir','out'):p.add_argument('--'+k,type=Path,required=True)
a=p.parse_args();print(json.dumps(prepare(**vars(a)),indent=2))
