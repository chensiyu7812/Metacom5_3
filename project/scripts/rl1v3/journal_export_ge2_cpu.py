#!/usr/bin/env python3
"""Allowlisted public projection of GE2 CPU results; no query/RAW/gold export."""
import argparse
import json
from pathlib import Path
from metacom_pm.rl1v3.io import file_sha256, write_json_once, write_jsonl_once
from metacom_pm.rl1v3.journal import ge2_sources as S


def main():
    p=argparse.ArgumentParser()
    for n in ('root','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    root=a.root
    selection=json.loads((root/'sources/SELECTION_PRIVATE.json').read_text())
    aliases={r['task_id']:r['task_alias'] for r in selection['tasks']}
    original=S.rows(root/'source-bundle-v2/CPU_TASKS_46.runtime.jsonl')
    aliases.update({t['task_id']:'D%02d'%(i+1) for i,t in enumerate(original)})
    rows=[]
    for r in S.rows(root/'cpu-final-v1/SUPPLY_DIAGNOSTICS_PRIVATE.jsonl'):
        coverage={name:{k:v for k,v in value.items() if k!='atoms'} for name,value in r['coverage'].items()}
        rows.append(dict(task_alias=aliases[r['task_id']],task_id=r['task_id'],cohort=r['cohort'],
            origin=r['origin'],channel=r['channel'],backend=r['backend'],source_count=r['source_count'],
            source_coverage=coverage,cost=r['cost'],cpu_seconds=r['cpu_seconds'],time_scope=r['time_scope'],
            task_success=None,model_calls=0))
    write_jsonl_once(a.out/'RETRIEVAL_TASKWISE_PUBLIC.jsonl',rows)
    counts=json.loads((root/'cpu-final-v1/COUNTS_PUBLIC.json').read_text())
    write_json_once(a.out/'RETRIEVAL_COUNTS_PUBLIC.json',counts)
    tasks={t['task_id']:t for t in S.rows(root/'source-bundle-v2/TASKS.runtime.jsonl')}
    evals={e['task_id']:e for e in S.rows(root/'source-bundle-v2/EVALSPEC.private.jsonl')}
    pools={e['task_id']:e['records'] for e in S.rows(root/'source-bundle-v2/LEGAL_POOLS_PRIVATE.jsonl')}
    direct=[]
    for recipe in S.rows(root/'source-bundle-v2/DIRECT_SOURCE_RECIPE_PRIVATE.jsonl'):
        tid=recipe['task_id']; supplied=[]
        for u in recipe['source_units']:
            record=next(r for r in pools[tid] if r['record_id']==u['record_id'])
            text='\n'.join(r['exact_quote'] for r in record['source_refs'] if u['start_turn']<=r['turn_index']<=u['end_turn'])
            supplied.append(dict(record_id=u['record_id'],text=text))
        c=S.evaluate_supply(evals[tid]['required_atoms'],supplied,tasks[tid]['query'])
        direct.append(dict(task_alias=aliases[tid],task_id=tid,source_units=len(recipe['source_units']),
            source_coverage={k:v for k,v in c.items() if k!='atoms'},
            reference_caveats=[x.get('reference_status') for x in evals[tid]['required_atoms'] if x.get('reference_status') not in (None,'supported')],
            task_success=None,diagnostic_only=True))
    write_jsonl_once(a.out/'DIRECT_SOURCE_COVERAGE_PUBLIC.jsonl',direct)
    inputs={str(p):file_sha256(p) for p in (
        root/'source-bundle-v2/MANIFEST_PRIVATE.json',root/'cpu-final-v1/MANIFEST_PRIVATE.json',
        root/'sources/SELECTION_PRIVATE.json',root/'sources/RETRIEVAL_CONFIG_FREEZE.json')}
    write_json_once(a.out/'CPU_EXPORT_RECEIPT_PUBLIC.json',dict(inputs_sha256=inputs,
        source_tables=108,original_task_count=46,selected_task_count=8,selected_official_overlap=3,
        export_allowlist_only=True,model_calls=0,formal_reward=None))
    print(json.dumps(dict(out=str(a.out),taskwise_rows=len(rows),direct_rows=len(direct),model_calls=0)))


if __name__=='__main__':main()
