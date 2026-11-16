"""Launch hook for paired.py. Not invoked by preparation or mock tests."""
from decimal import Decimal
import fcntl
from html.parser import HTMLParser
import json
from pathlib import Path
import time
import urllib.request

import paired as p
from paired import s
from deepseek_access import read_key, credential_scope, management_once, visible_paid_writers
from adapters import DeepSeekTransport


class Text(HTMLParser):
    def __init__(self): super().__init__(); self.parts=[]
    def handle_data(self,data): self.parts.append(data)


class FirstTable(HTMLParser):
    def __init__(self):
        super().__init__();self.depth=0;self.done=False;self.cell=None;self.row=[];self.rows=[]
    def handle_starttag(self,tag,attrs):
        if tag=='table' and not self.done:self.depth+=1
        if self.depth and tag=='tr':self.row=[]
        if self.depth and tag in ('th','td'):self.cell=[]
    def handle_data(self,data):
        if self.depth and self.cell is not None:self.cell.append(data)
    def handle_endtag(self,tag):
        if self.depth and tag in ('th','td') and self.cell is not None:
            self.row.append(' '.join(' '.join(self.cell).split()));self.cell=None
        if self.depth and tag=='tr' and self.row:self.rows.append(self.row)
        if self.depth and tag=='table':self.depth-=1;self.done=True


def table_identity(raw):
    parser=FirstTable();parser.feed(raw.decode());
    if not parser.rows:raise ValueError('official pricing table unavailable')
    return s.digest(parser.rows)


def public_service_check(out,expected_table_identity):
    """Public, unauthenticated GET; no research payload or credential."""
    url='https://api-docs.deepseek.com/quick_start/pricing/'
    op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    raw=op.open(url,timeout=30).read();parser=Text();parser.feed(raw.decode())
    text=' '.join(parser.parts)
    if table_identity(raw)!=expected_table_identity:
        raise ValueError('published service/capabilities/pricing table changed; no automatic substitution')
    # This check binds the already-reviewed table, not an inferred tariff.
    s.save(out/'public_service_check.json',dict(url=url,checked_unix=time.time(),
        expected_model='DeepSeek-V4.1-Flash-1017',html_sha256=__import__('hashlib').sha256(raw).hexdigest(),
        model_alias='deepseek-flash',immutable_weights=False,prices='peak input0.30/output1.20 per million; no cache discount reserved'))


def launch(protocol,items,auth):
    p.approved(protocol,auth)
    try:
        return _launch(protocol,items,auth)
    except Exception as exc:
        root=p.BASE/'paired_diagnostic_runs'/p.STUDY/'live'
        root.mkdir(parents=True,exist_ok=True)
        # Only controlled guard messages may be logged; never HTTP/credential exceptions.
        prefixes=('historical count changed','other diagnostic starts exist','study STOP preserved',
            'shared ledger changed','visible concurrent paid writer','prior preflight exists',
            'published service/','model-list query failed','approved alias missing',
            'model identity/','balance unavailable','unknown prior financial liabilities','trial baseline changed')
        reason=str(exc) if type(exc) is ValueError and str(exc).startswith(prefixes) else 'launch/preflight exception; sensitive exception details suppressed'
        receipt=dict(reason=reason,error_type=type(exc).__name__,automatic_retry=False,
            old_stops_released=False,real_started=len(list(root.glob('*.started.json'))),timestamp=time.time())
        s.save(root/('launch_failure_'+str(time.time_ns())+'.json'),receipt)
        if not (root/'STOP.json').exists():s.save(root/'STOP.json',receipt)
        raise SystemExit('Launch stopped; local STOP and failure receipt preserved.') from None


def _launch(protocol,items,auth):
    p.approved(protocol,auth)  # Before any key read or HTTP operation.
    historical=p.BASE/'live_runs'
    new_base=p.BASE/'paired_diagnostic_runs'
    root=new_base/p.STUDY/'live'
    ledger=s.REPO/'project/outputs/paper1_api_budget/cumulative_paid_api_budget.jsonl'
    new_base.mkdir(exist_ok=True);root.mkdir(parents=True,exist_ok=True)
    with (historical/'.pool.lock').open('a') as old_lock, ledger.with_suffix('.lock').open('a') as legacy_lock, \
            (new_base/'.launch.lock').open('a') as stage_lock:
        for lock in (old_lock,legacy_lock,stage_lock): fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        count=lambda:66+len(list(historical.rglob('*.started.json')))
        if count()!=120: raise ValueError('historical count changed; reconcile scope before launch')
        # Other new diagnostic studies would also consume the cumulative capacity.
        other=[x for x in new_base.rglob('*.started.json') if 'management' not in x.parts and not x.is_relative_to(root)]
        if other: raise ValueError('other diagnostic starts exist; cumulative scope needs reconciliation')
        starts,results=p.replay(root,protocol)
        if starts:
            # No automatic resumption under a new invocation. Read-only closeout is safe.
            print(s.canonical(p.summarize(protocol,root,count())))
            return
        if (root/'STOP.json').exists(): raise ValueError('study STOP preserved; no automatic resume')
        baseline=protocol['financial_baseline']
        if s.sha(ledger)!=baseline['ledger_sha256']: raise ValueError('shared ledger changed; reconcile before launch')
        original=ledger.read_bytes()
        if visible_paid_writers(): raise ValueError('visible concurrent paid writer; no process operated on')
        management=root/'management';management.mkdir(exist_ok=True)
        if list(management.glob('*.started.json')) or (management/'public_service_check.json').exists():
            raise ValueError('prior preflight exists; no automatic management-request retry')
        public_service_check(management,protocol['public_price_table_identity'])
        key=read_key()
        with credential_scope(key):
            models=management_once(management,'models',key)
            if models['status']!=200: raise ValueError('model-list query failed; no scoring')
            model=next((x for x in models.get('body',{}).get('data',[]) if x.get('id')=='deepseek-flash'),{})
            if not model:raise ValueError('approved alias missing; no substitution')
            # Optional provider metadata must not contradict the reviewed public table.
            if ('name' in model and model['name'] not in ('DeepSeek-V4.1-Flash','DeepSeek-V4.1-Flash-1017')) or \
                    ('context_window' in model and model['context_window']!=1048576) or \
                    ('max_output_tokens' in model and model['max_output_tokens']!=393216):
                raise ValueError('model identity/capabilities contradict published mapping')
            balance=management_once(management,'user/balance',key)
            if balance['status']!=200 or not balance.get('body',{}).get('is_available'):
                raise ValueError('balance unavailable; no scoring')
            amounts={x['currency']:Decimal(x['total_balance']) for x in balance['body']['balance_infos']}
            available=amounts.get('USD',Decimal(0))+amounts.get('CNY',Decimal(0))*Decimal('.15')
            # The .15 factor is the reviewed USD/CNY tariff equivalence, not FX.
            budget=p.DiagnosticBudget(ledger,trial=baseline['financial_trial_identity'],
                trial_cap=s.nanodollars(2),shared_cap=s.nanodollars(20),
                baseline=s.nanodollars('1.50724291'),opening=s.nanodollars('0.03079930'),
                account_opening=s.nanodollars(available),opening_trial=s.nanodollars(baseline['trial_accounted_usd']))
            total,trial,reserved,settled=budget._totals(budget.events())
            if set(reserved)-set(settled): raise ValueError('unknown prior financial liabilities')
            if s.usd(trial)!=baseline['trial_accounted_usd']: raise ValueError('trial baseline changed')
            s.save(management/'preflight.json',dict(service=model,balance_tariff_equivalent_usd=str(available),
                trial_accounted_usd=s.usd(trial),shared_accounted_usd=s.usd(total),known_unsettled=0,
                visibility='read-only visible-process check and known ledger reconciliation; not a claim of visibility into all accounts',
                old_stops_released=False))
            def guard():
                if count()!=120: raise ValueError('concurrent historical scoring start')
                current=ledger.read_bytes()
                if not current.startswith(original): raise ValueError('shared ledger history changed')
                events=[json.loads(x) for x in current[len(original):].decode().splitlines()]
                ids={x['slot_id'] for x in protocol['schedule']}
                if any(x.get('reservation_id') not in ids for x in events):
                    raise ValueError('concurrent foreign paid writer in ledger')
                if visible_paid_writers(): raise ValueError('visible concurrent paid writer')
                p.load_package()  # Every request binds unchanged source/prompt/code.
            result=p.run(protocol,items,root,DeepSeekTransport(protocol['config']),budget,
                mode='live',auth=auth,before_dispatch=guard,global_count=count)
        del key
        s.save(root/'stage_result.json',result)
        _,trial,reserved,settled=budget._totals(budget.events())
        s.save(root/'financial_closeout.json',dict(trial_accounted_usd=s.usd(trial),
            stage_accounted_usd=s.usd(budget.stage_total(reserved,settled)),
            unsettled=[k for k in reserved if k not in settled],ledger_sha256=s.sha(ledger),
            original_prefix_preserved=ledger.read_bytes().startswith(original)))
        print(s.canonical(dict(started=result['started'],cumulative=result['cumulative'],reward_eligible=False)))
