"""Offline closeout of the fixed local generation batch; never dispatches."""
from pathlib import Path
from datetime import datetime, timedelta
import csv
import hashlib
import json

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent
RUN = PACKAGE / 'execution'
BASE = PACKAGE.parent


def read(p):
    return json.loads(p.read_text())


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def digest(v):
    return hashlib.sha256(json.dumps(v, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def save(name, v):
    with (HERE / name).open('x') as f:
        json.dump(v, f, ensure_ascii=False, indent=2)
        f.write('\n')


def main():
    p = read(PACKAGE/'protocol.json')
    jobs = read(PACKAGE/'jobs_private.json')
    assert (RUN/'results.json').exists() or (RUN/'STOP.json').exists()
    assert digest(jobs) == p['jobs_identity'] and len(jobs) == 16
    old = {r['row_id']: r for r in read(BASE/'acceptability_resource_review_20261019_v1/materials/selected_existing_records.json')}
    rows = []
    for i, j in enumerate(jobs, 1):
        sid = j['slot_id']; req = j['request']
        a, r = RUN/(sid+'.started.json'), RUN/(sid+'.raw.json')
        row = dict(order=i, slot_id=sid, row_id=j['row_id'], context_id=j['context_id'],
            arm=j['arm'], request_id=req['request_id'], old_request_id=j['old_request_id'],
            old_slot_id=j['old_slot_id'], started=a.exists(), status='not_dispatched',
            input_tokens=None, output_tokens=None, generation_seconds=None,
            peak_allocated_bytes=None, resource_tokens=j['resource_tokens'],
            reply=None, q=None, m=None, U=None, formal_reward_eligible=False)
        if a.exists():
            assert read(a)['request_identity'] == req['request_id']
            assert read(RUN/(sid+'.request.json')) == req
            row['started_utc'] = read(a)['utc']
            row['status'] = 'started_unresolved'
        if r.exists():
            assert a.exists()
            raw = read(r)
            assert raw['request_id'] == req['request_id']
            assert raw['runtime_identity'] == req['executor_identity'] == p['runtime']['identity']
            row.update(status=raw['finish_reason'], reply=raw.get('text'), raw_file_sha256=sha(r),
                input_tokens=raw.get('input_tokens'), output_tokens=raw.get('output_tokens'),
                generation_seconds=raw.get('generation_seconds'), peak_allocated_bytes=raw.get('peak_allocated_bytes'))
            if raw['finish_reason'] == 'natural_stop':
                assert raw['text'].strip() and raw['input_tokens'] == j['input_tokens']
                assert len(raw['output_token_ids']) == raw['output_tokens']
                assert raw['output_token_ids'][-1] in p['runtime']['policy']['eos_token_ids']
                assert raw['source_provenance_identity'] == digest(req['provenance'])
            row['matches_historical_reply_exactly'] = raw.get('text') == old[j['row_id']]['reply']
        rows.append(row)
    assert sum(r['started'] for r in rows) == len(list(RUN.glob('*.started.json'))) <= 16
    save('per_slot_results.json', rows)
    pairs = []
    for q in read(PACKAGE/'pairs.json'):
        rr = {r['arm']: r for r in rows if r['row_id'] == q['row_id']}
        pairs.append(dict(row_id=q['row_id'], context_id=q['context_id'], counts=q['counts'],
            old_reply=old[q['row_id']]['reply'],
            baseline=rr['baseline'], intervention=rr['rs_applicability'],
            exact_paired_reply_equal=(rr['baseline']['reply'] == rr['rs_applicability']['reply'])
                if all(r['status']=='natural_stop' for r in rr.values()) else None))
    save('paired_outputs.json', pairs)
    summary = {}
    for arm in ['baseline', 'rs_applicability']:
        rr = [r for r in rows if r['arm']==arm]
        summary[arm] = dict(planned=len(rr), started=sum(r['started'] for r in rr),
            completed=sum(r['status']=='natural_stop' for r in rr),
            input_tokens=sum(r['input_tokens'] or 0 for r in rr),
            output_tokens=sum(r['output_tokens'] or 0 for r in rr),
            generation_seconds=sum(r['generation_seconds'] or 0 for r in rr),
            peak_allocated_bytes=max((r['peak_allocated_bytes'] or 0 for r in rr), default=0),
            resource_tokens=sum(r['resource_tokens'] for r in rr if r['started']))
    save('usage_summary.json', dict(arms=summary, planned=16,
        started=sum(r['started'] for r in rows), completed=sum(r['status']=='natural_stop' for r in rows),
        not_dispatched=sum(not r['started'] for r in rows),
        generation_seconds=sum(r['generation_seconds'] or 0 for r in rows),
        process_receipt=read(HERE/'process_receipt.json'),
        idle_wait=read(RUN/'gpu_checks/idle_wait_result.json'),
        new_judge_requests=0, judge_cumulative=144, judge_capacity=289,
        api_cost_usd=0, new_unsettled_liability_usd=0, retries=0,
        fresh_baseline_matches_historical=sum(r.get('matches_historical_reply_exactly',False) for r in rows if r['arm']=='baseline'),
        paired_equal=sum(q['exact_paired_reply_equal'] is True for q in pairs)))
    columns = [k for k in rows[0] if k not in ('reply',)]
    with (HERE/'SLOTS_16.csv').open('x', newline='') as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction='ignore'); w.writeheader(); w.writerows(rows)
    with (HERE/'ALL_REPLIES_EN.md').open('x') as f:
        f.write('# All paired replies — complete raw text\n\nNo scores or independent human labels are assigned. Historical replies are separate comparators.\n\n')
        for q in pairs:
            f.write('## '+q['row_id']+'\n\nHistorical cached reply:\n\n'+q['old_reply']+'\n\n')
            for arm in ['baseline','intervention']:
                r = q[arm]
                f.write('### '+arm+'\n\nRequest: `'+r['request_id']+'`; status: '+r['status']+'\n\n'+(r['reply'] or '[No complete reply]')+'\n\n')
    print(json.dumps(dict(completed=sum(r['status']=='natural_stop' for r in rows), arms=summary), ensure_ascii=False))


if __name__ == '__main__':
    main()
