#!/usr/bin/env python3
"""Execute only the frozen, bounded Claude pilot; default is offline preflight."""
import argparse
from contextlib import ExitStack
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
import time

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT/'src'))
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.claude_delivery import parse_message
from metacom_pm.rl1.claude_trial import VERSION, Transport, budget_class, nominal_nanodollars
from metacom_pm.rl1.recovery_schedule import RecoverySchedule, Slot

BASE = PROJECT/'outputs/pm_rl1/judge_selection_preparation_20261014_v1'
DEFAULT = PROJECT/'outputs/pm_rl1/claude_pilot_20261022_v1'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    with Path(path).open('x') as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n');f.flush();os.fsync(f.fileno())
    Path(path).chmod(0o600)


def engine():
    sys.path.insert(0, str(BASE/'paired_diagnostic_20261019_v1'))
    import paired
    return paired


def preflight(root):
    pr, auth = read(root/'protocol.json'), read(root/'authorization.json')
    if pr['identity'] != digest({k:v for k,v in pr.items() if k!='identity'}):
        raise ValueError('protocol drift')
    if (auth.get('status') != 'APPROVED_BOUNDED_TRY' or auth.get('protocol_identity') != pr['identity']
            or auth.get('user_quote') != '可以先尝试一下，然后再看看如何去使用这个Claude，然后，按计划推进。'):
        raise ValueError('no bound user authorization')
    if (pr['version'] != VERSION or pr['limits'] != dict(primary_inputs=10,max_attempts=12,
            recovery_cap=2,stage_usd='6',trial_usd='7.9058232',shared_usd='20',
            baseline_attempts=307,max_cumulative=319,active_capacity=374)
            or pr['reserve_usd'] != '3.28' or pr['qualifies_reward'] or pr['training_authorized']):
        raise ValueError('pilot scope changed')
    for path, expected in pr['immutable_files'].items():
        if sha(path) != expected:
            raise ValueError('immutable pilot code/input drift')
    ledger = Path(pr['ledger']['path'])
    if hashlib.sha256(ledger.read_bytes()[:pr['ledger']['bytes']]).hexdigest() != pr['ledger']['sha256']:
        raise ValueError('historical money prefix changed')
    prepared = read(pr['prepared_file'])
    originals = read(pr['original_file'])
    items = {x['key']:x for x in read(pr['material_file'])}
    lookup = {x['identity']: x for x in prepared}
    original_lookup = {x['identity']:x for x in originals}
    for slot in pr['slots']:
        request = lookup[slot['input_identity']]
        original = original_lookup[request['source_primary_identity']]
        data = json.loads(request['wire_body']['messages'][0]['content'])
        item = items[slot['slot_id']]
        if (data['reply'] != item['reply'] or data['legal_evidence'] != item['evidence']
                or digest(item['reply']) != request['response_identity']
                or digest(item['evidence']) != request['evidence_identity']
                or original['local_schema'] != pr['schemas'][slot['slot_id']]):
            raise ValueError('full source/reply/schema delivery drift')
    return pr, auth, lookup, items


def execute(pr, root, lookup, items, budget, transport, validate, guard, *, mode):
    """All live access is in main after authorization; synthetic tests inject IO."""
    run = root/mode
    run.mkdir(parents=True, exist_ok=True, mode=0o700)
    if (run/'CLOSED.json').exists():
        return read(run/'CLOSED.json')
    slots = [Slot(**x) for x in pr['slots']]
    queue = RecoverySchedule(run/'schedule.sqlite', slots, protocol_identity=pr['identity'],
        max_attempts=pr['limits']['max_attempts'], recovery_cap=pr['limits']['recovery_cap'])
    reserve_amount = engine().s.nanodollars(pr['reserve_usd'])
    stop = None
    def reserve(claim):
        guard()
        budget.reserve(claim['attempt_id'], reserve_amount, claim | dict(study=VERSION))
        return dict(attempt_id=claim['attempt_id'], reservation_identity=digest(claim))
    _, _, reservations, settlements = budget._totals(budget.events())
    own = {k for k,v in reservations.items() if v.get('binding',{}).get('study')==VERSION}
    recorded = {r['claim']['attempt_id'] for r in queue.report()['attempts_log']}
    if own != recorded or set(reservations)-set(settlements):
        stop = 'UNKNOWN_START_OR_SETTLEMENT_RECONCILE'
    while not stop:
        try:
            claim = queue.claim_next(reserve)
        except ValueError as exc:
            stop = 'PRE_DISPATCH:' + str(exc)
            break
        if claim is None:
            break
        sid, aid = claim['slot_id'], claim['attempt_id']
        prepared = lookup[claim['input_identity']]
        save(run/(aid+'.started.json'), dict(claim=claim, mode=mode, utc_unix=time.time()))
        save(run/(aid+'.request.json'), prepared)
        actual, evaluation, outcome = None, None, 'global_risk'
        message = None
        try:
            raw = transport.send(prepared, run/(aid+'.sse'))
            save(run/(aid+'.raw.json'), raw)
            if raw['http_status'] == 200:
                message = raw['message']
                actual = nominal_nanodollars(message)
                try:
                    def semantic(value):
                        nonlocal evaluation
                        evaluation = validate(value, items[sid], claim)
                    value = parse_message(message, prepared, pr['schemas'][sid], semantic)
                    outcome = 'semantic_unknown' if value['status']=='uncertain' else 'valid'
                except Exception as exc:
                    outcome = 'format_failure' if isinstance(exc, json.JSONDecodeError) else 'schema_failure'
                    if message.get('stop_reason') in ('refusal','max_tokens'):
                        outcome = 'unavailable'
                    evaluation = dict(error_type=type(exc).__name__, error=str(exc), reward_eligible=False)
                if message.get('unrecognized_events'):
                    outcome = 'global_risk'
            elif raw['http_status'] in (400,401,402,403,404,413,422,429):
                # Explicit rejection, no generated message: official failed-request
                # billing policy; not the policy for timeout/disconnected streams.
                actual, outcome = 0, 'unavailable'
                stop = 'EXPLICIT_PROVIDER_REJECTION_' + str(raw['http_status'])
            else:
                stop = 'UNKNOWN_SERVER_FAILURE_COST'
        except Exception as exc:
            save(run/(aid+'.exception.json'), dict(error_type=type(exc).__name__,
                settlement_unknown=True, automatic_retry=False))
            stop = 'UNKNOWN_DELIVERY_OR_COST'
        settled_ok = budget.settle(aid, actual, outcome)
        if actual is None or not settled_ok:
            outcome = 'global_risk'
            stop = stop or 'UNKNOWN_OR_EXCESS_LIABILITY'
        identity_ok = message is None or message.get('model') == prepared['wire_body']['model']
        if not identity_ok:
            outcome, stop = 'global_risk', 'PROVIDER_MODEL_DRIFT'
        result = dict(attempt_id=aid,slot_id=sid,ordinal=claim['ordinal'],outcome=outcome,
            evaluation=evaluation,cost_usd=None if actual is None else engine().s.usd(actual),
            nominal_cost_not_verified_credit_redemption=True, reward_eligible=False)
        save(run/(aid+'.result.json'), result)
        queue.settle(aid,outcome=outcome,input_identity=claim['input_identity'],
            config_identity=claim['config_identity'] if identity_ok else 'DRIFT',
            settlement_identity=digest(dict(aid=aid,actual=actual)) if actual is not None else None,
            result_identity=digest(result),settled=actual is not None)
        seal = {p.name:sha(p) for p in run.glob(aid+'.*') if p.is_file()}
        save(run/(aid+'.seal.json'), seal)
        print(json.dumps(dict(slot=sid,attempt=claim['ordinal'],outcome=outcome,cost_usd=result['cost_usd'])),flush=True)
    report = queue.report()
    total, trial, reserved, settled = budget._totals(budget.events())
    report.update(status='PILOT_CLOSED',stop_reason=stop or report['global_stop'],mode=mode,
        cumulative_attempts=pr['limits']['baseline_attempts']+report['attempts'],
        stage_cost_or_liability_usd=engine().s.usd(budget.stage_total(reserved,settled)),
        shared_followup_usd=engine().s.usd(total-budget.baseline),trial_usd=engine().s.usd(trial),
        unsettled_reservations=len(set(reserved)-set(settled)), qualification_granted=False,
        natural_updates=0,unstarted_slots=[k for k,v in report['states'].items() if v=='READY'])
    save(run/'CLOSED.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--root',type=Path,default=DEFAULT)
    parser.add_argument('--live',action='store_true')
    args=parser.parse_args()
    pr,auth,lookup,items=preflight(args.root)
    if not args.live:
        print(json.dumps(dict(status='BOUND_PILOT_READY',limits=pr['limits'],new_calls=0)));return
    os.umask(0o077)
    p=engine()
    from deepseek_access import visible_paid_writers
    ledger=Path(pr['ledger']['path'])
    with ExitStack() as stack:
        for path in (BASE/'live_runs/.pool.lock',ledger.with_suffix('.lock'),args.root/'.launch.lock'):
            path.parent.mkdir(exist_ok=True)
            lock=stack.enter_context(path.open('a'));fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        budget=budget_class(p)(ledger,trial=pr['ledger']['trial_identity'],study=VERSION,
            stage_cap=p.s.nanodollars('6'),trial_cap=p.s.nanodollars('7.9058232'),shared_cap=p.s.nanodollars('20'),
            baseline=p.s.nanodollars('1.50724291'),opening=p.s.nanodollars('.03079930'))
        def guard():
            preflight(args.root)
            if visible_paid_writers():raise ValueError('another visible paid writer')
            suffix=ledger.read_bytes()[pr['ledger']['bytes']:].decode()
            for line in suffix.splitlines():
                e=json.loads(line)
                if e.get('selection_trial')!=pr['ledger']['trial_identity']:
                    raise ValueError('foreign ledger writer')
                if e['event']=='RESERVED' and e.get('binding',{}).get('study')!=VERSION:
                    raise ValueError('foreign stage writer')
        guard()
        def validate(value,item,claim):
            result=p.s.judge.parse_completion(json.dumps(value,ensure_ascii=False),reply=item['reply'],
                evidence=item['evidence'],runtime_identity=claim['config_identity'],
                draw_id=claim['attempt_id'],finish_reason='natural_stop')
            if result['measurement_status'] not in p.s.VALID:
                raise ValueError('existing bound score/source validator rejected output')
            return result
        key=None
        for line in Path('/home/tokkio/metacom5_3.env').read_text().splitlines():
            name,sep,value=line.partition('=')
            if sep and name.strip().removeprefix('export ').strip()=='ANTHROPIC_API_KEY':
                key=value.strip()
                if len(key)>1 and key[0]==key[-1] and key[0] in ('"',"'"):key=key[1:-1]
                break
        report=execute(pr,args.root,lookup,items,budget,Transport(key),validate,guard,mode='live')
        print(json.dumps({k:v for k,v in report.items() if k not in ('attempts_log','states')},ensure_ascii=False))


if __name__=='__main__':main()
