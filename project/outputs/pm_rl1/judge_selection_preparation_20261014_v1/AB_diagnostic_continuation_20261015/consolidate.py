"""Offline, append-only reporting of completed diagnostics; no runner/model calls."""
import copy
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

OUT = Path(__file__).resolve().parent
B = OUT.parent
R = B.parents[3]
LIVE = B / 'live_runs/output_interface_v1_AB_diagnostic'
STAGE = LIVE / 'stage'
read = lambda p: json.loads(p.read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
digest = lambda x: hashlib.sha256(json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
now = datetime.now(ZoneInfo('Asia/Tokyo')).isoformat()

def save(name, value):
    with (OUT / name).open('x') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write('\n')

def csvwrite(name, rows, fields=None):
    fields = fields or list(dict.fromkeys(k for r in rows for k in r))
    with (OUT / name).open('x', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: json.dumps(r.get(k), ensure_ascii=False) if isinstance(r.get(k), (dict,list)) else r.get(k) for k in fields})

plan = read(B / 'plan.json')
protocol = read(OUT / 'protocol.json')
previous = read(B / 'AB_development_20261015/results_private.json')
stage = read(STAGE / 'stage_result.json')
requests = {r['original_slot_request_id']: r for r in protocol['requests']}
original_requests = {r['request_id']: r for r in plan['requests']}
rows = copy.deepcopy(previous['rows'])
by_slot = {r['original_slot_request_id']: r for r in rows}
attempt_order = {r['request_id']: n for n, r in enumerate([x for x in stage['attempts'] if x['started']], 1)}
newrows = []
for row in rows:
    row['started_this_stage'] = False
    row['previous_planned_request_id'] = row['planned_request_id']
    req = requests[row['original_slot_request_id']]
    row['planned_request_id'] = req['request_id']
    row['planned_configuration_identity'] = req['configuration_identity']
    review = row.get('source_review') or {}
    row.update(reviewer_unresolved_ambiguity=bool(review.get('critical_unknown')),
        source_proven_material_error=bool(review.get('material_source_proven_error')),
        model_self_unknown=None if row['analysis_q'] is None else False,
        usable_for_qualification=False, reward_eligible=False, independent_human_observations_added=0)
    if not row['started']:
        row['not_dispatched_reason'] = ('A stopped at dev16A source-proven speaker-ownership error' if row['label']=='A'
            else 'B stopped at dev06A timeout/incomplete thought channel; no complete final')

for path in LIVE.glob('*/*.result.json'):
    result = read(path); req = result['request']; orig = result['original_request']; rid = req['request_id']
    row = by_slot[orig['request_id']]
    assert not row['started'] and orig == original_requests[orig['request_id']]
    ev = result['evaluation']; m = ev['measurement']
    response_path = path.with_name(rid+'.response.json'); response = read(response_path)
    raw_path = path.with_name(rid+'.raw.json'); started_path = path.with_name(rid+'.started.json')
    review_path = STAGE / (rid+'.review.json'); diag_path = STAGE / (rid+'.diagnostic.json')
    review = read(review_path) if review_path.exists() else None
    diag = read(diag_path) if diag_path.exists() else None
    a = response['token_accounting']
    model_unknown = (m.get('parsed',{}).get('status')=='uncertain') if ev['validation_stage']=='complete' else None
    row.update(started=True, started_this_stage=True, execution_order_this_stage=attempt_order[rid],
        record_class='development_diagnostic_after_known_unresolved_dispute',
        technical_status=m['measurement_status'], validation_stage=ev['validation_stage'],
        technical_failure_detail=None if ev['validation_stage']=='complete' else {
            'original_error':m.get('error'), 'natural_eos':response['natural_eos'],
            'time_limit_seconds':900,'observed_seconds':response['total_seconds'],
            'final_present':bool(response.get('raw_text')), 'classification':'timeout_non_natural_incomplete_thought_no_final'},
        formal_q=m.get('q'),formal_m=m.get('m'),formal_U=m.get('candidate_utility'),
        analysis_q=m.get('q'),analysis_m=m.get('m'),analysis_U=m.get('candidate_utility'),
        derived_q=None,derived_m=None,derived_U=None,
        semantic_hold=bool(review and (review['critical_unknown'] or review['material_source_proven_error'])),
        reviewer_unresolved_ambiguity=bool(review and review['critical_unknown']),
        source_proven_material_error=bool(review and review['material_source_proven_error']),
        unexplained_equivalence_difference=bool(review and review['unexplained_equivalence_difference']),
        model_self_unknown=model_unknown, model_unknown_observability='complete validated final' if model_unknown is not None else 'not observable: technical failure',
        not_dispatched_reason=None, actual_request_id=rid,actual_configuration_identity=req['configuration_identity'],
        raw_path=str(raw_path),response_path=str(response_path),result_path=str(path),started_path=str(started_path),
        review_path=str(review_path) if review else None,diagnostic_path=str(diag_path) if diag else None,
        input_tokens=response['input_tokens'],total_output_tokens=response['output_tokens'],
        thinking_tokens=a['thinking'],final_tokens=a['final'],format_tokens=a['format'],token_accounting=a,
        generation_seconds=response['total_seconds'],peak_allocated_bytes=response['peak_allocated_bytes'],
        peak_reserved_bytes=response['peak_reserved_bytes'], API_usd=0,
        source_review=review,model_evaluation=ev,diagnostic_disposition=diag,model_qualified=False,
        complete_final=response.get('raw_text') if response['natural_eos'] else None,
        artifact_sha256={str(p):sha(p) for p in [path,response_path,raw_path,started_path]+([review_path,diag_path] if review else [])})
    row['semantic_disposition'] = ('source_proven_material_error_hard_stop' if row['source_proven_material_error'] else
        'reviewer_unresolved_continue_diagnostics_only' if row['reviewer_unresolved_ambiguity'] else
        'technical_failure_no_semantic_assessment' if model_unknown is None else 'reviewed_with_limitations_not_qualified')
    newrows.append(row)
newrows.sort(key=lambda r:r['execution_order_this_stage'])
assert len(newrows)==11 and len({r['original_slot_request_id'] for r in rows if r['started']})==33

# Restore the reference join by immutable reply identity. No label is edited,
# and the declared Du copy is used only to verify positional mapping.
intake_path=R/'project/outputs/pm_rl1/development_closeout_20261014_v1/acceptance_final/development_intake_private.json'
intakes=read(intake_path); legacy_refs=read(B/'human_and_historical_reference_private.json')
refs={}; corrections=[]
for oldref in legacy_refs:
    key=oldref['item_key']; item=plan['items'][key]; pair=item['pair_id']
    ch=next(x for x in intakes if x['pair_id']==pair and x['reviewer']=='Chen')
    du=next(x for x in intakes if x['pair_id']==pair and x['reviewer']=='Du')
    identity=digest(item['reply'])
    side=next(k for k,v in ch['reply_identities'].items() if v==identity)
    dside=next(k for k,v in du['reply_identities'].items() if v==identity)
    assert side==item['side'] and ch['risks'][side]['level']==du['risks'][dside]['level']
    pref=ch['preference']['value']; dpref=du['preference']['value']
    assert (ch['reply_identities'][pref]==du['reply_identities'][dpref]) if pref in ('A','B') else pref==dpref
    ref=dict(item_key=key,pair_id=pair,reply_identity=identity,Chen_intake_identity=ch['identity'],
        Chen_side=side,Du_side=dside,Du_identity=du['identity'],Du_independent_observations=0,
        human_preference=pref,human_risk_level=ch['risks'][side]['level'],
        preference_comparable=ch['preference']['comparable'],human_q=None,
        legacy_preference=oldref['human_preference'],legacy_risk_level=oldref['human_risk_level'],
        original_labels_unchanged=True,join='reply identity; Chen saved source; Du positional consistency only')
    refs[key]=ref
    if pref!=oldref['human_preference'] or ref['human_risk_level']!=oldref['human_risk_level']:corrections.append(ref)
save('reference_binding_addendum.json',dict(time_jst=now,source=str(intake_path),source_sha256=sha(intake_path),
    problem='prepare.py pair_id-only dict selected last Du row then joined original Chen-side item by A/B position; display permutation ignored',
    change='analysis join only; frozen plan, source labels, scores, runner and original references untouched',
    cases_changed=sorted({x['item_key'][3:5] for x in corrections}),corrections=corrections,all_32_references=list(refs.values())))

primary={(r['label'],r['item_key']):r for r in rows if r['draw']=='primary'}
pairs=[]; risk=[]; repeats=[]; variants=[]
orders=sorted({i['Chen_order'] for i in plan['items'].values() if 'Chen_order'in i})
for label in 'AB':
    for order in orders:
        a=primary[(label,f'dev{order:02}A')];b=primary[(label,f'dev{order:02}B')]; ref=refs[a['item_key']]
        complete=a['analysis_U'] is not None and b['analysis_U'] is not None
        direction=('tie' if a['analysis_U']==b['analysis_U'] else 'A' if a['analysis_U']>b['analysis_U'] else 'B') if complete else None
        comparable=complete and ref['preference_comparable']
        pairs.append(dict(label=label,Chen_order=order,human_preference=ref['human_preference'],
            legacy_human_preference=ref['legacy_preference'],human_comparable=ref['preference_comparable'],
            numeric_complete=complete,raw_numeric_direction=direction,raw_numeric_comparable=comparable,
            raw_numeric_agreement=direction==ref['human_preference'] if comparable else None,
            reviewer_unresolved=a['reviewer_unresolved_ambiguity'] or b['reviewer_unresolved_ambiguity'],
            source_proven_material_error=a['source_proven_material_error'] or b['source_proven_material_error'],
            contains_offline_derivative=any(x['record_class'].startswith('old_strict_failure') for x in [a,b]),
            reason=None if comparable else 'human unknown' if complete else 'one or both numeric results absent',
            reward_eligible=False, independent_Du_observations=0))
    for key,ref in refs.items():
        row=primary[(label,key)]; human_m={'none_detected':0,'local':0.5,'severe':1}.get(ref['human_risk_level'])
        comparable=row['analysis_m'] is not None and human_m is not None
        risk.append(dict(label=label,item_key=key,human_risk=ref['human_risk_level'],human_q=None,
            model_m=row['analysis_m'],raw_comparable=comparable,raw_agreement=row['analysis_m']==human_m if comparable else None,
            reviewer_unresolved=row['reviewer_unresolved_ambiguity'],source_proven_material_error=row['source_proven_material_error'],
            reason=None if comparable else 'human risk unknown' if human_m is None else 'model numeric result absent',not_severity_gold=True))
for row in rows:
    if row['draw']!='primary':
        item=dict(label=row['label'],item_key=row['item_key'],draw=row['draw'],original_slot_request_id=row['original_slot_request_id'],
            started=row['started'],comparable=False,reason=row['not_dispatched_reason'])
        (variants if row['item_key'].startswith('variant_') else repeats).append(item)
assert len(repeats)==8 and len(variants)==8 and not any(x['started'] for x in repeats+variants)

summary=dict(time_jst=now,HEAD='0c85538ad9a5f6065a7bc31ee0769cb76eaa0f28',branch='work/paper1-rq1-integration-20260816',
    protocol_identity=protocol['identity'],interface=protocol['interface'],dispatch_policy=protocol['diagnostic_policy'],
    baseline=88,new_attempts=11,cumulative_attempts=99,capacity=289,stage_hard_stop=146,
    remaining_authorized_but_hard_stopped=47,per_candidate={},new_generation_seconds=sum(r['generation_seconds'] for r in newrows),
    shared_load_seconds=stage['loads'][0]['seconds'],new_shared_residence_seconds=stage['shared_residence_seconds'],
    runner_process=read(OUT/'process_exit.json'),API_usd=0,API_calls=0,env_or_key_reads=0,recovery_calls=0,
    source_proven_material_errors_new=1,reviewer_unresolved_records_new=1,reviewer_unresolved_records_total=3,
    reviewer_unresolved_case_keys=['dev04B','dev06B'],model_self_unknown_new=0,
    technical_failures_new=1,technical_failures_all_pool=3,offline_derivatives=2,
    human_context=dict(pairs=16,comparable=15,clear=4,tie=11,unknown=1,risk_slots=32,risk_known=26,risk_unknown=6,
        absolute_q_gold=False,Du_independent_observations=0,reference_join_addendum='reference_binding_addendum.json'),
    four_config_states=dict(A='HARD_STOP_SOURCE_PROVEN_SPEAKER_ERROR_21_OF_40',B='HARD_STOP_TIMEOUT_NO_FINAL_12_OF_40',
        C='PENDING_NOT_EXECUTED_0_OF_40',D='PENDING_NOT_EXECUTED_0_OF_40'),reward_eligible=False,winner=None)
for label in 'AB':
    allr=[r for r in rows if r['label']==label]; live=[r for r in allr if r['started_this_stage']]; done=[r for r in allr if r['started']]
    ps=[p for p in pairs if p['label']==label]; rs=[r for r in risk if r['label']==label]; pscomp=[p for p in ps if p['raw_numeric_comparable']]
    vals=[r['generation_seconds'] for r in live]; allvals=[r['generation_seconds'] for r in done]
    summary['per_candidate'][label]=dict(new_calls=len(live),slots_started=len(done),numeric_slots=sum(r['analysis_q'] is not None for r in allr),
        formal_numeric_slots=sum(r['formal_q'] is not None for r in allr),offline_numeric_derivatives=sum(r['derived_q'] is not None for r in allr),
        remaining=40-len(done),remaining_primary=sum(not r['started'] and r['draw']=='primary' for r in allr),remaining_repeat=4,remaining_variant=4,
        new_generation_seconds=sum(vals),new_mean_generation_seconds=sum(vals)/len(vals),new_generation_range_seconds=[min(vals),max(vals)],
        all_generation_seconds=sum(allvals),new_input_tokens=sum(r['input_tokens'] for r in live),new_output_tokens=sum(r['total_output_tokens'] for r in live),
        new_final_tokens=sum(r['final_tokens'] for r in live) if all(r['final_tokens'] is not None for r in live) else None,
        new_thinking_tokens=sum(r['thinking_tokens'] for r in live) if all(r['thinking_tokens'] is not None for r in live) else None,
        peak_new_allocated_GiB=max(r['peak_allocated_bytes'] for r in live)/2**30,
        peak_new_reserved_GiB=max(r['peak_reserved_bytes'] for r in live)/2**30,
        numeric_complete_pairs=sum(p['numeric_complete'] for p in ps),raw_pair_comparable=len(pscomp),
        raw_pair_matches=sum(p['raw_numeric_agreement'] for p in pscomp),reviewer_unresolved_pairs=sum(p['reviewer_unresolved'] for p in pscomp),
        clear_compared=sum(p['human_preference']in ['A','B'] for p in pscomp),clear_matches=sum(p['raw_numeric_agreement'] for p in pscomp if p['human_preference']in ['A','B']),
        ties_compared=sum(p['human_preference']=='tie' for p in pscomp),ties_matched=sum(p['raw_numeric_agreement'] for p in pscomp if p['human_preference']=='tie'),
        risk_comparable=sum(r['raw_comparable'] for r in rs),risk_matches=sum(r['raw_agreement'] is True for r in rs),
        risk_human_unknown_with_model_numeric=sum(r['human_risk'] is None and r['model_m'] is not None for r in rs),
        risk_comparable_reviewer_unresolved=sum(r['raw_comparable'] and r['reviewer_unresolved'] for r in rs),
        risk_comparable_proven_error=sum(r['raw_comparable'] and r['source_proven_material_error'] for r in rs))
summary['all_33_generation_seconds']=previous['summary']['all_22_generation_seconds']+summary['new_generation_seconds']
summary['all_pool_residence_seconds']=previous['summary']['all_22_residence_seconds']+summary['new_shared_residence_seconds']
gpu=[read(p) for p in sorted(STAGE.glob('gpu_check_*.json'))]
summary['GPU_checks']=len(gpu);summary['GPU_query_failures']=sum(q['returncode']!=0 or bool(q.get('error')) for g in gpu for q in g['queries'])
summary['GPU_first_check']={k:gpu[0][k] for k in ['selected_gpu','visible_processes','process_visibility','eligible','rejection_reasons']}

# Preserve original hashes, exact slot bindings and failed requests. No GPU/API read.
baseline=read(OUT/'baseline.json'); changed=[p for p,h in baseline['original_sha256'].items() if sha(Path(p))!=h]
assert not changed
assert len(list(LIVE.glob('*/*.started.json')))==len(newrows)==len(list(LIVE.glob('*/*.result.json')))
for row in newrows:
    req=requests[row['original_slot_request_id']]
    assert req['request_id']==row['actual_request_id']
    assert req['messages_identity']==row['messages_identity'] and req['schema_identity']==row['schema_identity']
    assert sha(Path(row['response_path']))==row['artifact_sha256'][row['response_path']]
    if row['source_review']:
        assert row['source_review']['response_sha256']==sha(Path(row['response_path']))
        assert row['source_review']['raw_sha256']==sha(Path(row['raw_path']))
        assert row['model_evaluation']['validation_stage']=='complete'
assert sum(r['reviewer_unresolved_ambiguity'] for r in rows)==3
assert sum(r['source_proven_material_error'] for r in rows)==1
assert sha(B/'outer_format_v1_20261015/continue_v1.py')==protocol['implementation']['continuation']
assert not Path('/proc/685683').exists()
save('targeted_final_integrity.json',dict(time_jst=now,original_files_checked=len(baseline['original_sha256']),changed_original_files=changed,
    new_started=11,new_results=11,new_reviews=10,new_diagnostic_records=10,all_pool_unique_started_slots=33,cumulative=99,
    source_plan_identity=plan['identity'],protocol_identity=protocol['identity'],original_slots_and_input_bindings_match=True,
    original_STOPs_preserved=True,new_STOPs=[str(p) for p in LIVE.glob('*/STOP.json')],model_process_exited=True,
    no_model_or_API_requests_in_report=True,reporting_reference_join_separately_recorded=True))
save('summary.json',summary)
save('results_private.json',dict(summary=summary,rows=rows,pairs=pairs,risk=risk,repeats=repeats,variants=variants))
fields=[k for k in dict.fromkeys(k for r in rows for k in r) if k not in ['model_evaluation','source_review','complete_final','diagnostic_disposition','artifact_sha256']]
csvwrite('all_80_slots_private.csv',rows,fields)
csvwrite('new_11_attempts_private.csv',newrows,fields)
csvwrite('pair_comparisons_private.csv',pairs)
csvwrite('risk_comparisons_private.csv',risk)
csvwrite('predeclared_repeat_status.csv',repeats)
csvwrite('mechanism_variant_status.csv',variants)
print(json.dumps(summary,ensure_ascii=False,indent=2))
