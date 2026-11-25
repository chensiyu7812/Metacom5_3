"""CPU-only replay of actual 154 calls and fixed development observations.

Requires local private evidence. It never starts a worker or creates new labels.
Original journals, requests and reviews are only read; output must be new.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from metacom_pm.rl1v3.io import file_sha256,write_json_once
from metacom_pm.rl1v3.journal import structured_results,structured_analysis,structured_format_diagnostic
from metacom_pm.rl1v3.journal import joint_results,joint_outcomes
from metacom_pm.rl1v3.journal.temporal_outcomes import representation_oracle


def main():
    p=argparse.ArgumentParser()
    for n in ('root','closeout','keycap','evidence','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    os.environ.update(CUDA_VISIBLE_DEVICES='',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
    scripts=Path(__file__).resolve().parent;verified=[]
    def read(path):return json.loads(path.read_text())
    def rows(path):return [json.loads(s) for s in path.read_text().splitlines()]
    def job(label):
        found=list((a.root/(label+'_run1')).glob('job-*'))
        if len(found)!=1:raise ValueError('exactly one original run required: '+label)
        return found[0]
    def run(script,*args):
        result=subprocess.run([sys.executable,str(scripts/script),*map(str,args)],capture_output=True,text=True)
        if result.returncode:raise RuntimeError(script+' failed: '+result.stderr)
    def equal(actual,original,ignore=()):
        x,y=read(actual),read(original)
        for k in ignore:x.pop(k,None);y.pop(k,None)
        if x!=y:raise ValueError('replay differs from frozen observed result: '+str(original))
        verified.append(dict(original=str(original),original_sha256=file_sha256(original),replay_sha256=file_sha256(actual),ignored_nonmetric_keys=list(ignore)))
    run('journal_terminal_measurements.py','--root',a.root,'--packages',a.closeout,'--out',a.out/'TS58.json')
    equal(a.out/'TS58.json',a.root/'TECHNICAL_MEASUREMENTS.json')
    run('journal_joint_measurements.py','--root',a.root,'--catalog',a.root/'joint/RUN_CATALOG.json','--out',a.out/'J96.json')
    equal(a.out/'J96.json',a.root/'JOINT_TECHNICAL_MEASUREMENTS.json')
    package=a.closeout/'structured/packages-v2';dirs=[]
    for n in (1,2):
        dest=a.out/f'S{n}';dirs.append(dest)
        structured_results.collect(package/f'batch-{n:02d}/PLAN.json',job(f'S{n}'),a.closeout/'structured/endpoints-v1',dest)
        equal(dest/'AGGREGATE_PUBLIC.json',a.root/f'structured/S{n}_results_v1/AGGREGATE_PUBLIC.json')
    policy=a.root/'structured/POLICIES_PREOUTPUT.json'
    structured_analysis.analyze(package,dirs,policy,a.out/'structured-paired')
    equal(a.out/'structured-paired/AGGREGATE_PUBLIC.json',a.root/'structured/paired_v1/AGGREGATE_PUBLIC.json',('input_sources_sha256',))
    structured_format_diagnostic.analyze(package,dirs,policy,a.root/'structured/FORMAT_DIAGNOSTIC_RULE_POSTHOC.json',a.out/'format-diagnostic')
    equal(a.out/'format-diagnostic/AGGREGATE_PUBLIC.json',a.root/'structured/format_diagnostic_v1/AGGREGATE_PUBLIC.json')
    run('journal_observable_field_diagnostic.py','--source',a.out/'format-diagnostic/FORMAT_DIAGNOSTIC_PRIVATE.jsonl','--out',a.out/'OBSERVABLE_FIELDS.json')
    equal(a.out/'OBSERVABLE_FIELDS.json',a.root/'structured/OBSERVABLE_FIELD_DIAGNOSTIC_PUBLIC.json')
    run('journal_structured_diagnostic_counts.py','--source',a.out/'format-diagnostic/FORMAT_DIAGNOSTIC_PRIVATE.jsonl',
        '--references',package/'REFERENCES.private.jsonl','--out',a.out/'diagnostic-counts')
    for name in ('FORMAT_WRAPPER_CATEGORIES_PUBLIC.json','DIAGNOSTIC_FIELD_DENOMINATORS_PUBLIC.json'):
        equal(a.out/'diagnostic-counts'/name,a.root/'structured'/name)
    run('journal_temporal_outcomes.py','--candidate',a.keycap/'temporal_generation/candidate-v1',
        '--t1-job',job('T1'),'--t2-job',job('T2'),'--audit',a.evidence/'memory_audit/v2/ATOMS_PRIVATE.jsonl',
        '--reviews',a.root/'memory/review-v1/ALL_REVIEWS_PRIVATE.jsonl','--out',a.out/'temporal')
    for name in ('TEMPORAL_AGGREGATE_PUBLIC.json','TEMPORAL_TASK_TABLE_PUBLIC.json'):
        equal(a.out/'temporal'/name,a.root/'memory/validated-v1'/name)
    oracle=representation_oracle(rows(a.closeout/'memory/validated-v2/MEMORY36_REVIEW_PRIVATE.jsonl'),
        {r['task_id']:r for r in rows(a.evidence/'memory_audit/v2/ATOMS_PRIVATE.jsonl')})
    write_json_once(a.out/'REPRESENTATION_ORACLE.json',oracle)
    # JSON normalization also normalizes the documented tuple tie order.
    equal(a.out/'REPRESENTATION_ORACLE.json',a.root/'memory/REPRESENTATION_ORACLE_PUBLIC.json',('inputs_sha256',))
    for n in range(1,7):
        dest=a.out/f'J{n}'
        joint_results.collect(a.root/f'joint/packages-v5/batch-{n:02d}/PLAN.json',job(f'J{n}'),dest)
        original=a.root/f'joint/actual-v1/batch-{n:02d}/ACTUAL_RESPONSES_PRIVATE.jsonl'
        if rows(dest/'ACTUAL_RESPONSES_PRIVATE.jsonl')!=rows(original):raise ValueError('joint recollection differs')
        equal(dest/'COLLECTION_PUBLIC.json',original.parent/'COLLECTION_PUBLIC.json')
    run('journal_joint_fact_review.py','--joint-root',a.root/'joint','--review-root',a.root/'joint/fact-review-v1','--out',a.out/'FACT_CHECKS.json')
    joint_outcomes.merge(a.root/'joint',a.out/'joint-analysis')
    equal(a.out/'joint-analysis/AGGREGATE_PUBLIC.json',a.root/'joint/analysis-v2/AGGREGATE_PUBLIC.json')
    run('journal_render_joint_review.py','--joint-root',a.root/'joint','--analysis',a.out/'joint-analysis','--out',a.out/'joint-readback')
    equal(a.out/'joint-readback/FOUR_ARM_CELLS_PUBLIC.json',a.root/'joint/readback-v2/FOUR_ARM_CELLS_PUBLIC.json')
    receipt=dict(protocol='terminal154-cpu-replay-v1',model_calls=0,new_semantic_labels=0,
        verified=verified,original_evidence_modified=False,formal_reward_qualified=False)
    write_json_once(a.out/'REPLAY_RECEIPT.json',receipt)
    print(json.dumps(dict(verified_outputs=len(verified),new_model_calls=0,receipt_sha256=file_sha256(a.out/'REPLAY_RECEIPT.json'))))


if __name__=='__main__':main()
