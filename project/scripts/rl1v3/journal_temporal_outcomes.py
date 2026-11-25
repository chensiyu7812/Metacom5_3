#!/usr/bin/env python3
"""Validate private fixed T1/T2 reviews and produce safe count-only tables."""
import argparse
from collections import Counter
import json
from pathlib import Path

from metacom_pm.rl1v3.io import file_sha256,object_sha256,write_bytes_once,write_json_once,write_jsonl_once
from metacom_pm.rl1v3.journal.keycap_memory_review import jsonl,load_completed_job
from metacom_pm.rl1v3.journal.temporal_outcomes import join_temporal_outputs,temporal_aggregate,validate_temporal_review


def main():
    parser=argparse.ArgumentParser()
    for name in ('candidate','t1-job','t2-job','audit','reviews','out'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=False)
    physical=load_completed_job(args.candidate/'batch-01/REQUESTS.private.jsonl',args.t1_job)+load_completed_job(args.candidate/'batch-02/REQUESTS.private.jsonl',args.t2_job)
    joined=join_temporal_outputs(jsonl(args.candidate/'REQUESTS_LOGICAL.private.jsonl'),physical)
    reviews=jsonl(args.reviews);audits={r['task_id']:r for r in jsonl(args.audit)}
    deliveries={(r['task_id'],r['arm']):r for r in jsonl(args.candidate/'DELIVERY.private.jsonl')}
    supplies={(r['task_id'],r['arm']):{a['atom_id']:a['sufficient_group_covered'] for a in r['atoms']} for r in jsonl(args.candidate/'SUPPLY_EVALUATION.private.jsonl')}
    if len(joined)!=24 or len(physical)!=22 or len(reviews)!=24 or {r['logical_id'] for r in reviews}!={r['logical_id'] for r in joined}:
        raise ValueError('fixed T1/T2 denominator changed')
    by_logical={r['logical_id']:r for r in joined};same_physical={};public=[]
    for review in reviews:
        row=by_logical[review['logical_id']];delivery=deliveries[row['request']['task_id'],review['arm']]
        validate_temporal_review(review,row,audits[review['original_task_id']],delivery)
        actual=row['output'];technical=review['technical']
        if (technical['input_tokens'],technical['output_tokens'],technical['seconds'],technical['finish_reason'])!=(actual['input_tokens'],len(actual['token_ids']),actual['seconds'],actual['finish_reason']):
            raise ValueError('reported cost/status differs from actual returned event')
        for atom in review['atoms']:
            if atom['reference_status'] in {'supported','calendar_derived'} and atom['frozen_group_covered']!=supplies[row['request']['task_id'],review['arm']][atom['atom_id']]:
                raise ValueError('frozen source-group coverage changed')
        content=object_sha256(dict(atoms=review['atoms'],abstention=review['abstention_status'],findings=review['additional_findings']))
        if review['request_id'] in same_physical and same_physical[review['request_id']]!=content:
            raise ValueError('identical physical response has inconsistent duplicate review')
        same_physical[review['request_id']]=content
        eligible=[a for a in review['atoms'] if a['reference_status'] in {'supported','calendar_derived'}]
        public.append(dict(original_task_id=review['original_task_id'],strict_task_id=row['request']['task_id'],arm=review['arm'],request_id=review['request_id'],
            physical_reuse_count=row['physical_reuse_count'],original_required_atoms=len(review['atoms']),supported_atoms=len(eligible),unresolved_reference_atoms=len(review['atoms'])-len(eligible),
            reference_status_counts=dict(Counter(a['reference_status'] for a in review['atoms'])),frozen_supply_covered=sum(a['frozen_group_covered'] for a in eligible),
            completion_counts=dict(Counter(a['observed'] for a in eligible)),source_sessions_count=review['source_sessions_count'],future_sources=review['future_sources'],
            date_scope_kind=delivery['scope']['kind'],abstention_status=review['abstention_status'],
            input_tokens=review['technical']['input_tokens'],output_tokens=review['technical']['output_tokens'],local_seconds=review['technical']['seconds'],
            formal_semantic_status='uncertain',reward=None))
    aggregate=temporal_aggregate(reviews)
    write_json_once(args.out/'TEMPORAL_AGGREGATE_PUBLIC.json',aggregate)
    write_json_once(args.out/'TEMPORAL_TASK_TABLE_PUBLIC.json',dict(rows=public,semantic_approved=0,rewards=0))
    write_jsonl_once(args.out/'VERIFIED_REVIEWS_PRIVATE.jsonl',reviews)
    lines=['# Private strict-date outcome review','','Original 24 logical / 22 physical outputs retained. Source supply differs across methods; reused outputs are not independent observations. Same-model assistant development review, no qualified semantic reward.','']
    for review in reviews:
        lines+=['## '+review['original_task_id']+' / '+review['arm'],'','Original question: '+review['question'],'','Original Gold: '+review['gold'],'','Strict cutoff: '+review['cutoff']+'; source sessions: '+', '.join(review['source_sessions']),'','Actual reply:','',review['full_response'],'','| Atom | Reference | Frozen group supplied | Observation | Exact answer evidence |','|---|---|---|---|---|']
        for atom in review['atoms']:
            lines+=['| '+atom['claim']+' | '+atom['reference_status']+' | '+str(atom['frozen_group_covered'])+' | '+atom['observed']+' | '+' / '.join(atom['output_quotes'])+' |']
        lines+=['']
        for atom in review['atoms']:
            lines+=['- '+atom['atom_id']+': '+atom['reason']]
            for source in atom['source_quotes']:
                lines+=['  - '+source['location']+' '+source['speaker']+' '+source['report_date']+': '+source['quote']]
        for finding in review['additional_findings']:
            lines+=['- '+finding['kind']+': '+finding['reason']+' Output: '+' / '.join(finding['output_quotes'])+' Source: '+' / '.join(finding.get('source_quotes',[]))]
        lines+=['','Abstention: '+review['abstention_status'],'','Technical: '+json.dumps(review['technical']),'']
    write_bytes_once(args.out/'TEMPORAL_REVIEW_PRIVATE.md','\n'.join(lines).encode())
    write_json_once(args.out/'MANIFEST_PRIVATE.json',dict(inputs_sha256={str(p):file_sha256(p) for p in [args.audit,args.reviews,args.candidate/'EVALUATION_RULES.json',args.candidate/'REQUESTS_LOGICAL.private.jsonl']},
        output_sha256={p.name:file_sha256(p) for p in args.out.iterdir() if p.is_file()},code_sha256=file_sha256(__file__),model_calls=0))
    print(json.dumps(aggregate,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
