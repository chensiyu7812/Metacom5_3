"""Offline proposal only. No transport, credential, account, or launch call."""
from pathlib import Path
import hashlib, json, os, sys, statistics
from datetime import datetime
from zoneinfo import ZoneInfo
from decimal import Decimal

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
REPO = BASE.parents[3]
sys.path.insert(0, str(BASE / 'paired_diagnostic_20261019_v1'))
import paired as p

os.umask(0o077)
VERSION = 'pmrl1-resource-decision-noise-proposal-v1-20261020'
STATUS = 'PROPOSED RESEARCH CHANGE — NOT AUTHORIZED'
def read(path): return json.loads(Path(path).read_text())
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def digest(value): return hashlib.sha256(p.s.canonical(value).encode()).hexdigest()
def write(name, data):
    path = HERE / name
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open('x') as f:
        f.write(json.dumps(data, ensure_ascii=False, indent=2) + '\n' if not isinstance(data, str) else data)
    path.chmod(0o600)

inventory_path = BASE / 'acceptability_resource_review_20261019_v1/materials/selected_existing_records.json'
contexts_path = inventory_path.with_name('contexts.json')
inventory = read(inventory_path)
contexts = read(contexts_path)
old_items = read(BASE / 'paired_diagnostic_20261019_v1/package/items.json')
old_protocol = read(BASE / 'action_stage_diagnostic_20261020_v1/protocol.json')
prompt_path = BASE / 'continuation_20261020_v1/measurement_proposal/PROPOSED_JOINT_PROMPT_EN.txt'
assert sha(prompt_path) == '70e47c3da4167787b37a189688d7f8122d4eb7175abb97ad7fc1192f80a4eed2'
ledger = REPO / 'project/outputs/paper1_api_budget/cumulative_paid_api_budget.jsonl'
assert sha(ledger) == 'cc7c0d6696562d9fbbee83736ea92632f28e41e7b591fcf2721d7e0d73eca3a1'
counts = {name:len([x for x in (BASE/name).rglob('*.started.json') if 'management' not in x.parts])
          for name in ('live_runs','paired_diagnostic_runs','action_stage_runs')}
assert counts == {'live_runs':54,'paired_diagnostic_runs':24,'action_stage_runs':9}
assert 66 + sum(counts.values()) == 153

# Purposeful development coverage: all OFF/RS; the remaining four slots cover
# MP/ME/MS/combo. ME in context_02 also reuses an exact previous human reply.
# This known-problem inventory was already inspected; selection is not blinded.
plans = {'context_01':['0000','1000','0100'],
         'context_02':['0000','1000','0001'],
         'context_03':['0000','1000','0010'],
         'context_04':['0000','1000','1111']}
by_id = {x['row_id']:x for x in inventory}
selected = [by_id[c+'_'+plan] for c, ps in plans.items() for plan in ps]
assert len(selected) == len({x['reply_identity'] for x in selected}) == 12
assert {x['split'] for x in selected} == {'dev'}
assert len({x['owner'] for x in selected}) == 2
assert len({x['executor_identity'] for x in selected}) == 1

old_results = read(BASE / 'action_stage_diagnostic_20261020_v1/per_request_results.json')
completed = [x for x in old_results if x['state']=='completed']
ratio = {}
for c in contexts:
    rows = [x for x in completed if x['context_id']==c]
    slotmap = {x['slot_id']:x for x in old_protocol['schedule']}
    ratio[c] = statistics.mean(x['usage']['prompt_tokens']/slotmap[x['slot_id']]['serialized_messages_bytes'] for x in rows)

endpoints, payload_hashes, estimated_input = [], [], []
for row in selected:
    assert sha(row['request_path']) == row['request_file_sha256']
    assert sha(row['raw_path']) == row['raw_file_sha256']
    raw = read(row['raw_path'])
    assert raw['text'] == row['reply']
    assert hashlib.sha256(row['reply'].encode()).hexdigest() == row['reply_text_sha256']
    evidence = contexts[row['context_id']]
    evidence = {k:evidence[k] for k in ('current_date','current_prefix','legal_past_sessions')}
    matching = next(x for x in old_items.values() if x['context_id']==row['context_id'])
    assert evidence == matching['evidence']
    item = {'evidence':evidence, 'reply':row['reply']}
    messages, schema = p.payload(item, 'joint')
    messages[0]['content'] = prompt_path.read_text()
    screen = p.input_guard(messages)
    data = {'messages':messages, 'schema':schema}
    name = 'payloads/'+row['row_id']+'.json'
    write(name, data)
    estimated_input.append(screen['serialized_messages_utf8_bytes'] * ratio[row['context_id']])
    endpoint = {k:row[k] for k in ('row_id','context_id','prefix_index','owner','split','prefix_identity','counts',
         'slot_id','request_id','request_path','raw_path','request_file_sha256','raw_file_sha256',
         'reply_identity','reply_text_sha256','resource_tokens','executor_identity','renderer_identity','draw_identity')}
    endpoint.update(payload_file=name, payload_file_sha256=sha(HERE/name), payload_identity=digest(data),
        evidence_identity=digest(evidence), input_screen=screen,
        exact_old_reference_items=[k for k,v in old_items.items() if v['reply']==row['reply'] and v['evidence']==evidence],
        original_scores_changed=False, new_human_pair_direction=None)
    endpoints.append(endpoint)
    payload_hashes.append(endpoint['payload_identity'])

contrasts = []
for c, ps in plans.items():
    for plan in ps[1:]:
        row = by_id[c+'_'+plan]
        contrasts.append(dict(id=c+'_'+plan+'_vs_OFF', off=c+'_0000', on=c+'_'+plan,
            resource_tokens=row['resource_tokens'], cost=float(Decimal('.05')*row['resource_tokens']/2048),
            source_reference_state='not_a_completed_human_pair_judgment'))

# Four complete rounds; two nonoverlapping two-draw blocks. Reversal counterbalances
# OFF-first versus ON-first. No result-dependent order or optional repeats.
orders = [selected, list(reversed(selected)), selected, list(reversed(selected))]
schedule = []
for rnd, order in enumerate(orders, 1):
    for row in order:
        endpoint = next(x for x in endpoints if x['row_id']==row['row_id'])
        schedule.append(dict(position=len(schedule)+1, draw=rnd, block='A' if rnd<=2 else 'B',
            endpoint=row['row_id'], slot_id=f'{VERSION}-r{rnd}-{row["row_id"]}',
            payload_identity=endpoint['payload_identity'], state='NOT_AUTHORIZED_NOT_STARTED'))
assert len(schedule)==len({x['slot_id'] for x in schedule})==48
assert all(len([s for s in schedule if s['endpoint']==x['row_id']])==4 for x in endpoints)
assert all(len({s['payload_identity'] for s in schedule if s['endpoint']==x['row_id']})==1 for x in endpoints)

mean_output = statistics.mean(x['usage']['completion_tokens'] for x in completed)
min_output = min(x['usage']['completion_tokens'] for x in completed)
max_output = max(x['usage']['completion_tokens'] for x in completed)
def projected(out): return 4*sum(estimated_input)*.3/1e6 + 48*out*1.2/1e6
budget = dict(status=STATUS, official_price_checked_at=datetime.now(ZoneInfo('Asia/Tokyo')).isoformat(),
    official_price_url='https://api-docs.deepseek.com/quick_start/pricing/',
    public_model_mapping='DeepSeek-V4.1-Flash-1017', model_alias_not_immutable=True,
    peak_usd_per_million=dict(input_miss=.3,input_hit=.006,output=1.2),
    current_trial_accounted_usd='0.461787',current_shared_total_usd='1.96902991',
    original_shared_boundary_usd='1.50724291',current_shared_followup_spent_usd='0.461787',
    known_unsettled_usd='0',ledger_sha256=sha(ledger),
    proposed_stage_spend_plus_unsettled_cap_usd='1.25',trial_cap_usd='2',shared_followup_cap_usd='20',
    unchanged_per_request_reservation_usd='0.786432',
    reservation_formula='1048576*0.30/1e6 + 393216*1.20/1e6; keep existing conservative native-bound guard',
    stage_completed_cost_ceiling_before_next_reservation_usd='0.463568',
    input_estimation='Same-context observed provider-token/serialized-message-byte ratio, not exact tokenization or a reservation basis',
    estimated_input_tokens_all_48=4*sum(estimated_input),
    empirical_output_tokens_min_mean_max=[min_output,mean_output,max_output],
    peak_no_cache_projection_usd=dict(short_observed_length=projected(min_output),
        mean_observed_length=projected(mean_output),long_observed_length=projected(max_output)),
    not_confidence_interval_or_quote=True,can_stop_before_48=True,
    output_limit_unchanged=393216,all_48_simultaneous_worst_case_usd=str(Decimal('.786432')*48),
    max_new_score_attempts=48,cumulative_start=153,cumulative_proposed_cap=201,capacity=289,
    remaining_capacity_after_stage=88,old_conditional_acceptance_reserve=59,recovery_reserve=4,
    remaining_after_old_conditional_reserves=25,
    old_59_not_automatically_sufficient_for_aggregation=True,
    future_models_query_requested=1,future_balance_query_requested=1,new_account_calls_now=0,
    budget_guard_checks_all_concurrent_paid_liability=True,
    future_full_research_double_scoring_warning='No blanket two-draw deployment is authorized. Old no-dedup 24.42–36.48 USD projections already exceed the shared remaining budget; doubling paid reward measurements needs separate unique-endpoint cost reconciliation.')

protocol = dict(version=VERSION,status=STATUS,created_at=datetime.now(ZoneInfo('Asia/Tokyo')).isoformat(),
    goal='Diagnose whether fixed terminal OFF/ON decision variability is reduced by a two-draw mean, and distinguish stability from evidence-backed correctness.',
    configuration=old_protocol['config'], frozen_prompt_sha256=sha(prompt_path),
    interface=old_protocol['final_interface'], semantic_revisions_applied=2,semantic_revision_delta=0,
    frozen_executor_identity=selected[0]['executor_identity'],
    selection='Purposeful already-exposed development inventory; all four OFF and RS1, then MP1/ME1/MS1/combo. Selection includes known errors and reference availability, not a blind or random population sample.',
    endpoints=endpoints,contrasts=contrasts,schedule=schedule,
    statistical_units=dict(replies=12,contrasts=8,contexts=4,source_owners=2,independent_new_users=0),
    human_reference=dict(max_pairs=8,max_minutes_total=120,reviewers_required=1,
        max_consolidated_clarification_rounds=1,original_annotations_unchanged=True,
        exact_old_reply_reference_matches=sum(bool(x['exact_old_reference_items']) for x in endpoints),
        timing='Before new scores are shown; old result exposure disclosed. No annotation task is issued now.',
        answers=['left_better','right_better','tie','unknown'],
        extra_fields=['important_factual_or_attribution_problem_with_source','what_current_need_is_met_or_missing','uncertainty_reason'],
        no_forced_q_m_point_labels=True,no_new_independent_rater_claim=True,
        if_time_exhausted='Retain incomplete/unknown; no follow-on assignment. Accuracy statements only for completed, explicitly comparable references.'),
    estimators=dict(single_blocks=[[1],[3]],mean_two_blocks=[[1,2],[3,4]],
        U='q/4-m; retain each original q,m,U',
        decision_difference='D(plan,draw)=U(plan,draw)-U(OFF_same_context,draw)-0.05*resource_tokens/2048',
        aggregate='Arithmetic mean of the two complete D values in each block; descriptive candidate only, not a new certified q/m label',
        same_OFF_shared_by_all_plans_in_context=True,OFF_self_contrast_exactly_zero=True,
        null='Any missing/invalid/model-unknown draw makes that block estimate null; never average only surviving draws',
        severe='Keep each evidence finding, every m=1, disagreement and unresolved risk beside the mean; mean never clears a risk or grants eligibility'),
    readout=['raw U and fact-stage/severity judgments by all four draws',
        'single-block versus disjoint-mean-block D sign, exact zeros, absolute discrepancy',
        'within-context three-plan ranking/ties with shared OFF; not independent pair observations',
        'completed human directional pairs, ties and unknowns separately; no forced denominator',
        'whether wrong fact or current-need conclusions persist across draws; repeated error not estimated as population-wide bias',
        'technical delivery, numeric coverage, disputed evidence, all missing slots, real costs and elapsed time'],
    limitations=['Four draws do not certify independent sampling, stationarity or a population error rate.',
        'This tests k=2 only; k=3 would need 72 calls for two disjoint triplets over these same endpoints and is not included.',
        'Terminal contrasts do not certify every intermediate GET marginal value or all 70 plans.',
        'No known human-confirmed positive resource-gain pair is guaranteed. Stable all-ties cannot validate directional sensitivity.',
        'No prompt, executor, source, rubric, reward formula or qualification threshold is changed by this proposal.'],
    proposed_dispatch_policy=dict(old_stops_released=False,old_stage_resumed=False,automatic_retries=0,
        isolated_semantic_errors_continue=True,semantic_variation_continue=True,
        isolated_complete_but_invalid_final_continue=True,
        consecutive_mechanical_failures_stop=2,
        incomplete_transport_or_usage_unknown_stop=True,
        identity_hash_data_service_violation_stop_immediately=True,
        insufficient_liability_capacity_stop=True,
        error_categories_and_missingness_retained=True,
        policy_rationale='A fixed diagnostic batch must observe error frequency rather than censor at the first semantic discrepancy. This prospective dispatch amendment does not relax qualification.'),
    eligibility=dict(reward_eligible=False,training_authorized=False,freeze_authorized=False,
        original_contract_and_stops_unchanged=True,stage_cannot_grant_qualification=True),
    authority_requested=dict(max_calls=48,cumulative_cap=201,stage_liability_usd='1.25',
        accounts={'GET /models':1,'GET /user/balance':1},
        credentials='Process-only DEEPSEEK_API_KEY from the previously designated env; no access now.',
        outbound='Only frozen scoring/AI-role instructions, one reply with stable units, its complete legal current/past sources and IDs. No conditions, costs, annotations, reference verdicts, previous draws, review notes or other model outputs.',
        data_use_conditions='Same official service and previously approved source-use scope; no new policy acceptance or account changes.',
        human_scope='At most eight paired directions within 120 minutes; no assignment sent now.'))
protocol['decision_rules'] = {
    'status':'PROPOSED_DEVELOPMENT_RESOURCE_DECISION_NOT_QUALIFICATION',
    'consider_independent_validation':[
        'At least two contexts with single-draw variability have a smaller absolute between-block D discrepancy under k=2.',
        'Total between-block D sign flips decrease; comparable human-direction errors do not increase.',
        'Effective paired coverage does not fall; all material-risk findings remain separately unresolved or evidence-reviewed.'
    ],
    'persistent_error_or_added_direction_error':'Do not equate variance reduction with usable reward. Target the demonstrated error class in a separately bounded calibration proposal.',
    'no_demonstrable_gain':'Report stable-single floor, low contrast, missing reference, no variance benefit or missingness as observed; no extra draws or model switches.',
    'no_safety_or_qualification_override':True,
}
protocol['decision_document_sha256'] = sha(HERE/'DECISION_ZH.md')
protocol['identity']=digest(protocol)
write('proposal.json',protocol)
write('budget.json',budget)
write('selected_endpoints.json',endpoints)
write('OFF_ON_CONTRASTS.json',contrasts)
write('SCHEDULE_48.json',schedule)
checks=dict(status='OFFLINE_BINDING_AND_ARITHMETIC_CHECKS_PASSED_NOT_SEMANTIC_VALIDATION',
    actual_attempts=153,counts=counts,ledger_unchanged=sha(ledger)==budget['ledger_sha256'],
    raw_request_reply_hashes_verified=12,source_bundles_exact_old_evidence=4,
    repeated_payload_bytes_unchanged=True,distinct_prespecified_draw_slots=48,
    exact_old_human_reply_reuse_count=protocol['human_reference']['exact_old_reply_reference_matches'],
    provider_tokenization_not_claimed=True,full_input_byte_screens_passed=12,
    proposed_201_plus_old_59_plus_4=264,capacity=289,
    new_score_calls=0,new_generation_calls=0,new_human_judgments=0,new_account_requests=0,
    credentials_read=False,protected_data_read=False,model_or_GPU_loaded=False,
    production_runner_changed=False,formal_contract_changed=False,
    preserved_inputs={str(x):sha(x) for x in (inventory_path,contexts_path,prompt_path,ledger,
        BASE/'action_stage_diagnostic_20261020_v1/protocol.json',
        REPO/'project/docs/pm_rl1_completion_20260930_v2/execution_contract.json')})
write('offline_receipt.json',checks)
print(json.dumps({'proposal_identity':protocol['identity'],'endpoints':12,'contrasts':8,
    'requests_proposed_not_started':48,'exact_prior_reference_matches':checks['exact_old_human_reply_reuse_count'],
    'peak_cost_projection':budget['peak_no_cache_projection_usd'],'new_calls':0},ensure_ascii=False))
