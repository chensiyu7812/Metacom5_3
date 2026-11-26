#!/usr/bin/env python3
"""CPU check or explicitly authorized four-terminal restored-state contrast."""
import argparse
import json
from metacom_pm.rl1v3.journal.pomdp_midstate_counterfactual import check,run
from metacom_pm.rl1v3.io import object_sha256

p=argparse.ArgumentParser();p.add_argument('operation',choices=['check','run'])
p.add_argument('--plan',required=True);p.add_argument('--approval');p.add_argument('--run-root')
a=p.parse_args()
if a.operation=='check':
    plan,requests,states,_=check(a.plan)
    print(json.dumps(dict(status='CPU_CHECK_PASSED',plan_sha256=object_sha256(plan),requests=len(requests),
        states=len(states),model_loads=0,model_calls=0,authorized=False),indent=2))
else:
    if not a.approval or not a.run_root:p.error('run requires exact new approval and run-root')
    print(json.dumps(run(a.plan,a.approval,a.run_root),indent=2))
