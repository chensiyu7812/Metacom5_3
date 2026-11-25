#!/usr/bin/env python3
"""Join the six actual J06 batches and independent source/support observations."""
import argparse,json
from pathlib import Path
from metacom_pm.rl1v3.journal.joint_outcomes import merge
p=argparse.ArgumentParser();p.add_argument('--joint-root',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
a=p.parse_args();r=merge(a.joint_root,a.out)
print(json.dumps({k:v for k,v in r.items() if k not in ('inputs_sha256',)},indent=2))
