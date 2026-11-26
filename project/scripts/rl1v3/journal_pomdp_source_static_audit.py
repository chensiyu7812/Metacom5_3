#!/usr/bin/env python3
"""Audit delivery of the unchanged source cases under the separate Top4 macro."""
import argparse,json
from pathlib import Path
from metacom_pm.rl1v3.journal.pomdp_source_static_audit import audit
p=argparse.ArgumentParser()
for name in ('bundle','cpu','pressure','original-audit','out'):p.add_argument('--'+name,type=Path,required=True)
a=p.parse_args();print(json.dumps(audit(**vars(a)),indent=2))
