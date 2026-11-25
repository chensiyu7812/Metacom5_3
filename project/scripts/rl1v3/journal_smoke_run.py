"""Explicit check/run entry point; check is CPU-only and creates no authority."""
import argparse
import json
from metacom_pm.rl1v3.io import object_sha256
from metacom_pm.rl1v3.journal.run import check,run

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('operation',choices=['check','run']);p.add_argument('--plan',required=True);p.add_argument('--approval');p.add_argument('--run-root')
    a=p.parse_args()
    if a.operation=='check':
        plan,rows,baseline=check(a.plan)
        print(json.dumps(dict(status='CPU_CHECK_PASSED',plan_sha256=object_sha256(plan),requests=len(rows),model_loads=0,device_access=False,authorized=False),indent=2))
    else:
        if not a.approval or not a.run_root:p.error('run requires --approval and --run-root')
        print(json.dumps(run(a.plan,a.approval,a.run_root),indent=2))
