#!/usr/bin/env python3
import argparse,json
from metacom_pm.rl1v3.journal.structured_endpoints import prepare_pending,collect
p=argparse.ArgumentParser();p.add_argument('operation',choices=['pending','collect'])
p.add_argument('--package');p.add_argument('--plan');p.add_argument('--job');p.add_argument('--pending');p.add_argument('--out',required=True)
a=p.parse_args()
if a.operation=='pending':
    if not a.package:p.error('--package required')
    result=prepare_pending(a.package,a.out)
else:
    if not all([a.plan,a.job,a.pending]):p.error('--plan --job --pending required')
    result=collect(a.plan,a.job,a.pending,a.out)
print(json.dumps(result,indent=2))
