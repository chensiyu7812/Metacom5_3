#!/usr/bin/env python3
"""Fixed six-slot delivery continuation. Preparation is offline; live needs approval.

Reuses the original paired dispatcher, atomic shared budget and account helpers.
No JSON repairs, retries, extra prompts, local generation, or optimizer updates.
"""
import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
from decimal import Decimal
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.rl1 import strict_audit_delivery as t, relation_reference as r, paired_dependencies as d
spec=importlib.util.spec_from_file_location('old_score_entry',PROJECT/'scripts/rl1/123_score_audit_validation.py')
old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
BASE=old.BASE;PREP=BASE/'score_audit_strict_preparation_20261022_v1'


def save(path,value):old.save(path,value)


def prepare():
    if (PREP/'protocol.json').exists():return check()
    prev,items,scores,rubric=old.load();p=old.existing.engine();root=Path(prev['run_dir'])
    started,results=p.replay(root,prev);d.verify_receipts(p,root,prev,started,results);t.prior.historical_guard(prev,BASE)
    if len(started)!=2 or len(results)!=2 or not (root/'STOP.json').exists():raise ValueError('actual prior stage differs')
    schedule=t.remaining_schedule(prev['schedule'],started)
    if [s['position'] for s in schedule]!=list(range(3,9)):raise ValueError('remaining fixed slots changed')
    cost=r.read(BASE/'score_audit_validation_results_20261022_v1/VALIDATION_AND_COST.json')
    ledger=Path(cost['ledger_path'])
    if r.sha(ledger)!=cost['ledger_sha256'] or cost['known_unsettled_usd']!='0':raise ValueError('current ledger differs')
    fin=dict(prev['financial_baseline'],ledger_sha256=r.sha(ledger),ledger_bytes=ledger.stat().st_size,
        trial_accounted_usd=cost['trial_accounted_usd'],shared_total_usd=cost['full_ledger_usd'],shared_followup_usd=cost['shared_followup_usd'])
    approval=dict(study=t.VERSION,new_request_limit=6,baseline_cumulative=304,cumulative_cap=310,capacity=374,
        original_phase_max_calls=8,stage_cap_usd='1',stage_includes_prior_spend_usd='.0548997',
        trial_cap_usd='3.65',shared_cap_usd='20',endpoint=t.ENDPOINT,delivery=t.DELIVERY,
        strict_tool_arguments_authorized=True,tool_choice='auto',thinking='enabled/high',
        execution_of_tools_authorized=False,extra_tool_result_calls=0,
        exact_same_source_and_preliminary_score_outbound=True,human_reference_outbound=False,
        credential_process_read_authorized=True,management_requests={'models':1,'user/balance':1},
        old_stops_released=False,old_started_retried=False,diagnostic_policy=t.prior.POLICY,
        numeric_rescoring=False,natural_updates=0,reward_eligible=False)
    immutable=dict(prev['immutable_files'])
    for f in [old.PREP/'protocol.json',Path(__file__),PROJECT/'src/metacom_pm/rl1/strict_audit_delivery.py',
              PROJECT/'tests/test_rl1_strict_audit_delivery.py',BASE/'score_audit_validation_results_20261022_v1/VALIDATION_AND_COST.json']:
        immutable[str(f)]=r.sha(f)
    for f in root.rglob('*'):
        if f.is_file() and not f.name.startswith('.'):immutable[str(f)]=r.sha(f)
    starts={str(f):r.sha(f) for name in t.prior.RUN_ROOTS for f in (BASE/name).rglob('*.started.json') if 'management' not in f.parts}
    if len(starts)+66!=304:raise ValueError('real count changed')
    stops={str(f):r.sha(f) for name in t.prior.RUN_ROOTS for f in (BASE/name).rglob('STOP.json')}
    pr=dict(version=t.VERSION,status='PREPARED_NOT_AUTHORIZED',prepared_utc=datetime.now(timezone.utc).isoformat(),
        prior_protocol_path=str(old.PREP/'protocol.json'),prior_protocol_identity=prev['identity'],
        prior_run=str(root),inherited_started_ids=list(started),full_schedule=prev['schedule'],schedule=schedule,
        run_dir=str(BASE/'score_audit_validation_runs'/t.VERSION/'live'),
        activation_file=str(BASE/'score_audit_strict_authorization_20261022_v1/activation.json'),
        baseline_cumulative=304,limits=dict(max_calls=6,cumulative_cap=310),capacity=374,
        config=dict(prev['config'],endpoint=t.ENDPOINT,response_format='strict_tool_arguments',delivery=t.DELIVERY),
        financial_baseline=fin,public_price_table_identity=prev['public_price_table_identity'],
        approval_required=approval,immutable_files=immutable,historical_started_hashes=starts,old_stop_hashes=stops,
        input_origin=str(old.PREP),prior_spend_usd='.0548997',statistics='development only; cross-delivery repeats are not same-configuration reliability',
        no_same_configuration_complete_repeat_claim=True)
    proxy=t.engine_proxy(p,pr,items,scores,rubric);screens=[]
    for slot in schedule:
        msgs,schema=t.payload(slot,items[slot['item_key']],scores,p,rubric)
        projected,projection=t.server_schema(schema);screen=proxy.input_guard(msgs);screens.append(screen)
        path=PREP/'outbound_private'/f'{slot["position"]:02d}.json'
        save(path,dict(slot=slot,messages=msgs,local_schema=schema,server_schema=projected,
            schema_projection=projection,wire_body=proxy.api_body(pr['config'],msgs),screen=screen,status='PREPARED_NOT_SENT'))
        immutable[str(path)]=r.sha(path)
    pr['identity']=r.digest(pr);save(PREP/'protocol.json',pr)
    save(PREP/'PENDING_EXECUTION_SCOPE.json',dict(status='PENDING',protocol_identity=pr['identity'],**approval))
    save(PREP/'PROPOSED_ACTIVATION_NOT_APPLIED.json',dict(applied=False,protocol_identity=pr['identity'],
        changes=['Beta strict tool-argument delivery for unstarted original slots only'],new_semantic_revision=False,
        capacity_increase=0,money_increase=0,old_stop_preserved=True))
    mean=Decimal(cost['accounted_upper_usd'])/2
    save(PREP/'BUDGET.json',dict(stage_including_old_usd='1',old_spend_usd='.0548997',remaining_stage_usd='.9451003',
        single_reserve_usd='.786432',max_new_spend_before_next_request_usd='.1586683',
        first_five_new_mean_limit_for_sixth_usd=str(Decimal('.1586683')/5),
        six_at_old_two_call_mean_usd=str(mean*6),not_a_confidence_interval=True,tool_mode_cost_unmeasured=True,
        trial_accounted_usd=cost['trial_accounted_usd'],trial_cap_usd='3.65',shared_cap_usd='20',
        native_screen=screens,no_more_than_six=True,failures_count=True,remaining_not_guaranteed=True,
        full_research_not_funded_by_this_scope=True))
    return check()


def history(pr):
    root=Path(pr['run_dir']).resolve()
    all_starts={str(f):r.sha(f) for name in t.prior.RUN_ROOTS for f in (BASE/name).rglob('*.started.json')
        if 'management' not in f.parts and not f.resolve().is_relative_to(root)}
    if all_starts!=pr['historical_started_hashes'] or len(all_starts)+66!=304:raise ValueError('cross-version attempt history changed')
    for path,h in pr['old_stop_hashes'].items():
        if r.sha(path)!=h:raise ValueError('old STOP changed')
    return 304


def load():
    pr=r.read(PREP/'protocol.json')
    if r.digest({k:v for k,v in pr.items() if k!='identity'})!=pr['identity']:raise ValueError('protocol changed')
    for path,h in pr['immutable_files'].items():
        if r.sha(path)!=h:raise ValueError('frozen code/input/history changed')
    prev,items,scores,rubric=old.load();p=old.existing.engine()
    starts,results=p.replay(pr['prior_run'],prev);d.verify_receipts(p,Path(pr['prior_run']),prev,starts,results)
    if t.remaining_schedule(prev['schedule'],starts)!=pr['schedule']:raise ValueError('original slot identity changed')
    history(pr);return pr,items,scores,rubric,p,t.engine_proxy(p,pr,items,scores,rubric)


def check():
    pr,items,scores,rubric,p,proxy=load()
    screens=[proxy.input_guard(t.payload(s,items[s['item_key']],scores,p,rubric)[0]) for s in pr['schedule']]
    return dict(status='PREPARED_NOT_AUTHORIZED',protocol_identity=pr['identity'],remaining_original_slots=6,
        baseline=304,cumulative_cap=310,capacity=374,source_evidence_preserved=True,old_failed_unchanged=True,
        complete_wire_inputs_checked=len(screens),actual_calls=0,credential_reads=0,account_queries=0,trained=0)


def summary(pr,proxy,scores):
    current=t.prior.summary(pr,pr['run_dir'],proxy,scores)
    previous=r.read(pr['prior_protocol_path'])
    inherited=t.prior.summary(previous,pr['prior_run'],old.existing.engine(),scores)
    old_rows={s['slot_id']:dict(s,delivery='original_message_final') for s in inherited['slots'] if s['result']}
    new_rows={s['slot_id']:dict(s,delivery=t.DELIVERY) for s in current['slots']}
    current['all_original_slots']=[(old_rows|new_rows)[s['slot_id']] for s in pr['full_schedule']]
    current.update(study=t.VERSION,delivery=t.DELIVERY,old_attempts=2,full_plan=8,
        earlier_valid=1,earlier_failure=1,old_stops_preserved=True,mixed_delivery_repeats_not_same_configuration=True)
    return current


def launch(approval_path):
    pr,items,scores,rubric,p,proxy=load();auth=r.read(approval_path);t.require_approval(pr,auth)
    from deepseek_access import read_key,credential_scope,management_once,visible_paid_writers
    from live import public_service_check
    s=p.s;root=Path(pr['run_dir']);root.mkdir(parents=True,exist_ok=True,mode=0o700)
    fin=pr['financial_baseline'];ledger=Path(fin['ledger_path']);phase='history/locks'
    try:
        with ExitStack() as stack:
            for lockpath in [BASE/'live_runs/.pool.lock',ledger.with_suffix('.lock')]+[BASE/name/'.launch.lock' for name in t.prior.RUN_ROOTS if name!='live_runs']:
                lockpath.parent.mkdir(exist_ok=True);lock=stack.enter_context(lockpath.open('a'));fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            history(pr);starts,results=proxy.replay(root,pr);d.verify_receipts(proxy,root,pr,starts,results)
            if (root/'STOP.json').exists() or (root/'CLOSED.json').exists():return summary(pr,proxy,scores)
            if t.prior.old.stop(pr,starts,results):raise ValueError('started incomplete/failed; never retry')
            opening=old.existing.ledger_prefix(pr,ledger)
            budget=t.budget_class(p)(ledger,trial=fin['financial_trial_identity'],study=t.VERSION,
                stage_cap=s.nanodollars(1),trial_cap=s.nanodollars('3.65'),shared_cap=s.nanodollars(20),
                baseline=s.nanodollars('1.50724291'),opening=s.nanodollars('.03079930'))
            def guard():
                load();history(pr);t.require_approval(pr,r.read(approval_path))
                if r.read(approval_path)!=auth:raise ValueError('authorization changed')
                current=ledger.read_bytes()
                if not current.startswith(opening):raise ValueError('ledger prefix changed')
                ids={x['slot_id'] for x in pr['schedule']}
                if any(json.loads(line).get('reservation_id') not in ids for line in current[len(opening):].decode().splitlines()):raise ValueError('foreign paid writer')
                if visible_paid_writers():raise ValueError('visible concurrent paid writer')
            guard();total,trial,reserved,settled=budget._totals(budget.events())
            if set(reserved)-set(settled):raise ValueError('unresolved liability')
            if {k for k,z in reserved.items() if z.get('binding',{}).get('study')==t.VERSION}!=set(starts):raise ValueError('reservation mismatch')
            if budget.stage_total(reserved,settled)+p.RESERVE>budget.stage_cap or trial+p.RESERVE>budget.trial_cap or total-budget.baseline+p.RESERVE>budget.shared_cap:raise ValueError('native headroom insufficient')
            mg=root/'management';preflight=mg/'preflight.json';phase='public/account preflight'
            if preflight.exists():
                prior=r.read(preflight)
                if prior['protocol_identity']!=pr['identity'] or prior['approval_identity']!=r.digest(auth):raise ValueError('preflight changed')
                for path,h in prior['management_hashes'].items():
                    if r.sha(path)!=h:raise ValueError('management receipt changed')
                available=Decimal(prior['available_tariff_equivalent_usd'])
                public_service_check(root/('public_resume_'+str(time.time_ns())),pr['public_price_table_identity'])
            else:
                if starts or mg.exists():raise ValueError('partial preflight; no repeated management requests')
                mg.mkdir(mode=0o700);public_service_check(mg,pr['public_price_table_identity']);available=None
            phase='authorized credential';key=read_key()
            with credential_scope(key):
                if available is None:
                    models=management_once(mg,'models',key)
                    model=next((x for x in models.get('body',{}).get('data',[]) if x.get('id')=='deepseek-flash'),{})
                    if models['status']!=200 or not model or ('name' in model and model['name'] not in ('DeepSeek-V4.1-Flash','DeepSeek-V4.1-Flash-1017')) or ('context_window' in model and model['context_window']!=1048576) or ('max_output_tokens' in model and model['max_output_tokens']!=393216):raise ValueError('service changed')
                    balance=management_once(mg,'user/balance',key)
                    if balance['status']!=200 or not balance.get('body',{}).get('is_available'):raise ValueError('account unavailable')
                    amounts={x['currency']:Decimal(x['total_balance']) for x in balance['body']['balance_infos']}
                    available=amounts.get('USD',Decimal(0))+amounts.get('CNY',Decimal(0))*Decimal('.15')
                    if available<Decimal('.786432'):raise ValueError('account headroom insufficient')
                    d.save(p,preflight,dict(protocol_identity=pr['identity'],approval_identity=r.digest(auth),
                        available_tariff_equivalent_usd=str(available),opening_trial_usd=fin['trial_accounted_usd'],
                        tariff_basis='existing USD/CNY tariff ratio, not FX',account_wide_exclusivity_verified=False,
                        management_hashes={str(f):r.sha(f) for f in mg.rglob('*') if f.is_file()}))
                budget.account_opening=s.nanodollars(available);budget.opening_trial=s.nanodollars(fin['trial_accounted_usd'])
                phase='fixed six original slots'
                rt=t.runtime(pr,items,scores,p,rubric,proxy);rt['summarize']=lambda pr,root,p:summary(pr,proxy,scores)
                out=d.run(proxy,pr,items,root,t.Transport(pr['config'],proxy),budget,mode='live',auth=auth,runtime=rt,
                    before_dispatch=guard,global_count=lambda:history(pr))
            del key;return out
    except Exception as exc:
        failure=dict(phase=phase,reason='guard/delivery failure; sensitive exception suppressed',error_type=type(exc).__name__,automatic_retry=False)
        d.save(p,root/('launch_failure_'+str(time.time_ns())+'.json'),failure)
        if not (root/'STOP.json').exists():d.save(p,root/'STOP.json',failure)
        raise ValueError('Stopped; no retry or fallback; original receipts retained') from None


if __name__=='__main__':
    os.umask(0o077);ap=argparse.ArgumentParser();g=ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--prepare',action='store_true');g.add_argument('--check',action='store_true')
    g.add_argument('--report',action='store_true');g.add_argument('--live',action='store_true')
    ap.add_argument('--approval',type=Path);a=ap.parse_args()
    if a.prepare:out=prepare()
    elif a.check:out=check()
    elif a.report:
        pr,_,scores,_,_,proxy=load();out=summary(pr,proxy,scores)
    else:
        if not a.approval:raise SystemExit('specific Beta continuation approval required')
        out=launch(a.approval)
    print(json.dumps(out,ensure_ascii=False,indent=2))
