#!/usr/bin/env python3
"""Bind the known journal failure and reuse its completed original-model calls.

This is a new, explicit technical-repair run from the unchanged original
adapter, not a resume, checkpoint search, or reset of an unknown model entry.
"""
from copy import deepcopy
import json
from pathlib import Path
import sys
PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.rl1.calibration_workflow import stamp
from metacom_pm.rl1.durable import save_json_once
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.supervised_learning import file_sha


def read(p):return json.loads(p.read_text())


def main():
    old=PROJECT/'outputs/pm_rl1/executor_revision_20261104_v1'
    out=PROJECT/'outputs/pm_rl1/executor_revision_20261104_v2'
    if out.exists():raise ValueError('repair package already exists; no restart')
    log=(old/'TRAIN.log').read_text();assert 'FileExistsError' in log and "save_json(run/'steps.json',steps)" in log
    assert not (old/'training/FINAL.json').exists() and not list((old/'training').rglob('*.safetensors'))
    jobs=read(old/'BASELINE_JOBS_PRIVATE.json');assert len(jobs)==5
    baselines=read(old/'REUSED_BASELINES_PRIVATE.json');replays=[]
    for job in jobs:
        key=job['request']['request_id'];rawpath=old/'baseline_G'/(key+'.raw.json');raw=read(rawpath)
        assert read(old/'baseline_G'/(key+'.started.json'))==job
        assert raw['finish_reason']=='natural_stop' and raw['request_id']==key
        if job.get('replay'):
            previous=baselines[job['input_identity']]['raw']
            replays.append(dict(input_identity=job['input_identity'],text_equal=previous['text']==raw['text'],
                                tokens_equal=previous['output_token_ids']==raw['output_token_ids']))
        else:baselines[job['input_identity']]=dict(messages=job['request']['messages'],raw=raw,provenance=dict(path=str(rawpath.resolve()),request_id=key))
    assert len(baselines)==32
    failure=dict(status='KNOWN_JOURNAL_FAILURE_NO_CHECKPOINT',exit_code=1,original_generation_completed=5,
        persisted_step_records=1,second_optimizer_step_returned_before_journal_exception=True,
        optimizer_updates_in_lost_process=2,usable_checkpoints=0,unknown_G_calls=0,
        error='immutable save_json was wrongly used to replace the growing steps list',
        repair='append separate immutable step/epoch files; aggregate once after all epochs; initialize baseline directory',
        initialization='same original P2 epoch_3, not lost in-memory weights',original_replays=replays)
    save_json_once(old/'FAILURE.json',failure)
    save_json_once(old/'OUTPUT_MANIFEST.json',{str(p.relative_to(old)):file_sha(p) for p in sorted(old.rglob('*')) if p.is_file() and p.name!='OUTPUT_MANIFEST.json'})
    p=deepcopy(read(old/'PROTOCOL.json'));p.pop('identity')
    paths=[Path(__file__),PROJECT/'scripts/rl1/165_train_executor_revision_repair.py',PROJECT/'src/metacom_pm/rl1/revision_journal.py']
    p['assets'].update({str(x.resolve()):file_sha(x) for x in paths})
    p['sources'].update({str((old/'OUTPUT_MANIFEST.json').resolve()):file_sha(old/'OUTPUT_MANIFEST.json')})
    p.update(baseline_jobs_identity=digest([]),reused_identity=digest(baselines),max_baseline_G_calls=0,
        run_directory=str(out.resolve()),technical_repair_parent=str(old.resolve()),technical_failure=failure,
        additional_training_loads_for_repair=1,all_attempts_training_loads_including_failed=2,
        hyperparameters_and_examples_unchanged=True,quality_based_restart=False)
    p=stamp(p);out.mkdir(mode=0o700)
    for name in ['TRAINING_PRIVATE.json','INPUTS_PRIVATE.json','EVAL_CARDS_PRIVATE.json','PROJECTIONS_PRIVATE.json']:
        save_json_once(out/name,read(old/name))
    save_json_once(out/'BASELINE_JOBS_PRIVATE.json',[]);save_json_once(out/'REUSED_BASELINES_PRIVATE.json',baselines)
    save_json_once(out/'PROTOCOL.json',p)
    review=read(old/'WEAK_SOURCE_REVIEW_PRIVATE.json');review.pop('identity');review['protocol_identity']=p['identity']
    review['carried_unchanged_review_from']=str((old/'WEAK_SOURCE_REVIEW_PRIVATE.json').resolve())
    save_json_once(out/'WEAK_SOURCE_REVIEW_PRIVATE.json',stamp(review))
    summary=read(old/'SUMMARY_PREPARE.json');summary.update(reused_baselines=32,new_baseline_calls=0,technical_repair=failure)
    save_json_once(out/'SUMMARY_PREPARE.json',summary)
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':main()
