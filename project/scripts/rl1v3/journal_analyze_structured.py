#!/usr/bin/env python3
"""Frozen scoring and read-only cost/paired diagnostics for actual structured jobs."""
import argparse,json
from metacom_pm.rl1v3.journal.structured_results import collect
from metacom_pm.rl1v3.journal.structured_analysis import analyze
p=argparse.ArgumentParser();p.add_argument('operation',choices=['collect','analyze'])
for k in ('plan','job','pending','package','policy','out'):p.add_argument('--'+k,required=k=='out')
p.add_argument('--endpoints',action='append')
a=p.parse_args()
if a.operation=='collect':
    if not all([a.plan,a.job,a.pending]):p.error('--plan --job --pending required')
    r=collect(a.plan,a.job,a.pending,a.out)
else:
    if not all([a.package,a.policy,a.endpoints]):p.error('--package --policy --endpoints required')
    r=analyze(a.package,a.endpoints,a.policy,a.out)
print(json.dumps(r,indent=2))
