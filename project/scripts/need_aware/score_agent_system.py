#!/usr/bin/env python3
"""Score sealed actual open replies and executed lifecycle traces, with optional limited review.

Literal checks remain observations. No automatic helpfulness/semantic judge, no
invented independent reviewer, no stripping reply text into action labels.
"""
import argparse,json
from pathlib import Path
from collections import Counter
from metacom_pm.need_aware.data.personamem import sha_file,write_json,write_jsonl
from metacom_pm.need_aware.data.response_data import jsonl
from metacom_pm.need_aware.data.contracts import text_hash
from metacom_pm.need_aware.evaluation.agent_system import check_trace,check_reply
from metacom_pm.need_aware.evaluation.wp2 import unique,require


def run(a):
    root=Path(a.material);sealed=Path(a.sealed);out=Path(a.out)
    if out.exists():raise FileExistsError('immutable system evaluation output')
    summary=json.loads((sealed/'EXPORT_SUMMARY.json').read_text())
    require(summary['final'] and summary['result_kind']=='model','real terminal seal required')
    cell=summary['files'][a.cell];file=sealed/cell['path']
    require(sha_file(file)==cell['sha256'],'prediction seal changed')
    tasks=unique(jsonl(root/'runtime/tasks.private.jsonl'),'task_id')
    specs=unique(jsonl(root/'evaluation/specs.private.jsonl'),'task_id')
    predictions=unique(jsonl(file),'task_id');episodes=unique(jsonl(a.episodes),'task_id')
    require(set(predictions)==set(tasks),'full frozen system task denominator required')
    require(set(episodes)<=set(tasks),'foreign episode')
    checks=[];review_ids={r['task_id'] for r in jsonl(root/'evaluation/review60.private.jsonl')}
    packets=[]
    for tid,task in tasks.items():
        p=predictions[tid];r=dict(task_id=tid,status=p['status'],request_sha256=p['request_sha256'])
        if p['status']=='completed':
            e=episodes.get(tid)
            require(e is not None and e['reply']==p['output'],'episode reply is not the sealed full reply')
            require(e['request_sha256']==p['request_sha256'] and e['run_id']==p['run_id'],'episode identity mismatch')
            r.update(lifecycle=check_trace(task,e['trace']['events'],p['output']),
                reply_checks=check_reply(p['output'],specs[tid]))
        checks.append(r)
        if tid in review_ids:
            packets.append(dict(task_id=tid,status=p['status'],actual_reply=p['output'] if p['status']=='completed' else None,
                actual_reply_sha256=text_hash(p['output']) if p['status']=='completed' else None,
                task=task,spec=specs[tid],review_status='not_reviewed'))
    ratings=jsonl(a.ratings) if a.ratings else [];seen=set();reviewers=set()
    for r in ratings:
        tid=r['task_id'];key=(tid,r['reviewer_id'])
        require(key not in seen,'duplicate reviewer/task');seen.add(key)
        require(tid in review_ids and predictions[tid]['status']=='completed','rating outside frozen completed review set')
        require(r['reply_sha256']==text_hash(predictions[tid]['output']),'rating reply changed')
        require(r['quality'] in (0,1,2,3,4) and type(r['misuse']) is bool,'invalid actual review values')
        require(r.get('method') in ('human','ai_assisted_single_review'),'record review method honestly')
        reviewers.add(r['reviewer_id'])
    report=dict(protocol='naa-full-agent-checks-v1',result_kind='real_model',planned=len(tasks),
        statuses=dict(Counter(r['status'] for r in checks)),
        lifecycle_complete=sum(r.get('lifecycle',{}).get('lifecycle_complete',False) for r in checks),
        predefined_review_slots=len(review_ids),actual_reviewed_replies=len({r['task_id'] for r in ratings}),
        reviewer_count=len(reviewers),independent_review_established=False,
        review_methods=dict(Counter(r['method'] for r in ratings)),
        single_reviewer_limit='one reviewer cannot establish inter-rater reliability; no independence inferred from count',
        quality_mean=sum(r['quality'] for r in ratings)/len(ratings) if ratings else None,
        misuse_review_count=sum(r['misuse'] for r in ratings),
        literal_checks_are_not_helpfulness=True,inputs=dict(seal=sha_file(sealed/'EXPORT_SUMMARY.json'),
            episodes=sha_file(a.episodes),ratings=sha_file(a.ratings) if a.ratings else None))
    write_jsonl(out/'checks.private.jsonl',checks);write_jsonl(out/'review60.private.jsonl',packets)
    write_json(out/'SUMMARY.json',report);print(json.dumps(report))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('material','sealed','cell','episodes','out'):p.add_argument('--'+name,required=True)
    p.add_argument('--ratings');run(p.parse_args())
