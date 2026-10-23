#!/usr/bin/env python3
"""Parse source reviews without turning bad/missing reviews into accepted rows.

Creates provisional admission and an immutable fixed audit pack. Training freeze
requires the separate coordinator audit and final admission step.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.p2_supervision import validate_review
OUT=PROJECT/'outputs/pm_rl1/completion_20260930_v2/P2'


def read(p):return json.loads(p.read_text())


def main(repair,review_root):
    stage='review_repair' if repair else 'review'
    review_root=review_root or OUT
    jf=read(review_root/(stage+'_jobs_freeze.json'))
    for n,h in jf['files'].items():assert sha256_file(PROJECT/n)==h,n
    jobs=read(review_root/(stage+'_jobs_private.json'));jobs_by_id={j['slot_id']:j for j in jobs}
    run=Path(read(review_root/(stage+'_pointer.json'))['run_dir']);summary=read(run/'summary.json')
    assert summary['status']=='COMPLETE_UNADMITTED' and len(summary['rows'])==len(jobs)
    assert {r['slot_id'] for r in summary['rows']}==set(jobs_by_id)
    evidence=read(OUT/'source_evidence_private.json');slots={s['slot_id']:s for s in read(OUT/'authoring_slots_private.json')['slots']}
    rows=[]
    for row in summary['rows']:
        sid=row['slot_id'];job=jobs_by_id[sid];rid=row['request_id']
        raw_path=run/(rid+'.raw.json');raw=read(raw_path);request=read(run/(rid+'.request.json'))
        author_path=Path(job['author_run'])/(job['author_request_id']+'.raw.json')
        assert sha256_file(author_path)==job['author_raw_sha256']
        response=read(author_path)['text'];docs=evidence[sid]['documents']
        assert request['messages']==job['messages'] and raw['request_id']==rid
        assert raw['runtime_identity']==request['executor_identity']
        parsed=None;error=None
        if raw['finish_reason']!='natural_stop':status='technical_failure';error=raw['finish_reason']
        else:
            try:parsed=validate_review(raw['text'],response,docs);status=parsed['status']
            except (ValueError,KeyError,TypeError) as exc:status='unresolved_review';error=f'{type(exc).__name__}: {exc}'
        rows.append(dict(slot_id=sid,index=job['index'],category=job['category'],split=job['split'],attempt=job['attempt'],
            author_request_id=job['author_request_id'],author_raw_path=str(author_path),author_raw_sha256=sha256_file(author_path),
            review_request_id=rid,review_raw_path=str(raw_path),review_raw_sha256=sha256_file(raw_path),
            status=status,parse_error=error,parsed=parsed,source_evidence_identity=digest(docs),
            response_identity=digest(response),messages_identity=slots[sid]['messages_identity']))
    # A failed repair author attempt has no source-review call. Retain its slot
    # explicitly, rather than losing it or requiring a fabricated review row.
    technical=read(review_root/(stage+'_technical_exclusions.json')) if (review_root/(stage+'_technical_exclusions.json')).exists() else []
    if technical:
        author_stage='repair' if repair else 'author'
        author_run=Path(read(OUT/(author_stage+'_pointer.json'))['run_dir'])
        attempts={j['slot_id']:j['attempt'] for j in read(OUT/(author_stage+'_jobs_private.json'))}
        for item in technical:
            sid=item['slot_id'];slot=slots[sid];path=author_run/(item['request_id']+'.raw.json');raw=read(path)
            assert sid not in {r['slot_id'] for r in rows}
            rows.append(dict(slot_id=sid,index=slot['index'],category=slot['category'],split=slot['split'],
                attempt=attempts[sid],author_request_id=item['request_id'],author_raw_path=str(path),
                author_raw_sha256=sha256_file(path),review_request_id=None,review_raw_path=None,review_raw_sha256=None,
                status='author_technical_failure',parse_error=item['reason'],parsed=None,
                source_evidence_identity=digest(evidence[sid]['documents']),
                response_identity=digest(raw['text']),messages_identity=slot['messages_identity']))
    suffix='_repair' if repair else ''
    def save(name,obj):
        path=OUT/name;text=json.dumps(obj,ensure_ascii=False,indent=2)+'\n'
        if path.exists():
            if path.read_text()!=text:raise ValueError('immutable existing result: '+name)
        else:path.write_text(text)
    save('provisional_admission'+suffix+'_private.json',dict(status='PROVISIONAL_AI_REVIEW_NOT_TRAINING_FREEZE',rows=rows,
        review_summary_sha256=sha256_file(run/'summary.json'),review_root=str(review_root),script_sha256=sha256_file(Path(__file__))))
    save('review_parse_summary'+suffix+'.json',dict(total=len(rows),statuses=dict(Counter(r['status'] for r in rows)),
        parse_errors=dict(Counter(r['parse_error'] for r in rows if r['parse_error'])),
        by_split={s:dict(Counter(r['status'] for r in rows if r['split']==s)) for s in ('train','dev')},
        RL_reward_calls=0,accepted_training_freeze=False))
    if not repair:
        selected=read(OUT/'coordinator_audit_slots.json')['slot_ids'];by_id={r['slot_id']:r for r in rows}
        audit=[]
        for sid in selected:
            slot=slots[sid];review=by_id.get(sid)
            audit.append(dict(slot=slot,review=review,
                response=read(Path(review['author_raw_path']))['text'] if review else None,
                documents=evidence[sid]['documents']))
        save('coordinator_audit_pack_private.json',dict(rows=audit,review_scope='AI development spot audit, not independent human validation'))
    print(json.dumps(dict(stage=stage,total=len(rows),statuses=dict(Counter(r['status'] for r in rows)),
        errors=dict(Counter(r['parse_error'] for r in rows if r['parse_error'])))))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--repair',action='store_true');p.add_argument('--review-root',type=Path)
    a=p.parse_args();main(a.repair,a.review_root)
