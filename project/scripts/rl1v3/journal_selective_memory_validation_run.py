#!/usr/bin/env python3
"""CPU check or separately authorized bounded selective Memory validation; no implicit execution."""
import argparse,json
from metacom_pm.rl1v3.journal.selective_memory_validation_run import check,run
from metacom_pm.rl1v3.io import object_sha256
p=argparse.ArgumentParser()
p.add_argument('operation',choices=['check','run'])
p.add_argument('--plan',required=True);p.add_argument('--approval');p.add_argument('--run-root')
a=p.parse_args()
if a.operation=='check':
    plan,rows,_=check(a.plan)
    print(json.dumps(dict(status='CPU_CHECK_PASSED',plan_sha256=object_sha256(plan),
        requests=len(rows),authorized=False,model_loads=0,device_access=False),indent=2))
else:
    if not a.approval or not a.run_root:p.error('run requires --approval and --run-root')
    print(json.dumps(run(a.plan,a.approval,a.run_root),indent=2))
