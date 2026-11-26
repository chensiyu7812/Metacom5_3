#!/usr/bin/env python3
"""Independent CPU check or explicitly approved dynamic comparison; no autorun."""
import argparse
import json
from metacom_pm.rl1v3.journal.pomdp_dynamic_run import check, run
from metacom_pm.rl1v3.io import object_sha256

p = argparse.ArgumentParser()
p.add_argument('operation', choices=['check', 'run'])
p.add_argument('--plan', required=True)
p.add_argument('--approval')
p.add_argument('--run-root')
a = p.parse_args()
if a.operation == 'check':
    plan, tasks, _ = check(a.plan)
    print(json.dumps(dict(status='CPU_CHECK_PASSED', plan_sha256=object_sha256(plan),
        tasks=len(tasks), terminal_slots=12, maximum_actual_calls=22, authorized=False,
        device_access=False, model_loads=0), indent=2))
else:
    if not a.approval or not a.run_root:
        p.error('run requires --approval and --run-root')
    print(json.dumps(run(a.plan, a.approval, a.run_root), indent=2))
