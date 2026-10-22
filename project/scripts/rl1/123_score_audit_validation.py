#!/usr/bin/env python3
"""Prepare/check the fixed eight-audit diagnostic; live requires specific approval.

Uses paired_dependencies.run, existing transport, native reserve, shared budget,
credential scope and account-query receipts. Does not create approval/activation.
"""
import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
from decimal import Decimal
import fcntl
import importlib.util
import json
from pathlib import Path
import os
import sys
import time

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT/'src'))
from metacom_pm.rl1 import score_audit_validation as v, paired_dependencies as d
from metacom_pm.rl1 import relation_reference as r
spec=importlib.util.spec_from_file_location('existing_feedback_entry', PROJECT/'scripts/rl1/119_run_feedback_validation.py')
existing=importlib.util.module_from_spec(spec);spec.loader.exec_module(existing)
BASE=existing.BASE
PREP=BASE/'score_audit_validation_preparation_20261022_v1'


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open('x', encoding='utf-8') as f:
        f.write(value if isinstance(value,str) else json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    path.chmod(0o600)


def prepare():
    if PREP.exists():return check()
    p=existing.engine();items={};scores={};materials=[];bound={}
    refs=BASE/'relation_reference_preparation_20261021_v2'
    refpr=r.read(refs/'protocol.json');refitems=r.read(refs/'inputs_private.json')
    refmaterials={x['material_id']:x for x in r.read(refs/'materials.json')}
    latest=BASE/'feedback_source_evidence_results_20261022_v2'
    latestpr=r.read(BASE/'feedback_source_evidence_preparation_20261022_v2/protocol.json')
    latestsummary=r.read(latest/'ALL_SLOTS.json');latestitems=r.read(latest/'ORIGINAL_INPUTS.json')
    contexts={x['context_id']:x for x in r.read(BASE/'feedback_source_evidence_preparation_20261022_v2/MATERIALS.json')['contexts']}
    summary=r.read(BASE/'relation_reference_results_20261021_v1/runtime_summary.json')
    for key in dict(v.ORDER):
        if key.startswith('V'):
            slot=next(x for x in latestsummary['slots'] if x['item_key']==key and x['component']=='joint')
            pr=latestpr;item=latestitems[key];context=contexts[key.split('_')[0]]
            meta=dict(owner=context['owner'],context_id=context['prefix_identity'],kind='natural')
        else:
            slot=next(x for x in summary['slots'] if x['material_id']==key and x['arm']=='A' and x['repetition']==1)
            pr=refpr;item=refitems[key];context=refmaterials[key]
            meta={k:context[k] for k in ('owner','context_id','kind')}
        result=slot['result'];sid=slot['slot_id'];root=Path(pr['run_dir'])
        rawresult=root/(sid+'.result.json');rawrequest=root/(sid+'.request.json')
        if r.read(rawresult)!=result or not result['technical_valid']:
            raise ValueError('selected preliminary score unavailable or changed')
        request=r.read(rawrequest);data=json.loads(request['messages'][1]['content'])
        if data['legal_evidence']!=item['evidence'] or data['reply']!=item['reply']:
            raise ValueError('original score not bound to exact full input')
        if r.digest(item['evidence'])!=slot['evidence_identity'] or r.digest(item['reply'])!=slot['reply_identity']:
            raise ValueError('original material identity changed')
        items[key]={k:item[k] for k in ('reply','evidence')};scores[key]=result
        for suffix in ('result.json','request.json','response.json','started.json'):
            path=root/(sid+'.'+suffix);bound[str(path)]=r.sha(path)
        materials.append(dict(item_key=key,**meta,preliminary_request=result['request_identity'],
            preliminary_protocol=pr['identity'],preliminary_slot=sid,reply_identity=slot['reply_identity'],
            evidence_identity=slot['evidence_identity'],old_result_path=str(rawresult),
            selection='purposeful diagnosis using exposed records, not random or independent validation',
            human_gold_for_whole_score=False))
    schedule=v.schedule(items,scores)
    rubricpath=BASE/'feedback_source_evidence_preparation_20261022_v2/JOINT_PROMPT_EN.txt'
    rubric=rubricpath.read_text()
    ledger=Path(latestpr['financial_baseline']['ledger_path']);cost=r.read(latest/'VALIDATION_AND_COST.json')
    if r.sha(ledger)!=cost['ledger_sha256']:raise ValueError('financial baseline changed')
    fin=dict(latestpr['financial_baseline'],ledger_sha256=r.sha(ledger),ledger_bytes=ledger.stat().st_size,
        trial_accounted_usd=cost['trial_accounted_usd'],shared_total_usd=cost['full_ledger_usd'],
        shared_followup_usd=cost['shared_followup_usd'],known_unsettled=0)
    starts={str(x):r.sha(x) for name in v.RUN_ROOTS for x in (BASE/name).rglob('*.started.json') if 'management' not in x.parts}
    if len(starts)+66!=302:raise ValueError('actual count differs from302')
    stops={str(x):r.sha(x) for name in v.RUN_ROOTS for x in (BASE/name).rglob('STOP.json')}
    approval=dict(study=v.VERSION,baseline_cumulative=302,new_request_limit=8,cumulative_cap=310,capacity=374,
        stage_cap_usd='1',trial_cap_usd='3.65',shared_cap_usd='20',diagnostic_policy=v.POLICY,
        official_research_payload_authorized=True,historical_same_reply_score_outbound_authorized=True,
        frozen_rubric_reference_authorized=True,manual_reference_outbound_authorized=False,
        credential_process_read_authorized=True,management_requests={'models':1,'user/balance':1},
        new_generation_authorized=False,natural_updates_authorized=False,old_stops_released=False,reward_eligible=False)
    for name,value in [('inputs_private.json',items),('historical_scores_private.json',scores),
                       ('MATERIALS.json',materials),('SCHEDULE.json',schedule),('FROZEN_RUBRIC_EN.txt',rubric)]:
        save(PREP/name,value)
    immutable=latestpr['immutable_files']|bound
    for path in [Path(__file__), PROJECT/'src/metacom_pm/rl1/score_audit_validation.py',
                 PROJECT/'src/metacom_pm/rl1/feedback_score_audit.py',PROJECT/'tests/test_rl1_score_audit_validation.py',
                 rubricpath, refs/'protocol.json',refs/'inputs_private.json',refs/'materials.json']:
        immutable[str(path)]=r.sha(path)
    for name in ('inputs_private.json','historical_scores_private.json','MATERIALS.json','SCHEDULE.json','FROZEN_RUBRIC_EN.txt'):
        immutable[str(PREP/name)]=r.sha(PREP/name)
    pr=dict(version=v.VERSION,status='PENDING_NOT_AUTHORIZED',prepared_utc=datetime.now(timezone.utc).isoformat(),
        run_dir=str(BASE/'score_audit_validation_runs'/v.VERSION/'live'),
        activation_file=str(BASE/'score_audit_validation_authorization_20261022_v1/activation.json'),
        baseline_cumulative=302,config=latestpr['config'],schedule=schedule,
        input_version=v.INPUT_VERSION,interface=v.audit.INTERFACE,
        limits=dict(max_calls=8,cumulative_cap=310),capacity=374,active_capacity=369,financial_baseline=fin,
        public_price_table_identity=latestpr['public_price_table_identity'],
        approval_required=approval,immutable_files=immutable,historical_started_hashes=starts,old_stop_hashes=stops,
        policy=v.POLICY,statistics=dict(replies=6,contexts=5,owners=4,repeated_items=2,independent_validation=0),
        numeric_rescoring=False,within_output_trigger_comparison=True,training_authorized=False)
    pr['identity']=r.digest(pr);save(PREP/'protocol.json',pr)
    save(PREP/'PENDING_EXECUTION_SCOPE.json',dict(status='PENDING',protocol_identity=pr['identity'],**approval))
    screens=[]
    for slot in schedule:
        messages,schema=v.payload(slot,items[slot['item_key']],scores,p,rubric)
        screen=p.input_guard(messages);screens.append(dict(position=slot['position'],**screen))
        save(PREP/'outbound_private'/f'{slot["position"]:02d}.json',dict(slot=slot,messages=messages,schema=schema,
             messages_identity=r.digest(messages),input_screen=screen,status='PREPARED_NOT_SENT'))
    historical_audits=[s['result'] for s in latestsummary['slots'] if s['component']=='audit' and s.get('result')]
    mean=sum(Decimal(x['financial']['accounted_upper_usd']) for x in historical_audits)/8
    output_mean=sum(x['usage']['completion_tokens'] for x in historical_audits)/8
    conservative_typical=sum((Decimal(s['serialized_messages_utf8_bytes']+8192)*Decimal('.3')/1000000
                             +Decimal(str(output_mean))*Decimal('1.2')/1000000 for s in screens),Decimal(0))
    budget=dict(phase_cap_usd='1',native_single_reserve_usd='.786432',trial_cap_usd='3.65',shared_cap_usd='20',
        phase_start_trial_usd=cost['trial_accounted_usd'],trial_max_if_fully_spent=str(Decimal(cost['trial_accounted_usd'])+1),
        historical_audit_mean_usd=str(mean),eight_at_old_mean_usd=str(mean*8),
        utf8_input_bound_plus_old_mean_output_scenario_usd=str(conservative_typical),
        not_a_probability_interval=True,no_exact_provider_tokenizer=True,
        maximum_spend_before_next_request_usd='.213568',
        average_first_seven_for_eighth_request_usd=str(Decimal('.213568')/7),
        sequential_unsettled_max_usd='.786432',all_eight_native_worst_sum_usd='6.291456',
        enough_for_eight_not_guaranteed=True,old_capacity_after_eight=59,proposed_capacity=374,
        proposed_capacity_after_eight=64,capacity_rationale='310+59 acceptance+4 recovery+1 margin; future calls NOT authorized',
        final_acceptance_not_authorized_or_guaranteed_by_capacity=True,new_generator_or_training_calls=0)
    save(PREP/'BUDGET.json',budget);return check()


def load(prep=PREP):
    pr=r.read(prep/'protocol.json')
    if r.digest({k:x for k,x in pr.items() if k!='identity'})!=pr['identity']:raise ValueError('protocol changed')
    for path,h in pr['immutable_files'].items():
        if r.sha(path)!=h:raise ValueError('frozen inputs/code changed')
    items=r.read(prep/'inputs_private.json');scores=r.read(prep/'historical_scores_private.json')
    if pr['schedule']!=v.schedule(items,scores):raise ValueError('planned repetition/slot binding changed')
    return pr,items,scores,(prep/'FROZEN_RUBRIC_EN.txt').read_text()


def check(prep=PREP):
    pr,items,scores,rubric=load(prep);p=existing.engine();v.historical_guard(pr,BASE)
    screens=[p.input_guard(v.payload(s,items[s['item_key']],scores,p,rubric)[0]) for s in pr['schedule']]
    return dict(status='PREPARED_NOT_AUTHORIZED',protocol_identity=pr['identity'],planned_calls=8,
        baseline=302,cumulative_cap=310,active_capacity=369,proposed_capacity=374,inputs_checked=len(screens),credential_reads=0,
        account_queries=0,new_calls=0,natural_updates=0)


def launch(approval_path,prep=PREP):
    pr,items,scores,rubric=load(prep);auth=r.read(approval_path);v.require_approval(pr,auth)
    p=existing.engine();s=p.s
    from deepseek_access import read_key,credential_scope,management_once,visible_paid_writers
    from adapters import DeepSeekTransport
    from live import public_service_check
    root=Path(pr['run_dir']);root.mkdir(parents=True,exist_ok=True,mode=0o700)
    fin=pr['financial_baseline'];ledger=Path(fin['ledger_path']);phase='locks/history'
    try:
        with ExitStack() as stack:
            for path in [BASE/'live_runs/.pool.lock',ledger.with_suffix('.lock')]+[BASE/name/'.launch.lock' for name in v.RUN_ROOTS if name!='live_runs']:
                path.parent.mkdir(exist_ok=True);lock=stack.enter_context(path.open('a'));fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            v.historical_guard(pr,BASE);starts,results=p.replay(root,pr);d.verify_receipts(p,root,pr,starts,results)
            if (root/'CLOSED.json').exists() or (root/'STOP.json').exists():return v.summary(pr,root,p,scores)
            reason=v.old.stop(pr,starts,results)
            if reason:
                d.save(p,root/'STOP.json',dict(reason=reason,automatic_retry=False));return v.summary(pr,root,p,scores)
            opening=existing.ledger_prefix(pr,ledger)
            budget=p.DiagnosticBudget(ledger,trial=fin['financial_trial_identity'],study=v.VERSION,
                stage_cap=s.nanodollars('1'),trial_cap=s.nanodollars('3.65'),shared_cap=s.nanodollars(20),
                baseline=s.nanodollars('1.50724291'),opening=s.nanodollars('.03079930'))
            def guard():
                load(prep);v.historical_guard(pr,BASE);v.require_approval(pr,r.read(approval_path))
                if r.read(approval_path)!=auth:raise ValueError('approval changed')
                current=ledger.read_bytes()
                if not current.startswith(opening):raise ValueError('financial prefix changed')
                ids={x['slot_id'] for x in pr['schedule']}
                if any(json.loads(line).get('reservation_id') not in ids for line in current[len(opening):].decode().splitlines()):raise ValueError('foreign paid writer')
                if visible_paid_writers():raise ValueError('concurrent paid writer')
            guard();total,trial,reserved,settled=budget._totals(budget.events())
            if set(reserved)-set(settled):raise ValueError('unresolved liability')
            if {k for k,z in reserved.items() if z.get('binding',{}).get('study')==v.VERSION}!=set(starts):raise ValueError('started/reservation mismatch')
            if budget.stage_total(reserved,settled)+p.RESERVE>budget.stage_cap or trial+p.RESERVE>budget.trial_cap or total-budget.baseline+p.RESERVE>budget.shared_cap:raise ValueError('native headroom insufficient')
            phase='public and account preflight';mg=root/'management';preflight=mg/'preflight.json'
            if preflight.exists():
                prior=r.read(preflight)
                if prior['protocol_identity']!=pr['identity'] or prior['approval_identity']!=r.digest(auth):raise ValueError('preflight binding changed')
                for path,h in prior['management_hashes'].items():
                    if r.sha(path)!=h:raise ValueError('management receipt changed')
                available=Decimal(prior['available_tariff_equivalent_usd'])
                public_service_check(root/('public_resume_'+str(time.time_ns())),pr['public_price_table_identity'])
            else:
                if starts or mg.exists():raise ValueError('incomplete preflight; no repeated account queries')
                mg.mkdir(mode=0o700);public_service_check(mg,pr['public_price_table_identity']);available=None
            phase='authorized process credential read';key=read_key()
            with credential_scope(key):
                if available is None:
                    models=management_once(mg,'models',key)
                    model=next((x for x in models.get('body',{}).get('data',[]) if x.get('id')=='deepseek-flash'),{})
                    if models['status']!=200 or not model or ('name' in model and model['name'] not in ('DeepSeek-V4.1-Flash','DeepSeek-V4.1-Flash-1017')) or ('context_window' in model and model['context_window']!=1048576) or ('max_output_tokens' in model and model['max_output_tokens']!=393216):raise ValueError('service identity changed')
                    balance=management_once(mg,'user/balance',key)
                    if balance['status']!=200 or not balance.get('body',{}).get('is_available'):raise ValueError('account unavailable')
                    amounts={x['currency']:Decimal(x['total_balance']) for x in balance['body']['balance_infos']}
                    available=amounts.get('USD',Decimal(0))+amounts.get('CNY',Decimal(0))*Decimal('.15')
                    if available<Decimal('.786432'):raise ValueError('balance headroom insufficient')
                    d.save(p,preflight,dict(protocol_identity=pr['identity'],approval_identity=r.digest(auth),
                        available_tariff_equivalent_usd=str(available),opening_trial_usd=fin['trial_accounted_usd'],
                        tariff_basis='existing USD/CNY price ratio, not FX',account_wide_exclusivity_verified=False,
                        management_hashes={str(x):r.sha(x) for x in mg.rglob('*') if x.is_file()}))
                budget.account_opening=s.nanodollars(available);budget.opening_trial=s.nanodollars(fin['trial_accounted_usd'])
                phase='fixed audit dispatch'
                result=d.run(p,pr,items,root,DeepSeekTransport(pr['config']),budget,mode='live',auth=auth,
                    runtime=v.runtime(pr,scores,p,rubric),before_dispatch=guard,global_count=lambda:v.historical_guard(pr,BASE))
            del key;return result
    except Exception as exc:
        receipt=dict(phase=phase,reason='guard/launch failure; sensitive exception suppressed',error_type=type(exc).__name__,automatic_retry=False)
        d.save(p,root/('launch_failure_'+str(time.time_ns())+'.json'),receipt)
        if not (root/'STOP.json').exists():d.save(p,root/'STOP.json',receipt)
        raise ValueError('Stopped; original receipts retained; no automatic retry') from None


if __name__=='__main__':
    os.umask(0o077);ap=argparse.ArgumentParser();g=ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--prepare',action='store_true');g.add_argument('--check',action='store_true')
    g.add_argument('--report',action='store_true');g.add_argument('--live',action='store_true')
    ap.add_argument('--approval',type=Path);a=ap.parse_args()
    if a.prepare:out=prepare()
    elif a.check:out=check()
    elif a.report:
        pr,_,scores,_=load();out=v.summary(pr,pr['run_dir'],existing.engine(),scores)
    else:
        if not a.approval:raise SystemExit('explicit scoped approval file required')
        out=launch(a.approval)
    print(json.dumps(out,ensure_ascii=False,indent=2))
