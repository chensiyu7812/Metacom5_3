#!/usr/bin/env python3
"""De-identified per-slot statistics for the GSWS v3 actual run (no text, no gold).

Reads actual ENDPOINT / MODEL_CALL_RETURNED events. Reports per state x arm:
interpreter validation failure, whether the terminal input fell back to RAW
(identical input token count to A0 of the same state), input/output tokens,
interpreter and terminal model seconds, local agent seconds; plus nearest-rank
P50/P95 over states where all three arms reached EOS.
"""
import argparse, glob, json, math
from collections import Counter
from pathlib import Path


def nearest_rank(xs, q):
    xs = sorted(xs); return xs[max(0, math.ceil(q * len(xs)) - 1)] if xs else None


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--run-root', required=True); p.add_argument('--catalog', required=True)
    p.add_argument('--job-dir-prefix', default='run-v3-'); p.add_argument('--output', required=True)
    a = p.parse_args()
    cat = json.loads(Path(a.catalog).read_text())
    plan0 = json.loads(Path(cat['batches'][0]['plan_path']).read_text())
    tasks = [json.loads(s) for s in Path(plan0['task_manifest_path']).read_text().splitlines()]
    alias = {t['task_id']: f'Q{i+1:02}' for i, t in enumerate(tasks)}
    rows = []
    for n in range(1, 5):
        for job in glob.glob(f'{a.run_root}/{a.job_dir_prefix}{n:02}/job-*'):
            ev = [json.load(open(f)) for f in sorted(glob.glob(job + '/[0-9]*.json'))]
            starts = {e['request']['request_id']: e['request'] for e in ev if e['event'] == 'MODEL_CALL_START'}
            ret = {e['request_id']: e['output'] for e in ev if e['event'] == 'MODEL_CALL_RETURNED'}
            interp = {}
            for rid, req in starts.items():
                if req['role'] != 'terminal' and rid in ret:
                    b = req['binding']; interp[(b['task_id'], b['stage'], b['arm'])] = ret[rid]
            for e in ev:
                if e['event'] != 'ENDPOINT':
                    continue
                o = e['output']; key = (e['task_id'], e['stage'], e['arm']); io = interp.get(key)
                rows.append(dict(job=f'GSWS-{n}', task=alias[e['task_id']], stage=e['stage'], arm=e['arm'],
                    terminal_finish=o.get('finish_reason'), terminal_in_tokens=o.get('input_tokens'),
                    terminal_out_tokens=len(o.get('token_ids') or []), terminal_model_seconds=o.get('seconds'),
                    interpreter_finish=io.get('finish_reason') if io else None,
                    interpreter_in_tokens=io.get('input_tokens') if io else None,
                    interpreter_out_tokens=len(io.get('token_ids') or []) if io else None,
                    interpreter_model_seconds=io.get('seconds') if io else None,
                    interpreter_parent_seconds=e.get('interpreter_parent_ns', 0) / 1e9,
                    interpreter_failure=e.get('interpreter_failure'),
                    local_agent_seconds=e['local_agent_ns'] / 1e9,
                    first_inference_after_load=o.get('first_inference_after_load')))
    a0 = {(r['task'], r['stage']): r['terminal_in_tokens'] for r in rows if r['arm'] == 'A0_RAW'}
    for r in rows:
        r['state_delivered_to_G'] = None if r['arm'] == 'A0_RAW' else r['terminal_in_tokens'] != a0[(r['task'], r['stage'])]
    rows.sort(key=lambda r: (r['task'], r['stage'], r['arm']))
    out = Path(a.output); out.mkdir(parents=True, exist_ok=True)
    (out / 'SLOT_STATS_PUBLIC.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
    summ = dict(protocol='gsws-v3-slot-stats-v1', terminals=len(rows), by_arm={})
    states_all_eos = {(r['task'], r['stage']) for r in rows} - {(r['task'], r['stage']) for r in rows if r['terminal_finish'] != 'eos'}
    for arm in ('A0_RAW', 'A1_READING_NOTES', 'A2_GSWS'):
        rs = [r for r in rows if r['arm'] == arm]; ok = [r for r in rs if (r['task'], r['stage']) in states_all_eos]
        d = dict(slots=len(rs), terminal_eos=sum(r['terminal_finish'] == 'eos' for r in rs))
        if arm != 'A0_RAW':
            d['interpreter_failures'] = dict(Counter(r['interpreter_failure'] for r in rs if r['interpreter_failure']))
            d['state_delivered_to_G'] = sum(bool(r['state_delivered_to_G']) for r in rs)
            d['interpreter_out_tokens_mean'] = sum(r['interpreter_out_tokens'] for r in rs) / len(rs)
            d['interpreter_model_seconds_p50_p95'] = [nearest_rank([r['interpreter_model_seconds'] for r in rs], q) for q in (.5, .95)]
        d['terminal_in_tokens_mean'] = sum(r['terminal_in_tokens'] for r in rs) / len(rs)
        d['terminal_model_seconds_p50_p95'] = [nearest_rank([r['terminal_model_seconds'] for r in ok], q) for q in (.5, .95)]
        d['local_agent_seconds_p50_p95'] = [nearest_rank([r['local_agent_seconds'] for r in ok], q) for q in (.5, .95)]
        summ['by_arm'][arm] = d
    summ['states_all_three_eos'] = len(states_all_eos)
    deltas = {}
    for arm in ('A1_READING_NOTES', 'A2_GSWS'):
        xs = []
        for (t, s) in states_all_eos:
            b = next(r for r in rows if (r['task'], r['stage'], r['arm']) == (t, s, 'A0_RAW'))
            c = next(r for r in rows if (r['task'], r['stage'], r['arm']) == (t, s, arm))
            xs.append(c['local_agent_seconds'] - b['local_agent_seconds'])
        deltas[arm] = dict(paired_local_agent_delta_seconds_p50_p95=[nearest_rank(xs, .5), nearest_rank(xs, .95)], n=len(xs))
    summ['paired_delta_vs_A0'] = deltas
    summ['scope'] = 'model-internal and local Agent times; not client first text or Tokkio audio; fixed order, no warmup, not randomized'
    (out / 'SLOT_STATS_SUMMARY_PUBLIC.json').write_text(json.dumps(summ, indent=1) + '\n')
    print(json.dumps(summ, indent=1))


if __name__ == '__main__':
    main()
