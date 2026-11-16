"""Independent PM-RL1 selection runner. Default: offline; no sealed reader.

No imports of model runtimes or network clients until explicit live execution.
The existing scorer, rubric, contract, outputs and human intake are read-only.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from decimal import Decimal

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO / 'project/src'))
from metacom_pm.rl1 import judge_completion_candidate as judge

STAGES = ('engineering', 'development', 'diagnostics')
CANDIDATES = ('gemma4_12b_bf16','gemma4_12b_bf16_thinking','deepseek_flash_off','deepseek_flash_high')
VALID = ('measured_candidate', 'semantic_uncertainty')
OLD_STARTS = 66
OLD_REVISION = 1
NANO = 10**9
API_WORST = 786432000  # $0.786432: full 1M input PLUS 384K output, peak, no cache.
PARSER_FILES = ('judge_completion_candidate.py', 'judge_completion.py', 'judge_flat.py',
                'judge_scoped.py', 'judge_indexed.py', 'judge.py', 'evidence.py', 'schema.py')


def canonical(x):
    return json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def digest(x):
    return hashlib.sha256(canonical(x).encode()).hexdigest()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as f:
        f.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def nanodollars(x):
    return int(Decimal(str(x)) * NANO)


def usd(n):
    return str(Decimal(n) / NANO)


def code_identity():
    return digest({**{n: sha(REPO / 'project/src/metacom_pm/rl1' / n) for n in PARSER_FILES},
                   'runner': sha(__file__), 'adapters': sha(HERE / 'adapters.py'),
                   'readiness': sha(HERE / 'runtime_receipts.py'), 'analysis': sha(HERE / 'analyze.py'),
                   'preparation': sha(HERE / 'prepare.py'),
                   'official_template': sha(HERE / 'official_chat_template_707f0a3.jinja'),
                   'gemma_public_metadata': sha(HERE / 'gemma_public_file_metadata.json')})


def load_plan():
    p = read(HERE / 'plan.json')
    claimed = p.pop('identity')
    if digest(p) != claimed:
        raise ValueError('plan identity mismatch')
    p['identity'] = claimed
    if p['implementation_identity'] != code_identity():
        raise ValueError('implementation changed; regenerate and review plan before approval')
    # Only these development-only sources are ever opened. No packet/private key reader.
    for rel, expected in p['source_hashes'].items():
        if sha(REPO / rel) != expected:
            raise ValueError('source changed: ' + rel)
    return p


def config_for(plan, candidate):
    c = plan['configs'][candidate]
    if c['identity'] != digest({k: v for k, v in c.items() if k != 'identity'}):
        raise ValueError('configuration binding mismatch')
    return c


def stage_requests(plan, candidate, phase):
    if phase not in STAGES:
        raise ValueError('sealed/qualification/training access is outside this executable')
    c = config_for(plan, candidate)
    return [r for r in plan['requests'] if r['configuration_identity'] == c['identity']
            and r['phase'] == phase]


def payload(plan, request):
    item = plan['items'][request['item_key']]
    if item['split'] != 'development' or request['request_id'] != digest(
        {k: v for k, v in request.items() if k != 'request_id'}):
        raise ValueError('non-development or changed request')
    messages, schema = judge.messages_and_schema(item['evidence'], item['reply'])
    if digest(messages) != request['messages_identity'] or digest(schema) != request['schema_identity']:
        raise ValueError('payload identity mismatch')
    return messages, schema


class Budget:
    """Append-only shared money ledger, serialized for this writer family.

    Old writers do not all take this lock: live approval MUST reconcile all other
    liabilities and ensure no concurrent legacy paid writer. No implicit lease.
    UNKNOWN settlement retains the complete reservation indefinitely.
    """
    def __init__(self, path, *, trial, trial_cap, shared_cap, baseline,
                 opening, external_liability=0, old_cap=nanodollars(50)):
        self.path = Path(path)
        self.trial = trial
        self.trial_cap, self.shared_cap = trial_cap, shared_cap
        self.baseline, self.opening = baseline, opening
        self.external_liability, self.old_cap = external_liability, old_cap
        if min(trial_cap, shared_cap, baseline, opening, external_liability, old_cap) < 0:
            raise ValueError('negative budget or liability is invalid')

    @contextlib.contextmanager
    def locked(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with Path(str(self.path) + '.selection.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield
            fcntl.flock(lock, fcntl.LOCK_UN)

    def events(self):
        return [json.loads(s) for s in self.path.read_text().splitlines()] if self.path.exists() else []

    def _totals(self, events):
        reserved, settled = {}, {}
        for e in events:
            if e['event'] == 'RESERVED':
                if e['reservation_id'] in reserved:
                    raise ValueError('duplicate financial reservation')
                reserved[e['reservation_id']] = e
            elif e['event'] == 'SETTLED':
                if e['reservation_id'] in settled:
                    raise ValueError('duplicate settlement')
                settled[e['reservation_id']] = e
        total, trial = self.opening, 0
        for key, e in reserved.items():
            if key in settled:
                value = nanodollars(settled[key]['actual_cost_usd'])
            else:
                value = nanodollars(e['maximum_cost_usd'])
            if value < 0:
                raise ValueError('negative financial amount')
            total += value
            if e.get('selection_trial') == self.trial:
                trial += value
        return total, trial, reserved, settled

    def _append(self, e):
        with self.path.open('a') as f:
            f.write(canonical(e) + '\n'); f.flush(); os.fsync(f.fileno())

    def reserve(self, reservation_id, amount, binding):
        with self.locked():
            total, trial, reserved, _ = self._totals(self.events())
            if reservation_id in reserved:
                raise ValueError('attempt already reserved; no automatic retry')
            if amount < 0 or trial + amount > self.trial_cap:
                raise ValueError('trial pre-reservation budget exhausted')
            if total - self.baseline + self.external_liability + amount > self.shared_cap:
                raise ValueError('shared follow-up budget exhausted')
            if total + self.external_liability + amount > self.old_cap:
                raise ValueError('older programme cap exhausted')
            self._append(dict(event='RESERVED', reservation_id=reservation_id,
                maximum_cost_usd=usd(amount), selection_trial=self.trial,
                stage='pmrl1-smallpool', call_class='PRIMARY', logical_call_id=reservation_id,
                call_hash=reservation_id, provider='DeepSeek official API', model='deepseek-flash',
                hard_cap_usd='50', opening_cost_usd=usd(self.opening),
                binding=binding, timestamp=time.time(), protocol='pmrl1-selection-reservation-v1'))

    def settle(self, reservation_id, actual, outcome):
        # Missing usage is NOT a zero-cost settlement, including HTTP/timeout failures.
        if actual is None:
            return False
        with self.locked():
            _, _, reserved, settled = self._totals(self.events())
            if reservation_id not in reserved or reservation_id in settled or actual < 0:
                raise ValueError('invalid settlement')
            self._append(dict(event='SETTLED', reservation_id=reservation_id,
                actual_cost_usd=usd(actual), outcome=outcome, timestamp=time.time(),
                selection_trial=self.trial, protocol='pmrl1-selection-reservation-v1'))
            return actual <= nanodollars(reserved[reservation_id]['maximum_cost_usd'])


def measured(plan, req, raw):
    from adapters import final_content
    item = plan['items'][req['item_key']]
    try:
        content, finish = final_content(raw)
    except (KeyError, ValueError, TypeError) as e:
        return dict(measurement_status='technical_failure', q=None, m=None,
                    candidate_utility=None, error=str(e), reward_eligible=False)
    return judge.parse_completion(content, reply=item['reply'], evidence=item['evidence'],
        runtime_identity=req['configuration_identity'], draw_id=req['request_id'], finish_reason=finish)


def verify_approval(plan, candidate, phase, approval):
    if approval.get('status') != 'APPROVED' or approval.get('plan_identity') != plan['identity']:
        raise ValueError('explicit approval for this exact plan is missing')
    c = config_for(plan, candidate)
    if c['identity'] not in approval.get('configuration_identities', []):
        raise ValueError('configuration not approved')
    if phase not in approval.get('phases', []) or phase not in STAGES:
        raise ValueError('phase not approved')
    if approval.get('old_calls') != 66 or approval.get('old_semantic_revision') != 1:
        raise ValueError('historical accounting must be retained')
    if not approval.get('confirmation_reference') or not approval.get('research_scope_unchanged'):
        raise ValueError('missing approval provenance or scope')
    if type(approval.get('new_calls_limit')) is not int or not 1 <= approval['new_calls_limit'] <= 160:
        raise ValueError('selection only supports at most 160 new starts; no recovery dispatch here')
    if type(approval.get('cumulative_calls_limit')) is not int or approval['cumulative_calls_limit'] > 226:
        raise ValueError('selection cumulative limit invalid')
    if approval['cumulative_calls_limit'] > 140 and not approval.get('call_cap_amendment_reference'):
        raise ValueError('old 140 cap cannot be silently raised')
    return c


def check_stage_gate(plan, candidate, phase, run_dir):
    if phase == 'engineering':
        return
    prior = 'engineering' if phase == 'development' else 'development'
    reqs = stage_requests(plan, candidate, prior)
    for r in reqs:
        p = run_dir / (r['request_id'] + '.result.json')
        if not p.exists():
            raise ValueError('prior phase incomplete: ' + prior)
        row = read(p)
        if row['request'] != r or row['mode'] != 'live':
            raise ValueError('mock or wrong identity cannot unlock live stage')
        if row['measurement']['measurement_status'] not in VALID:
            raise ValueError('prior phase has technical/parse failures')
    gate = read(run_dir / (prior + '.review.json'))
    if gate != dict(plan_identity=plan['identity'], configuration_identity=plan['configs'][candidate]['identity'],
                    phase=prior, disposition='proceed', reviewed_request_ids=[r['request_id'] for r in reqs]):
        raise ValueError('missing exact stage review; no automatic semantic clearance')


def live_preflight(plan, c, approval):
    # Does not load weights or read credentials. Must precede even transport construction.
    if c['backend'] == 'deepseek':
        if not os.environ.get('DEEPSEEK_API_KEY'):
            raise ValueError('credential not configured locally; do not print or paste it')
        for k in ('data_transfer_approved', 'exclusive_paid_writer_confirmed',
                  'provider_account_reconciled', 'price_and_capabilities_rechecked',
                  'service_data_conditions_acknowledged'):
            if approval.get(k) is not True:
                raise ValueError('live blocker: ' + k)
        if not approval.get('data_permission_evidence'):
            raise ValueError('missing specific data permission basis; generic agreement is insufficient')
        for k in ('account_available_usd', 'external_liability_usd', 'trial_cap_usd'):
            if approval.get(k) is None:
                raise ValueError('unknown funding: ' + k)
        if Decimal(approval['trial_cap_usd']) > 5:
            raise ValueError('proposal only permits at most $5; new review required')
        if Decimal(approval['account_available_usd']) < Decimal(approval['trial_cap_usd']):
            raise ValueError('account funds do not cover requested allocation')
        if not approval.get('provider_metadata_receipt'):
            raise ValueError('missing independently checked /models receipt')
        meta = read(approval['provider_metadata_receipt'])
        if not any(x.get('id') == 'deepseek-flash' and x.get('name') == 'DeepSeek-V4.1-Flash'
                   and x.get('context_window') == 1048576 and x.get('max_output_tokens') == 393216
                   for x in meta.get('data', [])):
            raise ValueError('provider alias/capability drift')
    else:
        path = Path(approval.get('local_model_path', '/missing-approved-model'))
        manifest_path = approval.get('local_snapshot_receipts',{}).get(c['identity'])
        if not manifest_path:
            raise ValueError('missing local weights/revision/length receipt')
        receipt = read(manifest_path)
        if receipt.get('revision') != c['revision'] or receipt.get('configuration_identity') != c['identity']:
            raise ValueError('local snapshot identity mismatch')
        if receipt.get('all_full_inputs_fit') is not True or receipt.get('output_reserve_tokens', 0) < 32768:
            raise ValueError('full legal input plus output reserve not verified')
        for name, expected in receipt['files'].items():
            q = (path / name).resolve()
            if not q.is_relative_to(path.resolve()) or sha(q) != expected:
                raise ValueError('local model artifact mismatch')
        if not any(n.endswith('.safetensors') for n in receipt['files']):
            raise ValueError('weights absent from revision receipt')
        expected = read(HERE / 'gemma_public_file_metadata.json')
        required = {x['rfilename'] for x in expected['files']}
        if set(receipt['files']) != required:
            raise ValueError('local snapshot receipt omits required official files')
        if receipt['files']['model.safetensors'] != next(x['lfs']['sha256'] for x in expected['files']
                                                       if x['rfilename']=='model.safetensors'):
            raise ValueError('local weight hash is not the fixed public revision')
        import importlib.metadata as md
        for name, version in c['packages'].items():
            if md.version(name) != version:
                raise ValueError('local package drift: ' + name)
        q = subprocess.check_output(['nvidia-smi', '--query-gpu=uuid,memory.free,utilization.gpu',
                                     '--format=csv,noheader,nounits'], text=True)
        row = next((s.split(',') for s in q.splitlines() if s.startswith(c['gpu_uuid'])), None)
        if row is None or int(row[1]) < 45000 or int(row[2]) != 0:
            raise ValueError('designated GPU not idle/free; never kill or switch devices')


def execute(plan, candidate, phase, run_dir, *, mode, approval=None, fail_at=None,
            request_ids=None, transport=None, readiness_checked=False, pool_root=None):
    """Serial dispatch. STOP is durable; recovery is a separately approved future action."""
    reqs = stage_requests(plan, candidate, phase)
    if request_ids is not None:
        if not set(request_ids).issubset({r['request_id'] for r in reqs}):
            raise ValueError('request subset violates phase/configuration')
        reqs=[r for r in reqs if r['request_id'] in request_ids]
    c = config_for(plan, candidate)
    run_dir = Path(run_dir)
    if mode == 'live':
        verify_approval(plan, candidate, phase, approval)
        check_stage_gate(plan, candidate, phase, run_dir)
        if not readiness_checked:live_preflight(plan, c, approval)
    run_dir.mkdir(parents=True, exist_ok=True)
    with (run_dir / '.dispatch.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (run_dir / 'STOP.json').exists():
            raise ValueError('previous failure stop; no automatic resume/retry')
        # Reject output mixing and protect against duplicate physical attempts across stages.
        marker = dict(plan_identity=plan['identity'], candidate=candidate,
                      configuration_identity=c['identity'], mode=mode)
        if (run_dir / 'binding.json').exists():
            if read(run_dir / 'binding.json') != marker:
                raise ValueError('run identity/mode mismatch')
        else:
            save(run_dir / 'binding.json', marker)
        if mode == 'mock':
            budget = Budget((Path(pool_root) if pool_root else run_dir) / 'mock_money.jsonl', trial=plan['identity'],
                trial_cap=nanodollars(5), shared_cap=nanodollars(20), baseline=0, opening=0)
            from adapters import MockTransport
            transport = transport or MockTransport(plan, fail_at=fail_at)
            max_starts = len(plan['requests'])
        else:
            budget = Budget(REPO / 'project/outputs/paper1_api_budget/cumulative_paid_api_budget.jsonl',
                trial=plan['identity'], trial_cap=nanodollars(approval.get('trial_cap_usd') or '0'),
                shared_cap=nanodollars(20), baseline=nanodollars('1.50724291'),
                opening=nanodollars('0.03079930'),
                external_liability=nanodollars(approval.get('external_liability_usd') or '0'))
            from adapters import DeepSeekTransport, GemmaTransport
            try:
                transport = transport or (DeepSeekTransport(c) if c['backend'] == 'deepseek'
                             else GemmaTransport(c, approval['local_model_path']))
            except Exception as exc:
                save(run_dir / 'STOP.json',dict(reason='runtime_load_failure',started_requests=0,
                                              error_type=type(exc).__name__))
                raise RuntimeError('runtime loading failed before any J dispatch') from None
            max_starts = approval['new_calls_limit']
        started = 0
        # This root is fixed for real runs so another --out cannot evade attempt count.
        run_root = HERE / 'live_runs' if mode == 'live' else Path(pool_root) if pool_root else run_dir
        for req in reqs:
            count = len(list(run_root.rglob('*.started.json')))
            if count >= max_starts or (mode == 'live' and OLD_STARTS + count >= approval['cumulative_calls_limit']):
                raise ValueError('pre-dispatch call ceiling reached')
            base = run_dir / req['request_id']
            if base.with_suffix('.started.json').exists():
                raise ValueError('already attempted; no automatic replay')
            messages, schema = payload(plan, req)
            amount = API_WORST if c['backend'] == 'deepseek' else 0
            reservation_id = 'pmrl1-smallpool:' + req['request_id']
            if amount:
                budget.reserve(reservation_id, amount, dict(plan=plan['identity'], request=req))
            save(base.with_suffix('.started.json'), dict(request=req, mode=mode, timestamp=time.time(),
                old_calls=OLD_STARTS, old_revision=OLD_REVISION, reservation_id=reservation_id))
            started += 1
            start = time.monotonic()
            raw, result, actual = None, None, None
            try:
                raw = transport.send(messages, schema, request=req, raw_path=base.with_suffix('.raw.json'))
                # save transport bytes before interpreting output; no repairs or selection.
                save(base.with_suffix('.response.json'), raw)
                if raw.get('request_identity') != req['request_id']:
                    raise ValueError('response/request binding mismatch')
                from adapters import billed_peak_nanodollars
                actual = billed_peak_nanodollars(raw) if amount else 0
                result = measured(plan, req, raw)
                if c['backend'] == 'deepseek':
                    service = {k: raw.get(k) for k in ('model', 'system_fingerprint')}
                    if mode == 'live' and service['model'] not in c['response_model_allowlist']:
                        raise ValueError('unexpected provider returned model identity')
                    fp = (run_root if pool_root else run_dir) / 'service_identity.json'
                    if fp.exists() and read(fp) != service:
                        raise ValueError('provider model/fingerprint changed')
                    if not fp.exists():
                        save(fp, service)
                    if not service['model'] or not raw.get('id') or not raw.get('created'):
                        raise ValueError('missing provider response identity')
                if amount and actual is None:
                    raise ValueError('usage missing; keep financial reservation')
            except Exception as exc:
                # Deliberately exclude exception text: HTTP errors can contain headers/credentials.
                result = dict(measurement_status='technical_failure', q=None, m=None,
                    candidate_utility=None, reward_eligible=False, error_type=type(exc).__name__,
                    error_reason=str(exc) if isinstance(exc, ValueError) else 'transport/runtime failure',
                    detail='See saved raw response/stream; no credential-bearing exception dump.')
            within = budget.settle(reservation_id, actual, result['measurement_status']) if amount else True
            row = dict(request=req, mode=mode, measurement=result, elapsed_seconds=time.monotonic()-start,
                started_unix=read(base.with_suffix('.started.json'))['timestamp'],
                accounted_peak_usd=None if actual is None else usd(actual), reservation_retained=bool(amount and actual is None))
            if raw:
                from adapters import token_accounting
                row['token_accounting']=token_accounting(raw)
                row['gpu_usage']={k:raw.get(k) for k in ('gpu_seconds','peak_allocated_bytes','peak_reserved_bytes')}
                row['provider_usage']=raw.get('usage')
            save(base.with_suffix('.result.json'), row)
            if result['measurement_status'] not in VALID or not within:
                save(run_dir / 'STOP.json', dict(request_id=req['request_id'],
                    reason=result['measurement_status'], budget_within_reservation=within,
                    remaining_not_dispatched=len(reqs)-started))
                break
        return dict(mode=mode, started=started, phase=phase, candidate=candidate,
                    stopped=(run_dir / 'STOP.json').exists(), real_calls=(started if mode == 'live' else 0))


def run_stage(plan,phase,root,*,mode,candidates=None,approval=None,failures=None):
    """Counterbalanced paired dispatch on the existing executor, one phase only.

    Single serial stream; one shared local model. A failed configuration is
    skipped thereafter, not retried; authorized peers still get their slots.
    """
    if phase not in STAGES:raise ValueError('forbidden phase')
    candidates=tuple(candidates or CANDIDATES)
    if not set(candidates).issubset(CANDIDATES) or len(set(candidates))!=len(candidates):
        raise ValueError('unknown or duplicate configuration')
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    rows=sorted([r for r in plan['requests'] if r['phase']==phase],key=lambda r:r['schedule_position'])
    scope=''.join(plan['configs'][c]['label'] for c in CANDIDATES if c in candidates)
    # AB can be approved before CD; distinct scope receipts preserve both starts.
    receipt_prefix=phase+'.'+scope
    save(root/(receipt_prefix+'.schedule.json'),dict(plan_identity=plan['identity'],mode=mode,
        candidates=candidates,request_ids=[r['request_id'] for r in rows],automatic_next_stage=False))
    blocked={};transports={};shared_local=None;attempts=[];loads=[];resident_start=None
    for candidate in candidates:
        try:
            if mode=='live':
                verify_approval(plan,candidate,phase,approval)
                check_stage_gate(plan,candidate,phase,root/candidate)
                live_preflight(plan,config_for(plan,candidate),approval)
        except Exception as exc:
            blocked[candidate]=str(exc) if isinstance(exc,ValueError) else type(exc).__name__
    for r in rows:
        candidate=r['candidate'];c=config_for(plan,candidate)
        if candidate not in candidates or candidate in blocked:
            attempts.append(dict(request_id=r['request_id'],candidate=candidate,started=False,
                reason=blocked.get(candidate,'not selected/authorized in this stage'),schedule_position=r['schedule_position']))
            continue
        try:
            if mode=='mock':
                from adapters import MockTransport
                if candidate not in transports:transports[candidate]=MockTransport(plan,(failures or {}).get(candidate))
                transport=transports[candidate]
            elif c['backend']=='gemma':
                from adapters import GemmaTransport
                if shared_local is None:
                    resident_start=time.monotonic()
                    shared_local=GemmaTransport(c,approval['local_model_path'])
                    loads.append(dict(backend='gemma',seconds=shared_local.load_seconds,
                                      attribution='one shared load for on/off modes, not duplicated'))
                if (shared_local.config['revision'],shared_local.config['model'])!=(c['revision'],c['model']):
                    raise ValueError('shared local model revision mismatch')
                transport=shared_local;transport.config=c
                transport.gpu_condition()
            else:
                from adapters import DeepSeekTransport
                transport=DeepSeekTransport(c)
            result=execute(plan,candidate,phase,root/candidate,mode=mode,approval=approval,
                request_ids=[r['request_id']],transport=transport,readiness_checked=True,pool_root=root)
            attempts.append(dict(request_id=r['request_id'],candidate=candidate,started=bool(result['started']),
                                 stopped=result['stopped'],schedule_position=r['schedule_position']))
            if result['stopped']:blocked[candidate]='technical failure; no automatic retry'
        except Exception as exc:
            blocked[candidate]=str(exc) if isinstance(exc,ValueError) else type(exc).__name__
            attempts.append(dict(request_id=r['request_id'],candidate=candidate,started=(root/candidate/(r['request_id']+'.started.json')).exists(),
                reason=blocked[candidate],schedule_position=r['schedule_position']))
    summary=dict(plan_identity=plan['identity'],mode=mode,phase=phase,attempts=attempts,
        blocked_configurations=blocked,loads=loads,started=sum(x['started'] for x in attempts),
        shared_GPU_residence_seconds=(time.monotonic()-resident_start) if resident_start is not None else None,
        GPU_residence_definition='shared local weights held across API slots; includes load and API waits, not duplicated per mode',
        next_phase_started=False,qualification='NOT_EVALUATED')
    save(root/(receipt_prefix+'.stage_result.json'),summary)
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='command', required=True)
    d = sub.add_parser('dry-run', help='verify dev-only plan and list phases; no model or network')
    d.add_argument('--candidate', choices=CANDIDATES, required=True)
    d.add_argument('--phase', choices=STAGES, required=True)
    m = sub.add_parser('mock', help='run offline transport, original parser and mock budget ledger')
    m.add_argument('--candidate', choices=CANDIDATES, required=True)
    m.add_argument('--phase', choices=STAGES, required=True)
    m.add_argument('--out', type=Path, required=True)
    m.add_argument('--fail-at', type=int)
    l = sub.add_parser('execute', help='legacy individual real entry disabled; use paired run-stage')
    l.add_argument('--candidate', choices=CANDIDATES, required=True)
    l.add_argument('--phase', choices=STAGES, required=True)
    l.add_argument('--approval', type=Path, required=True)
    l.add_argument('--execute-live', action='store_true', required=True)
    st=sub.add_parser('run-stage',help='counterbalanced four-configuration stage; defaults to mock')
    st.add_argument('--phase',choices=STAGES,required=True)
    st.add_argument('--candidates',nargs='+',choices=CANDIDATES)
    st.add_argument('--out',type=Path,help='mock output directory; forbidden for live')
    st.add_argument('--approval',type=Path)
    st.add_argument('--execute-live',action='store_true')
    a = ap.parse_args()
    plan = load_plan()
    if a.command == 'dry-run':
        rs = stage_requests(plan, a.candidate, a.phase)
        for r in rs:
            payload(plan, r)
        print(json.dumps(dict(plan_identity=plan['identity'], candidate=a.candidate, phase=a.phase,
            requests=len(rs), real_calls=0, sealed_access=False,
            max_single_reservation_usd=usd(API_WORST) if a.candidate.startswith('deepseek') else '0',
            request_ids=[r['request_id'] for r in rs]), indent=2))
    elif a.command == 'mock':
        print(json.dumps(execute(plan, a.candidate, a.phase, a.out, mode='mock', fail_at=a.fail_at)))
    elif a.command=='execute':
        raise ValueError('individual live entry retired for paired design; use run-stage')
    elif a.execute_live:
        if a.out or not a.approval:raise ValueError('live requires approval and uses fixed live_runs')
        # One lock and one fixed root protect the pool-level limit across both candidates.
        root = HERE / 'live_runs'; root.mkdir(exist_ok=True)
        with (root / '.pool.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result=run_stage(plan,a.phase,root,mode='live',candidates=a.candidates,approval=read(a.approval))
            print(json.dumps({k:result[k] for k in ['started','blocked_configurations','phase','mode']}))
    else:
        if not a.out:raise ValueError('mock requires a fresh --out')
        result=run_stage(plan,a.phase,a.out,mode='mock',candidates=a.candidates)
        print(json.dumps({k:result[k] for k in ['started','blocked_configurations','phase','mode']}))


if __name__ == '__main__':
    main()
