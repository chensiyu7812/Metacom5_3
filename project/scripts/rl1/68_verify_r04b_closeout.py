#!/usr/bin/env python3
"""Read-only recheck of the completed R04B artifacts; no model loading or writes."""
import collections
import json
from pathlib import Path
import sys

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.measurement_candidates import parse_native_choice,paired_native_status
OUT=PROJECT/'outputs/pm_rl1/r04b_measurement_20260930_v1'


def read(p):return json.loads(p.read_text())


def main():
    close=read(OUT/'closeout_manifest.json')
    for name,h in close['artifacts'].items():
        if sha256_file(PROJECT/name)!=h:raise ValueError('closeout artifact changed: '+name)
    for name,h in read(OUT/'freeze.json')['files'].items():
        if sha256_file(Path(name))!=h:raise ValueError('frozen experiment changed: '+name)
    root=PROJECT.parent
    for name,h in read(OUT/'preexisting_files.json').items():
        if sha256_file(root/name)!=h:raise ValueError('preexisting workspace changed: '+name)
    prior=read(root/read(OUT/'prior_closeout_verified.json')['file'])
    for name,h in prior['artifacts'].items():
        if sha256_file(root/name)!=h:raise ValueError('prior experiment changed: '+name)
    jobs=read(OUT/'jobs_private.json');raw={};counts=collections.Counter()
    for j in jobs:
        if j['job_id']!=digest({k:v for k,v in j.items() if k!='job_id'}):raise ValueError('job digest')
        if digest(j['input_ids'])!=j['input_identity']:raise ValueError('input digest')
        r=read(OUT/'runs'/j['model']/(j['job_id']+'.raw.json'))
        if (r['job_id'],r['input_identity'])!=(j['job_id'],j['input_identity']):raise ValueError('raw identity')
        runtime=read(OUT/'runs'/j['model']/'runtime.json')
        if r['runtime_identity']!=runtime['identity']:raise ValueError('raw runtime')
        if runtime['identity']!=digest({k:v for k,v in runtime.items() if k!='identity'}):raise ValueError('runtime digest')
        counts[j['model'],r['finish_reason']]+=1
        if j['model']=='prometheus' and parse_native_choice(r['text'],r['finish_reason'])!=r['parsed']:raise ValueError('parser drift')
        raw[j['model'],j['case_id'],j['draw'],j.get('side')]=r
    for row in read(OUT/'pair_results_private.json'):
        cid=row['case_id'];f=raw['prometheus',cid,'forward',None];r=raw['prometheus',cid,'reverse',None]
        paired=paired_native_status(f['parsed'],r['parsed'])
        if any(row['prometheus'][k]!=v for k,v in paired.items()):raise ValueError('order accounting')
        a=raw['skywork',cid,'primary','A'].get('score');b=raw['skywork',cid,'primary','B'].get('score')
        d=a-b if a is not None and b is not None else None
        if row['skywork']['delta_A_minus_B']!=d:raise ValueError('score subtraction')
    assert counts=={('prometheus','natural_stop'):88,('skywork','scored'):94,('skywork','technical_context_missing'):2}
    print(json.dumps(dict(status='VERIFIED_READ_ONLY_NO_MODEL_CALLS',jobs=len(jobs),
        closeout_files=len(close['artifacts']),prior_artifacts=len(prior['artifacts']),
        preexisting_files=len(read(OUT/'preexisting_files.json'))),indent=2))


if __name__=='__main__':main()
