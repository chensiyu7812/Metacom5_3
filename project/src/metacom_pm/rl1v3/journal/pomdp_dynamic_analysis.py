"""Read-only quality/latency join for the fixed dynamic comparison.

Development observations are not reward qualifications. Missing terminal
counterfactuals stay missing, and generation time is never substituted for
the directly measured local Agent interval.
"""
from __future__ import annotations

from collections import Counter
import json
import math
from pathlib import Path

from ..io import file_sha256, object_sha256, write_json_once, write_jsonl_once

ARMS = ('STOP', 'FixedTop4Macro', 'LLMOneShot', 'LLMToolAgent',
        'SequentialRule', 'SequentialNoText')


def rows(path):
    return [json.loads(s) for s in Path(path).read_text().splitlines()]


def interval(review):
    value = review['task_completion']['development_interval']
    if value is None:
        return None
    if value not in ([0, 0], [0, 1], [1, 1]):
        raise ValueError('invalid development interval')
    return value


def quantile(values, p):
    values = sorted(x for x in values if x is not None)
    return None if not values else values[math.ceil(len(values) * p) - 1]


def paired(a, b):
    """Same-input/same-text semantic ambiguity is shared; timing is actual."""
    ia, ib = a['completion_interval'], b['completion_interval']
    same = (a['payload_sha256'] is not None and
            a['payload_sha256'] == b['payload_sha256'] and
            a['text_sha256'] == b['text_sha256'])
    if same and ia != ib:
        raise ValueError('same task/input/output received inconsistent quality')
    delta = None if ia is None or ib is None else (
        [0, 0] if same else [ia[0] - ib[1], ia[1] - ib[0]])
    if ia is None or ib is None:
        kind = 'missing_terminal_or_review'
    elif ia == ib == [1, 1]:
        kind = 'both_definite_complete'
    elif ia == ib == [0, 0]:
        kind = 'both_definite_incomplete'
    elif ia == [1, 1] and ib == [0, 0]:
        kind = 'definite_repair'
    elif ia == [0, 0] and ib == [1, 1]:
        kind = 'definite_regression'
    else:
        kind = 'semantic_uncertainty'
    ta, tb = a['agent_wall_ns'], b['agent_wall_ns']
    return dict(task=a['task'], method=a['method'], baseline=b['method'],
                stratum=kind, completion_difference_interval=delta,
                same_payload_and_text=same,
                agent_wall_difference_ns=None if ta is None or tb is None else ta - tb,
                actual_endpoint_latency_not_cache=True, formal_reward=None)


def group_summary(group):
    evaluable = [r for r in group if r['completion_interval'] is not None]
    times = [r['agent_wall_ns'] for r in group if r['agent_wall_ns'] is not None]
    def total(key):
        values = [r[key] for r in group if r[key] is not None]
        return sum(values) if values else None
    return dict(slots=len(group), evaluated=len(evaluable),
        missing_quality=len(group) - len(evaluable),
        completion_interval_observed=None if not evaluable else [sum(r['completion_interval'][i] for r in evaluable) for i in (0, 1)],
        completion_status_counts=dict(Counter(r['completion_status'] for r in group)),
        technical_status_counts=dict(Counter(r['technical_status'] for r in group)),
        agent_wall_observations=len(times), agent_wall_sum_ns=sum(times) if times else None,
        agent_wall_p50_ns=quantile(times, .5), agent_wall_p95_ns=quantile(times, .95),
        pm_ns_sum_observed=total('pm_ns'), guard_ns_sum_observed=total('guard_ns'),
        controller_generation_ns_sum_observed=total('controller_generation_ns'),
        logging_wall_ns=None, formal_reward=None)


def analyze(collection, reviews, out):
    collection, reviews, out = Path(collection), Path(reviews), Path(out)
    if out.exists():
        raise FileExistsError(out)
    endpoints = rows(collection / 'ALL_48_ENDPOINTS_PRIVATE.jsonl')
    public = rows(collection / 'ALL_48_ENDPOINTS_PUBLIC.jsonl')
    quality = rows(reviews)
    by_key = {(r['task_id'], r['method']): r for r in quality}
    if len(endpoints) != 48 or len(quality) != 48 or len(by_key) != 48 or len(public) != 48:
        raise ValueError('retain all 48 unique frozen slots')
    if set(by_key) != {(e['task_id'], e['method']) for e in endpoints}:
        raise ValueError('quality/endpoint task identity')
    joined = []
    private_keys = []
    aliases = {}
    review_aliases = {}
    for e, p in zip(endpoints, public):
        q = by_key[(e['task_id'], e['method'])]
        aliases.setdefault(e['task_id'], p['task'])
        review_aliases.setdefault(e['task_id'], q['task_alias'])
        # Quality and transport use independent display prefixes (Q/T).
        # Identity joins use the actual task ID and immutable bytes, not names.
        if (e['method'] != p['method'] or aliases[e['task_id']] != p['task']
                or review_aliases[e['task_id']] != q['task_alias']):
            raise ValueError('anonymous slot alignment')
        for key in ('payload_sha256', 'output_sha256', 'request_id', 'evalspec_sha256'):
            if e.get(key) != q.get(key):
                raise ValueError('review byte binding: ' + key)
        complete_technical = e['status'] == 'returned_eos' and e['endpoint_committed']
        value = interval(q)
        if complete_technical:
            if not e['real_model_output'] or value is None or e['output']['text'] != q['output_text']:
                raise ValueError('actual output/review required')
        elif value is not None:
            raise ValueError('technical/missing terminal cannot get semantic score')
        if q['formal_reward'] is not None or (value is not None and not q['assistant_development_review']):
            raise ValueError('review is development only')
        required = [f for f in (q.get('facts') or []) if f['required']]
        atoms = (q.get('source_coverage') or {}).get('atoms', [])
        source_slots = [a for a in atoms if a['required']]
        row = dict(task=p['task'], source_group=p['source_group'], method=e['method'],
            channel=q['goal_kind'], technical_status=e['status'],
            completion_status=q['task_completion']['status'], completion_interval=value,
            support_status=(q.get('support') or {}).get('status'),
            constraint_status=(q.get('request_constraints') or {}).get('status'),
            required_fact_content_counts=dict(Counter(f['status'] for f in required)),
            required_fact_count=len(required),
            original_evidence_groups_delivered=None if not complete_technical else sum(any(g['complete_original_group_present'] for g in a['groups']) for a in source_slots),
            original_evidence_slots=len(required),
            source_coverage_is_not_success=True,
            error_types=q.get('error_types', []),
            additional_claim_status_counts=dict(Counter(a.get('status', 'unspecified') for a in (q.get('additional_claims') or []))),
            uncertainty_items=len(q.get('uncertainty') or []),
            agent_wall_ns=e['agent_to_reply_ns'], observed_partial_path_ns=e['observed_partial_path_ns'],
            pm_ns=e['pm_ns'], guard_ns=p['guard_wall_ns'], logging_wall_ns=None,
            controller_starts=p.get('controller_starts', 0),
            controller_generation_ns=p.get('controller_generation_ns_observed'),
            terminal_generation_ns=p['generation_ns'], terminal_first_text_ns=p['terminal_first_text_ns'],
            client_ttft_ns=None, resource_accesses=p.get('source_receipt_accesses'),
            input_tokens=p['input_tokens'], output_tokens=p['output_tokens'],
            payload_sha256=e.get('payload_sha256'), output_sha256=e.get('output_sha256'),
            text_sha256=None if e.get('output') is None else object_sha256(e['output']['text']),
            evalspec_sha256=e['evalspec_sha256'], formal_reward=None,
            quality_scope='assistant development observation, not independent human or reward')
        joined.append(row)
        private_keys.append(dict(task=row['task'], review_alias=q['task_alias'], task_id=e['task_id'], method=e['method'], slot_id=q['slot_id']))
    if len(set(aliases.values())) != 8 or len(set(review_aliases.values())) != 8:
        raise ValueError('anonymous aliases must be bijective over eight tasks')
    tasks = list(dict.fromkeys(r['task'] for r in joined))
    groups = {t: [r for r in joined if r['task'] == t] for t in tasks}
    common = [t for t, group in groups.items() if len(group) == 6 and all(r['completion_interval'] is not None for r in group)]
    comparisons = []
    for group in groups.values():
        lookup = {r['method']: r for r in group}
        for base in ('STOP', 'FixedTop4Macro', 'LLMOneShot'):
            comparisons += [paired(r, lookup[base]) for r in group if r['method'] != base]
    oracle = []
    for t in common:
        group = groups[t]
        oracle.append(dict(task=t,
            observed_privileged_completion_interval=[max(r['completion_interval'][i] for r in group) for i in (0, 1)],
            definite_complete_arms=[r['method'] for r in group if r['completion_interval'] == [1, 1]],
            formal_reward=None))
    summary = dict(protocol='pmrl1-j-dynamic-quality-latency-analysis-v1',
        tasks=8, terminal_slots=48, common_six_arm_tasks=common,
        incomplete_counterfactual_tasks=[t for t in tasks if t not in common],
        per_method_all_observed={m: group_summary([r for r in joined if r['method'] == m]) for m in ARMS},
        per_method_common_six_arm_tasks={m: group_summary([r for r in joined if r['method'] == m and r['task'] in common]) for m in ARMS},
        per_channel_common={c: {m: group_summary([r for r in joined if r['method'] == m and r['task'] in common and r['channel'] == c]) for m in ARMS} for c in ('fact', 'natural_support')},
        common_task_privileged_envelope=oracle,
        common_task_privileged_interval=[sum(r['observed_privileged_completion_interval'][i] for r in oracle) for i in (0, 1)],
        task_quality_not_used_for_runtime_actions=True, formal_reward=None,
        limitations=['Incomplete six-arm tasks excluded from common comparisons, retained in all slots.',
          'No same-state branch generation is created; observed envelope is posthoc, not a deployable policy.',
          'Reference content agreement, actual evidence supply and supported use are distinct.',
          'Fixed order, cold first inference, small source-clustered sample; no causal latency claim.',
          'Internal first text, local Agent reply-ready, client text and audio are distinct.'])
    fixed = [d['completion_interval_observed'] for d in summary['per_method_common_six_arm_tasks'].values()]
    fixed = [v for v in fixed if v is not None]
    best = [max(v[i] for v in fixed) for i in (0, 1)] if fixed else None
    upper = summary['common_task_privileged_interval']
    summary['best_fixed_common_completion_interval'] = best
    summary['privileged_minus_best_fixed_common_interval'] = None if best is None else [max(0, upper[0]-best[1]), upper[1]-best[0]]
    stratified = []
    for base in ('STOP','FixedTop4Macro','LLMOneShot'):
        for method in ARMS:
            chosen = [p for p in comparisons if p['baseline']==base and p['method']==method]
            for stratum in sorted({p['stratum'] for p in chosen}):
                subset = [p for p in chosen if p['stratum']==stratum]
                durations = [p['agent_wall_difference_ns'] for p in subset if p['agent_wall_difference_ns'] is not None]
                stratified.append(dict(baseline=base,method=method,stratum=stratum,tasks=[p['task'] for p in subset],
                    observed_paired_times=len(durations), paired_agent_ns_sum=None if not durations else sum(durations),
                    faster=sum(x<0 for x in durations),slower=sum(x>0 for x in durations),equal=sum(x==0 for x in durations)))
    summary['paired_latency_by_quality_stratum'] = stratified
    out.mkdir(parents=True)
    write_jsonl_once(out / 'TASKWISE_PUBLIC.jsonl', joined)
    write_jsonl_once(out / 'PAIRED_PUBLIC.jsonl', comparisons)
    write_jsonl_once(out / 'PRIVATE_KEYS.jsonl', private_keys)
    write_json_once(out / 'SUMMARY_PUBLIC.json', summary)
    write_json_once(out / 'MANIFEST_PRIVATE.json', dict(protocol=summary['protocol'],
        inputs_sha256={str(p):file_sha256(p) for p in (collection/'ALL_48_ENDPOINTS_PRIVATE.jsonl', collection/'ALL_48_ENDPOINTS_PUBLIC.jsonl', reviews)},
        code_sha256=file_sha256(__file__), files_sha256={p.name:file_sha256(p) for p in out.iterdir()}, formal_reward=None))
    return summary
