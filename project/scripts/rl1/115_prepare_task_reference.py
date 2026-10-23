#!/usr/bin/env python3
"""Offline-only, exclusive-write preparation. No keys, HTTP or model imports."""
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import os
import sys

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.rl1 import relation_reference as r
from metacom_pm.rl1 import task_reference as t
BASE=PROJECT/'outputs/pm_rl1/judge_selection_preparation_20261014_v1'
OLD=BASE/'relation_reference_preparation_20261021_v2'
PREP=BASE/'task_reference_preparation_20261021_v1'
sys.path.insert(0,str(BASE/'paired_diagnostic_20261019_v1'))
import paired as p


def main():
    os.umask(0o077)
    if PREP.exists():raise SystemExit('Preparation already exists; never overwrite a frozen package')
    old=r.read(OLD/'protocol.json');cost=r.read(BASE/'relation_reference_results_20261021_v1/COST_AND_EXECUTION.json')
    ledger=Path(old['financial_baseline']['ledger_path'])
    if r.sha(ledger)!=cost['financial_closeout']['ledger_sha256']:raise ValueError('ledger changed; reconcile first')
    items=r.read(OLD/'inputs_private.json');refs=r.read(OLD/'references.json');materials=r.read(OLD/'materials.json')
    run_dir=BASE/'task_reference_runs'/t.VERSION/'live'
    snapshots=t.history_snapshot(BASE,run_dir)
    assert 66+len(snapshots)==253
    stops={str(path):r.sha(path) for name in t.RUN_ROOTS for path in (BASE/name).rglob('STOP.json')}
    fin=dict(old['financial_baseline'],ledger_sha256=r.sha(ledger),ledger_bytes=ledger.stat().st_size,
             trial_accounted_usd=cost['financial_closeout']['trial_accounted_usd'],shared_total_usd='2.85236851',known_unsettled=0)
    b=p.DiagnosticBudget(ledger,trial=fin['financial_trial_identity'],study=t.VERSION,
        stage_cap=p.s.nanodollars(2),trial_cap=p.s.nanodollars('3.15'),shared_cap=p.s.nanodollars(20),
        baseline=p.s.nanodollars('1.50724291'),opening=p.s.nanodollars('.03079930'))
    total,trial,reserved,settled=b._totals(b.events())
    assert p.s.usd(total)==fin['shared_total_usd'] and p.s.usd(trial)==fin['trial_accounted_usd']
    assert not set(reserved)-set(settled)
    save=lambda name,value:r.save_new(PREP/name,value)
    for name,value in (('inputs_private.json',items),('references.json',refs),('materials.json',materials)):
        save(name,value)
    base_prompt=(OLD/'BASELINE_PROMPT_EN.txt').read_text()
    alignment_path=BASE/'anchor_calibration_preparation_20261020_v1/COMMON_TASK_ADDITION_EN.txt'
    common_policy=alignment_path.read_text().split('TASK ALIGNMENT:\n',1)[1].split('\nEVIDENCE APPLICATION:',1)[0].strip()
    prompt=base_prompt+'\n\nSHARED TASK ALIGNMENT FOR THIS NEW DIAGNOSTIC\n'+common_policy+'\n'
    save('BASELINE_PROMPT_EN.txt',base_prompt);save('SHARED_TASK_POLICY_EN.txt',common_policy+'\n');save('COMMON_PROMPT_EN.txt',prompt)
    # No candidate-specific judgment, resource label, numeric target or human score.
    descriptions={
      'context_01':dict(ids=['C:T001','C:T006','C:T008'],
        requests=['The user reports distress about workplace favoritism/injustice.',
                  'The earlier request asks for help handling this situation; the final turn confirms that injustice bothers the user.'],
        role='The new AI cannot own the earlier supporter\'s workplace experience. The final user turn does not ask the AI to recount that experience.',
        options=['Acknowledgment, a relevant exploratory question, discussion of options, or concrete advice may contribute; no style is preferred by itself.'],
        unresolved=['How much concrete advice is needed at this conversational point is not fixed by these source turns.',
                    'This card supplies no claim that effects on team morale or productivity have occurred.']),
      'context_02':dict(ids=['C:T007','C:T008','C:T009'],
        requests=['The user reports anger about the mother restricting friend choices.',
                  'The user directly asks how the preceding supporter dealt with a similar situation; this personal-experience question is part of the current request.'],
        role='The prior supporter owns the experience in C:T008. The responding new AI cannot claim it as its own. Apply the same conditional attribution-clarification policy to this user request for every candidate reply.',
        options=['After handling attribution, exploring anger, discussing coping, or accurately attributing a previous supporter strategy can contribute; no one strategy is required.'],
        unresolved=['This card does not decide how important an omission is in a particular reply, whether other content adequately addresses the request, or its severity.',
                    'An attribution omission is distinct from an affirmative false autobiographical claim; neither supplies an automatic numeric grade.']),
      'context_03':dict(ids=['C:T005','C:T009','C:T013'],
        requests=['The user is reporting that support from an old college friend helped with the perspective on a thesis.',
                  'The final turn continues sharing that experience; there is no explicit request for a particular advice style.'],
        role='The friend, the historical supporter and the new AI are different actors. Preserve the source attribution.',
        options=['Acknowledgment or relevant reflection/exploration can fit the report; do not assume that more advice is needed.'],
        unresolved=['This card does not grade any candidate or assign a severity to an attribution problem.']),
      'context_04':dict(ids=['C:T000','C:T001','C:T002'],
        requests=['The user says things have been tough lately without stating the present cause.'],
        role='The new AI responds to this limited current disclosure; historical context is not automatically the current cause.',
        options=['A gentle acknowledgment and an invitation to elaborate can be sufficient at this stage.'],
        unresolved=['The present cause is unspecified; the card does not identify one or grade a candidate response.']),
      'context_05':dict(ids=['C:T007','C:T019','C:T021'],
        requests=['The final user turn thanks the supporter after the advice exchange.',
                  'Earlier turns report reduced drinking aimed at saving the marriage and a future intention to avoid drinking.'],
        role='Reported effort, future intention and achieved marital outcome are distinct. The new AI cannot guarantee a future outcome.',
        options=['Acknowledging thanks and closing warmly may fit the current turn without requiring more advice.'],
        unresolved=['No achieved marital recovery is established by the listed turns; the card does not equate effort with success or grade encouragement.'])}
    cards={};card_map={};zh={}
    for m in materials:
        key=m['evidence_identity'];card_map[m['material_id']]=key
        if key in cards:continue
        d=descriptions[m['context_id']];e=items[m['material_id']]['evidence'];turns={x['id']:x for x in e['current_prefix']}
        card=dict(interface_version=t.INTERFACE,evidence_identity=key,current_date=e['current_date'],
            source_facts=[dict(source_id=i,speaker=turns[i]['role'],quote=turns[i]['text']) for i in d['ids']],
            request_elements=d['requests'],role_application=d['role'],acceptable_options=d['options'],
            unresolved_importance=d['unresolved'],provenance='analyst_prepared_after_development_exposure_not_independent_gold',independent_gold=False)
        t.validate_card(items[m['material_id']],card);cards[key]=card;zh[m['context_id']]=key
    save('task_cards.json',cards);save('material_task_bindings.json',card_map)
    # Order fixed from source context and known controls; not from newly obtained outputs.
    order=['dev06B','dev06A','context_02_1000','dev04B','dev04A','dev07A','dev15B','dev16A','dev35B','context_01_1000','context_04_0000','dev108_OFF']
    repeats=['dev06B','dev06A','context_02_1000','dev04B']
    schedule=t.schedule(items,order,repeats);assert len(schedule)==32
    save('schedule.json',schedule)
    screens={}
    for key,item in items.items():
        for arm in ('A','B'):
            data=t.make_payload(item,refs[key],cards[card_map[key]],arm,prompt,p)
            screens[key+'__'+arm]=t.validate_payload(item,refs[key],cards[card_map[key]],arm,prompt,data,p)
            save('payloads/'+key+'__'+arm+'.json',data)
    policy=dict(r.POLICY)
    analysis=dict(primary_context='context_02',primary_endpoints=['dev06B','dev06A','context_02_1000'],
      within_reply_repetition_pairs=[[k,1,2] for k in repeats],
      within_context_pairs=[['dev06B','dev06A'],['dev06B','context_02_1000'],['dev06A','context_02_1000'],['dev04A','dev07A'],['dev04B','context_01_1000']],
      do_not_count_as_inconsistency='different q alone; missing favored style; a justified different content contribution; an explicitly unresolved reasonable reading',
      inconsistency_requires='quoted public rationale applies incompatible task obligations to identical context without a source/content-specific reason; analyst finding, not independent gold',
      primary_success='B adopts the common task reference correctly; at least one prespecified standard-switch issue observed in A is absent across both B repetitions; no newly introduced source-proven checking error or task-basis contradiction; all six mother endpoint outputs per arm are valid; no lower whole-batch usable coverage than A',
      success_scope='development route-selection only; no unique-q gold, no qualification, no generalization, no automatic C',
      no_effect_or_ceiling='A has no evaluable target inconsistency or B does not improve: report no demonstrated benefit/inconclusive; no more draws',
      mixed='improvement and regression are separate; never net them into a winner',
      interpretation='adoption failure -> interface/execution; adoption with unsupported scoring -> mapping; justified residual readings -> numerical ambiguity study; not proof of a unique cause',
      technical_missing='hard stop, retain all planned slots and missingness; do not call incomplete delivery semantic failure',
      unknown='model missing; no zero/tie; primary paired comparison missing where any endpoint unknown',
      resource_contrasts='use matched repetition when both endpoints repeated; workplace repeat reuses its single ON and is marked dependent',
      no_correct_direction_gold=True,no_new_independent_human_review=True,no_target_scores=True)
    save('analysis_rules.json',analysis)
    save('ANALYST_REVIEW_TEMPLATE.json',dict(status='NOT_REVIEWED',slot_id=None,original_result_sha256=None,
       task_uptake=None,relationship_check=None,q_basis=None,severity_basis=None,
       public_final_quotes=[],source_checks=[],confirmed_error=None,reviewer_ambiguity=None,
       independent_human_reference=False,note='No model/human answers prefilled. Adjacent q is not automatically error.'))
    limits=dict(max_calls=32,cumulative_cap=285,proposed_capacity=349,stage_usd='2',trial_usd='3.15',shared_usd='20',
                native_single_reserve_usd='0.786432',management_requests={'models':1,'user/balance':1},new_generation=0,natural_updates=0)
    stats=dict(distinct_replies=12,current_contexts=5,source_owners=2,mechanism_controls=3,natural_replies=9,
               planned_repetitions_per_arm=4,total_requests=32,independent_validation_cases=0,
               history_overlap='same source owners and overlapping past sessions; repeated replies not independent cases')
    save('exposure.json',dict(statistics=stats,materials=materials,prior_exposure=old['statistics'],
         new_source_groups=0,protected_content_read=False,semantic_family_independence=False))
    mean=Decimal(cost['financial_closeout']['stage_accounted_usd'])/28
    effective=min(Decimal(2),Decimal('3.15')-Decimal(fin['trial_accounted_usd']))
    native=Decimal('.786432')
    estimated={}
    for arm in ('A','B'):
        size=sum(screens[s['item_key']]['serialized_messages_utf8_bytes']+8192 for s in schedule if s['arm']==arm)
        old_output=Decimal(cost['arms']['B']['output_tokens_including_thinking'])/14
        estimated[arm]=dict(requests=16,input_byte_upper_screen=size,
           peak_input_byte_screen_plus_old_B_output_usd=str(Decimal(size)*Decimal('.30')/1000000+16*old_output*Decimal('1.20')/1000000))
    full=r.read(BASE/'four_head_diagnostic_preparation_20261020_v1/budget.json')
    future=[]
    for row in full['rows'][6:]:
        future.append(dict(row,latest_28_mean_estimate_usd=str(mean*row['maximum_new_J']),authorized=False,
                          exact_future_compatibility_or_deduplication=False))
    scenarios=[]
    for scenario in full['full_research_scenarios']:
        scenarios.append(dict(scenario,latest_28_mean_with_reserves_usd=str(mean*scenario['slots_with_original_reserves']),
          scenario_half_to_twice_mean_usd=[str(mean*scenario['slots_with_original_reserves']/2),str(mean*scenario['slots_with_original_reserves']*2)],
          training_measurement_version_not_yet_qualified=True,not_confidence_interval=True))
    budget=dict(limits=limits,current_trial_usd=fin['trial_accounted_usd'],shared_followup_accounted_usd=fin['trial_accounted_usd'],known_unsettled=0,
       historical_mean_usd=str(mean),estimate_32_usd=str(mean*32),half_to_twice_mean_scenario=[str(mean*16),str(mean*64)],
       exact_provider_input_tokens=None,actual_input_screens=estimated,not_a_confidence_interval=True,
       native_all_32_upper_usd=str(native*32),effective_current_stage_headroom_usd=str(effective),
       maximum_stage_settled_before_next_native_reservation_usd=str(effective-native),
       completion_not_guaranteed=True,capacity_math='253+32=285; proposed349 leaves64=59+4+1; current317 leaves32, insufficient reserve',
       current_capacity=317,proposed_capacity_applied=False,
       reference_preparation_review=dict(new_model_calls=0,new_human_questionnaire=0,existing_human_answers_reused=True,analyst_cards_not_gold=True),
       conditional_C=dict(max_planning_J=42,latest_mean_usd=str(mean*42),authorized=False),
       minimal_real_wiring=dict(new_J=2,new_G=2,updates=0,latest_mean_J_usd=str(mean*2),authorized=False),
       deferred_random32=dict(new_J=80,new_G=44,stage_usd='3',capacity=369,trial_usd='4.25',authorized=False),
       remaining_stages=future,full_research_scenarios=scenarios,
       independent_evaluation='same judge x960 is not independent evaluation; human protocol/materials/cost remain unresolved',
       budget_choice='full study not yet executable inside shared20; later increase budget or explicit scale tradeoff, no baselines silently removed')
    save('budget.json',budget)
    save('PUBLIC_SERVICE_CHECK.json',dict(checked_date='2026-10-21',source_url='https://api-docs.deepseek.com/quick_start/pricing/',
         method='unauthenticated public document lookup only',published_mapping='DeepSeek-V4.1-Flash-1017',model='deepseek-flash',
         input_peak_cache_miss_usd_per_million='.30',output_peak_usd_per_million='1.20',
         input_peak_cache_hit_usd_per_million='.006',off_peak_multiplier='.5',context_tokens=1048576,max_output_tokens=393216,
         native_reserve_formula='1048576*.30/1e6+393216*1.20/1e6=.786432',
         live_identity_recheck_required=True,no_account_or_model_api_call=True))
    save('OUTBOUND_MANIFEST.json',dict(service='DeepSeek official https://api.deepseek.com/chat/completions',purpose='bounded task-reference diagnostic only',
      both_arms=['full original v2 reply and response units','complete legal current/past source and stable IDs',
                 'same frozen reply-level partial relation reference, including previously authorized limited researcher interpretations',
                 'same explicitly versioned task policy, copied from the prior calibration task-alignment section'],
      B_addition=['context source quotes/IDs/roles','analyst summary of current request and role application',
                  'nonexclusive response options and unresolved importance; explicit non-gold provenance'],
      prohibited=['numeric human labels','human overall preferences','other candidate outputs','desired q/m/U','resource plan/winner',
                  'postrun review records','private notes','sealed data','credential files/headers'],
      analyst_draft_not_new_human_gold=True,approval_required=True,
      credential_file='/home/tokkio/metacom5_3.env',credential_variable='DEEPSEEK_API_KEY',process_only=True,
      no_source_exec=True,no_secret_logs=True,no_persistent_credentials=True,no_zero_retention_claim=True))
    immutable={}
    for path in (Path(__file__),PROJECT/'scripts/rl1/116_run_task_reference.py',PROJECT/'src/metacom_pm/rl1/task_reference.py',
                 PROJECT/'src/metacom_pm/rl1/relation_reference.py',BASE/'paired_diagnostic_20261019_v1/paired.py',
                 BASE/'paired_diagnostic_20261019_v1/live.py',BASE/'selection.py',BASE/'adapters.py',
                 BASE/'outer_format_v1_20261015/deepseek_access.py',BASE/'outer_format_v1_20261015/outer_format_v1.py',
                 PROJECT/'src/metacom_pm/rl1/judge_completion.py',PROJECT/'src/metacom_pm/rl1/judge_indexed.py',
                 alignment_path,BASE/'relation_reference_authorization_20261021_v1/REFERENCE_REVIEW_COMPLETED.json'):
        immutable[str(path)]=r.sha(path)
    for path in PREP.rglob('*'):
        if path.is_file():immutable[str(path)]=r.sha(path)
    expected=dict(study=t.VERSION,baseline_cumulative=253,new_request_limit=32,cumulative_cap=285,capacity=349,
       stage_cap_usd='2',trial_cap_usd='3.15',shared_cap_usd='20',old_stops_released=False,reward_eligible=False,
       diagnostic_policy=policy,official_research_payload_authorized=True,relation_reference_outbound_authorized=True,
       context_task_reference_outbound_authorized=True,analyst_card_diagnostic_use_not_gold_authorized=True,
       common_task_policy_version_authorized=True,proposed_semantic_revision_count=4,
       credential_process_read_authorized=True,management_requests={'models':1,'user/balance':1},
       natural_updates_authorized=False,no_automatic_retries=True,task_interface_version=t.INTERFACE)
    config=dict(old['config'],wrapper='original two-message transport; both arms same task policy and relation data; only B adds shared context task data')
    protocol=dict(version=t.VERSION,status='PREPARED_NOT_AUTHORIZED',created_at=datetime.now(ZoneInfo('Asia/Tokyo')).isoformat(),
      current_plan=str(PROJECT/'docs/PM_RL1_FEASIBLE_COMPLETION_PLAN_20260930_ZH.md'),
      run_dir=str(run_dir),activation_file=str(PROJECT/'docs/pm_rl1_completion_20260930_v2/task_reference_execution_amendment_20261021.json'),
      config=config,limits=limits,baseline_cumulative=253,historical_semantic_revisions=3,proposed_semantic_revision_count=4,
      new_prompt_identity_disclosed=True,policy_text_reused_from=str(alignment_path),
      prompt_change='new shared composition of rev2 + exact previous task-alignment section; no q/m scale or reward changes',
      context_card_intervention='data/materialization only on top of common aligned policy; both arms share reply-level relations',
      schedule=schedule,statistics=stats,resource_pairs=old['resource_pairs'],diagnostic_policy=policy,analysis_rules=analysis,
      input_file=str(PREP/'inputs_private.json'),task_cards_sha256=r.sha(PREP/'task_cards.json'),
      reference_bundle_sha256=r.sha(PREP/'references.json'),approval_required=expected,immutable_files=immutable,
      historical_started_hashes=snapshots,old_stop_hashes=stops,financial_baseline=fin,
      public_price_table_identity=old['public_price_table_identity'],judge_python=old['judge_python'],final_interface=old['final_interface'],
      training_cache_unchanged=True,old_results_invalidated=False,new_human_review_requested=False)
    protocol['identity']=r.digest(protocol);save('protocol.json',protocol)
    save('APPROVAL_REQUIRED.json',dict(status='PENDING',protocol_identity=protocol['identity'],**expected,
        researcher_authorization_record=None,researcher_record_sha256=None))
    save('PROPOSED_AMENDMENT.json',dict(status='PROPOSED RESEARCH CHANGE — NOT AUTHORIZED',applied=False,
        protocol_identity=protocol['identity'],capacity=349,current_capacity=317,stage_scoring=[253,285],
        common_task_policy_recomposition=True,proposed_semantic_revision_count=4,trial_cap_unchanged='3.15',shared_cap_unchanged='20',
        old_results_invalidated=False,old_stops_released=False,paper_scope_change=False,approval_identity=None))
    save('preparation_check.json',dict(protocol_identity=protocol['identity'],planned_requests=32,payload_count=24,shared_context_cards=5,
       longest_serialized_message_bytes=max(v['serialized_messages_utf8_bytes'] for v in screens.values()),
       complete_user_and_schema_equal_between_arms=True,reply_reference_equal_between_arms=True,
       new_calls=0,new_generation=0,natural_updates=0,credentials_read=False,account_queries=0))
    print(json.dumps(dict(prepared=str(PREP),protocol_identity=protocol['identity'],calls=32,cumulative_cap=285,
       estimate_usd=str(mean*32),tail_headroom_usd=str(effective-native)),ensure_ascii=False))


if __name__=='__main__':main()
