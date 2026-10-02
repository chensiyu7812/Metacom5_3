#!/usr/bin/env python3
"""Freeze one source review for each naturally completed author candidate."""
import argparse
import json
from pathlib import Path
import sys

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.p2_supervision import review_messages,REVIEW_INSTRUCTION
OUT=PROJECT/'outputs/pm_rl1/completion_20260930_v2/P2'


def read(p):return json.loads(p.read_text())


def main(repair):
    source_stage='repair' if repair else 'author';stage='review_repair' if repair else 'review'
    if (OUT/(stage+'_jobs_freeze.json')).exists():raise RuntimeError('reviews already frozen')
    sf=read(OUT/'supervision_freeze.json')
    for n,h in sf['files'].items():assert sha256_file(OUT/n)==h,n
    for n,h in sf['source_files'].items():assert sha256_file(PROJECT/n)==h,n
    run=Path(read(OUT/(source_stage+'_pointer.json'))['run_dir']);summary=read(run/'summary.json')
    jobs=read(OUT/(source_stage+'_jobs_private.json'));bound={j['slot_id']:j for j in jobs}
    slots={s['slot_id']:s for s in read(OUT/'authoring_slots_private.json')['slots']}
    evidence=read(OUT/'source_evidence_private.json')
    assert summary['status']=='COMPLETE_UNADMITTED' and len(summary['rows'])==len(jobs)
    assert {r['slot_id'] for r in summary['rows']}==set(bound)
    requests=[];technical=[]
    guards=[run/'summary.json',run/'runtime.json',OUT/'source_evidence_private.json',OUT/'supervision_freeze.json',
        OUT/'authoring_slots_private.json',OUT/(source_stage+'_jobs_private.json'),Path(__file__)]
    for row in summary['rows']:
        sid=row['slot_id'];rid=row['request_id'];raw_path=run/(rid+'.raw.json');req_path=run/(rid+'.request.json')
        raw=read(raw_path);request=read(req_path);slot=slots[sid]
        assert request['request_id']==raw['request_id']==rid
        assert request['messages']==bound[sid]['messages']
        assert raw['runtime_identity']==request['executor_identity']
        guards.extend([raw_path,req_path])
        if raw['finish_reason']!='natural_stop' or not raw['text'].strip():
            technical.append(dict(slot_id=sid,request_id=rid,reason=raw['finish_reason']));continue
        erow=evidence[sid];assert erow['documents_identity']==digest(erow['documents'])
        assert erow['visible_messages_identity']==slot['messages_identity']
        messages=review_messages(slot,raw['text'],erow['documents'])
        requests.append(dict(slot_id=sid,index=slot['index'],category=slot['category'],split=slot['split'],
            prefix_identity=slot['prefix_identity'],attempt=row['attempt'],seed=17,messages=messages,
            renderer_identity=digest(REVIEW_INSTRUCTION),author_request_id=rid,author_raw_sha256=sha256_file(raw_path),
            author_run=str(run),documents_identity=erow['documents_identity']))
    def save(name,v):
        with (OUT/name).open('x') as f:f.write(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
    save(stage+'_jobs_private.json',requests)
    save(stage+'_technical_exclusions.json',technical)
    guards.extend([OUT/(stage+'_jobs_private.json'),OUT/(stage+'_technical_exclusions.json')])
    save(stage+'_jobs_freeze.json',dict(status='FROZEN_BEFORE_SOURCE_REVIEW',jobs=len(requests),
        technical_exclusions=len(technical),author_stage=source_stage,
        files={str(p.relative_to(PROJECT)):sha256_file(p) for p in guards},
        note='One review per natural candidate. Full sources are reviewer-only; SFT messages remain the original slot.'))
    print(json.dumps(dict(stage=stage,jobs=len(requests),technical_exclusions=len(technical))))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--repair',action='store_true');main(p.parse_args().repair)
