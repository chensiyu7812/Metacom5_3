#!/usr/bin/env python3
"""Record completed engineering/development evidence, never human qualification."""
from collections import Counter
import json
from pathlib import Path
import sqlite3
import statistics
import sys
import xml.etree.ElementTree as ET

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.schema import digest

ROOT=PROJECT/'outputs/pm_rl1/completion_20260930_v2'
P3=ROOT/'P3'


def read(p):return json.loads(p.read_text())


def save(p,v):
    text=json.dumps(v,ensure_ascii=False,indent=2)+'\n'
    if p.exists():assert p.read_text()==text,'immutable result differs: '+str(p)
    else:p.write_text(text)


def stats(values):
    return dict(min=min(values),median=statistics.median(values),mean=statistics.mean(values),max=max(values))


def main():
    pointer=read(P3/'candidate_v1/development_pointer.json');run=Path(pointer['run_dir'])
    summary=read(run/'summary.json')
    assert summary['status']=='DEVELOPMENT_COMPLETE_CANDIDATE_NOT_QUALIFIED'
    assert len(summary['rows'])==summary['planned']==33
    jobs={j['job_id']:j for j in read(P3/'candidate_v1/jobs_private.json')}
    by_id={r['job_id']:r for r in summary['rows']}
    assert len(by_id)==33 and all(jobs[i]['group'] in ('development','recheck_probe') for i in by_id)
    with sqlite3.connect('file:'+str(run/'attempts.sqlite')+'?mode=ro',uri=True) as db:
        attempts=dict(db.execute('SELECT status,count(*) FROM attempts GROUP BY status'))
    assert sum(attempts.values())==33
    for r in summary['rows']:
        request=read(run/(r['request_id']+'.request.json'));raw=read(run/(r['request_id']+'.raw.json'))
        assert digest({k:v for k,v in request.items() if k!='request_id'})==r['request_id']
        assert raw['request_id']==r['request_id'] and sha256_file(run/(r['request_id']+'.raw.json'))==r['raw_sha256']
        assert raw['runtime_identity']==request['executor_identity']==pointer['runtime_identity']
    rows=[r for r in summary['rows'] if r['group']=='development']
    probe=next(r for r in summary['rows'] if r['group']=='recheck_probe')
    assert len(rows)==32
    scored=sum(r['measurement_status']=='measured_candidate' for r in rows)
    structured=sum(r['measurement_status'] in ('measured_candidate','semantic_uncertainty') for r in rows)
    refs=read(P3/'candidate_v1/pair_score_map_private.json')
    score_map={(r['pair_id'],r['side']):r['job_id'] for r in refs}
    pairs=read(P3/'calibration/pairs_private.json')['pairs']
    development=[]
    for p in pairs:
        if p['group']!='development':continue
        result=[by_id[score_map[p['pair_id'],side]] for side in (0,1)]
        development.append(dict(pair_id=p['pair_id'],kind=p['kind'],index=p['index'],
            control_type=p.get('control_type'),contrast=p.get('contrast'),
            scores=[{k:r[k] for k in ('q','m','utility','measurement_status','request_id')} for r in result],
            interpretation='Machine development diagnostic, not human truth or qualification.'))
    save(P3/'development_diagnostics_private.json',dict(pairs=development,
        probe=probe,probe_counts_as_independent_stability_repeat=False,human_labels_read=0))
    context=read(P3/'verification/full_request_context.json')
    future_sources=read(P3/'verification/future_train_dev_source_lengths.json')
    # Warm batched aggregate is not an individual latency or universal runtime.
    amortized=summary['engine_wall_seconds']/33
    profile={}
    for label,lo,hi in [('under_8192',0,8192),('8192_to_16383',8192,16384),('at_least_16384',16384,float('inf'))]:
        selected=[r for r in summary['rows'] if lo<=r['input_tokens']<hi]
        profile[label]=dict(n=len(selected),latency_seconds=stats([r['seconds'] for r in selected]) if selected else None)
    original_budget=read(PROJECT/'docs/pm_rl1_completion_20260930_v2/budget_estimate.json')
    forecasts=[]
    for scenario in original_budget['scenarios']:
        # Original slots deliberately retain possible cache reuse and infeasible
        # planned slots as a conservative scheduling envelope, not an exact bill.
        remaining=scenario['counts']['J_quality_first_and_declared_calibration']-32
        extra=95+153  # One semantic probe consumed; P2 used 39 technical extras.
        forecasts.append(dict(episodes_per_seed=scenario['episodes_per_seed'],
            remaining_quality_slots_envelope=remaining,
            remaining_semantic_and_technical_extra_J_envelope=extra,
            warm_batched_J_hours_if_sample_rate_transfers=(remaining+extra)*amortized/3600,
            individual_request_seconds_linear_hours=(remaining+extra)*statistics.mean(r['seconds'] for r in summary['rows'])/3600,
            optional_RQX_J_hours_in_batched_envelope=288*amortized/3600))
    costs=dict(status='DEVELOPMENT_THROUGHPUT_SENSITIVITY_NOT_FINAL_PPO_BUDGET',
        actual_J_calls=33,API_usd=0,executor_G_calls=0,
        load_seconds=summary['load_seconds'],engine_wall_seconds=summary['engine_wall_seconds'],
        process_seconds=summary['total_process_seconds'],
        individual_request_seconds=stats([r['seconds'] for r in summary['rows']]),
        output_tokens_including_thinking=stats([r['output_tokens'] for r in summary['rows']]),
        recorded_output_tokens_total=sum(r['output_tokens'] for r in summary['rows']),
        warm_batched_engine_seconds_per_finished_job=amortized,by_context=profile,
        future_train_dev_source_coverage={k:v for k,v in future_sources.items() if k not in ('rows','source_files')},
        forecasts=forecasts,
        limitations=['Three development owners and constructed controls are not representative of all future replies.',
            'Future sources can exceed calibration context lengths; no test replies scored for this forecast.',
            'Batching/caching changes elapsed time; individual latencies overlap and must not be summed as GPU occupancy.',
            'Future executor generation, model reloads, encoding, policy compute, training and previous time still need a complete schedule.',
            'No dollar price for local GPU occupancy was assumed. API cost is zero.',
            '128/384 not selected yet; qualification and the complete <=96-hour prospective schedule control that choice.'])
    save(P3/'throughput_and_budget.json',costs)
    xml=ET.parse(P3/'verification/tests_ci_final.xml').getroot()
    tests={k:sum(int(s.attrib.get(k,0)) for s in xml.iter('testsuite')) for k in ('tests','failures','errors','skipped')}
    assert tests['failures']==tests['errors']==0
    assert tests['tests']-tests['skipped']>=1206
    public=dict(status='P3_INITIAL_DEVELOPMENT_RUN_AND_BLIND_HANDOFF_COMPLETE_HUMAN_CALIBRATION_PENDING',
        packet_identity=read(P3/'calibration/packet_summary.json')['packet_identity'],
        candidate_protocol_identity=read(P3/'candidate_v1/protocol.json')['identity'],
        runtime_identity=pointer['runtime_identity'],
        human_instrument=dict(active_pairs=40,development_natural=8,development_control=8,
            validation_natural=16,validation_control=8,reserve_natural=8,preferred_independent_raters=2,
            accepted_single_rater_with_limited_claim=True,labels_received=0,labels_decrypted=0,
            owner_disjoint_partition=dict(development=3,validation=12),
            natural_executor_contrasts_development_only=4,natural_resource_contrasts=20),
        context={k:v for k,v in context.items() if k not in ('rows','source_files')},
        development=dict(first_attempts=32,first_structurally_valid=structured,
            scored_candidates=scored,semantic_recheck_path_probes=1,
            statuses=dict(Counter(r['measurement_status'] for r in summary['rows'])),
            physical_J_calls=33,physical_G_calls=0,API_usd=0,
            independent_repeat_draws_prepared=12,independent_repeat_draws_run=0,
            sealed_validation_calls=0,reward_qualified=False,
            semantic_diagnostics='Private until human review to avoid exposing machine answers to raters; no automatic human agreement claim.'),
        tests=dict(passed=tests['tests']-tests['skipped'],skipped=tests['skipped'],failed=0,
            skip_reason='Old hardcoded tokenizer path; active candidate tokenizer/context checked separately.',
            browser_checks=read(P3/'verification/browser_qa_final.json'),
            old_artifacts_unchanged=read(P3/'verification/old_artifacts.json')['unchanged']),
        throughput=costs,
        resolved_implementation=['Explicit new-AI versus historical speaker contract in both judge and human instrument.',
            'Full source IDs restored mechanically; duplicate fields and nonfinite JSON rejected.',
            'Conditions locked before reply reading/scoring; equal content shares a scoring job.',
            'Whole-owner fact families separated between development and sealed validation.',
            'Offline source-linked forms, encrypted handoff, development-only intake and tested decision arithmetic.'],
        unresolved=['Human validity/preference/risk labels and control confirmation.',
            'At most one human-development-driven semantic revision and final full-runtime measurement freeze.',
            'Unopened validation, twelve independent rescoring draws and formal bounded qualification.',
            'A full source-length-aware <=96-hour P4/P5 schedule, then conditional 128/384 choice.',
            'Natural PPO learning/baselines and final independent task evaluation.'],
        handoff_archive='outputs/pm_rl1/completion_20260930_v2/P3/calibration/PM_RL1_40对人工校准包_20261001.zip',
        source_receipts={str(p.relative_to(PROJECT)):sha256_file(p) for p in [
            P3/'calibration/selection_lock_private.json',P3/'calibration/packet_freeze.json',
            P3/'calibration/human_handoff_final/release.json',P3/'calibration/human_handoff_final/distribution_manifest.json',
            P3/'candidate_v1/candidate_freeze.json',run/'summary.json',P3/'verification/packet_integrity.json',
            P3/'verification/full_request_context.json',P3/'verification/tests_ci_final.xml',
            P3/'verification/future_train_dev_source_lengths.json',
            PROJECT/'src/metacom_pm/rl1/calibration_decision.py',Path(__file__)]})
    save(P3/'development_closeout.json',public)
    save(PROJECT/'docs/pm_rl1_completion_20260930_v2/p3_development_results.json',public)
    state=read(ROOT/'current_state.json')
    state.update(P3='INITIAL_DEVELOPMENT_RUN_COMPLETE_HUMAN_CALIBRATION_PENDING',new_human_tasks=40,
        P3_reward_qualified=False,P3_human_labels_received=0,
        P3_candidate_protocol_identity=public['candidate_protocol_identity'],
        P3_development=public['development'],P3_human_instrument=public['human_instrument'],
        next='Receive genuine sealed human exports; read only development labels, complete the single allowed revision if needed, freeze final runtime/qualification, then open validation and run twelve independent repeats. Natural PPO remains pending.')
    state['call_accounting'].update(P3_initial_calibration_J=32,P3_semantic_path_probe_J=1,
        P3_total_J=33,P3_G=0,P3_API_usd=0)
    for name in public['source_receipts']:
        state['bindings']['project/'+name]=public['source_receipts'][name]
    (ROOT/'current_state.json').write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(status=public['status'],structured=structured,scored=scored,calls=33,
        tests=public['tests']['passed'],engine_seconds=summary['engine_wall_seconds'],
        seconds_per_finished_job=amortized,forecasts=forecasts),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
