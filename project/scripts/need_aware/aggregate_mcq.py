#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from metacom_pm.need_aware.evaluation.aggregate import paired_cluster
from metacom_pm.need_aware.data.personamem import write_json

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--left',required=True);p.add_argument('--right',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    load=lambda p:[json.loads(s) for s in Path(p).read_text().splitlines() if s.strip()]
    left,right=load(a.left),load(a.right)
    report={'all':paired_cluster(left,right)}
    for layer in ['representative','forget_updated','third_party','sensitive','implicit_scenario_proxy']:
        select=lambda rows:[r for r in rows if r['category'].get('selection_layer')==layer]
        report[layer]=paired_cluster(select(left),select(right))
    write_json(a.output,report);print(json.dumps(report,indent=2))
