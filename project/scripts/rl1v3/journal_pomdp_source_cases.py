#!/usr/bin/env python3
"""CPU-only construction of frozen source-derived POMDP candidates."""
import argparse,json
from pathlib import Path
from metacom_pm.rl1v3.journal.pomdp_source_cases import build
p=argparse.ArgumentParser()
for name in ('resources','metadata','design-path','selection-path','out'):p.add_argument('--'+name,type=Path,required=True)
a=p.parse_args();print(json.dumps(build(**vars(a)),indent=2))
