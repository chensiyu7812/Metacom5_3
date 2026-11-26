#!/usr/bin/env python3
"""Post-trace CPU source coverage, query provenance and explicit unknowns."""
import argparse,json
from pathlib import Path
from metacom_pm.rl1v3.journal.pomdp_source_trace_audit import audit
p=argparse.ArgumentParser()
for name in ('bundle','cpu','design-path','resources','metadata','out'):p.add_argument('--'+name,type=Path,required=True)
a=p.parse_args();print(json.dumps(audit(**vars(a)),indent=2))
