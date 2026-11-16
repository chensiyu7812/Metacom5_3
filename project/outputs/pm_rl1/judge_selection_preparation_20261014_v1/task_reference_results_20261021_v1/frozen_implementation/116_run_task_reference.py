#!/usr/bin/env python3
"""Thin stage adapter: reuse paired.run, transport, strict parser and shared ledger."""
import argparse
from contextlib import ExitStack
from decimal import Decimal
import fcntl
import json
import os
from pathlib import Path
import sys
import time

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT/'src'))
from metacom_pm.rl1 import task_reference as t
from metacom_pm.rl1 import relation_reference as r

BASE = PROJECT/'outputs/pm_rl1/judge_selection_preparation_20261014_v1'
PREP = BASE/'task_reference_preparation_20261021_v1'


def engine():
    sys.path.insert(0, str(BASE/'paired_diagnostic_20261019_v1'))
    import paired
    return paired


def load(prep=PREP):
    pr = r.read(prep/'protocol.json')
    if r.digest({k:v for k,v in pr.items() if k!='identity'}) != pr['identity']:
        raise ValueError('protocol identity mismatch')
    for path, expected in pr['immutable_files'].items():
        if r.sha(path)!=expected:
            raise ValueError('frozen data/code changed')
    p = engine()
    items=r.read(prep/'inputs_private.json');refs=r.read(prep/'references.json');cards=r.read(prep/'task_cards.json')
    prompt=(prep/'COMMON_PROMPT_EN.txt').read_text();payloads={};runtime_items={}
    for key, item in items.items():
        card=cards[r.digest(item['evidence'])]
        t.validate_card(item,card);r.validate_reference(item,refs[key],p)
        for arm in ('A','B'):
            k=key+'__'+arm;data=r.read(prep/'payloads'/(k+'.json'))
            t.validate_payload(item,refs[key],card,arm,prompt,data,p)
            payloads[k]=data;runtime_items[k]=dict(item,arm=arm)
    return pr,items,refs,cards,prompt,payloads,runtime_items


def check():
    pr,*_=load();count=t.historical_guard(pr,BASE)
    if r.sha(pr['financial_baseline']['ledger_path'])!=pr['financial_baseline']['ledger_sha256']:
        raise ValueError('financial baseline changed; reconcile before launch')
    return dict(status='OFFLINE_READY_NOT_AUTHORIZED',protocol_identity=pr['identity'],
        baseline=count,planned=len(pr['schedule']),new_calls=0,credentials_read=False,
        account_queries=0,new_generations=0,natural_updates=0,
        task_references='analyst-prepared; not independent gold; no fresh human answers required',
        proposed_capacity=pr['limits']['proposed_capacity'],active_capacity=317)


def launch(approval_path):
    pr,items,refs,cards,prompt,payloads,runtime_items=load()
    auth=r.read(approval_path)
    t.require_approval(pr,auth)  # Before credentials, management, locks or live mkdir.
    p=engine();s=p.s
    from deepseek_access import read_key,credential_scope,management_once,visible_paid_writers
    from adapters import DeepSeekTransport
    from live import public_service_check
    root=Path(pr['run_dir']);root.mkdir(parents=True,exist_ok=True,mode=0o700)
    ledger=Path(pr['financial_baseline']['ledger_path'])
    try:
        with ExitStack() as stack:
            lock_paths=[BASE/'live_runs/.pool.lock',ledger.with_suffix('.lock')]+[
                BASE/name/'.launch.lock' for name in t.RUN_ROOTS if name!='live_runs']
            for path in lock_paths:
                path.parent.mkdir(exist_ok=True)
                lock=stack.enter_context(path.open('a'));fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            t.historical_guard(pr,BASE)
            starts,_=p.replay(root,pr)
            if starts or (root/'STOP.json').exists() or (root/'CLOSED.json').exists():
                return dict(status='PRESERVED_NO_AUTOMATIC_RESTART',report=t.summarize(pr,root,253,p))
            fin=pr['financial_baseline']
            if r.sha(ledger)!=fin['ledger_sha256']:
                raise ValueError('shared ledger changed')
            original=ledger.read_bytes()
            if visible_paid_writers():raise ValueError('visible concurrent paid writer')
            budget=p.DiagnosticBudget(ledger,trial=fin['financial_trial_identity'],study=t.VERSION,
                stage_cap=s.nanodollars(pr['limits']['stage_usd']),trial_cap=s.nanodollars(pr['limits']['trial_usd']),
                shared_cap=s.nanodollars(20),baseline=s.nanodollars('1.50724291'),opening=s.nanodollars('.03079930'))
            total,trial,reserved,settled=budget._totals(budget.events())
            if set(reserved)-set(settled) or s.usd(trial)!=fin['trial_accounted_usd']:
                raise ValueError('unresolved liability or trial ledger drift')
            # Do not spend even one management allowance when native responsibility cannot fit.
            if (trial+p.RESERVE>budget.trial_cap or total-s.nanodollars('1.50724291')+p.RESERVE>budget.shared_cap
                    or p.RESERVE>budget.stage_cap):
                raise ValueError('insufficient native responsibility headroom')
            mg=root/'management';mg.mkdir(exist_ok=True)
            if list(mg.iterdir()):raise ValueError('prior management attempt; no retry')
            public_service_check(mg,pr['public_price_table_identity'])
            key=read_key()
            with credential_scope(key):
                models=management_once(mg,'models',key)
                if models['status']!=200:raise ValueError('model list failed')
                model=next((x for x in models.get('body',{}).get('data',[]) if x.get('id')=='deepseek-flash'),{})
                if (not model or ('name' in model and model['name'] not in ('DeepSeek-V4.1-Flash','DeepSeek-V4.1-Flash-1017'))
                        or ('context_window' in model and model['context_window']!=1048576)
                        or ('max_output_tokens' in model and model['max_output_tokens']!=393216)):
                    raise ValueError('official service identity drift')
                balance=management_once(mg,'user/balance',key)
                if balance['status']!=200 or not balance.get('body',{}).get('is_available'):
                    raise ValueError('account unavailable')
                amounts={x['currency']:Decimal(x['total_balance']) for x in balance['body']['balance_infos']}
                available=amounts.get('USD',Decimal(0))+amounts.get('CNY',Decimal(0))*Decimal('.15')
                budget.account_opening=s.nanodollars(available);budget.opening_trial=s.nanodollars(fin['trial_accounted_usd'])
                if budget.account_opening<p.RESERVE:raise ValueError('balance cannot cover native reserve')
                r.save_new(mg/'preflight.json',dict(protocol_identity=pr['identity'],approval_identity=r.digest(auth),
                    service=model,available_tariff_equivalent_usd=str(available),known_unsettled=0,
                    tariff_basis='existing USD/CNY tariff ratio, not market FX',
                    visibility='shared ledger and visible local writers; not guaranteed account-wide visibility'))
                def guard():
                    load();t.historical_guard(pr,BASE)
                    if r.read(approval_path)!=auth:raise ValueError('approval changed')
                    t.require_approval(pr,auth)
                    current=ledger.read_bytes()
                    if not current.startswith(original):raise ValueError('old ledger prefix changed')
                    ids={x['slot_id'] for x in pr['schedule']}
                    if any(json.loads(line).get('reservation_id') not in ids for line in current[len(original):].decode().splitlines()):
                        raise ValueError('foreign paid writer')
                    if visible_paid_writers():raise ValueError('visible concurrent paid writer')
                rt=t.runtime(pr,payloads,items,refs,cards,prompt,p,t.require_approval)
                result=p.run(pr,runtime_items,root,DeepSeekTransport(pr['config']),budget,mode='live',auth=auth,
                    before_dispatch=guard,global_count=lambda:t.historical_guard(pr,BASE),runtime=rt)
            del key
            r.save_new(root/'stage_result.json',result)
            total,trial,reserved,settled=budget._totals(budget.events())
            r.save_new(root/'financial_closeout.json',dict(trial_accounted_usd=s.usd(trial),
                stage_accounted_usd=s.usd(budget.stage_total(reserved,settled)),
                unsettled=[x for x in reserved if x not in settled],ledger_sha256=r.sha(ledger),
                original_prefix_preserved=ledger.read_bytes().startswith(original)))
            if result['started']==pr['limits']['max_calls'] and not result['stop']:
                r.save_new(root/'CLOSED.json',dict(status='COMPLETED_AUTHORIZED_SCOPE_EXHAUSTED',
                    protocol_identity=pr['identity'],started=result['started'],new_calls_authorized_remaining=0))
            return result
    except Exception as exc:
        receipt=dict(reason='launch/guard failure; sensitive exception details suppressed',
                     error_type=type(exc).__name__,timestamp=time.time(),automatic_retry=False)
        r.save_new(root/('launch_failure_'+str(time.time_ns())+'.json'),receipt)
        if not (root/'STOP.json').exists():r.save_new(root/'STOP.json',receipt)
        raise ValueError('Stopped; immutable receipt retained, no retry') from None


def main():
    os.umask(0o077)
    parser=argparse.ArgumentParser();g=parser.add_mutually_exclusive_group(required=True)
    g.add_argument('--check',action='store_true');g.add_argument('--report',action='store_true');g.add_argument('--live',action='store_true')
    parser.add_argument('--approval',type=Path);args=parser.parse_args()
    if args.check:out=check()
    elif args.report:
        pr,*_=load();out=t.summarize(pr,pr['run_dir'],t.historical_guard(pr,BASE),engine())
    else:
        if not args.approval:raise SystemExit('A new protocol-bound execution approval is required')
        out=launch(args.approval)
    print(json.dumps(out,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
