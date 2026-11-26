#!/usr/bin/env python3
"""Read-only, independent public-row recomputation; no model or training import."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path


METHODS = ['STOP', 'FixedTop4Macro', 'LLMOneShot', 'LLMToolAgent',
           'SequentialRule', 'SequentialNoText']
METRICS = ['agent_first_text_ns', 'agent_reply_ns', 'worker_first_text_ns']


def readl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def quantile(values, q):
    return sorted(values)[max(0, math.ceil(q * len(values)) - 1)] if values else None


def summarize(rows):
    observed = [r for r in rows if r['completion_interval'] is not None]
    result = dict(slots=len(rows), evaluated=len(observed),
                  completion_interval=[sum(r['completion_interval'][i] for r in observed)
                                       for i in (0, 1)] if observed else None)
    for key in METRICS:
        values = [r[key] for r in rows if r[key] is not None]
        result[key] = dict(n=len(values), sum=sum(values) if values else None,
                           p50=quantile(values, .5), p95=quantile(values, .95))
    return result


def choose(rows, metric, quality_first):
    # This explicitly uses old outcome labels: diagnostic ONLY, never policy.
    eligible = [r for r in rows if r[metric] is not None]
    if quality_first:
        complete = [r for r in eligible if r['completion_interval'] == [1, 1]]
        possible = [r for r in eligible if r['completion_interval'] == [0, 1]]
        eligible = complete or possible or eligible
    return min(eligible, key=lambda r: (r[metric], METHODS.index(r['method'])))


def run(source, out):
    files = ['ENDPOINTS_PUBLIC.jsonl', 'CALLS_PUBLIC.jsonl', 'JOB_TIMING_PUBLIC.jsonl',
             'QUALITY_LATENCY_TASKWISE_PUBLIC.jsonl']
    inputs = {name: readl(source / name) for name in files}
    endpoints, calls, jobs, quality = [inputs[name] for name in files]
    qmap = {(r['task'], r['method']): r for r in quality}
    assert len(qmap) == len(quality) == 48
    assert len({(r['task'], r['method']) for r in endpoints}) == len(endpoints) == 48
    assert Counter(r['status'] for r in endpoints) == Counter(
        returned_eos=38, path_technical_failure=1, unexecuted=9)
    assert len(calls) == sum(j['physical_starts'] for j in jobs) == 53
    rows = []
    for e in endpoints:
        q = qmap[e['task'], e['method']]
        actual = e['status'] == 'returned_eos'
        assert q['technical_status'] == e['status']
        first = e['agent_to_first_terminal_nonempty_text_ns']
        reply, worker = e['agent_to_reply_ns'], e['terminal_first_text_ns']
        if actual:
            assert e['real_model_output'] and e['endpoint_committed']
            assert 0 <= worker <= first <= reply
            assert reply == q['agent_wall_ns']
            assert q['completion_interval'] in ([0, 0], [0, 1], [1, 1])
        else:
            assert first is None and reply is None and worker is None
            assert q['completion_interval'] is None
        rows.append(dict(task=e['task'], method=e['method'], source_group=e['source_group'],
            status=e['status'], channel=q['channel'], completion_status=q['completion_status'],
            completion_interval=q['completion_interval'], agent_first_text_ns=first,
            agent_reply_ns=reply, worker_first_text_ns=worker,
            pre_worker_first_text_ns=None if first is None else first-worker,
            client_first_text_ns=None, first_effective_audio_ns=None,
            first_semantically_useful_text_ns=None,
            literal_thought_marker=(e.get('display_artifacts') or {}).get('leading_literal_thought_marker'),
            formal_reward=None))
    by_task = {t: [r for r in rows if r['task'] == t] for t in sorted({r['task'] for r in rows})}
    common = [t for t, rs in by_task.items() if len(rs) == 6 and all(r['status'] == 'returned_eos' for r in rs)]
    assert common == ['T01', 'T02', 'T03', 'T04', 'T07', 'T08']
    common_rows = [r for r in rows if r['task'] in common]
    choices = []
    choice_summaries = {}
    for metric in METRICS[:2]:
        for qfirst in (False, True):
            label = ('quality_then_' if qfirst else 'fastest_') + metric
            selected = [choose(by_task[t], metric, qfirst) for t in common]
            choice_summaries[label] = summarize(selected)
            for row in selected:
                choices.append(dict(row, diagnostic=label,
                    selection_uses_outcome_or_historical_latency=True,
                    deployment_policy=False, qualified_oracle=False))
    paired = []
    for t in common:
        base = next(r for r in by_task[t] if r['method'] == 'STOP')
        for r in by_task[t]:
            paired.append(dict(task=t, method=r['method'],
                completion_interval=r['completion_interval'], STOP_interval=base['completion_interval'],
                both_definite_complete=r['completion_interval']==base['completion_interval']==[1,1],
                agent_first_text_difference_ns=r['agent_first_text_ns']-base['agent_first_text_ns'],
                agent_reply_difference_ns=r['agent_reply_ns']-base['agent_reply_ns'],
                formal_reward=None))
    summary = dict(protocol='pmrl1-j-system-review-first-text-v1',
        base_commit='c40b90c99cb991cf1c2793ffbe9927a0011885ab',
        inputs_sha256={name: hashlib.sha256((source/name).read_bytes()).hexdigest() for name in files},
        actual_calls=len(calls), loads=len(jobs), endpoint_slots=len(rows),
        endpoint_status_counts=dict(Counter(r['status'] for r in rows)),
        common_tasks=common, all_observed={m:summarize([r for r in rows if r['method']==m]) for m in METHODS},
        common_six={m:summarize([r for r in common_rows if r['method']==m]) for m in METHODS},
        posthoc_choices=choice_summaries,
        quantile='nearest-rank: sorted[ceil(q*n)-1]; n=6 p95 is maximum',
        limitations=['first nonempty decoded text is not qualified useful text',
            'no client text or Tokkio audio measurement',
            'fixed execution order, one run per endpoint; no causal latency claim',
            'complete six-task subset excludes T05/T06; full 48-slot coverage preserved',
            'all joint quality-latency selections use historical outcomes or timings',
            'quality is assistant development review, not independent human qualification'],
        new_model_calls=0, formal_reward=None)
    out.mkdir(parents=True, exist_ok=False)
    (out/'FIRST_TEXT_SUMMARY_PUBLIC.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
    for name, values in [('FIRST_TEXT_TASKWISE_PUBLIC.jsonl',rows),
                         ('POSTHOC_QUALITY_LATENCY_CHOICES_PUBLIC.jsonl',choices),
                         ('FIRST_TEXT_PAIRED_PUBLIC.jsonl',paired)]:
        (out/name).write_text(''.join(json.dumps(v,ensure_ascii=False,sort_keys=True)+'\n' for v in values))
    return summary


if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args(); s=run(a.source,a.out)
    print(json.dumps({'calls':s['actual_calls'],'slots':s['endpoint_slots'],
        'common_tasks':s['common_tasks'],'first_text_p50_seconds':
        {m:r['agent_first_text_ns']['p50']/1e9 for m,r in s['common_six'].items()},
        'posthoc_choices':s['posthoc_choices']},ensure_ascii=False,indent=2))
