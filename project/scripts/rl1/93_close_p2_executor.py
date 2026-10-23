#!/usr/bin/env python3
"""Close P2 only from completed, bound training and unscored reply artifacts."""
from collections import Counter
import json
from pathlib import Path
import sqlite3
import sys
import xml.etree.ElementTree as ET

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.schema import digest
ROOT = PROJECT / 'outputs/pm_rl1/completion_20260930_v2'
OUT = ROOT / 'P2'


def read(path):
    return json.loads(path.read_text())


def save(path, value):
    text = json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    if path.exists():
        assert path.read_text() == text, 'immutable result already differs: ' + str(path)
    else:
        path.write_text(text)


def inspect_run(pointer, status):
    run = Path(read(pointer)['run_dir'])
    summary = read(run / 'summary.json')
    assert summary['status'] == status
    assert len(summary['rows']) == summary['planned']
    with sqlite3.connect('file:' + str(run / 'attempts.sqlite') + '?mode=ro', uri=True) as db:
        calls = dict(db.execute('SELECT status,count(*) FROM attempts GROUP BY status'))
    assert sum(calls.values()) == len(summary['rows'])
    for row in summary['rows']:
        rid = row['request_id']; raw = read(run / (rid + '.raw.json'))
        req = read(run / (rid + '.request.json'))
        assert digest({k: v for k, v in req.items() if k != 'request_id'}) == rid
        assert rid == req['request_id'] == raw['request_id']
        assert raw['runtime_identity'] == req['executor_identity']
        assert raw['finish_reason'] == row['finish_reason']
        if 'raw_sha256' in row:
            assert sha256_file(run / (rid + '.raw.json')) == row['raw_sha256']
    return run, summary, calls


def main():
    executor = read(OUT / 'executor_freeze.json')
    for name, expected in executor['files'].items():
        assert sha256_file(PROJECT / name) == expected, name
    dataset = read(OUT / 'dataset_freeze.json')
    for name, expected in dataset['files'].items():
        assert sha256_file(PROJECT / name) == expected, name
    guards = [OUT / n for n in ('executor_freeze.json', 'dataset_freeze.json',
        'admission_summary.json', 'review_parse_summary.json', 'repair_selection.json',
        'coordinator_audit_decisions_private.json', 'executor_selection.json',
        'behavior_reviews_private.json', 'tests_supervision.xml',
        'review_duplicate_key_audit.json', 'admission_duplicate_disposition.json')]
    timings = {}; call_counts = {}; output_tokens = 0
    for stage, pointer in [('author', OUT / 'author_pointer.json'),
            ('review', OUT / 'review_format_v2/review_pointer.json')]:
        run, summary, statuses = inspect_run(pointer, 'COMPLETE_UNADMITTED')
        call_counts[stage] = sum(statuses.values())
        timings[stage] = {k: summary[k] for k in ('load_seconds', 'engine_wall_seconds', 'elapsed_seconds')}
        output_tokens += sum(r['output_tokens'] for r in summary['rows'])
        guards.extend([run / 'runtime.json', run / 'summary.json'])
    repairs = read(OUT / 'repair_selection.json')['selected']
    for stage in ('repair', 'review_repair'):
        call_counts[stage] = 0
        if repairs:
            run, summary, statuses = inspect_run(OUT / (stage + '_pointer.json'), 'COMPLETE_UNADMITTED')
            assert len(summary['rows']) == repairs if stage == 'repair' else len(summary['rows']) <= repairs
            call_counts[stage] = sum(statuses.values())
            timings[stage] = {k: summary[k] for k in ('load_seconds', 'engine_wall_seconds', 'elapsed_seconds')}
            output_tokens += sum(r['output_tokens'] for r in summary['rows'])
            guards.extend([run / 'runtime.json', run / 'summary.json'])
    deviation = read(OUT / 'review_format_v2/format_deviation.json')
    abandoned = Path(deviation['original_run']); old = read(abandoned / 'summary.json')
    call_counts['review_abandoned_starts'] = deviation['prior_attempts']
    assert deviation['prior_attempts'] == 39 and deviation['prior_statuses'] == {'COMPLETED': 35, 'RUNNING': 4}
    output_tokens += sum(r['output_tokens'] for r in old['rows'])
    timings['abandoned_review'] = dict(last_recorded_elapsed_seconds=old['elapsed_seconds'],
        process_window_upper_proxy_seconds=old['elapsed_seconds'] + max(0.,
            (abandoned / 'stop_disposition.json').stat().st_mtime - (abandoned / 'summary.json').stat().st_mtime),
        caution='File-time conservative process window; includes overhead and is not exclusive GPU occupancy. Four unfinished outputs have unknown token count.')
    guards.extend([abandoned / 'summary.json', abandoned / 'stop_disposition.json',
        OUT / 'review_format_v2/format_deviation.json'])
    pool_results = {}; pool_runs = {}; pool_rows = {}
    startup_failures = []
    for disposition in sorted((OUT / 'common_pool/generation').glob('*/stop_disposition.json')):
        failure = read(disposition)
        assert failure['status'] == 'PRE_GENERATION_RUNTIME_COMPARISON_FAILURE'
        assert failure['physical_generation_starts'] == failure['physical_judge_starts'] == 0
        assert not (disposition.parent / 'attempts.sqlite').exists()
        assert not list(disposition.parent.glob('*.raw.json'))
        assert sha256_file(disposition.parent / 'runner_before_runtime_fix.py') == failure['old_runner_sha256']
        failure = dict(failure, process_window_upper_proxy_seconds=max(0.,
            disposition.stat().st_mtime - (disposition.parent / 'protocol.json').stat().st_mtime),
            timing_caution='Conservative file-time window from preflight to recorded stop; exact load/engine time was not captured.')
        startup_failures.append(failure)
        guards.extend([disposition, disposition.parent / 'runner_before_runtime_fix.py'])
    arms = ['primary'] + (['secondary'] if executor['selected'] != 'base' else [])
    for arm in arms:
        run, summary, statuses = inspect_run(OUT / ('common_pool/' + arm + '_generation_pointer.json'), 'COMPLETE_UNSCORED')
        assert read(run / 'runtime_observed.json') == read(run / 'runtime.json')
        assert sha256_file(PROJECT / 'scripts/rl1/92_run_p2_common_pool.py') == read(run / 'protocol.json')['runner_sha256']
        pool_runs[arm] = run
        pool_rows[arm] = summary['rows']
        for row in summary['rows']:
            raw = read(run / (row['request_id'] + '.raw.json'))
            if row['finish_reason'] == 'natural_stop':
                assert raw['text'].strip()
                assert raw['output_token_ids'][-1] in read(run / 'runtime.json')['policy']['eos_token_ids']
        call_counts['common_pool_' + arm] = sum(statuses.values())
        output_tokens += sum(r['output_tokens'] or 0 for r in summary['rows'])
        pool_results[arm] = dict(slots=len(summary['rows']), statuses=summary['statuses'],
            by_split=dict(Counter(r['split'] for r in summary['rows'])),
            output_tokens=sum(r['output_tokens'] or 0 for r in summary['rows']),
            generation_seconds=sum(r['generation_seconds'] or 0 for r in summary['rows']),
            reward_measurements=0)
        timings['common_pool_' + arm] = dict(load_seconds=summary['load_seconds'],
            generation_seconds=pool_results[arm]['generation_seconds'],
            final_invocation_seconds=summary['total_seconds_this_invocation'])
        guards.extend([run / 'protocol.json', run / 'summary.json', run / 'runtime.json', run / 'runtime_observed.json'])
    training = Path(read(OUT / 'training_pointer.json')['run_dir'])
    train = read(training / 'summary.json')
    diagnostic = Path(read(OUT / 'diagnostic_pointer.json')['run_dir'])
    diagnostics = read(diagnostic / 'summary.json')
    assert len(diagnostics['rows']) == 36
    primary = {(r['index'], tuple(r['counts'])): r for r in pool_rows['primary']}
    assert len(primary) == len(pool_rows['primary']) == 586
    assert len({i for i, counts in primary if not any(counts)}) == 42
    paired = 0
    if 'secondary' in pool_rows:
        for row in pool_rows['secondary']:
            counterpart = primary[(row['index'], tuple(row['counts']))]
            a = read(pool_runs['primary'] / (counterpart['request_id'] + '.request.json'))
            b = read(pool_runs['secondary'] / (row['request_id'] + '.request.json'))
            for key in ('messages', 'renderer_identity', 'draw_identity', 'provenance'):
                assert a[key] == b[key], key
            assert a['executor_identity'] != b['executor_identity']
            paired += 1
        assert paired == 53
    # Separate draws/runs can share a greedy input. Record actual replay
    # agreement without treating repeats as independent support-quality data.
    primary_messages = {}
    for row in pool_rows['primary']:
        req = read(pool_runs['primary'] / (row['request_id'] + '.request.json'))
        primary_messages.setdefault(digest(req['messages']), []).append(row)
    replay = []
    for row in diagnostics['rows']:
        if row['arm'] != executor['selected']:
            continue
        original = read(diagnostic / (row['request_id'] + '.raw.json'))
        for pool_row in primary_messages.get(row['messages_identity'], []):
            repeated = read(pool_runs['primary'] / (pool_row['request_id'] + '.raw.json'))
            replay.append(dict(diagnostic_request_id=row['request_id'],
                pool_request_id=pool_row['request_id'],
                exact_tokens=original['output_token_ids'] == repeated['output_token_ids'],
                exact_text=original['text'] == repeated['text']))
    call_counts['behavior_generation'] = 36
    output_tokens += sum(r['output_tokens'] or 0 for r in diagnostics['rows'])
    timings['training'] = {k: train[k] for k in ('load_seconds', 'train_and_epoch_dev_seconds', 'total_seconds')}
    timings['behavior'] = {k: diagnostics[k] for k in ('load_seconds', 'total_seconds')}
    if executor['selected'] != 'base':
        reload = read(training / 'reload.json')
        assert reload['passed']
        timings['reload'] = {k: reload[k] for k in ('load_seconds', 'total_seconds')}
    inv = read(PROJECT / 'docs/reviews/20260930/pm_rl1/LOCAL_ARTIFACT_INVENTORY.json')['files']
    for entry in inv:
        p = PROJECT.parent / entry['path']
        assert p.stat().st_size == entry['bytes'] and sha256_file(p) == entry['sha256'], entry['path']
    xml = ET.parse(OUT / 'tests_supervision.xml').getroot()
    tests = {k: sum(int(s.attrib.get(k, 0)) for s in xml.iter('testsuite'))
        for k in ('tests', 'failures', 'errors', 'skipped')}
    assert tests['tests'] == 185 and tests['failures'] == tests['errors'] == tests['skipped'] == 0
    ci_path = OUT / 'tests_ci_integration.xml'
    ci = ET.parse(ci_path).getroot()
    ci_tests = {k: sum(int(s.attrib.get(k, 0)) for s in ci.iter('testsuite'))
        for k in ('tests', 'failures', 'errors', 'skipped')}
    assert ci_tests['tests'] == 1173 and ci_tests['failures'] == ci_tests['errors'] == 0
    ci_tests['passed'] = ci_tests['tests'] - ci_tests['skipped']
    ci_tests['skip_records'] = [dict(test=c.attrib['name'],
        reason=c.find('skipped').attrib.get('message', ''))
        for c in ci.iter('testcase') if c.find('skipped') is not None]
    guards.append(ci_path)
    admission = read(OUT / 'admission_summary.json')
    content_summary_path = OUT / 'common_pool/primary_content_identity_summary.json'
    content_summary = read(content_summary_path)
    assert content_summary['source_summary_sha256'] == sha256_file(pool_runs['primary'] / 'summary.json')
    assert content_summary['reward_measurements'] == 0
    guards.append(content_summary_path)
    admission_defect = read(OUT / 'admission_duplicate_disposition.json')
    assert admission_defect['affected_frozen_targets'] == 4
    assert admission_defect['original_frozen_targets'] == admission['accepted'] == 493
    assert admission_defect['additional_training'] == 0
    selection = read(OUT / 'executor_selection.json')
    behavior_inputs = read(OUT / 'behavior_inputs_private.json')['slots']
    epoch_metrics = [dict(epoch=e['epoch'], nll=e['dev']['nll'],
        body_nll=e['dev']['body_nll'], eot_nll=e['dev']['eot_nll']) for e in read(training / 'epochs.json')]
    total_g = sum(call_counts[k] for k in ('author', 'repair', 'behavior_generation')) + sum(
        n for k, n in call_counts.items() if k.startswith('common_pool_'))
    total_j = sum(call_counts[k] for k in ('review', 'review_repair', 'review_abandoned_starts'))
    result = dict(phase='P2', status='COMPLETE_EXECUTOR_AND_UNSCORED_POOLS_WITH_DISCLOSED_ADMISSION_DEFECT',
        admission=admission, initial_review=read(OUT / 'review_parse_summary.json'),
        admission_duplicate_key_defect={k: admission_defect[k] for k in
            ('status', 'raw_duplicate_reviews', 'affected_frozen_targets', 'affected_by_split',
             'original_frozen_targets', 'targets_not_affected_by_detected_duplicate_keys',
             'strictly_reviewed_493_claim_allowed', 'posthoc_coordinator_cases',
             'disposition', 'future_parser')},
        repaired_review=read(OUT / 'review_parse_summary_repair.json') if repairs else None,
        repairs=read(OUT / 'repair_selection.json'),
        selected_executor=executor['selected'], executor_identity=executor['primary_runtime']['identity'],
        renderer_identity=executor['renderer_identity'],
        training=dict(epochs=3, steps=train['steps'], trainable_parameters=train['trainable_parameters'],
            baseline_dev_nll=train['baseline_dev_nll'], epoch_metrics=epoch_metrics,
            frozen_base_unchanged=train['frozen_base_hash_before'] == train['frozen_base_hash_after']),
        selection={k: selection[k] for k in ('selected', 'confirmed_severe_exclusions',
            'technical_exclusions', 'eligible_epochs', 'review_statuses', 'selected_dev_nll', 'rule')},
        behavior_scope=dict(inputs=len(behavior_inputs),
            prefixes=len({s['prefix_identity'] for s in behavior_inputs}),
            owners=len({s['owner'] for s in behavior_inputs}), new_generations=36,
            independent_human_gold=False, unseen_test=False),
        common_pool=pool_results,
        primary_text_identity_diagnostic=content_summary,
        pairing_integrity=dict(primary_unique_conditions=len(primary), primary_true_OFF_prefixes=42,
            base_adapter_equal_input_pairs=paired),
        same_input_greedy_diagnostic_replay=dict(rows=replay, comparisons=len(replay),
            exact_tokens=sum(row['exact_tokens'] for row in replay),
            exact_text=sum(row['exact_text'] for row in replay),
            scope='Repeatability check, not independent observations or evidence of quality gain'),
        unavailable_primary=read(OUT / 'common_pool/summary.json')['unavailable_slots'],
        unavailable_secondary=read(OUT / 'common_pool/secondary_inputs_private.json')['nominal_slots'] -
            read(OUT / 'common_pool/secondary_inputs_private.json')['legal_slots'],
        actual=dict(calls=call_counts, G=total_g, J_admission=total_j, J_RL_reward=0,
            pre_generation_startup_failures=startup_failures,
            observed_output_tokens=output_tokens, unfinished_output_token_counts=4,
            AI_coordinator_admission_cases=37, AI_coordinator_behavior_cases=36,
            AI_coordinator_posthoc_duplicate_cases=4,
            new_human_tasks=0, API_usd=0, timing=timings,
            timing_scope='Measured local process/engine wall time; not total analyst time or exclusive GPU occupancy'),
        tests=tests, CI_integration_tests=ci_tests, old_artifacts_unchanged=len(inv),
        unresolved=['AI weak supervision is not independent gold',
            'Four frozen targets have posthoc-detected duplicate-key admission defects; no retrospective strict-pass claim',
            'Model-reported resource behavior is not verified optional-resource uptake',
            'No support-quality improvement established by NLL/behavior selection',
            'Common replies have no calibrated q/m reward; missing measurement is not zero',
            'P3 bounded human calibration and formal natural PPO remain pending'],
        next='P3: source-bound single-reply measurement interface, finite development/sealed human calibration package; do not update PPO from unqualified scores')
    guards.extend([training / 'summary.json', training / 'epochs.json', diagnostic / 'summary.json', Path(__file__)])
    result['evidence_files'] = {str(p.relative_to(PROJECT)): sha256_file(p) for p in sorted(set(guards))}
    save(OUT / 'phase_closeout.json', result)
    public = dict(result)
    public['evidence_files'] = dict(result['evidence_files'], **{
        str((OUT / 'phase_closeout.json').relative_to(PROJECT)): sha256_file(OUT / 'phase_closeout.json')})
    save(PROJECT / 'docs/pm_rl1_completion_20260930_v2/p2_results.json', public)
    print(json.dumps(dict(status=result['status'], accepted=admission['accepted'],
        selected_executor=executor['selected'], G=total_g, J_admission=total_j, J_reward=0), ensure_ascii=False))


if __name__ == '__main__':
    main()
