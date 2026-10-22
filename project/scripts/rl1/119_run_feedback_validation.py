#!/usr/bin/env python3
"""Dependency adapter for the existing paired engine; offline unless --live.

This entry never creates approval/amendment records. Clean sealed boundaries can
resume; unresolved starts, technical STOPs and completed scopes cannot restart.
"""
import argparse
from contextlib import ExitStack
from decimal import Decimal
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
import time

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.rl1 import feedback_workflow as w, paired_dependencies as d, relation_reference as r
BASE=PROJECT/'outputs/pm_rl1/judge_selection_preparation_20261014_v1'
PREP=BASE/'feedback_validation_preparation_20261022_v2'


def engine():
    sys.path.insert(0,str(BASE/'paired_diagnostic_20261019_v1'))
    import paired
    return paired


def load(prep=PREP):
    pr=r.read(prep/'protocol.json')
    if r.digest({k:v for k,v in pr.items() if k!='identity'})!=pr['identity']:
        raise ValueError('protocol identity mismatch')
    for path,h in pr['immutable_files'].items():
        if r.sha(path)!=h:raise ValueError('frozen code/input changed')
    items=r.read(prep/'inputs_private.json');prompt=(prep/'JOINT_PROMPT_EN.txt').read_text()
    if w.schedule(r.read(pr['original_schedule'])['fixed'],items)!=pr['schedule']:
        raise ValueError('logical slot or ordering changed')
    for slot in pr['schedule']:
        item=items[slot['item_key']]
        if r.digest(item['reply'])!=slot['reply_identity'] or r.digest(item['evidence'])!=slot['evidence_identity']:
            raise ValueError('input binding changed')
    return pr,items,prompt


def check(prep=PREP):
    pr,items,prompt=load(prep);p=engine()
    count=w.historical_guard(pr,BASE)
    if r.sha(pr['financial_baseline']['ledger_path'])!=pr['financial_baseline']['ledger_sha256']:
        raise ValueError('ledger changed; reconcile before launch')
    screens=[]
    for slot in pr['schedule']:
        if slot['component']=='joint':
            messages,schema=w.payload(pr,slot,items[slot['item_key']],{},p,prompt)
            screens.append(p.input_guard(messages))
    return dict(status='OFFLINE_READY_NOT_AUTHORIZED',protocol_identity=pr['identity'],baseline=count,
        fixed_requests=16,conditional_slots=8,max_conditional_requests=4,max_requests=20,cumulative_cap=305,
        all_logical_slots=24,initial_input_screens=screens,dynamic_dependency_input_screen='at dispatch; never truncate',
        credentials_read=False,account_queries=0,new_model_calls=0,natural_updates=0,
        old_stops_released=False,reward_eligible=False)


def ledger_prefix(pr,ledger):
    original=ledger.read_bytes()[:pr['financial_baseline']['ledger_bytes']]
    if hashlib.sha256(original).hexdigest()!=pr['financial_baseline']['ledger_sha256']:
        raise ValueError('old financial prefix changed')
    return original


def launch(approval_path,prep=PREP):
    pr,items,prompt=load(prep);auth=r.read(approval_path)
    w.require_approval(pr,auth)  # Before imports of credential services or live files.
    p=engine();s=p.s
    from deepseek_access import read_key,credential_scope,management_once,visible_paid_writers
    from adapters import DeepSeekTransport
    from live import public_service_check
    root=Path(pr['run_dir']);root.mkdir(parents=True,exist_ok=True,mode=0o700)
    ledger=Path(pr['financial_baseline']['ledger_path']);fin=pr['financial_baseline']
    phase='locks and immutable history'
    try:
        with ExitStack() as stack:
            paths=[BASE/'live_runs/.pool.lock',ledger.with_suffix('.lock')]+[
                BASE/name/'.launch.lock' for name in w.RUN_ROOTS if name!='live_runs']
            for path in paths:
                path.parent.mkdir(exist_ok=True)
                lock=stack.enter_context(path.open('a'));fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            w.historical_guard(pr,BASE)
            starts,results=p.replay(root,pr);d.verify_receipts(p,root,pr,starts,results)
            if (root/'STOP.json').exists() or (root/'CLOSED.json').exists():
                return w.summarize(pr,root,p)
            reason=w.stop(pr,starts,results)
            if reason:
                d.save(p,root/'STOP.json',dict(reason=reason,automatic_retry=False,timestamp=time.time()))
                return w.summarize(pr,root,p)
            phase='financial prefix and concurrent liabilities'
            original=ledger_prefix(pr,ledger)
            budget=p.DiagnosticBudget(ledger,trial=fin['financial_trial_identity'],study=w.VERSION,
                stage_cap=s.nanodollars('2'),trial_cap=s.nanodollars('3.65'),shared_cap=s.nanodollars(20),
                baseline=s.nanodollars('1.50724291'),opening=s.nanodollars('.03079930'))
            def guard():
                load(prep);w.historical_guard(pr,BASE)
                if r.read(approval_path)!=auth:raise ValueError('approval changed')
                w.require_approval(pr,auth)
                current=ledger.read_bytes()
                if not current.startswith(original):raise ValueError('ledger prefix changed')
                ids={x['slot_id'] for x in pr['schedule']}
                if any(json.loads(line).get('reservation_id') not in ids for line in current[len(original):].decode().splitlines()):
                    raise ValueError('foreign paid writer')
                if visible_paid_writers():raise ValueError('visible concurrent paid writer')
            guard()
            total,trial,reserved,settled=budget._totals(budget.events())
            if set(reserved)-set(settled):raise ValueError('unsettled liability; no request retry')
            own={k for k,v in reserved.items() if v.get('binding',{}).get('study')==w.VERSION}
            if own!=set(starts):raise ValueError('accounting/started identities differ')
            if (trial+p.RESERVE>budget.trial_cap or total-budget.baseline+p.RESERVE>budget.shared_cap
                    or budget.stage_total(reserved,settled)+p.RESERVE>budget.stage_cap):
                raise ValueError('native responsibility headroom insufficient')
            mg=root/'management';preflight=mg/'preflight.json'
            phase='public service and prior management receipts'
            if preflight.exists():
                prior=r.read(preflight)
                if prior['protocol_identity']!=pr['identity'] or prior['approval_identity']!=r.digest(auth):
                    raise ValueError('preflight binding changed')
                for path,h in prior['management_hashes'].items():
                    if r.sha(path)!=h:raise ValueError('management receipt changed')
                available=Decimal(prior['available_tariff_equivalent_usd'])
                # Price public verification remains read-only; do not repeat account requests.
                public_service_check(root/('public_resume_'+str(time.time_ns())),pr['public_price_table_identity'])
            else:
                if starts or mg.exists():raise ValueError('incomplete preflight; no management retry')
                mg.mkdir(mode=0o700)
                public_service_check(mg,pr['public_price_table_identity'])
                available=None
            phase='authorized process credential read'
            key=read_key()
            with credential_scope(key):
                if available is None:
                    phase='one official model-list request'
                    models=management_once(mg,'models',key)
                    if models['status']!=200:raise ValueError('model list failed')
                    model=next((x for x in models.get('body',{}).get('data',[]) if x.get('id')=='deepseek-flash'),{})
                    if (not model or ('name' in model and model['name'] not in ('DeepSeek-V4.1-Flash','DeepSeek-V4.1-Flash-1017'))
                            or ('context_window' in model and model['context_window']!=1048576)
                            or ('max_output_tokens' in model and model['max_output_tokens']!=393216)):
                        raise ValueError('official service identity drift')
                    phase='one official balance request'
                    balance=management_once(mg,'user/balance',key)
                    if balance['status']!=200 or not balance.get('body',{}).get('is_available'):raise ValueError('account unavailable')
                    amounts={x['currency']:Decimal(x['total_balance']) for x in balance['body']['balance_infos']}
                    available=amounts.get('USD',Decimal(0))+amounts.get('CNY',Decimal(0))*Decimal('.15')
                    if available<Decimal('.786432'):raise ValueError('account balance below native reserve')
                    d.save(p,preflight,dict(protocol_identity=pr['identity'],approval_identity=r.digest(auth),service=model,
                        available_tariff_equivalent_usd=str(available),opening_trial_usd=fin['trial_accounted_usd'],
                        tariff_basis='existing USD/CNY tariff ratio, not market FX',
                        visibility='shared ledger and visible local processes; no account-wide exclusivity guarantee',
                        management_hashes={str(x):r.sha(x) for x in mg.rglob('*') if x.is_file()}))
                budget.account_opening=s.nanodollars(available);budget.opening_trial=s.nanodollars(fin['trial_accounted_usd'])
                phase='guarded dependency dispatch'
                result=d.run(p,pr,items,root,DeepSeekTransport(pr['config']),budget,mode='live',auth=auth,
                    runtime=w.runtime(pr,p,prompt),before_dispatch=guard,global_count=lambda:w.historical_guard(pr,BASE))
            del key
            stamp=str(time.time_ns())
            d.save(p,root/('stage_report_'+stamp+'.json'),result)
            total,trial,reserved,settled=budget._totals(budget.events())
            d.save(p,root/('financial_report_'+stamp+'.json'),dict(trial_accounted_usd=s.usd(trial),
                stage_accounted_usd=s.usd(budget.stage_total(reserved,settled)),unsettled=[x for x in reserved if x not in settled],
                ledger_sha256=r.sha(ledger),original_prefix_preserved=ledger.read_bytes().startswith(original)))
            return result
    except Exception as exc:
        receipt=dict(reason='launch/guard failure; sensitive exception text suppressed',phase=phase,error_type=type(exc).__name__,
                     timestamp=time.time(),automatic_retry=False)
        d.save(p,root/('launch_failure_'+str(time.time_ns())+'.json'),receipt)
        if not (root/'STOP.json').exists():d.save(p,root/'STOP.json',receipt)
        raise ValueError('Stopped; immutable receipt retained; no automatic retry') from None


def main():
    os.umask(0o077)
    ap=argparse.ArgumentParser();g=ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--check',action='store_true');g.add_argument('--report',action='store_true');g.add_argument('--live',action='store_true')
    ap.add_argument('--prep',type=Path,default=PREP);ap.add_argument('--approval',type=Path);args=ap.parse_args()
    if args.check:out=check(args.prep)
    elif args.report:
        pr,*_=load(args.prep);p=engine();starts,results=p.replay(pr['run_dir'],pr)
        d.verify_receipts(p,Path(pr['run_dir']),pr,starts,results);out=w.summarize(pr,pr['run_dir'],p)
    else:
        if not args.approval:raise SystemExit('Explicit protocol-bound approval required')
        out=launch(args.approval,args.prep)
    print(json.dumps(out,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
