#!/usr/bin/env python3
"""Account for completed, failed and interrupted development attempts together.

No calls or training. Reparse saved outputs, verify hashes, retain all protocols.
"""
import collections
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.judge_flat import parse_flat
from metacom_pm.rl1.judge_scoped import parse_scoped
from metacom_pm.rl1.pair_review import parse_pair as parse_complex
from metacom_pm.rl1.pair_review_simple import parse_pair as parse_simple

spec = importlib.util.spec_from_file_location('resolution_analysis', Path(__file__).with_name('29_analyze_resolution.py'))
analysis = importlib.util.module_from_spec(spec); spec.loader.exec_module(analysis)
OUT, PILOT, read = analysis.OUT, analysis.PILOT, analysis.read


def count(rows, field):
    return dict(collections.Counter(str(r.get(field)) for r in rows))


def verify_requests(folder, jobs, pair_draw_protocol=None):
    runtime=read(folder/'runtime.json')
    assert runtime['identity']==folder.name==digest({k:v for k,v in runtime.items() if k!='identity'})
    with sqlite3.connect(folder/'attempts.sqlite') as db:
        attempts=list(db.execute('select request_id,payload,status,result from attempts'))
    for request_id,payload,status,result in attempts:
        payload=json.loads(payload)
        assert digest(payload)==request_id and payload['executor_identity']==runtime['identity']
        assert read(folder/(request_id+'.request.json'))==payload|dict(request_id=request_id)
        if result is None:
            assert status=='RUNNING'  # v3 external interruption manifest accounts for these.
        else:
            raw=json.loads(result)
            assert read(folder/(request_id+'.raw.json'))==raw
            assert raw['runtime_identity']==runtime['identity'] and raw['request_id']==request_id
            completed=raw['finish_reason']=='natural_stop' and bool(raw['text'].strip())
            assert status==('COMPLETED' if completed else 'FAILED')
    lookup = {j.get('job_id', j.get('item_id')): j for j in jobs}
    summary = read(folder / 'summary.json')
    for r in summary['rows']:
        j = lookup[r['job_id']]
        req = read(folder / (r['request_id'] + '.request.json'))
        assert digest({k: v for k, v in req.items() if k != 'request_id'}) == r['request_id']
        assert req['evidence_identity'] == digest(j['evidence'])
        assert req['draw_identity'] == (j['draw_id'] if 'draw_id' in j else digest([pair_draw_protocol, j['item_id']]))
        if 'reply' in j:
            assert req['response_identity'] == digest(j['reply']) and req['seed'] == j['seed']
        else:
            assert req['response_identity'] == digest(j['replies']) and req['seed'] == 20260929
    return len(summary['rows'])


def interrupted(jobs):
    event = read(OUT / 'scoped_v3_interruption.json'); folder = Path(event['run_dir'])
    summary = read(folder / 'summary.json'); lookup = {j['job_id']: j for j in jobs}
    for row in summary['rows']:
        raw = read(folder / (row['request_id'] + '.raw.json')); j = lookup[row['job_id']]
        saved = read(folder / (row['request_id'] + '.measurement.json'))
        assert saved == parse_scoped(raw['text'], evidence=j['evidence'], reply=j['reply'],
            runtime_identity=raw['runtime_identity'], draw_id=j['draw_id'], finish_reason=raw['finish_reason'])
    with sqlite3.connect(folder / 'attempts.sqlite') as db:
        states = dict(db.execute('select status,count(*) from attempts group by status'))
        unresolved = sorted(r[0] for r in db.execute("select request_id from attempts where status='RUNNING'"))
    assert states == event['attempt_states_at_signal']
    assert unresolved == sorted(event['in_flight_request_ids'])
    verify_requests(folder, jobs)
    # The last completed-row timer excludes the tail before interruption.
    # Loaded log timestamp 11:08:01 JST and interruption UTC are external clocks;
    # retain both the monotonic lower bound and this rounded wall estimate.
    loaded = datetime.fromisoformat('2026-09-29T11:08:01+09:00')
    interrupted_at = datetime.fromisoformat(event['utc'].replace('Z', '+00:00'))
    return dict(status='INTERRUPTED_PROTOCOL_REPLACED', generation_starts=sum(states.values()),
        completed_rows=len(summary['rows']), planned_but_unattempted=67-sum(states.values()),
        unknown_interrupted=len(unresolved), interrupted_request_ids=unresolved,
        sqlite_states_preserved=states, states=count(summary['rows'], 'measurement_status'),
        errors=count([r for r in summary['rows'] if r.get('error')], 'error'),
        engine_seconds_to_last_completed_row=summary['engine_wall_seconds'],
        approximate_engine_seconds_to_signal=(interrupted_at-loaded).total_seconds(),
        load_seconds=summary['load_seconds'], all_completed_parses_reproduced=True,
        rows=summary['rows'], run_dir=str(folder), reward_eligible=False)


def model_diagnostic(name, items, parser):
    folder, s, attempts = analysis.load_run(name + '_pointer.json', 12)
    lookup = {i['item_id']: i for i in items}
    results = []
    for row in s['rows']:
        raw = read(folder / (row['request_id'] + '.raw.json'))
        parsed = read(folder / (row['request_id'] + '.measurement.json'))
        replay = parser(raw['text'], lookup[row['job_id']], raw['finish_reason'])
        assert all(parsed[k] == v for k, v in replay.items())
        results.append(dict(item_id=row['job_id'], **parsed))
    verify_requests(folder, items, 'compass-review-v2' if name.endswith('simple') else 'compass-review-v1')
    return dict(calls=12, states=count(s['rows'], 'measurement_status'),
        finishes=count(s['rows'], 'finish_reason'), verdicts=count(s['rows'], 'pairwise'),
        engine_wall_seconds=s['engine_wall_seconds'], load_seconds=s['load_seconds'],
        output_tokens=sum(r['output_tokens'] for r in s['rows']), attempt_states=attempts,
        all_parses_reproduced=True, rows=results, human_review=False,
        shared_qwen_lineage=True, promoted_to_teacher=False)


def main():
    original = read(PILOT / 'exam_private.json'); common = read(OUT / 'scoped_common_exam_private.json')
    v2 = analysis.measurement('indexed_pilot_pointer.json', original['jobs'], 55, analysis.parse_indexed)
    v3 = interrupted(common['jobs'])
    v4 = analysis.measurement('scoped_common_v4_pointer.json', common['jobs'], 67, parse_flat)
    for m in (v2, v4):
        style = [r for r in m['pairs'] if r['comparison']=='OFF/style']
        m['style_control_audit'] = dict(posthoc=True, full_planned_pairs=style,
            grammar_damaged_pairs=[r for r in style if r['pilot_index'] in (7,8)],
            remaining_mild_pairs=[r for r in style if r['pilot_index'] not in (7,8)],
            note='known has/is expansion defect; no old rows removed or rescored; not a large verbosity test')
        m['repeat_sensitivity'] = dict(planned=len(m['repeats']),
            complete=sum(r['valid'] for r in m['repeats']),
            nonzero=sum(r['valid'] and r['delta_utility']!=0 for r in m['repeats']),
            max_abs_observed_utility_delta=max((abs(r['delta_utility']) for r in m['repeats'] if r['valid']), default=None),
            largest_possible_resource_cost=.05,
            note='one repeat per selected item; not a calibrated variance or general error rate')
    for m, jobs in [(v2, original['jobs']), (v4, common['jobs'])]:
        verify_requests(Path(m['run_dir']), jobs)
    smoke = read(Path(v4['run_dir']) / 'smoke_summary.json')
    assert smoke['transport_ok'] and len(smoke['rows']) == 5
    assert {r['request_id'] for r in smoke['rows']} <= {r['request_id'] for r in v4['rows']}
    assert sum(r['cache_hit'] for r in v4['rows']) == 0
    keys = read(OUT / 'coordinator_only/coverage_keys.json'); coverage = []
    for i, k in enumerate(keys, 1):
        rs = {r['condition']: r for r in v4['rows'] if r['exam_section'] == 'coverage' and r['pilot_index'] == i}
        clean, changed = rs['supported_or_respectful'], rs['targeted_change']
        valid = clean['measurement_status'] == changed['measurement_status'] == 'measured_candidate'
        coverage.append(dict(category=k['category'], valid=valid, clean_q=clean['q'], clean_m=clean['m'],
            changed_q=changed['q'], changed_m=changed['m'],
            q_change=changed['q']-clean['q'] if valid else None,
            m_change=changed['m']-clean['m'] if valid else None,
            standard='assistant-authored directional hypothesis; not independent accuracy'))
    items = read(OUT / 'independent_pairs_private.json')['items']
    diagnostics = dict(compass_complex=model_diagnostic('compass_review', items, parse_complex),
                       compass_simple=model_diagnostic('compass_review_simple', items, parse_simple))
    simple = diagnostics['compass_simple']; lookup = {r['item_id']: r for r in simple['rows']}
    controls = []
    for k in keys:
        expected = next(label for label, variant in k['label_to_variant'].items() if variant == 'supported_or_respectful') + '_better'
        actual = (lookup[k['item_id']].get('verdict') or {}).get('pairwise')
        controls.append(dict(category=k['category'], assistant_hypothesis=expected, verdict=actual, agrees=expected==actual))
    simple.update(control_directions=controls,
        always_A_hypothesis_agreement=sum(r['assistant_hypothesis']=='A_better' for r in controls),
        model_hypothesis_agreement=sum(r['agrees'] for r in controls),
        label_rationale_conflict=dict(category='historical_only_relationship',
            finding='A_better label, rationale explicitly concludes B is better; original verdict retained',
            provenance='coordinator source audit, not human review'))
    before = read(OUT / 'preexisting_files.json')
    changed = [p for p, h in before.items() if not (PROJECT.parent/p).exists() or sha256_file(PROJECT.parent/p) != h]
    assert not changed, changed
    freeze = read(OUT / 'flat_transport_freeze.json')
    assert all(sha256_file(PROJECT.parent/p) == h for p, h in freeze['files'].items())
    calls = v2['calls'] + v3['generation_starts'] + v4['calls'] + sum(d['calls'] for d in diagnostics.values())
    gpu = dict(A6000_engine_seconds=v2['engine_wall_seconds']+v3['approximate_engine_seconds_to_signal']+v4['engine_wall_seconds'],
        A4500_engine_seconds=sum(d['engine_wall_seconds'] for d in diagnostics.values()),
        note='sum by device is compute occupancy, not elapsed project time; v3 uses rounded log-to-signal estimate; loading separate')
    inputs = [PILOT/'exam_private.json', OUT/'coverage_exam_private.json', OUT/'scoped_common_exam_private.json',
        OUT/'scoped_revision_freeze.json', OUT/'flat_transport_freeze.json', OUT/'scoped_v3_interruption.json',
        OUT/'e0_comparison.json', OUT/'e0_value_update_verification.json', OUT/'executor_encoding_probe.json',
        OUT/'coordinator_only/semantic_findings_first_pass.json', OUT/'coordinator_only/semantic_findings_repeat.json',
        OUT/'coordinator_only/semantic_findings_tentative_advice.json', OUT/'public_observation_feature_probe.json']
    result = dict(status='BOUNDED_DEVELOPMENT_EXECUTION_COMPLETE_SEMANTIC_SCOPE_IN_REPORT', v2=v2,
        v3_interrupted=v3, v4=v4, coverage=coverage, independent_model_diagnostics=diagnostics,
        e0={name: read(OUT/name/'summary.json') for name in ('e0','e0_initialized','e0_value_initialized')},
        physical_judge_generation_starts=calls, completed_raw_outputs=calls-v3['unknown_interrupted'],
        interrupted_unknown_attempts=v3['unknown_interrupted'], v4_smoke_draws_included_not_added=5,
        generator_calls=0, paid_API_usd=0, human_submissions=0, real_semantic_PM_training_updates=0,
        toy_PPO_episodes=3*(4096+128+128), executor_LoRA_updates=0, training_reward_labels_created=0,
        executor_encoding_probe=read(OUT/'executor_encoding_probe.json'),
        public_observation_feature_probe=read(OUT/'public_observation_feature_probe.json'),
        preexisting_files_preserved=len(before), gpu_compute=gpu,
        source_hashes={str(f.relative_to(PROJECT)):sha256_file(f) for f in inputs},
        script_sha256=sha256_file(Path(__file__)))
    (OUT/'analysis_final.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(v2=v2['states'],v4=v4['states'],coverage=coverage,
        physical_judge_generation_starts=calls,preexisting_files_preserved=len(before)),ensure_ascii=False))


if __name__ == '__main__': main()
