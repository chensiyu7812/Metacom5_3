"""48-slot adapter for the existing paired.run engine. No new transport/parser."""
from pathlib import Path
from decimal import Decimal
import sys, json, os, time, fcntl
HERE=Path(__file__).resolve().parent
BASE=HERE.parent
PROPOSAL=BASE/'reward_noise_proposal_20261020_v1'
sys.path.insert(0,str(BASE/'paired_diagnostic_20261019_v1'))
import paired as p
from paired import s
from adapters import DeepSeekTransport
from deepseek_access import read_key,credential_scope,management_once,visible_paid_writers
from live import public_service_check
STUDY='pmrl1-resource-decision-noise-v1-20261020'
ROOT=BASE/'reward_noise_runs'/STUDY/'live'
LEDGER=s.REPO/'project/outputs/paper1_api_budget/cumulative_paid_api_budget.jsonl'

def prepared_items():
    proposal=s.read(PROPOSAL/'proposal.json')
    items={}
    for e in proposal['endpoints']:
        data=s.read(PROPOSAL/e['payload_file']);user=json.loads(data['messages'][1]['content'])
        items[e['row_id']]=dict(reply=user['reply'],evidence=user['legal_evidence'],
            payload_file=e['payload_file'],payload_sha256=e['payload_file_sha256'],
            context_id=e['context_id'],reply_identity=e['reply_identity'])
    return items

def load():
    protocol=s.read(HERE/'protocol.json')
    if protocol['identity']!=s.digest({k:v for k,v in protocol.items() if k!='identity'}):
        raise ValueError('protocol identity mismatch')
    for file,h in protocol['immutable_files'].items():
        if s.sha(file)!=h:raise ValueError('immutable input/code changed')
    return protocol,prepared_items()

def approved(protocol,auth):
    required=dict(status='APPROVED',study=STUDY,protocol_identity=protocol['identity'],
        proposal_identity='5f6b05448286a8e4476ba6d6d0ce2cf1776d7af5d30ae47e1e3252f6e3c8104f',
        baseline_cumulative=153,new_request_limit=48,cumulative_cap=201,capacity=289,
        stage_cap_usd='1.25',trial_cap_usd='2',shared_cap_usd='20',
        management_requests={'models':1,'user/balance':1},credential_process_read_authorized=True,
        official_research_payload_authorized=True,semantic_revision_delta=0,semantic_revisions_applied=2,
        old_stops_released=False,qualifies_reward=False,
        diagnostic_policy=protocol['diagnostic_policy'])
    if any(auth.get(k)!=v for k,v in required.items()):raise ValueError('authorization scope mismatch')

def payload(item,component,first=None):
    if component!='joint' or first is not None:raise ValueError('joint-only frozen payload')
    path=PROPOSAL/item['payload_file']
    if s.sha(path)!=item['payload_sha256']:raise ValueError('payload changed')
    data=s.read(path)
    if s.digest(json.loads(data['messages'][1]['content'])['legal_evidence'])!=s.digest(item['evidence']):
        raise ValueError('source binding changed')
    return data['messages'],data['schema']

def stop_check(protocol,started,results):
    streak=0
    for slot in protocol['schedule']:
        sid=slot['slot_id']
        if sid not in started:continue
        row=results.get(sid)
        if row is None:return 'incomplete started request; no retry',streak,{}
        if row.get('hard_stop'):return row['hard_stop'],streak,{}
        if not row['financial']['settlement_confirmed']:
            return 'usage or liability unresolved; preserve reservation',streak,{}
        ev=row['evaluation']
        if ev.get('error')=='non-natural final' or ev.get('financial_usage_unknown'):
            return 'incomplete/truncated final or unknown usage; no retry',streak,{}
        streak=0 if row['technical_valid'] else streak+1
        if streak>=2:return 'two consecutive mechanical failures',streak,{}
    return None,streak,{}

def summarize(protocol,root,baseline):
    starts,results=p.replay(root,protocol)
    stop=s.read(Path(root)/'STOP.json') if (Path(root)/'STOP.json').exists() else None
    slots=[]
    for slot in protocol['schedule']:
        sid=slot['slot_id'];r=results.get(sid)
        slots.append(dict(**slot,state_actual='completed' if r and r['technical_valid'] else
            'failed' if r else 'started_unresolved' if sid in starts else 'not_dispatched',
            result=r,not_dispatched_reason=stop['reason'] if sid not in starts and stop else None))
    usage=[r['usage'] for r in results.values() if isinstance(r.get('usage'),dict)]
    return dict(study=STUDY,protocol_identity=protocol['identity'],planned=48,started=len(starts),
        cumulative=baseline+len(starts),technical_complete=sum(r['technical_valid'] for r in results.values()),
        model_unknown=sum(r['evaluation'].get('model_unknown') is True for r in results.values()),
        slots=slots,stop=stop,distinct_replies=12,contexts=4,source_owners=2,independent_new_cases=0,
        prompt_tokens=sum(u.get('prompt_tokens') or 0 for u in usage),
        completion_tokens_including_thinking=sum(u.get('completion_tokens') or 0 for u in usage),
        request_seconds=sum(r['elapsed_seconds'] for r in results.values()),
        accounted_usd=s.usd(sum(s.nanodollars(r['financial']['accounted_upper_usd'] or 0) for r in results.values())),
        unresolved_liability_usd=s.usd(sum(s.nanodollars(r['financial']['unsettled_reservation_usd']) for r in results.values())+
            p.RESERVE*(len(starts)-len(results))),reward_eligible=False,human_reference_status='PENDING_NOT_IMPUTED')

def observe(slot,row,root):
    # Semantic source audit is offline, not a per-item dispatch veto in this diagnostic.
    print(s.canonical(dict(position=slot['position'],draw=slot['draw'],technical_valid=row['technical_valid'],
        model_unknown=row['evaluation'].get('model_unknown'),seconds=round(row['elapsed_seconds'],2),
        accounted_usd=row['financial']['accounted_upper_usd'])),flush=True)
    return None

def runtime():
    return dict(max_calls=48,cap=201,study=STUDY,version=STUDY,approve=approved,payload=payload,
        streaks=stop_check,summarize=summarize,review=observe,semantic_revisions_applied=2,
        joint_prompt_unchanged=True)

def historical_count():
    return 66+sum(len([x for x in (BASE/name).rglob('*.started.json') if 'management' not in x.parts])
        for name in ('live_runs','paired_diagnostic_runs','action_stage_runs'))

def launch():
    protocol,items=load();auth=s.read(HERE/'APPROVED.json');approved(protocol,auth)
    ROOT.mkdir(parents=True,exist_ok=True)
    lock_paths=[BASE/'live_runs/.pool.lock',LEDGER.with_suffix('.lock'),
        BASE/'paired_diagnostic_runs/.launch.lock',BASE/'action_stage_runs/.launch.lock',
        ROOT.parent.parent/'.launch.lock']
    from contextlib import ExitStack
    with ExitStack() as stack:
        for path in lock_paths:
            lock=stack.enter_context(path.open('a'));fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if historical_count()!=153:raise ValueError('historical count changed')
        if [x for x in ROOT.parent.parent.rglob('*.started.json') if 'management' not in x.parts and not x.is_relative_to(ROOT)]:
            raise ValueError('other diagnostic starts exist; no cross-version redispatch')
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
                stage_cap=s.nanodollars('1.25'),trial_cap=s.nanodollars(2),shared_cap=s.nanodollars(20),
                baseline=s.nanodollars('1.50724291'),opening=s.nanodollars('0.03079930'),
                account_opening=s.nanodollars(available),opening_trial=s.nanodollars('0.461787'))
            total,trial,reserved,settled=budget._totals(budget.events())
            if set(reserved)-set(settled):raise ValueError('unknown prior liabilities')
            if s.usd(trial)!='0.461787':raise ValueError('trial baseline changed')
            s.save(management/'preflight.json',dict(service=model,available_tariff_equivalent_usd=str(available),
                trial_accounted_usd=s.usd(trial),shared_accounted_usd=s.usd(total),known_unsettled_count=0,
                visibility='visible local processes and known shared ledger; no all-account visibility claim',
                public_price_table_identity=protocol['public_price_table_identity'],GPU_used=False,
                old_stops_released=False,credential_value_persisted=False))
            def guard():
                load()
                if historical_count()!=153:raise ValueError('concurrent historical scoring')
                if [x for x in ROOT.parent.parent.rglob('*.started.json') if 'management' not in x.parts and not x.is_relative_to(ROOT)]:
                    raise ValueError('other diagnostic starts exist')
                current=LEDGER.read_bytes()
                if not current.startswith(original):raise ValueError('ledger prefix changed')
                ids={slot['slot_id'] for slot in protocol['schedule']}
                if any(json.loads(line).get('reservation_id') not in ids for line in current[len(original):].decode().splitlines()):
                    raise ValueError('foreign paid ledger writer')
                if visible_paid_writers():raise ValueError('visible concurrent paid writer')
            result=p.run(protocol,items,ROOT,DeepSeekTransport(protocol['config']),budget,mode='live',auth=auth,
                before_dispatch=guard,global_count=historical_count,runtime=runtime())
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
        safe=('historical count','other diagnostic','shared ledger','visible concurrent','prior preflight',
            'published service/','model-list','approved alias','model identity','balance unavailable',
            'unknown prior','trial baseline','authorization','immutable','protocol identity')
        reason=str(exc) if type(exc)is ValueError and str(exc).startswith(safe) else 'launch exception; sensitive details suppressed'
        row=dict(reason=reason,error_type=type(exc).__name__,automatic_retry=False,timestamp=time.time())
        s.save(ROOT/('failure_'+str(time.time_ns())+'.json'),row)
        if not (ROOT/'STOP.json').exists():s.save(ROOT/'STOP.json',row)
        raise SystemExit('Stopped; failure preserved, no retry.') from None
