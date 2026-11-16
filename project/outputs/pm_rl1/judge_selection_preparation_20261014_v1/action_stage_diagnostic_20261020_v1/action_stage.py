"""Approved 12-slot binding for the existing paired.run engine; no new transport."""
from pathlib import Path
import sys, json, time, fcntl, os
from decimal import Decimal

HERE=Path(__file__).resolve().parent
BASE=HERE.parent
sys.path.insert(0,str(BASE/'paired_diagnostic_20261019_v1'))
import paired as p
from paired import s
from adapters import DeepSeekTransport
from deepseek_access import read_key,credential_scope,management_once,visible_paid_writers
from live import public_service_check

STUDY='pmrl1-joint-action-stage-development-v1-20261020'
ROOT=BASE/'action_stage_runs'/STUDY/'live'
PROPOSAL=BASE/'continuation_20261020_v1/measurement_proposal'
LEDGER=s.REPO/'project/outputs/paper1_api_budget/cumulative_paid_api_budget.jsonl'

def load():
    protocol=s.read(HERE/'protocol.json')
    if protocol['identity']!=s.digest({k:v for k,v in protocol.items() if k!='identity'}):
        raise ValueError('protocol identity mismatch')
    for file,digest in protocol['immutable_files'].items():
        if s.sha(file)!=digest:raise ValueError('immutable input/code changed')
    return protocol,s.read(BASE/'paired_diagnostic_20261019_v1/package/items.json')

def approved(protocol,auth):
    required=dict(status='APPROVED',protocol_identity=protocol['identity'],study=STUDY,
        baseline_cumulative=144,new_request_limit=12,cumulative_cap=156,capacity=289,
        stage_cap_usd='1',trial_cap_usd='2',shared_cap_usd='20',
        semantic_revisions_previously_applied=1,additional_semantic_revision_authorized=1,
        credential_process_read_authorized=True,official_research_payload_authorized=True,
        management_requests={'models':1,'user/balance':1},old_stops_released=False,qualifies_reward=False)
    if any(auth.get(k)!=v for k,v in required.items()):raise ValueError('authorization scope mismatch')

def payload(item,component,first=None):
    if component!='joint' or first is not None:raise ValueError('joint-only stage')
    messages,schema=p.payload(item,'joint')
    messages[0]['content']=(PROPOSAL/'PROPOSED_JOINT_PROMPT_EN.txt').read_text()
    return messages,schema

def stop_check(protocol,started,results):
    for slot in protocol['schedule']:
        sid=slot['slot_id']
        if sid not in started:continue
        r=results.get(sid)
        if not r:return 'incomplete started request; no retry',0,{}
        if r.get('hard_stop'):return r['hard_stop'],0,{}
        if not r['technical_valid']:return 'first technical/incomplete/binding failure',1,{}
    return None,0,{}

def summary(protocol,root,baseline):
    starts,results=p.replay(root,protocol);slots=[]
    stop=s.read(Path(root)/'STOP.json') if (Path(root)/'STOP.json').exists() else None
    for slot in protocol['schedule']:
        sid=slot['slot_id'];r=results.get(sid);rev=Path(root)/(sid+'.review.json')
        slots.append(slot|dict(state='completed' if r and r['technical_valid'] else 'failed' if r else
            'started_unresolved' if sid in starts else 'not_dispatched',
            result=r,review=s.read(rev) if rev.exists() else None,
            not_dispatched_reason=stop['reason'] if sid not in starts and stop else None))
    usage=[r['usage'] for r in results.values() if isinstance(r.get('usage'),dict)]
    return dict(study=STUDY,protocol_identity=protocol['identity'],planned_requests=12,started=len(starts),
        cumulative=baseline+len(starts),technical_complete=sum(r['technical_valid'] for r in results.values()),
        model_unknown=sum(r['evaluation'].get('model_unknown') is True for r in results.values()),
        slots=slots,stop=stop,distinct_replies=8,distinct_contexts=4,independent_new_cases=0,
        prompt_tokens=sum(u.get('prompt_tokens') or 0 for u in usage),
        completion_tokens_including_thinking=sum(u.get('completion_tokens') or 0 for u in usage),
        usage_complete_requests=len(usage),request_seconds=sum(r['elapsed_seconds'] for r in results.values()),
        accounted_upper_usd=s.usd(sum(s.nanodollars(r['financial']['accounted_upper_usd'] or 0) for r in results.values())),
        unresolved_liability_usd=s.usd(sum(s.nanodollars(r['financial']['unsettled_reservation_usd']) for r in results.values())+
            p.RESERVE*(len(starts)-len(results))),reward_eligible=False)

def review(slot,row,root):
    path=Path(root)/(slot['slot_id']+'.review.json')
    print(s.canonical(dict(awaiting_source_review=str(path),item=slot['item_key'],position=slot['position'])),flush=True)
    start=time.monotonic()
    while not path.exists():
        if time.monotonic()-start>600:raise TimeoutError('source review absent')
        time.sleep(1)
    value=s.read(path)
    if value.get('slot_id')!=slot['slot_id'] or value.get('request_identity')!=row['request_identity'] or \
            value.get('response_sha256')!=s.sha(Path(root)/(slot['slot_id']+'.response.json')) or \
            value.get('reward_eligible') is not False:
        raise ValueError('review binding or qualification mismatch')
    disposition=value.get('disposition')
    errors=value.get('source_proved_substantial_errors',[])
    if disposition=='hard_stop':
        if not errors or any(not all(e.get(k) for k in ('claim','source_ids','source_quotes','original_rule','explanation')) for e in errors):
            raise ValueError('hard stop lacks source and original-rule evidence')
        return 'source-proved substantial error; see bound source review'
    if disposition not in ('continue','continue_with_unresolved_ambiguity') or errors:
        raise ValueError('inconsistent semantic disposition')
    return None

def runtime(review_fn=None):
    return dict(max_calls=12,cap=156,study=STUDY,version=STUDY,approve=approved,payload=payload,
        streaks=stop_check,summarize=summary,review=review_fn,semantic_revisions_applied=2,
        joint_prompt_unchanged=False)

def historical_count():
    return 66+len(list((BASE/'live_runs').rglob('*.started.json')))+len([
        x for x in (BASE/'paired_diagnostic_runs').rglob('*.started.json') if 'management' not in x.parts])

def launch():
    protocol,items=load();auth=s.read(HERE/'APPROVED.json');approved(protocol,auth)
    ROOT.mkdir(parents=True,exist_ok=True)
    with (BASE/'live_runs/.pool.lock').open('a') as old_lock,LEDGER.with_suffix('.lock').open('a') as legacy_lock, \
            (BASE/'paired_diagnostic_runs/.launch.lock').open('a') as paired_lock, \
            (ROOT.parent.parent/'.launch.lock').open('a') as new_lock:
        for lock in (old_lock,legacy_lock,paired_lock,new_lock):fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if historical_count()!=144:raise ValueError('historical count changed')
        foreign=[x for x in ROOT.parent.parent.rglob('*.started.json') if 'management' not in x.parts and not x.is_relative_to(ROOT)]
        if foreign:raise ValueError('other diagnostic starts exist')
        starts,_=p.replay(ROOT,protocol)
        if starts or (ROOT/'STOP.json').exists():
            print(s.canonical(dict(state='PRESERVED_NO_RESTART',started=len(starts))),flush=True);return
        baseline=protocol['financial_baseline']
        if s.sha(LEDGER)!=baseline['ledger_sha256']:raise ValueError('shared ledger changed')
        original=LEDGER.read_bytes()
        if visible_paid_writers():raise ValueError('visible concurrent paid writer')
        management=ROOT/'management';management.mkdir(exist_ok=True)
        if list(management.iterdir()):raise ValueError('prior preflight exists; no automatic retry')
        public_service_check(management,protocol['public_price_table_identity'])
        key=read_key()
        with credential_scope(key):
            models=management_once(management,'models',key)
            if models['status']!=200:raise ValueError('model-list query failed')
            model=next((m for m in models.get('body',{}).get('data',[]) if m.get('id')=='deepseek-flash'),{})
            if not model:raise ValueError('approved alias missing')
            if ('name' in model and model['name'] not in ('DeepSeek-V4.1-Flash','DeepSeek-V4.1-Flash-1017')) or \
                    ('context_window' in model and model['context_window']!=1048576) or \
                    ('max_output_tokens' in model and model['max_output_tokens']!=393216):
                raise ValueError('model identity/capability drift')
            balance=management_once(management,'user/balance',key)
            if balance['status']!=200 or not balance.get('body',{}).get('is_available'):raise ValueError('balance unavailable')
            amounts={x['currency']:Decimal(x['total_balance']) for x in balance['body']['balance_infos']}
            available=amounts.get('USD',Decimal(0))+amounts.get('CNY',Decimal(0))*Decimal('.15')
            budget=p.DiagnosticBudget(LEDGER,trial=baseline['financial_trial_identity'],study=STUDY,
                trial_cap=s.nanodollars(2),shared_cap=s.nanodollars(20),baseline=s.nanodollars('1.50724291'),
                opening=s.nanodollars('0.03079930'),account_opening=s.nanodollars(available),
                opening_trial=s.nanodollars(baseline['trial_accounted_usd']))
            total,trial,reserved,settled=budget._totals(budget.events())
            if set(reserved)-set(settled):raise ValueError('unknown prior liabilities')
            if s.usd(trial)!=baseline['trial_accounted_usd']:raise ValueError('trial baseline changed')
            s.save(management/'preflight.json',dict(service=model,available_tariff_equivalent_usd=str(available),
                trial_accounted_usd=s.usd(trial),shared_accounted_usd=s.usd(total),known_unsettled_count=0,
                visibility='visible local processes and shared known ledger; not all-account visibility',
                prior_stops_released=False,credential_value_persisted=False))
            def guard():
                load()
                if historical_count()!=144:raise ValueError('concurrent historical scoring')
                current=LEDGER.read_bytes()
                if not current.startswith(original):raise ValueError('ledger prefix changed')
                ids={slot['slot_id'] for slot in protocol['schedule']}
                if any(json.loads(line).get('reservation_id') not in ids for line in current[len(original):].decode().splitlines()):
                    raise ValueError('foreign paid ledger writer')
                if visible_paid_writers():raise ValueError('visible concurrent paid writer')
            result=p.run(protocol,items,ROOT,DeepSeekTransport(protocol['config']),budget,mode='live',auth=auth,
                before_dispatch=guard,global_count=historical_count,runtime=runtime(review))
        del key
        s.save(ROOT/'stage_result.json',result)
        total,trial,reserved,settled=budget._totals(budget.events())
        s.save(ROOT/'financial_closeout.json',dict(trial_accounted_usd=s.usd(trial),shared_accounted_usd=s.usd(total),
            stage_accounted_usd=s.usd(budget.stage_total(reserved,settled)),
            unsettled=[k for k in reserved if k not in settled],ledger_sha256=s.sha(LEDGER),
            original_prefix_preserved=LEDGER.read_bytes().startswith(original)))
        print(s.canonical(dict(started=result['started'],cumulative=result['cumulative'],stop=result['stop'])),flush=True)

if __name__=='__main__':
    os.umask(0o077)
    if sys.argv[1:]!=['--live']:raise SystemExit('Explicit --live and bound approval required')
    try:launch()
    except Exception as exc:
        ROOT.mkdir(parents=True,exist_ok=True)
        # Never serialize credential-bearing exceptions, HTTP bodies, or auth headers.
        safe=('historical count','other diagnostic','shared ledger','visible concurrent','prior preflight',
              'published service/','model-list','approved alias','model identity','balance unavailable',
              'unknown prior','trial baseline','authorization','immutable','protocol identity')
        reason=str(exc) if type(exc)is ValueError and str(exc).startswith(safe) else 'launch exception; details suppressed'
        row=dict(reason=reason,error_type=type(exc).__name__,automatic_retry=False,timestamp=time.time())
        s.save(ROOT/('failure_'+str(time.time_ns())+'.json'),row)
        if not (ROOT/'STOP.json').exists():s.save(ROOT/'STOP.json',row)
        raise SystemExit('Stopped; failure preserved, no retry.') from None
