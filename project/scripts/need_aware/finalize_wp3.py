#!/usr/bin/env python3
"""One deterministic terminal-only CPU hook for B's frozen WP3 run.

Invoke after B's runner exits. No polling, Generator, prompt edits or GPU access.
Uses existing frozen WP3 rules; mixed bridge/confirm exports are split by frozen IDs.
"""
import argparse
import json
from pathlib import Path
from metacom_pm.need_aware.data.contracts import load_runtime
from metacom_pm.need_aware.data.personamem import sha_file,write_json,write_jsonl
from metacom_pm.need_aware.data.response_data import jsonl
from metacom_pm.need_aware.evaluation.export import seal_export
from metacom_pm.need_aware.evaluation.contracts import EvalTask
from metacom_pm.need_aware.evaluation.wp3 import score_requests,paired_frozen_subset,holm_family
from metacom_pm.need_aware.evaluation.wp2 import counts
from aggregate_wp3 import aggregate


def run(a):
    out=Path(a.out);wp3=Path(a.wp3);policy=json.loads(Path(a.policy).read_text())
    if out.exists():raise FileExistsError('preserve previous terminal scoring output')
    assert sha_file(wp3/'FREEZE.json')==policy['material_freeze_sha256']
    freeze=json.loads((wp3/'FREEZE.json').read_text())
    for rel,sha in freeze['artifacts'].items():assert sha_file(wp3/rel)==sha
    seal=seal_export(a.manifest_dir,a.ledger_root,out/'sealed',kind='model',final=True)
    md=Path(a.manifest_dir);manifest=json.loads((md/'MANIFEST.json').read_text())
    req=jsonl(md/manifest['requests_file']);allcells={};bridge={}
    for population,root in [('confirm',wp3),('bridge',wp3/'bridge')]:
        tasks=load_runtime(root/'runtime/tasks.mcq.jsonl')
        ev={r['task_id']:EvalTask(**r) for r in jsonl(root/'evaluation/tasks.mcq.jsonl')}
        for cell,file in seal['files'].items():
            model,arm=cell.split('|')
            allowed={r['task_id'] for r in req if r['model_label']==model and r['arm']==arm}
            selected=[t for t in tasks if t.task_id in allowed]
            if not selected:continue
            ids={t.task_id for t in selected}
            predictions=[r for r in jsonl(out/'sealed'/file['path']) if r['task_id'] in ids]
            scored=score_requests(selected,{k:ev[k] for k in ids},req,predictions,model=model,arm=arm)
            write_jsonl(out/population/f'{model}.{arm}.private.jsonl',scored)
            (allcells if population=='confirm' else bridge)[cell]=scored
    selection=json.loads((wp3/'selection.json').read_text())
    write_json(out/'CONFIRM_AGGREGATE.json',aggregate(allcells,policy,selection['gemma_task_ids']))
    pairs=[]
    for model in ('G0e','Qwen35'):
        for arm,oldarm in [('B0','B'),('C','C')]:
            old=jsonl(Path(a.old_scored)/f'scored.{model}.{oldarm}.private.jsonl')
            new=bridge[model+'|'+arm]
            p=paired_frozen_subset(old,new,[t['task_id'] for t in new],policy)
            p.update(model=model,arm=arm);pairs.append(p)
    write_json(out/'BRIDGE_AGGREGATE.json',dict(comparisons=holm_family(pairs),
        scope='exposed 60-task protocol bridge; never pooled with confirmation or official WP2'))
    write_json(out/'POSTPROCESS_COMPLETE.json',dict(result_kind='real_model',final=True,
        seal_sha256=sha_file(out/'sealed/EXPORT_SUMMARY.json'),
        confirm_sha256=sha_file(out/'CONFIRM_AGGREGATE.json'),bridge_sha256=sha_file(out/'BRIDGE_AGGREGATE.json')))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for n in ('manifest-dir','ledger-root','wp3','policy','old-scored','out'):p.add_argument('--'+n,required=True)
    run(p.parse_args())
