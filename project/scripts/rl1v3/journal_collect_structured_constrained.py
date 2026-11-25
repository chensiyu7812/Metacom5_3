#!/usr/bin/env python3
"""CPU-only collection after separately authorized actual constrained generation."""
import argparse,json
from metacom_pm.rl1v3.journal.structured_constrained_results import collect
p=argparse.ArgumentParser()
for name in ('plan','job','original-outputs','out'):p.add_argument('--'+name,required=True)
a=p.parse_args();print(json.dumps(collect(a.plan,a.job,a.original_outputs,a.out),indent=2))
