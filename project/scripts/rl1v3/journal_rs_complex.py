"""Build exact complex RS requests, check, or run after separate plan approval."""
import argparse
import json

p=argparse.ArgumentParser();subs=p.add_subparsers(dest='command',required=True)
b=subs.add_parser('build')
for name in ('tasks-dir','candidates','sources','review-path','review-sha256','template-plan','repo','model','assets','output'):
    b.add_argument('--'+name,required=True)
for name in ('check','run'):
    c=subs.add_parser(name);c.add_argument('--plan',required=True)
    if name=='run':c.add_argument('--approval',required=True);c.add_argument('--run-root',required=True)
a=p.parse_args()
if a.command=='build':
    from metacom_pm.rl1v3.journal.rs_complex import build
    args=vars(a);args.pop('command');result=build(**args)
else:
    from metacom_pm.rl1v3.journal.rs_complex_run import check,run
    from metacom_pm.rl1v3.io import object_sha256
    if a.command=='check':
        plan,rows,_=check(a.plan)
        result=dict(status='CPU_CHECK_PASSED',plan_sha256=object_sha256(plan),requests=len(rows),
                    authorized=False,model_loads=0,device_access=False)
    else:result=run(a.plan,a.approval,a.run_root)
print(json.dumps(result,ensure_ascii=False,indent=2))
