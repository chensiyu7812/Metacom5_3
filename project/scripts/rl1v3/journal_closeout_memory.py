#!/usr/bin/env python3
"""Recheck fixed private M2/U1 observations and write safe CPU aggregates."""
import argparse
from collections import Counter
import json
from pathlib import Path

from metacom_pm.rl1v3.io import file_sha256, write_json_once, write_jsonl_once
from metacom_pm.rl1v3.journal.keycap_memory_review import jsonl, load_completed_job, validate_m1_manual
from metacom_pm.rl1v3.journal.closeout_memory import (
    check_update, combined_representation_aggregate, paired_representation_changes, per_task_representation_table,
    validate_update_review)


def main():
    parser=argparse.ArgumentParser()
    for name in ('package','m2-job','u1-job','audit','m1-review','m2-review','u1-review','u1-inventory','out'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=False)
    m2=load_completed_job(args.package/'representation-batch-2/REQUESTS.private.jsonl',args.m2_job)
    u1=load_completed_job(args.package/'mpme6/REQUESTS.private.jsonl',args.u1_job)
    audits={r['task_id']:r for r in jsonl(args.audit)}
    m1_reviews=jsonl(args.m1_review);m2_reviews=jsonl(args.m2_review);u1_reviews=jsonl(args.u1_review)
    inventories={r['request_id']:r for r in jsonl(args.u1_inventory)}
    for joined,reviews in [(m2,m2_reviews),(u1,u1_reviews)]:
        if len(reviews)!=len(joined) or {r['request_id'] for r in reviews}!={r['request_id'] for r in joined}:
            raise ValueError('fixed review denominator changed')
        if any(r['output_sha256']!=next(j['output_sha256'] for j in joined if j['request_id']==r['request_id']) for r in reviews):
            raise ValueError('review output identity mismatch')
    for joined in m2:
        review=next(r for r in m2_reviews if r['request_id']==joined['request_id'])
        validate_m1_manual(review,joined,audits[review['task_id']])
    checked=[]
    for joined in u1:
        rid=joined['request_id'];review=next(r for r in u1_reviews if r['request_id']==rid)
        if inventories[rid]['payload_sha256']!=joined['request']['payload_sha256']:
            raise ValueError('U1 source inventory payload mismatch')
        mechanical=check_update(joined['output']['text'],inventories[rid])
        if mechanical!=review['mechanical']:
            raise ValueError('U1 source checks do not reproduce')
        validate_update_review(review,mechanical,joined['output']['text'])
        checked.append(dict(request_id=rid,mechanical=mechanical))
    combined=m1_reviews+m2_reviews
    if len(combined)!=36 or len({r['task_id'] for r in combined})!=12:
        raise ValueError('combined original representation set must be 12 x 3')
    aggregate=combined_representation_aggregate(combined,audits)
    pairs=paired_representation_changes(combined,audits)
    write_json_once(args.out/'MEMORY12_AGGREGATE_PUBLIC.json',aggregate)
    write_json_once(args.out/'MEMORY12_PAIRS_PUBLIC.json',dict(rows=pairs,semantic_approved=0,rewards=0))
    write_json_once(args.out/'MEMORY12_TASK_TABLE_PUBLIC.json',dict(rows=per_task_representation_table(combined,audits),
        scope='Only supported/calendar-derived atoms count in completion; unresolved-only tasks are never complete by empty conjunction. Same-model assistant development observations; no formal success.'))
    write_jsonl_once(args.out/'MEMORY36_REVIEW_PRIVATE.jsonl',combined)
    write_jsonl_once(args.out/'U1_MECHANICAL_PRIVATE.jsonl',checked)
    statuses=Counter(c['mechanical']['primary_mechanical_status'] for c in checked)
    source_statuses=Counter(c['mechanical']['schema_and_source_status'] for c in checked)
    record_findings=Counter(f for r in u1_reviews for item in r['records'] for f in item['development_findings'])
    update_aggregate=dict(protocol='journal-u1-development-review-v1',cases=len({r['case_id'] for r in u1_reviews}),
        outputs=len(u1_reviews),returned_records=sum(len(r['records']) for r in u1_reviews),
        primary_mechanical_statuses=dict(statuses),schema_and_source_statuses=dict(source_statuses),
        record_development_findings=dict(record_findings),
        strict_json_parse_pass=sum(c['mechanical']['parse']['strict_parse_status']=='pass' for c in checked),
        fence_sensitivity_parse_pass=sum(c['mechanical']['parse']['sensitivity_parse_status']=='pass' for c in checked),
        input_tokens=sum(r['technical']['input_tokens'] for r in u1_reviews),
        output_tokens=sum(r['technical']['output_tokens'] for r in u1_reviews),
        local_seconds=sum(r['technical']['seconds'] for r in u1_reviews),
        scope='two source-report cases; CPU prior is not model-produced semantic state; no chained-model update claim',
        formal_semantic_status='uncertain',semantic_approved=0,rewards=0)
    write_json_once(args.out/'U1_AGGREGATE_PUBLIC.json',update_aggregate)
    write_json_once(args.out/'MANIFEST_PRIVATE.json',dict(files={p.name:file_sha256(p) for p in sorted(args.out.iterdir()) if p.is_file()},
        inputs={str(p):file_sha256(p) for p in [args.audit,args.m1_review,args.m2_review,args.u1_review,args.u1_inventory]},
        code_sha256=file_sha256(__file__),model_calls=0))
    print(json.dumps(dict(memory=aggregate,update=update_aggregate),ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
