#!/usr/bin/env python3
"""A-side concrete joint candidate inventory; not a GPU execution approval."""
import argparse,json
from pathlib import Path
from metacom_pm.need_aware.data.v11 import jsonl
from metacom_pm.need_aware.data.contracts import digest
from metacom_pm.need_aware.data.personamem import write_json,write_jsonl,sha_file
from metacom_pm.need_aware.evaluation.wp3 import ARMS

def create(root,out):
    root,out=Path(root),Path(out)
    if out.exists():raise FileExistsError('candidate already created')
    wp3=root/'wp3';rules=root/'rules-final';sel=json.loads((wp3/'selection.json').read_text());gemma=set(sel['gemma_task_ids'])
    slots=[]
    for material,models in [(wp3,{'Qwen35':ARMS,'G0e':('B0','E0s','C')}),
                            (wp3/'bridge',{'Qwen35':('B0','C'),'G0e':('B0','C')})]:
        ds={d['task_id']:d for d in jsonl(material/'direct/direct.jsonl')}
        for t in jsonl(material/'runtime/tasks.mcq.jsonl'):
            for model,arms in models.items():
                if material==wp3 and model=='G0e' and t['task_id'] not in gemma:continue
                for arm in arms:
                    missing=arm in ('C','C+noise') and ds[t['task_id']]['status']!='located_unique'
                    slots.append(dict(logical_id=f"{t['task_id']}|{arm}|{model}",task_id=t['task_id'],model_label=model,arm=arm,
                        material=str(material),task_sha256=digest(t),history_sha256=t['history_sha256'],
                        candidate_status='structural_direct_unlocated' if missing else 'awaiting_B_native_pack',
                        scoring_protocol='naa-short-mcq-v1',max_new_tokens=64))
    if len(slots)!=1400 or len({r['logical_id'] for r in slots})!=1400:raise ValueError('planned slot identity')
    write_jsonl(out/'WP3_SLOTS.private.jsonl',slots)
    op=json.loads((rules/'WP4_POLICY.json').read_text());train=json.loads((rules/'TRAINING_CANDIDATE.json').read_text())
    proposal=dict(protocol='naa-v11-joint-candidate-a-materials-v1',authorization='not_granted',
        status='A data/evaluation/CPU objective ready; B executable request manifest and backend resource attestation pending',
        authority='65424fd807e5e14284b70a9a184288bf0ce7a95e',integration='51b385b8bd57d60a133206c36003ea1b33a1e8bf',
        materials={p:sha_file(root/p) for p in ['ALLOCATION.json','wp3/FREEZE.json','wp4-final/FREEZE.json','rules-final/FREEZE.json','CPU_BATCH_FINAL.json']},
        wp3=dict(logical_slots=1400,before_native_pack_executable=1377,structural_unlocated=23,physical_attempt_ceiling=1500,
                 gpu_wall_ceiling_seconds=57600,per_model_seconds={'Qwen35':43200,'G0e':14400},smoke_attempts_per_model=16),
        wp4_baseline=dict(methods=['U0','U1'],logical_slots=op['actual_model_baseline_requests'],physical_attempt_ceiling=500,gpu_wall_ceiling_seconds=14400),
        wp4_training=dict(methods=['U2','U3'],fit_rows=train['rows'],optimizer_steps_ceiling_per_method=500,
                          gpu_wall_ceiling_seconds_per_method=14400,total_ceiling_seconds=28800,config_sha256=sha_file(rules/'TRAINING_CANDIDATE.json')),
        wp4_post_training=dict(methods=['U2','U3'],logical_slots=op['post_training_requests'],physical_attempt_ceiling=500,gpu_wall_ceiling_seconds=14400),
        combined_ceiling_seconds=115200,inference_physical_attempt_ceiling=2500,devices='one A6000, B exclusive manager',
        budget_status='A proposed upper ceilings, NOT measured forecasts or B-agreed authorization. B must bind actual native requests, load/teardown reserves and timed estimates before submitting executable joint package.',
        constraints=['zero paid API','no formal test','no private transfer','no historical 170-slot rerun','no unapproved GPU or optimizer'],
        triggers={'inference':'new explicit researcher authorization bound to B actual request manifest',
                  'training':'new explicit training authorization + two-rater calibration + B backend/resource acceptance',
                  'post_training':'same sealed independent tasks; do not select checkpoint by their outcomes'},
        missing_B=['native WP3 token/packing request identities','U1 verified Reglos implementation binding',
                   'LoRA training backend and exact module/memory/clock audit','joint execute commands and resource signature'],
        no_claim='This is a populated A-side input/target/budget candidate, not a jointly accepted executable manifest.')
    write_json(out/'CANDIDATE.json',proposal);return proposal

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();print(json.dumps(create(a.root,a.out),indent=2))
