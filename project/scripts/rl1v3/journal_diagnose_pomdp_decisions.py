#!/usr/bin/env python3
"""Read collector output, write new diagnostic artifacts; never call a model."""
from pathlib import Path
import argparse
import hashlib
import json
import sys


def main():
    p=argparse.ArgumentParser();p.add_argument('--collection',required=True)
    p.add_argument('--plan',required=True);p.add_argument('--out',required=True)
    group=p.add_mutually_exclusive_group();group.add_argument('--reviews');group.add_argument('--quality-review')
    args=p.parse_args();root=Path(__file__).resolve().parents[2];sys.path.insert(0,str(root/'src'))
    from metacom_pm.rl1v3.journal import pomdp_decision_diagnostics as D
    collection=Path(args.collection);out=Path(args.out);out.mkdir(parents=True,exist_ok=False)
    paths={'events':collection/'ALL_EVENTS_PRIVATE.jsonl','endpoints':collection/'ALL_48_ENDPOINTS_PRIVATE.jsonl','plan':Path(args.plan)}
    def rows(path):return [json.loads(x) for x in path.read_text().splitlines() if x]
    events=rows(paths['events']);endpoints=rows(paths['endpoints']);plan=json.loads(paths['plan'].read_text())
    task_order=[t for b in plan['batches'] for t in b['task_ids']]
    expected={(t,m) for t in task_order for m in D.ARMS}
    if len(endpoints)!=len(expected) or {(r['task_id'],r['method']) for r in endpoints}!=expected:
        raise ValueError('closed full planned endpoint grid required, including unexecuted')
    reviews={}
    if args.reviews:
        paths['reviews']=Path(args.reviews)
        for r in rows(paths['reviews']):
            key=(r['task_id'],r['method'])
            if key not in expected or key in reviews or r.get('task_success') not in ('pass','fail','uncertain','pending'):
                raise ValueError('explicit review identity/status')
            reviews[key]=r
    if args.quality_review:
        paths['quality_review']=Path(args.quality_review)
        reviews=D.normalize_quality_reviews(rows(paths['quality_review']),endpoints)
    result=D.diagnose(endpoints,events,reviews=reviews)
    public=D.public_projection(result,task_order);summary=D.aggregate(result)
    selected=D.select_midstates(plan,events)
    for name,value in [('DECISION_OBSERVATIONS_PRIVATE.jsonl',result),('DECISION_TASKWISE_PUBLIC.jsonl',public),
                       ('SELECTED_MIDSTATES_PRIVATE.jsonl',selected)]:
        (out/name).write_text(''.join(json.dumps(x,ensure_ascii=False,sort_keys=True)+'\n' for x in value))
    (out/'DECISION_AGGREGATE_PUBLIC.json').write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n')
    (out/'POLICY_PAIR_REUSE_PUBLIC.json').write_text(json.dumps(D.policy_pair_reuse(endpoints,task_order),indent=2,sort_keys=True)+'\n')
    manifest=dict(protocol=D.PROTOCOL,source_files_sha256={k:hashlib.sha256(v.read_bytes()).hexdigest() for k,v in paths.items()},
        implementation_sha256=hashlib.sha256(Path(D.__file__).read_bytes()).hexdigest(),
        outputs_sha256={x.name:hashlib.sha256(x.read_bytes()).hexdigest() for x in out.iterdir()},
        model_calls=0,gpu_calls=0,api_calls=0,training_calls=0,formal_reward=None,
        source_collection_validation='upstream collector verifies original journal and payload; this tool adds observations only')
    (out/'MANIFEST.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':main()
