"""Continue independent authorized slots while retaining one known liability.

The isolated request is never resent or settled without usage. Its original
journal row, failed delivery denominator, and full financial reservation remain.
Any OTHER unknown attempt stops the continuation. No new allowance or judge
configuration is introduced; the original stage, ledger and approval are used.
"""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import time

from .calibration_workflow import verify_identity
from .development_dispatch import DevelopmentBudget, PaidDevelopmentStage, sha, VERSION
from .development_feedback import save_once
from .diagnostic_support import usd
from .recovery_schedule import RecoverySchedule, Slot
from .schema import digest

STATUS = 'ISOLATE_ONE_UNKNOWN_NO_RETRY_RETAIN_FULL_RESERVATION'


def validate_isolation(record, *, stage_identity, policy):
    verify_identity(record)
    if (record.get('status') != STATUS or record.get('stage_identity') != stage_identity
            or record.get('financial_policy_identity') != digest(policy)
            or record.get('component') not in ('S','A','R') or record.get('new_allowance') != 0
            or record.get('retry_isolated_request') is not False):
        raise ValueError('bound single-request isolation required')
    for path, expected in record['source_hashes'].items():
        if sha(path) != expected: raise ValueError('isolation evidence or code changed')
    root = Path(record['run_directory']); aid = record['attempt_id']
    if (policy.get('run_directory') and str(root.resolve()) != policy['run_directory']):
        raise ValueError('isolated stage directory changed')
    for path in (root/'wire'/(aid+'.sse'), Path(__file__).resolve()):
        if str(path.resolve()) not in record['source_hashes']:
            raise ValueError('partial SSE and continuation implementation must be frozen')
    dbpath = root/record['component']/'attempts.sqlite'
    with sqlite3.connect('file:'+str(dbpath.resolve())+'?mode=ro', uri=True) as db:
        row = db.execute('SELECT claim,result FROM attempts WHERE id=?', (aid,)).fetchone()
    if row is None or row[1] is not None or digest(json.loads(row[0])) != record['claim_identity']:
        raise ValueError('isolated journal is not the original unresolved claim')
    claim = json.loads(row[0])
    if claim['protocol_identity'] != stage_identity or claim['slot_id'] != record['logical_slot']:
        raise ValueError('isolated claim belongs to another stage/input')
    # Do not pretend an available complete response is a failed/unknown one.
    if any((dbpath.parent/(aid+suffix)).exists() for suffix in ('.raw.json','.result.json')):
        raise ValueError('returned output exists; reconcile that output explicitly')
    data = (root/'wire'/(aid+'.sse')).read_bytes(); chunks = 0
    for line in data.splitlines():
        if not line.startswith(b'data:'): continue
        value = line[5:].strip()
        if value == b'[DONE]': raise ValueError('terminal SSE exists; no unknown isolation')
        event = json.loads(value); chunks += 1
        if event.get('error') or (event.get('model') and event['model'] not in policy['accepted_response_models']):
            raise ValueError('provider/model risk needs separate reconciliation')
        if event.get('usage') or any(x.get('finish_reason') is not None for x in event.get('choices',[])):
            raise ValueError('usage or finish exists; reconcile original return')
    if not chunks: raise ValueError('this bounded adapter requires actual partial SSE evidence')
    return claim


class RetainedBudget(DevelopmentBudget):
    def __init__(self, *args, isolation, **kwargs):
        super().__init__(*args, **kwargs); self.isolation = deepcopy(isolation)

    def reserve(self, reservation_id, amount, binding):
        if not self.lease_active: raise ValueError('legacy dispatch lease not held')
        with self.locked():
            validate_isolation(self.isolation, stage_identity=self.stage_identity, policy=self.policy)
            _, own = self._history()
            total, trial, reserved, settled = self._totals(self.events())
            isolated = self.isolation['attempt_id']
            if isolated not in reserved or isolated in settled:
                raise ValueError('full original unresolved reservation must remain')
            if reserved[isolated]['maximum_cost_usd'] != usd(self.policy['reserve_nanodollars']):
                raise ValueError('isolated financial liability changed')
            if set(reserved)-set(settled) != {isolated}:
                raise ValueError('another unknown liability; stop all new dispatch')
            if binding.get('logical_slot') == self.isolation['logical_slot']:
                raise ValueError('isolated input cannot be resent or audited without a primary')
            for field in ('trial','stage_cap','trial_cap','shared_cap','baseline','opening','external_liability','old_cap','account_opening','opening_trial'):
                if getattr(self,field) != self.policy[field]: raise ValueError('frozen monetary policy changed')
            if (reservation_id in reserved or amount != self.policy['reserve_nanodollars']
                    or binding.get('development_stage') != self.stage_identity
                    or binding.get('study') != self.policy['funding_identity']):
                raise ValueError('attempt/reservation identity changed')
            if len(own) >= self.policy['max_attempts'] or self.policy['baseline_cumulative']+len(own) >= self.policy['cumulative_cap']:
                raise ValueError('stage/global attempt capacity exhausted')
            if binding['ordinal'] and sum(x['binding']['ordinal'] > 0 for x in own.values()) >= self.policy['recovery_cap']:
                raise ValueError('shared technical recovery allowance exhausted')
            if self.stage_total(reserved,settled)+amount > self.stage_cap or trial+amount > self.trial_cap:
                raise ValueError('stage or cumulative service monetary envelope exhausted')
            if total-self.baseline+self.external_liability+amount > self.shared_cap or total+self.external_liability+amount > self.old_cap:
                raise ValueError('shared or legacy monetary envelope exhausted')
            if self.account_opening is not None and trial-self.opening_trial+amount > self.account_opening:
                raise ValueError('verified account balance insufficient')
            if self.verified_balance is not None and trial-self.verified_balance['opening_trial']+amount > self.verified_balance['available']:
                raise ValueError('verified account balance insufficient')
            self._append(dict(event='RESERVED', reservation_id=reservation_id, maximum_cost_usd=usd(amount),
                selection_trial=self.trial, stage=self.study, call_class='TECHNICAL_RECOVERY' if binding['ordinal'] else 'PRIMARY',
                logical_call_id=binding['logical_slot'], call_hash=reservation_id, provider='DeepSeek official API',
                model=self.policy['request_model'], binding=binding, timestamp=time.time(), protocol=VERSION,
                retained_liability_continuation_identity=self.isolation['identity']))


class RetainedSchedule(RecoverySchedule):
    def __init__(self,*args,isolated_attempt_id=None,**kwargs):
        self.isolated_attempt_id=isolated_attempt_id
        super().__init__(*args,**kwargs)

    def _view(self, db):
        view, grouped = super()._view(db)
        rows = self._rows(db)
        unknown = {c['attempt_id'] for c,r in rows if r is None}
        # Preserve every other global-risk cause, including an unexpected
        # unfinished request arriving after this continuation was prepared.
        other_risk = any(r is not None and (not r['identity_ok'] or not r['settled'] or r['outcome']=='global_risk') for _,r in rows)
        if (self.isolated_attempt_id and unknown == {self.isolated_attempt_id}
                and view['global_stop'] == 'OUTSTANDING_DELIVERY_OR_SETTLEMENT' and not other_risk):
            view['global_stop'] = None
            claim = next(c for c,r in rows if c['attempt_id']==self.isolated_attempt_id)
            view['states'][claim['slot_id']] = 'UNKNOWN_ISOLATED_FULL_LIABILITY_RETAINED'
        return view, grouped


class RetainedDevelopmentStage(PaidDevelopmentStage):
    def __init__(self,*args,isolation,**kwargs):
        super().__init__(*args,**kwargs)
        self.isolation=deepcopy(isolation)
        if str(self.root.resolve()) != self.isolation['run_directory']:
            raise ValueError('isolation cannot refer to another journal directory')
        validate_isolation(self.isolation,stage_identity=self.identity,policy=self.policy)
        self.budget=RetainedBudget(self.budget.path,policy=self.policy,stage_identity=self.identity,isolation=self.isolation)
        save_once(self.root/'RETAINED_LIABILITY_CONTINUATION.json',self.isolation)

    def authorize_transport(self, transport):
        if (json.loads((self.root/'RETAINED_LIABILITY_CONTINUATION.json').read_text()) != self.isolation
                or self.budget.isolation != self.isolation):
            raise ValueError('frozen continuation record changed')
        validate_isolation(self.isolation,stage_identity=self.identity,policy=self.policy)
        return super().authorize_transport(transport)

    def _wave(self, component, requests, remaining):
        directory=self.root/component;directory.mkdir(exist_ok=True,mode=0o700)
        save_once(directory/'REQUESTS.json',requests)
        slots=[Slot(k,r['identity'],digest([self.adapter.identity,component])) for k,r in requests.items()]
        isolated=self.isolation['attempt_id'] if component==self.isolation['component'] else None
        return RetainedSchedule(directory/'attempts.sqlite',slots,protocol_identity=self.identity,
            max_attempts=len(slots)*3,recovery_cap=remaining,isolated_attempt_id=isolated)

    def closed_extension(self,waves):
        return super().closed_extension(waves) | dict(
            retained_liability_continuation_identity=self.isolation['identity'],
            unresolved_attempt_preserved=self.isolation['attempt_id'],
            unresolved_maximum_usd=usd(self.policy['reserve_nanodollars']),
            unknown_attempt_retried=False,unknown_attempt_counted_in_first_attempt_denominator=True)
