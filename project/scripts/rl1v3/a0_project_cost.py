"""Project bounds only from the approved plan's measured GPU batch records."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'project/src'))
from metacom_pm.rl1v3.generator.bounded_probe import estimate
from metacom_pm.rl1v3.io import write_json_once
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--measurements',type=Path,nargs='*',default=[]);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    plan=json.loads(a.plan.read_text());metrics=[]
    for directory in a.measurements:
        for path in directory.glob('batch_*.json'):
            if path.name.endswith('.started.json'):continue
            row=json.loads(path.read_text())
            if row.get('warmup'):continue
            w=row['workload']
            if row['execution_identity']!=plan['workloads'][w]['execution_identity']:raise ValueError('wrong model/runtime/workload')
            metrics.append(row)
    pilot=estimate(metrics,needcards=20,g_terminals=120,j1_calls=360)
    tiers={str(n):estimate(metrics,needcards=n,g_terminals=n*16,j1_calls=n*16*3) for n in (288,482,748)}
    write_json_once(a.out,dict(pilot=pilot,tiers=tiers,actual_batches=len(metrics),gpu_measured=bool(metrics),
        limits='Upper request counts; no J1 timing until real B2 packs are prepared. Load/queue/retry time excluded. No cost-quality claim.'))
