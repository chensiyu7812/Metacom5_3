#!/usr/bin/env python3
"""Continue only unstarted fixed slots using the existing paired dispatcher."""
import argparse
from contextlib import ExitStack
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
from metacom_pm.rl1 import feedback_source_evidence as c, feedback_workflow as w
from metacom_pm.rl1 import paired_dependencies as d, relation_reference as r
spec=importlib.util.spec_from_file_location('frozen_feedback_entry',PROJECT/'scripts/rl1/119_run_feedback_validation.py')
original=importlib.util.module_from_spec(spec);spec.loader.exec_module(original)
BASE=original.BASE
PREP=BASE/'feedback_source_evidence_preparation_20261022_v2'


def load(prep=PREP):
    pr=r.read(prep/'protocol.json')
    if r.digest({k:v for k,v in pr.items() if k!='identity'})!=pr['identity']:raise ValueError('protocol changed')
    for path,h in pr['immutable_files'].items():
        if r.sha(path)!=h:raise ValueError('frozen code/input changed')
    prior=r.read(pr['prior_protocol_path']);p=original.engine();starts,_=c.inherited(pr,p)
    if (prior['identity']!=pr['prior_protocol_identity'] or prior['schedule']!=pr['full_schedule']
            or pr['schedule']!=[x for x in prior['schedule'] if x['slot_id'] not in starts]):
        raise ValueError('unstarted fixed schedule changed')
    if pr['config']!=prior['config']:raise ValueError('model settings changed')
    items=r.read(prep/'inputs_private.json');prompt=(prep/'JOINT_PROMPT_EN.txt').read_text()
    for slot in pr['full_schedule']:
        item=items[slot['item_key']]
        if r.digest(item['reply'])!=slot['reply_identity'] or r.digest(item['evidence'])!=slot['evidence_identity']:
            raise ValueError('source/reply binding changed')
    return pr,items,prompt


def check(prep=PREP):
    pr,items,prompt=load(prep);p=original.engine();c.historical_guard(pr,BASE)
    screens=[]
    for slot in pr['schedule']:
        if slot['component']=='joint':
            messages,_=c.payload(pr,slot,items[slot['item_key']],{},p,prompt)
            screens.append(p.input_guard(messages))
    return dict(status='OFFLINE_CHECKED',protocol_identity=pr['identity'],baseline=291,max_additional=14,
        cumulative_cap=305,remaining_fixed=10,remaining_logical=18,stage_cap_includes_old_cost=True,
        input_screens=screens,account_queries=0,new_calls=0,old_stop_preserved=True)


def launch(approval_path,prep=PREP):
    pr,items,prompt=load(prep);auth=r.read(approval_path);c.require_approval(pr,auth)
    p=original.engine();s=p.s
    from deepseek_access import read_key,credential_scope,visible_paid_writers
    from adapters import DeepSeekTransport
    from live import public_service_check
    root=Path(pr['run_dir']);root.mkdir(parents=True,exist_ok=True,mode=0o700)
    ledger=Path(pr['financial_baseline']['ledger_path']);phase='locks and history'
    try:
        with ExitStack() as stack:
            for path in [BASE/'live_runs/.pool.lock',ledger.with_suffix('.lock')]+[
                    BASE/name/'.launch.lock' for name in w.RUN_ROOTS if name!='live_runs']:
                path.parent.mkdir(exist_ok=True);lock=stack.enter_context(path.open('a'))
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            c.historical_guard(pr,BASE)
            starts,results=p.replay(root,pr);d.verify_receipts(p,root,pr,starts,results)
            if (root/'STOP.json').exists() or (root/'CLOSED.json').exists():return c.summary(pr,root,p)
            reason=w.stop(pr,starts,results)
            if reason:
                d.save(p,root/'STOP.json',dict(reason=reason,automatic_retry=False));return c.summary(pr,root,p)
            phase='combined experiment accounting'
            opening=original.ledger_prefix(pr,ledger);fin=pr['financial_baseline']
            budget=c.budget_class(p)(ledger,trial=fin['financial_trial_identity'],study=c.VERSION,
                stage_cap=s.nanodollars(2),trial_cap=s.nanodollars('3.65'),shared_cap=s.nanodollars(20),
                baseline=s.nanodollars('1.50724291'),opening=s.nanodollars('.03079930'))
            def guard():
                load(prep);c.historical_guard(pr,BASE);c.require_approval(pr,r.read(approval_path))
                if r.read(approval_path)!=auth:raise ValueError('approval changed')
                current=ledger.read_bytes()
                if not current.startswith(opening):raise ValueError('financial prefix changed')
                ids={x['slot_id'] for x in pr['schedule']}
                if any(json.loads(x).get('reservation_id') not in ids for x in current[len(opening):].decode().splitlines()):
                    raise ValueError('foreign paid writer')
                if visible_paid_writers():raise ValueError('concurrent paid writer')
            guard();total,trial,reserved,settled=budget._totals(budget.events())
            if set(reserved)-set(settled):raise ValueError('unsettled responsibility')
            own={k for k,v in reserved.items() if v.get('binding',{}).get('study')==c.VERSION}
            if own!=set(starts):raise ValueError('started/accounting discrepancy')
            if (budget.stage_total(reserved,settled)+p.RESERVE>budget.stage_cap or trial+p.RESERVE>budget.trial_cap
                    or total-budget.baseline+p.RESERVE>budget.shared_cap):raise ValueError('insufficient responsibility headroom')
            phase='reuse original account receipts and check public service'
            prior=r.read(pr['prior_management_preflight'])
            for path,h in prior['management_hashes'].items():
                if r.sha(path)!=h:raise ValueError('original management receipt changed')
            budget.account_opening=s.nanodollars(Decimal(prior['available_tariff_equivalent_usd']))
            budget.opening_trial=s.nanodollars(prior['opening_trial_usd'])
            if trial-budget.opening_trial+p.RESERVE>budget.account_opening:raise ValueError('original balance headroom insufficient')
            public_service_check(root/('public_service_'+str(time.time_ns())),pr['public_price_table_identity'])
            inner=DeepSeekTransport(pr['config'])
            class BoundTransport:
                def send(self,messages,schema,*,request,raw_path):
                    raw=inner.send(messages,schema,request=request,raw_path=raw_path)
                    if raw.get('system_fingerprint')!=pr['inherited_fingerprint']:
                        d.save(p,root/(request['slot_id']+'.response.json'),raw)
                        raise ValueError('service fingerprint differs from original stage')
                    return raw
            phase='authorized credential and fixed continuation'
            key=read_key()
            with credential_scope(key):
                def after(slot,result):
                    print(json.dumps(dict(position=slot['position'],material=slot['material_id'],component=slot['component'],
                        technical_valid=result['technical_valid'],seconds=round(result['elapsed_seconds'],3)),ensure_ascii=False),flush=True)
                report=d.run(p,pr,items,root,BoundTransport(),budget,mode='live',runtime=c.runtime(pr,p,prompt),
                    auth=auth,before_dispatch=guard,global_count=lambda:c.historical_guard(pr,BASE),after_result=after)
            del key
            d.save(p,root/('stage_report_'+str(time.time_ns())+'.json'),report)
            return report
    except Exception as exc:
        receipt=dict(reason='continuation launch/guard failure; exception text suppressed',phase=phase,
            error_type=type(exc).__name__,automatic_retry=False,timestamp=time.time())
        d.save(p,root/('launch_failure_'+str(time.time_ns())+'.json'),receipt)
        if not (root/'STOP.json').exists():d.save(p,root/'STOP.json',receipt)
        raise ValueError('Stopped; original and new receipts retained; no automatic retry') from None


if __name__=='__main__':
    os.umask(0o077);ap=argparse.ArgumentParser();g=ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--check',action='store_true');g.add_argument('--report',action='store_true');g.add_argument('--live',action='store_true')
    ap.add_argument('--prep',type=Path,default=PREP);ap.add_argument('--approval',type=Path);args=ap.parse_args()
    if args.check:out=check(args.prep)
    elif args.report:
        pr,*_=load(args.prep);p=original.engine();out=c.summary(pr,pr['run_dir'],p)
    else:
        if not args.approval:raise SystemExit('protocol-bound continuation approval required')
        out=launch(args.approval,args.prep)
    print(json.dumps({k:v for k,v in out.items() if k not in ('slots','endpoints')},ensure_ascii=False,indent=2))
