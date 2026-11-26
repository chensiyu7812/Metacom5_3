"""CPU-only SMV timing readback: reused generator components, never Agent E2E.

Frozen policy choices and development intervals are joined by endpoint identity.
No output text is scored, no uncertainty is relabeled, and no model is called.
"""
import argparse
import json
import math
from collections import Counter
from pathlib import Path

from metacom_pm.rl1v3.io import file_sha256, object_sha256, write_json_once, write_jsonl_once

POLICIES = ('STOP', 'MS', 'C1', 'simple_visible')
CHANNELS = ('fact', 'natural_support', 'joint')
KINDS = ('both_definite_success', 'both_definite_failure', 'uncertain', 'definite_repair', 'definite_regression')


def read_rows(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines()]


def unique_index(rows, key):
    result = {}
    for row in rows:
        value = row[key]
        if value in result:
            raise ValueError('duplicate identity: ' + key)
        result[value] = row
    return result


def nearest_rank(values, p):
    if not 0 < p <= 1 or any(not math.isfinite(x) for x in values):
        raise ValueError('finite samples and 0 < percentile <= 1 required')
    if not values:
        return None
    return sorted(values)[math.ceil(p * len(values)) - 1]


def distribution(values):
    return dict(n=len(values), sum_seconds=math.fsum(values),
                p50_seconds=nearest_rank(values, .5), p95_seconds=nearest_rank(values, .95),
                minimum_seconds=min(values) if values else None,
                maximum_seconds=max(values) if values else None)


def outcome_kind(a, b):
    for row in (a, b):
        if row['completion'] not in ([0, 0], [0, 1], [1, 1]):
            raise ValueError('frozen completion interval required')
    if a['request_id'] == b['request_id']:
        for key in ('completion', 'generation_seconds', 'output_object_sha256'):
            if a[key] != b[key]:
                raise ValueError('same endpoint has inconsistent observation')
    aa, bb = a['completion'], b['completion']
    if aa == bb == [1, 1]:
        return 'both_definite_success'
    if aa == bb == [0, 0]:
        return 'both_definite_failure'
    if [0, 1] in (aa, bb):
        return 'uncertain'
    return 'definite_repair' if aa == [1, 1] else 'definite_regression'


def paired(a, b):
    kind = outcome_kind(a, b)
    delta = a['generation_seconds'] - b['generation_seconds']
    same = a['request_id'] == b['request_id']
    return dict(selected_arm=a['arm'], selected_request_id=a['request_id'],
                selected_output_sha256=a['output_object_sha256'],
                reference_request_id=b['request_id'], reference_output_sha256=b['output_object_sha256'],
                selected_completion=a['completion'], reference_completion=b['completion'],
                completion_difference=[0, 0] if same else [a['completion'][0]-b['completion'][1], a['completion'][1]-b['completion'][0]],
                selected_seconds=a['generation_seconds'], reference_seconds=b['generation_seconds'],
                selected_minus_MS_seconds=delta,
                direction='reduced' if delta < 0 else 'increased' if delta > 0 else 'equal',
                same_physical_endpoint=same, outcome_stratum=kind,
                selected_input_tokens=a['input_tokens'], selected_output_tokens=a['output_tokens'],
                MS_input_tokens=b['input_tokens'], MS_output_tokens=b['output_tokens'])


def summarize_pairs(rows):
    def bucket(rs):
        return dict(tasks=len(rs), task_aliases=[r['task'] for r in rs],
                    selected_generation=distribution([r['selected_seconds'] for r in rs]),
                    paired_delta=distribution([r['selected_minus_MS_seconds'] for r in rs]),
                    direction_counts={k:sum(r['direction'] == k for r in rs) for k in ('reduced', 'increased', 'equal')},
                    same_endpoint_tasks=sum(r['same_physical_endpoint'] for r in rs))
    result = bucket(rows)
    result['completion_bounds'] = [sum(r['selected_completion'][i] for r in rows) for i in (0, 1)]
    result['paired_completion_difference'] = [sum(r['completion_difference'][i] for r in rows) for i in (0, 1)]
    result['choices'] = dict(Counter(r['selected_arm'] for r in rows))
    result['outcome_strata'] = {k:dict(all_pairs=bucket([r for r in rows if r['outcome_stratum'] == k]),
        changed_endpoints_only=bucket([r for r in rows if r['outcome_stratum'] == k and not r['same_physical_endpoint']])) for k in KINDS}
    return result


def analyze(*, source, static, out):
    source, static, out = map(Path, (source, static, out))
    if out.exists():
        raise FileExistsError(out)
    files = dict(
        pairs=static/'analysis-v1/SMV30_TASKWISE_PUBLIC.json',
        summary=static/'analysis-v1/SMV30_SUMMARY_PUBLIC.json',
        actual=static/'collected-v1/ACTUAL_RESPONSES_PRIVATE.jsonl',
        technical=static/'collected-v1/TECHNICAL_PUBLIC.json',
        journal_inputs=static/'collected-v1/INPUTS_PRIVATE.json',
        review=static/'review-final-v1/DEVELOPMENT_REVIEW_PRIVATE.jsonl',
        choices=source/'source-bundle-v3/POLICY_CHOICES.private.jsonl',
        evals=source/'source-bundle-v3/EVALSPEC.private.jsonl')
    original_hashes = {str(p):file_sha256(p) for p in files.values()}
    old = json.loads(files['summary'].read_text())
    for name, key in [('review', 'review_records_sha256'), ('choices', 'frozen_policy_sha256'), ('evals', 'old_evaluation_sha256')]:
        if file_sha256(files[name]) != old[key]:
            raise ValueError('frozen analysis dependency changed: ' + name)
    journal_inputs = json.loads(files['journal_inputs'].read_text())
    for path, expected in journal_inputs.items():
        if file_sha256(path) != expected:
            raise ValueError('preserved run artifact changed')
    pairs = json.loads(files['pairs'].read_text())['rows']
    actual = unique_index(read_rows(files['actual']), 'request_id')
    review = unique_index(read_rows(files['review']), 'request_id')
    choices = unique_index(read_rows(files['choices']), 'task_id')
    evaluations = unique_index(read_rows(files['evals']), 'task_id')
    if len(pairs) != 15 or len(actual) != 30 or len(review) != 30 or len(choices) != 15:
        raise ValueError('frozen 15 tasks / 30 physical endpoints required')
    if Counter(r['channel'] for r in pairs) != {ch:5 for ch in CHANNELS}:
        raise ValueError('fixed channel cohort required')
    endpoint_ids = []
    for row in pairs:
        for arm in ('STOP', 'MS'):
            cell = row[arm];rid = cell['request_id'];response = actual[rid];observation = review[rid]
            output = response['output'];endpoint_ids.append(rid)
            if response['technical_status'] != 'eos' or output['finish_reason'] != 'eos':
                raise ValueError('technical failure must remain separate, never complete-case deletion')
            if object_sha256(output) != response['output_sha256'] or cell['output_object_sha256'] != response['output_sha256']:
                raise ValueError('actual output identity mismatch')
            if response['evalspec_sha256'] != object_sha256(evaluations[cell['task_id']]):
                raise ValueError('evaluation identity mismatch')
            if observation['development_interval'] != cell['completion'] or observation['output_sha256'] != response['output_sha256']:
                raise ValueError('frozen development observation mismatch')
            for key in ('task_id', 'arm', 'payload_sha256'):
                if response[key] != cell[key] or observation[key] != cell[key]:
                    raise ValueError('endpoint metadata mismatch')
            seconds = output['seconds']
            if not math.isfinite(seconds) or seconds < 0 or cell['generation_seconds'] != seconds:
                raise ValueError('invalid or changed actual timing')
            if cell['input_tokens'] != output['input_tokens'] or cell['output_tokens'] != len(output['token_ids']):
                raise ValueError('token identity mismatch')
            if output['timing_scope'] != 'synchronized local single HF call; not user-visible end-to-end latency':
                raise ValueError('unexpected measurement surface')
            if cell['task_id'] != row['STOP']['task_id'] or cell['arm'] != arm:
                raise ValueError('pair identity mismatch')
        choice = choices[row['STOP']['task_id']]
        if any(choice[p] != row['frozen_choices'][p] or choice[p] not in ('STOP', 'MS') for p in POLICIES):
            raise ValueError('frozen policy choice changed')
    if len(set(endpoint_ids)) != 30 or set(endpoint_ids) != set(actual):
        raise ValueError('each physical endpoint must be included once')
    technical = json.loads(files['technical'].read_text())
    generation_sum = math.fsum(r['output']['seconds'] for r in actual.values())
    if not math.isclose(generation_sum, technical['generation_seconds'], abs_tol=1e-9):
        raise ValueError('physical timing reconciliation failed')
    logical = []
    for policy in POLICIES:
        for row in pairs:
            logical.append(dict(policy=policy, task=row['task'], task_id=row['STOP']['task_id'], channel=row['channel'],
                                **paired(row[row['frozen_choices'][policy]], row['MS'])))
    policies = {p:{ch:summarize_pairs([r for r in logical if r['policy'] == p and (ch == 'all' or r['channel'] == ch)])
                  for ch in ('all', *CHANNELS)} for p in POLICIES}
    report = dict(protocol='smv-reused-generation-latency-components-v1', physical_calls=30, logical_selections=60,
        source_families=3, source_situations=5, tasks=15, tasks_per_channel=5, policies=policies,
        measurement_surface='synchronized local single HF call; no Agent/client/audio end-to-end observation',
        quantile=dict(method='nearest-rank: sorted_samples[ceil(p*n)-1]; no interpolation',
                      p95_equals_max_for_n_15_and_n_5=True, input='raw selected endpoint seconds, not per-state means',
                      small_n_tail_estimate=True, confidence_interval=False),
        physical_accounting=dict(generation_seconds=generation_sum, worker_load_seconds=technical['worker_load_seconds'],
            supervisor_load_seconds=sum(j['supervisor_load_seconds'] for j in technical['jobs']),
            job_wall_seconds=technical['job_wall_seconds'], model_loads=technical['model_loads'],
            physical_calls=30, eos=technical['eos'], successful_call_filter_applied=False,
            loads_are_nested_not_additive=True, policy_sums_are_shared_components_not_executed_policy_latency=True),
        new_model_calls=0, formal_reward=None, old_observations_unchanged=True,
        limitations=['One observation per endpoint; no randomized repeated latency experiment.',
            'Channel variants share five source situations and three exposed families.',
            'Policies share physical outputs; equal reused endpoint times are identities, not timing replications.',
            'Output length, sequential call order, GPU scheduling/cache/load state confound latency attribution.',
            'No retrieval/controller, queue, network, ASR, TTS, playback, TTFT or deployed Agent wall measurement.',
            'Unknown completion is retained; common-success strata are descriptive, not causal selection estimates.'])
    if not all(file_sha256(p) == h for p, h in original_hashes.items()):
        raise ValueError('original input changed during analysis')
    out.mkdir(parents=True)
    write_json_once(out/'SMV_LATENCY_SUMMARY.json', report)
    write_jsonl_once(out/'SMV_LATENCY_TASKWISE.jsonl', logical)
    write_json_once(out/'INPUT_IDENTITIES_PRIVATE.json', dict(inputs=original_hashes, preserved_journal_inputs=journal_inputs,
        output_objects={rid:actual[rid]['output_sha256'] for rid in endpoint_ids},
        immutable_input_check_passed=True,
        code_sha256=file_sha256(__file__)))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ('source', 'static', 'out'):
        parser.add_argument('--'+name, required=True)
    result = analyze(**vars(parser.parse_args()))
    print(json.dumps({p:result['policies'][p]['all'] for p in POLICIES}, indent=2))
