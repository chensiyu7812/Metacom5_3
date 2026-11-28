#!/usr/bin/env python3
"""Terminal W4-0 score/aggregate using the pre-output frozen modified-MCQ policy.

No new sampling, protocol changes, independent-question intervals or GPU calls.
Raw outputs/owner-level material stay private. Aggregate is safe to publish.
"""
import argparse,json,os
from collections import Counter
from pathlib import Path
from metacom_pm.need_aware.data.contracts import load_runtime,digest
from metacom_pm.need_aware.data.personamem import sha_file,write_json,write_jsonl
from metacom_pm.need_aware.data.response_data import jsonl
from metacom_pm.need_aware.evaluation.contracts import EvalTask
from metacom_pm.need_aware.evaluation.wp2 import require
from metacom_pm.need_aware.evaluation.wp4_mcq import POLICY,score,summarize,paired,clusters

ARMS=('U0','U1','U1+','NoMem','OptOnly')
# Every completed base comparison was frozen before outputs. Primary U3-U2 remains pending.
BASE_COMPARISONS=(('U1','U1+','U1+-U1'),('U0','U1','U1-U0'),
                  ('NoMem','U0','U0-No-memory'),('OptOnly','NoMem','No-memory-Options-only'))


def run(a):
    os.umask(0o077);out=Path(a.out);material=Path(a.material);sealed=Path(a.sealed);md=Path(a.manifest)
    require(not out.exists(),'immutable destination already exists')
    frozen=json.loads((material/'FREEZE.json').read_text())
    for rel,sha in frozen['artifacts'].items():require(sha_file(material/rel)==sha,'frozen artifact changed: '+rel)
    policy=json.loads((material/'POLICY.json').read_text())
    require(policy==POLICY,'scorer differs from pre-output policy')
    manifest=json.loads((md/'MANIFEST.json').read_text());seal=json.loads((sealed/'EXPORT_SUMMARY.json').read_text())
    require(seal['final'] and seal['result_kind']=='model','real terminal model seal required')
    require(digest(manifest)==seal['manifest_sha256'],'manifest/seal mismatch')
    require(manifest==json.loads(Path(a.original_manifest).read_text()),'executed manifest differs from A freeze')
    require(sha_file(sealed/'LEDGER_SNAPSHOT.private.jsonl')==seal['ledger_snapshot_sha256'],'ledger snapshot changed')
    reqfile=md/manifest['requests_file'];require(sha_file(reqfile)==manifest['requests_sha256'],'requests changed')
    tasks=load_runtime(material/'runtime/tasks.mcq.jsonl');requests=jsonl(reqfile)
    require(len(tasks)==frozen['tasks'] and len({t.persona_group for t in tasks})==frozen['owners'],'population changed')
    expected={f'{t.task_id}|{arm}|Qwen35' for t in tasks for arm in ARMS}
    require(len(requests)==len(expected) and {r['logical_id'] for r in requests}==expected,'planned logical cells changed')
    require(set(seal['files'])=={'Qwen35|'+arm for arm in ARMS},'five complete cells required')
    evaluations={r['task_id']:EvalTask(**r) for r in jsonl(material/'evaluation/tasks.mcq.jsonl')}
    cells={};categories=sorted({(k,v) for e in evaluations.values() for k,v in e.category.items()})
    for arm in ARMS:
        meta=seal['files']['Qwen35|'+arm];file=sealed/meta['path']
        require(sha_file(file)==meta['sha256'],'prediction file changed')
        rows=score(tasks,evaluations,requests,jsonl(file),model='Qwen35',arm=arm,kind='model')
        cells[arm]=rows;write_jsonl(out/'scored'/f'Qwen35.{arm}.private.jsonl',rows)
    comparisons={name:paired(cells[left],cells[right]) for left,right,name in BASE_COMPARISONS}
    by_category={f'{k}:{v}':dict(
        cells={arm:summarize([r for r in rows if r['category'].get(k)==v]) for arm,rows in cells.items()},
        paired={name:paired([r for r in cells[left] if r['category'].get(k)==v],
                           [r for r in cells[right] if r['category'].get(k)==v]) for left,right,name in BASE_COMPARISONS})
        for k,v in categories}
    private=[]
    indexed={arm:{r['task_id']:r for r in rows} for arm,rows in cells.items()}
    for task in tasks:
        private.append(dict(task_id=task.task_id,owner=task.persona_group,history_family=task.source_family,
            category=evaluations[task.task_id].category,
            outcomes={arm:indexed[arm][task.task_id]['outcome'] for arm in ARMS},
            choices={arm:indexed[arm][task.task_id]['predicted_choice'] for arm in ARMS}))
    write_jsonl(out/'paired_records.private.jsonl',private)
    report=dict(protocol='naa-w40-terminal-aggregate-v1',result_kind='real_model',policy=policy,
        tasks=len(tasks),owners=frozen['owners'],clusters=len(set(clusters(tasks).values())),
        cells={arm:summarize(rows) for arm,rows in cells.items()},paired=comparisons,categories=by_category,
        choice_counts={arm:dict(Counter(r['predicted_choice'] for r in rows if r['status']=='completed')) for arm,rows in cells.items()},
        primary_status='U3-U2 not yet executed; not replaced by a favorable secondary contrast',
        secondary_status='predeclared descriptive owner/history-family cluster intervals; no unadjusted significance claim',
        outcome_scope='modified protocol development only; others metadata is not a validated third-party task label',
        costs=seal['execution_metrics']['per_model']['Qwen35'],
        identities=dict(material_freeze_sha256=sha_file(material/'FREEZE.json'),policy_sha256=sha_file(material/'POLICY.json'),
            manifest_sha256=digest(manifest),requests_sha256=manifest['requests_sha256'],
            seal_sha256=sha_file(sealed/'EXPORT_SUMMARY.json'),ledger_head_sha256=seal['ledger_head_sha256'],
            scored_files={arm:sha_file(out/'scored'/f'Qwen35.{arm}.private.jsonl') for arm in ARMS}))
    write_json(out/'AGGREGATE.json',report)
    write_json(out/'COMPLETE.json',dict(protocol=report['protocol'],aggregate_sha256=sha_file(out/'AGGREGATE.json'),
        real_model=True,gpu_calls_by_scorer=0,manifest_sha256=digest(manifest),policy_sha256=sha_file(material/'POLICY.json')))
    print(json.dumps({k:report[k] for k in ('cells','paired')},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('material','sealed','manifest','original-manifest','out'):p.add_argument('--'+name,required=True)
    run(p.parse_args())
