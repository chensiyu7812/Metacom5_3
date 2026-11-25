#!/usr/bin/env python3
"""Replay private quote/identity checks and export content-free fact counts."""
import argparse
import html
import json
from pathlib import Path
from metacom_pm.rl1v3.io import file_sha256, object_sha256
from metacom_pm.rl1v3.journal.joint_fact_review import validate_review, aggregate, completion_intervals


def read_rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--joint-root', type=Path, required=True)
    parser.add_argument('--review-root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    receipt = json.loads((args.review_root/'SOURCE_READ_RECEIPT_PRIVATE.json').read_text())
    if receipt['joint_generation_outputs_read'] != 0:
        raise ValueError('source receipt was not frozen before output reading')
    for path, expected in receipt['files'].items():
        if file_sha256(path) != expected:
            raise ValueError('frozen source input changed')
    evaluations = {r['task_id']:r for r in read_rows(args.joint_root/'source-bundle-v1/EVALSPEC.private.jsonl')}
    requests = {r['logical_id']:r for r in read_rows(args.joint_root/'packages-v5/REQUESTS_ALL.private.jsonl')}
    supply = {r['logical_id']:r for r in read_rows(args.review_root/'SUPPLY_FROZEN_PRIVATE.jsonl')}
    actual = {}
    for path in sorted((args.joint_root/'actual-v1').glob('batch-*/ACTUAL_RESPONSES_PRIVATE.jsonl')):
        for row in read_rows(path):
            if row['logical_id'] in actual:
                raise ValueError('duplicate actual logical output')
            actual[row['logical_id']] = row
    reviews = []
    for path in sorted(args.review_root.glob('BATCH_*_FACT_REVIEW_PRIVATE.jsonl')):
        reviews.extend(read_rows(path))
    if not reviews:
        raise ValueError('no private observations supplied')
    for row in reviews:
        key=row['logical_id']; request=requests[key]; item=actual[key]; delivered=supply[key]
        if object_sha256(request['model_input']) != request['payload_sha256'] or request['payload_sha256'] != item['payload_sha256']:
            raise ValueError('actual request payload mismatch')
        msgs=request['model_input']['messages']; current=html.unescape(msgs[-1]['content'])
        resource=html.unescape('\n'.join(m['content'] for m in msgs[:-1]))
        quote=delivered['source_binding']['exact_quote']
        if (quote in current) != delivered['exact_source_quote_present_current'] or (quote in resource) != delivered['exact_source_quote_present_MS']:
            raise ValueError('actual supplied quote differs from source receipt')
        validate_review(row,item,evaluations[row['task_id']],delivered)
    result=aggregate(reviews)
    scope_file=args.review_root/'CONTEXT_SCOPE_UNCERTAINTY_PRIVATE.json'
    disputes=[]
    if scope_file.exists():
        scope=json.loads(scope_file.read_text())
        if file_sha256(args.review_root/'BATCH_01_FACT_REVIEW_PRIVATE.jsonl') != scope['original_review_sha256']:
            raise ValueError('original observations changed after scope sidecar')
        disputes=scope['affected_atoms']
        result['interpretation_sidecar_sha256']=file_sha256(scope_file)
    result['context_interpretation_intervals']=completion_intervals(reviews,disputes)
    result['source_receipt_sha256']=file_sha256(args.review_root/'SOURCE_READ_RECEIPT_PRIVATE.json')
    result['review_rows_validated']=len(reviews)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    with args.out.open('x') as handle:
        json.dump(result,handle,ensure_ascii=False,indent=2)
        handle.write('\n')
    print(json.dumps(dict(review_rows=len(reviews),public_aggregate_sha256=file_sha256(args.out))))


if __name__ == '__main__':
    main()
