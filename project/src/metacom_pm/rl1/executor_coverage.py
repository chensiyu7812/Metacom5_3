"""Evidence-bound admission and exact deduplication for the frozen supplement.

These are integrity checks on separately supplied semantic reviews, not an
automatic quality classifier. No all-cell pass or positive-benefit gate.
"""
from .schema import HEADS, digest


def admitted_supplement(contract, jobs, requests, raws, reviews, evidence):
    conditions = {(c['index'], c['condition']): c for c in contract['conditions']}
    ids = [j['request_id'] for j in jobs]
    if len(ids) != len(set(ids)) or set(ids) != set(reviews) or set(ids) != set(requests) or set(ids) != set(raws):
        raise ValueError('every new attempted request needs exactly one bound review')
    rows = []
    seen_jobs = set()
    for job in jobs:
        key = job['request_id']
        c = conditions[job['index'], job['condition']]
        req, raw, review = requests[key], raws[key], reviews[key]
        jk = (job['index'], job['condition'], job['seed'])
        if jk in seen_jobs or job['seed'] not in contract['seeds']:
            raise ValueError('duplicate or undeclared author draw')
        seen_jobs.add(jk)
        if (c['split'] not in ('train', 'dev') or job['split'] != c['split']
                or job['prefix_identity'] != c['prefix_identity'] or req['seed'] != job['seed']
                or req['request_id'] != key or digest({k: v for k, v in req.items() if k != 'request_id'}) != key
                or req['messages'] != c['messages'] or digest(req['messages']) != c['messages_identity']
                or raw['request_id'] != key or raw['runtime_identity'] != req['executor_identity']):
            raise ValueError('request/answer/prefix/split/draw identity changed')
        erow = evidence[job['index'] - 1]
        if (erow['prefix_identity'] != c['prefix_identity'] or digest(erow['evidence']) != erow['evidence_identity']
                or review.get('evidence_identity') != erow['evidence_identity']
                or review.get('request_identity') != key or review.get('raw_identity') != digest(raw)
                or review.get('messages_identity') != c['messages_identity']
                or not review.get('rationale') or not review.get('checks')
                or not review.get('resource_behavior')):
            raise ValueError('review is not bound to exact output and legal evidence')
        if review['status'] not in ('accept', 'reject', 'uncertain', 'technical_failure'):
            raise ValueError('invalid admission status')
        if review['status'] != 'accept':
            continue
        if raw['finish_reason'] != 'natural_stop' or not raw['text'].strip():
            raise ValueError('unfinished answer cannot become a target')
        if review.get('unresolved_claims') or any(x is not True for x in review['checks'].values()):
            raise ValueError('unresolved admission checks')
        rows.append(dict(request_id=key, index=job['index'], owner=c['owner'], split=c['split'],
            condition=job['condition'], counts=list(c['counts']), prefix_identity=c['prefix_identity'],
            messages=req['messages'], response=raw['text'], messages_identity=digest(req['messages']),
            response_identity=digest(raw['text']), review_identity=digest(review),
            resource_behavior=review['resource_behavior'], historical_uptake=review.get('historical_uptake', False),
            provenance_batch='coverage_supplement_20260930'))
    return rows


def merge_accepted(old_rows, new_rows):
    """Keep every accepted exact prompt/response once, with all origins visible."""
    merged, by_content, seen_ids, duplicates = [], {}, set(), []
    owners = {'train': set(), 'dev': set()}
    for row in old_rows + new_rows:
        rid = row['request_id']
        if rid in seen_ids:
            raise ValueError('same request appended twice instead of reusing provenance')
        seen_ids.add(rid)
        if row['split'] not in owners or not row['response'].strip():
            raise ValueError('invalid split or empty accepted response')
        owners[row['split']].add(row['owner'])
        if row['messages_identity'] != digest(row['messages']) or row['response_identity'] != digest(row['response']):
            raise ValueError('accepted content identity changed')
        key = digest(dict(messages=row['messages'], response=row['response']))
        if key in by_content:
            kept = merged[by_content[key]]
            if kept['split'] != row['split']:
                raise ValueError('exact train/dev prompt-response collision; cannot silently drop or move it')
            kept['duplicate_request_ids'].append(rid)
            duplicates.append(dict(kept_request_id=kept['request_id'], duplicate_request_id=rid,
                duplicate_owner=row['owner'], split=row['split'], content_identity=key))
        else:
            by_content[key] = len(merged)
            merged.append(dict(row, duplicate_request_ids=[], content_identity=key))
    if owners['train'] & owners['dev']:
        raise ValueError('train/dev owner leakage')
    if not all(owners.values()):
        raise ValueError('training and development examples are both required')
    return merged, duplicates


def coverage(rows):
    result = {}
    for split in ('train', 'dev'):
        group = [r for r in rows if r['split'] == split]
        result[split] = dict(examples=len(group), owners=len({r['owner'] for r in group}),
            prefixes=len({r['prefix_identity'] for r in group}),
            by_head={h: sum(r['counts'][i] > 0 for r in group) for i, h in enumerate(HEADS)},
            off=sum(sum(r['counts']) == 0 for r in group),
            multiple_resources=sum(sum(r['counts']) > 1 for r in group),
            mp_owners=len({r['owner'] for r in group if r['counts'][1]}))
    return result
