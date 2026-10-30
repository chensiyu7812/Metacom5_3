"""Explicitly approved S/A dispatch over the existing append-only money ledger.

No credential or network operation occurs on import, construction, or check.
Old contracts, STOPs, ledger prefix and counters are never rewritten. The caller
holds the listed legacy launch locks for a live run; non-cooperating writers are
not assumed safe merely because this writer uses a lock.
"""
from contextlib import ExitStack, contextmanager
from copy import deepcopy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import time

from . import diagnostic_support as money
from .development_feedback import OfflineDevelopmentStage, save_once
from .diagnostic_engine import DiagnosticBudget
from .schema import digest
from .strict_audit_delivery import Collector, DELIVERY, ENDPOINT

VERSION = 'pmrl1-paid-development-bridge-v1-20261030'
ENDPOINTS = {ENDPOINT, 'https://api.deepseek.com/chat/completions'}


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require_approval(identity, policy, approval):
    if (not isinstance(approval, dict) or approval.get('status') != 'APPROVED'
            or approval.get('protocol_identity') != identity
            or approval.get('operation') != 'bounded_development_scoring'
            or approval.get('financial_policy_identity') != digest(policy)):
        raise ValueError('this complete development stage and financial policy are not approved')
    record = approval.get('researcher_authorization_record')
    if not record or sha(record) != approval.get('researcher_record_sha256'):
        raise ValueError('bound actual researcher authorization record required')


class DevelopmentBudget(DiagnosticBudget):
    """Money AND attempt limits checked under the same inherited ledger lock."""
    def __init__(self, path, *, policy, stage_identity):
        self.policy, self.stage_identity = deepcopy(policy), stage_identity
        self.lease_active = False
        self.verified_balance = None
        names = ('trial', 'stage_cap', 'trial_cap', 'shared_cap', 'baseline', 'opening',
                 'external_liability', 'old_cap', 'account_opening', 'opening_trial')
        if not policy.get('funding_identity'): raise ValueError('shared phase funding identity required')
        super().__init__(path, study=policy['funding_identity'], **{k: policy[k] for k in names})
        for k in ('max_attempts', 'recovery_cap', 'baseline_cumulative', 'cumulative_cap', 'reserve_nanodollars'):
            if type(policy[k]) is not int or policy[k] < 0: raise ValueError('finite nonnegative policy required')
        if policy['reserve_nanodollars'] < 1: raise ValueError('positive monetary liability required')

    @contextmanager
    def legacy_lease(self):
        with ExitStack() as stack:
            for p in sorted(set(self.policy['legacy_lock_paths'])):
                path = Path(p); path.parent.mkdir(parents=True, exist_ok=True)
                f = stack.enter_context(path.open('a'))
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.lease_active = True
            try: yield
            finally: self.lease_active = False

    def _history(self):
        data = self.path.read_bytes() if self.path.exists() else b''
        n = self.policy['opening_ledger_bytes']
        if len(data) < n or hashlib.sha256(data[:n]).hexdigest() != self.policy['opening_ledger_sha256']:
            raise ValueError('historical financial prefix changed')
        for path, expected in self.policy['historical_files'].items():
            if sha(path) != expected: raise ValueError('historical execution receipt changed')
        found = {str(p.resolve()) for root in self.policy['historical_start_roots']
                 for p in Path(root).rglob('*.started.json') if 'management' not in p.parts}
        if found != set(self.policy['historical_start_paths']):
            raise ValueError('other legacy attempt set changed; reconcile cumulative identity')
        suffix = [json.loads(s) for s in data[n:].splitlines() if s.strip()]
        own = {}
        for e in suffix:
            if e['event'] == 'RESERVED':
                if e.get('binding', {}).get('development_stage') != self.stage_identity:
                    raise ValueError('foreign new financial writer; reconcile')
                own[e['reservation_id']] = e
            elif e['event'] != 'SETTLED' or e['reservation_id'] not in own:
                raise ValueError('unowned or malformed new financial event')
        return suffix, own

    def reserve(self, reservation_id, amount, binding):
        if not self.lease_active: raise ValueError('legacy dispatch lease not held')
        with self.locked():
            _, own = self._history()
            total, trial, reserved, settled = self._totals(self.events())
            for field in ('trial','stage_cap','trial_cap','shared_cap','baseline','opening','external_liability','old_cap','account_opening','opening_trial'):
                if getattr(self, field) != self.policy[field]: raise ValueError('frozen monetary policy changed')
            if set(reserved) - set(settled): raise ValueError('outstanding liability; never redispatch')
            if (reservation_id in reserved or amount != self.policy['reserve_nanodollars']
                    or binding.get('development_stage') != self.stage_identity
                    or binding.get('study') != self.policy['funding_identity']):
                raise ValueError('attempt/reservation identity changed')
            if len(own) >= self.policy['max_attempts'] or self.policy['baseline_cumulative'] + len(own) >= self.policy['cumulative_cap']:
                raise ValueError('stage/global attempt capacity exhausted')
            if binding['ordinal'] and sum(x['binding']['ordinal'] > 0 for x in own.values()) >= self.policy['recovery_cap']:
                raise ValueError('shared technical recovery allowance exhausted')
            if self.stage_total(reserved, settled) + amount > self.stage_cap or trial + amount > self.trial_cap:
                raise ValueError('stage or cumulative service monetary envelope exhausted')
            if total-self.baseline+self.external_liability+amount > self.shared_cap or total+self.external_liability+amount > self.old_cap:
                raise ValueError('shared or legacy monetary envelope exhausted')
            if self.account_opening is not None and trial-self.opening_trial+amount > self.account_opening:
                raise ValueError('verified account balance insufficient')
            if self.verified_balance is not None and trial-self.verified_balance['opening_trial']+amount > self.verified_balance['available']:
                raise ValueError('verified account balance insufficient')
            self._append(dict(event='RESERVED', reservation_id=reservation_id, maximum_cost_usd=money.usd(amount),
                selection_trial=self.trial, stage=self.study, call_class='TECHNICAL_RECOVERY' if binding['ordinal'] else 'PRIMARY',
                logical_call_id=binding['logical_slot'], call_hash=reservation_id, provider='DeepSeek official API',
                model=self.policy['request_model'], binding=binding, timestamp=time.time(), protocol=VERSION))


class PaidDevelopmentStage(OfflineDevelopmentStage):
    def __init__(self, root, materials, adapter, *, ledger, policy, approval=None, engineering=False):
        self.policy, self.approval = deepcopy(policy), deepcopy(approval)
        self.engineering = engineering
        if not engineering and (str(Path(root).resolve()) != policy.get('run_directory')
                or str(Path(ledger).resolve()) != policy.get('ledger_path')):
            raise ValueError('fixed stage/ledger directory changed; no new allowance')
        super().__init__(root, materials, adapter, recovery_cap=policy['recovery_cap'])
        if self.protocol['max_attempts'] != policy['max_attempts']:
            raise ValueError('material count and approved physical attempt envelope differ')
        self.budget = DevelopmentBudget(ledger, policy=policy, stage_identity=self.identity)

    def protocol_extension(self):
        return dict(mode='synthetic_financial_bridge' if self.engineering else 'bounded_paid_development',
                    dispatch_version=VERSION, financial_policy=deepcopy(self.policy))

    def authorize_transport(self, transport):
        if self.engineering:
            if getattr(transport, 'synthetic_only', False) is not True: raise ValueError('engineering requires synthetic transport')
        else:
            require_approval(self.identity, self.policy, self.approval)
            if type(transport) is not DeepSeekStageTransport: raise ValueError('approved native transport required')
            from .development_preflight import validate_preflight, visible_paid_writers
            receipt = validate_preflight(self.root/'management', self.identity, self.policy, self.approval)
            if visible_paid_writers(): raise ValueError('visible concurrent paid writer')
            if transport.credential_fingerprint != receipt['credential_fingerprint']:
                raise ValueError('transport differs from preflight credential scope')
            self.budget.verified_balance = dict(available=receipt['available_nanodollars'],opening_trial=receipt['opening_trial_nanodollars'])
        if not self.budget.lease_active: raise ValueError('legacy dispatch lease not held')
        self.budget._history()

    def reserve(self, claim, request):
        if not self.engineering: require_approval(self.identity, self.policy, self.approval)
        if self.budget.policy != self.policy: raise ValueError('budget policy changed')
        binding = dict(development_stage=self.identity, study=self.policy['funding_identity'], component=request['component'],
            logical_slot=claim['slot_id'], ordinal=claim['ordinal'], input_identity=request['identity'])
        self.budget.reserve(claim['attempt_id'], self.policy['reserve_nanodollars'], binding)
        return dict(attempt_id=claim['attempt_id'], reservation_identity=digest(binding), ledger=str(self.budget.path.resolve()))

    def perform(self, transport, claim, request, item, score, directory):
        raw = transport.send(deepcopy(request), attempt_id=claim['attempt_id'])
        save_once(directory/(claim['attempt_id']+'.raw.json'), raw)
        if self.engineering and raw.get('synthetic_only') is not True: raise ValueError('synthetic raw required')
        usage = raw.get('usage') or {}
        amount = None
        if all(type(usage.get(k)) is int and usage[k] >= 0 for k in ('prompt_tokens','completion_tokens')):
            amount = (usage['prompt_tokens'] * self.policy['input_nanodollars_per_token'] +
                      usage['completion_tokens'] * self.policy['output_nanodollars_per_token'])
        within = self.budget.settle(claim['attempt_id'], amount, 'development attempt; no qualified reward')
        if amount is None: raise ValueError('usage unknown; retain full reservation and reconcile, no retry')
        if (not within or raw.get('model') not in self.policy['accepted_response_models']
                or raw.get('request_identity') != request['identity'] or raw.get('adapter_identity') != self.adapter.identity
                or raw.get('attempt_id') != claim['attempt_id']):
            evaluation = dict(technical_valid=False, value=None, q=None, m=None, U=None, reward_eligible=False)
            outcome = 'global_risk'
        else:
            evaluation = self.adapter.evaluate(request, item, raw, score=score)
            outcome = 'valid' if evaluation['technical_valid'] else evaluation['failure_kind']
        record = dict(evaluation=evaluation, raw_identity=digest(raw), outcome=outcome,
            synthetic_only=self.engineering, accounted_nanodollars=amount, reward_eligible=False)
        save_once(directory/(claim['attempt_id']+'.result.json'), record)
        return dict(outcome=outcome, settlement_identity=digest(self.budget.events()[-1]), result_identity=digest(record))

    def closed_extension(self, waves):
        _, _, reserved, settled = self.budget._totals(self.budget.events())
        own = {k:v for k,v in reserved.items() if v.get('binding',{}).get('development_stage') == self.identity}
        return dict(status='CLOSED_SYNTHETIC_FINANCIAL_REHEARSAL' if self.engineering else 'CLOSED_DEVELOPMENT_NOT_QUALIFIED',
            real_calls=0 if self.engineering else len(own), physical_attempts=len(own),
            accounted_usd=money.usd(sum(money.nanodollars(settled[k]['actual_cost_usd']) for k in own if k in settled)),
            unknown_liabilities=len(set(own)-set(settled)), cumulative_attempts=self.policy['baseline_cumulative']+len(own))


class DeepSeekStageTransport:
    """Exact supplied wire bytes, lossless SSE, no redirects/proxies/retries."""
    def __init__(self, archive_root, *, timeout_seconds, credential_fingerprint):
        if timeout_seconds <= 0: raise ValueError('positive native watchdog required')
        self.root, self.timeout = Path(archive_root), timeout_seconds
        self.credential_fingerprint = credential_fingerprint

    def send(self, request, *, attempt_id):
        import urllib.request
        if request['endpoint'] not in ENDPOINTS or request['identity'] != digest({k:v for k,v in request.items() if k!='identity'}):
            raise ValueError('outbound endpoint/identity changed')
        key = os.environ.get('DEEPSEEK_API_KEY')
        if not key: raise RuntimeError('authorized process credential absent; reservation remains unresolved')
        if hashlib.sha256(key.encode()).hexdigest() != self.credential_fingerprint:
            raise ValueError('credential changed after service/account preflight')
        data = json.dumps(request['wire_body'], ensure_ascii=False).encode()
        req = urllib.request.Request(request['endpoint'], data=data,
            headers={'Content-Type':'application/json', 'Authorization':'Bearer '+key})
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs): return None
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        save_once(self.root/(attempt_id+'.wire.json'), dict(request_identity=request['identity'],
            body=request['wire_body'], serialized_body_sha256=hashlib.sha256(data).hexdigest()))
        collector = Collector(request['identity']); started = time.monotonic()
        with (self.root/(attempt_id+'.sse')).open('xb') as archive:
            with opener.open(req, timeout=30) as response:
                for line in response:
                    archive.write(line); archive.flush(); os.fsync(archive.fileno())
                    if time.monotonic()-started > self.timeout: raise TimeoutError('native total watchdog')
                    collector.feed(line)
                    if collector.done: break
        return collector.complete() | dict(adapter_identity=request['adapter_identity'], attempt_id=attempt_id,
            elapsed_seconds=time.monotonic()-started, wire_body_sha256=hashlib.sha256(data).hexdigest(),
            delivery=DELIVERY if request['component']=='A' else 'native_json_content')
