#!/usr/bin/env python3
"""Refresh one balance receipt, retaining old liabilities and all spending caps."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import time

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT/'src'))
from metacom_pm.rl1 import account_balance_refresh as refresh
from metacom_pm.rl1.calibration_workflow import stamp
from metacom_pm.rl1.development_dispatch import DeepSeekStageTransport, require_approval, sha
from metacom_pm.rl1.development_feedback import save_once, thaw_inputs
from metacom_pm.rl1.development_preflight import ensure_preflight, visible_paid_writers
from metacom_pm.rl1.retained_liability_continuation import RetainedDevelopmentStage
from metacom_pm.rl1.schema import digest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['prepare', 'check', 'execute'])
    for name in ('package', 'approval', 'isolation', 'output'):
        p.add_argument('--'+name, type=Path, required=True)
    a = p.parse_args(); package = a.package.resolve(); output = a.output.resolve()
    for name, expected in json.loads((package/'PACKAGE_MANIFEST.json').read_text()).items():
        if Path(name).is_absolute() or '..' in Path(name).parts or sha(package/name) != expected:
            raise ValueError('original package changed')
    config = json.loads((package/'J_CONFIG_PRIVATE.json').read_text())
    approval = json.loads(a.approval.read_text()); isolation = json.loads(a.isolation.read_text())
    require_approval(config['protocol_identity'], config['policy'], approval)
    materials, adapter = thaw_inputs(config['inputs'])
    args = dict(ledger=config['ledger'], policy=config['policy'], approval=approval, isolation=isolation)
    if a.mode == 'prepare':
        stage = RetainedDevelopmentStage(config['policy']['run_directory'], materials, adapter, **args)
        output.mkdir(parents=True, mode=0o700, exist_ok=False)
        with stage.budget.legacy_lease(), stage.budget.locked():
            stage.budget._history()
            preflight = json.loads((stage.root/'management/PREFLIGHT.json').read_text())
            snapshot = refresh.snapshot_fields(stage.budget)
            if snapshot['trial_nanodollars']-preflight['opening_trial_nanodollars']+stage.policy['reserve_nanodollars'] <= preflight['available_nanodollars']:
                raise ValueError('original account snapshot is not the blocking constraint')
            if visible_paid_writers(): raise ValueError('visible concurrent paid writer')
            key = os.environ.get('DEEPSEEK_API_KEY')
            if not key or hashlib.sha256(key.encode()).hexdigest() != preflight['credential_fingerprint']:
                raise ValueError('original authorized credential required')
            import urllib.request
            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, *args, **kwargs): return None
            endpoint = 'https://api.deepseek.com/user/balance'
            save_once(output/'balance.started.json', dict(endpoint=endpoint, timestamp=time.time(),
                stage_identity=stage.identity, reason='original account availability exhausted; no settlement inference'))
            request = urllib.request.Request(endpoint, headers={'Authorization': 'Bearer '+key})
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect)
            with opener.open(request, timeout=30) as response: raw = response.read()
            balance = json.loads(raw); (output/'balance.raw.json').write_bytes(raw)
            available = refresh.available_nanodollars(balance)
            paths = [output/'balance.raw.json', Path(refresh.__file__), Path(__file__), a.approval,
                     a.isolation, stage.root/'management/PREFLIGHT.json', package/'J_CONTINUATION_20261103.log']
            record = stamp(dict(status=refresh.STATUS, stage_identity=stage.identity,
                financial_policy_identity=digest(stage.policy), isolation_identity=isolation['identity'],
                credential_fingerprint=preflight['credential_fingerprint'], balance_path=str(output/'balance.raw.json'),
                available_nanodollars=available, **snapshot, new_allowance=0, settlement_changes=0,
                management_requests=1, captured_unix=time.time(),
                source_hashes={str(path.resolve()): sha(path) for path in paths}))
            refresh.validate_refresh(record, stage.budget)
            save_once(output/'REFRESH.json', record)
        print(json.dumps(dict(status='ACCOUNT_REFRESH_PREPARED', available_nanodollars=available,
            outstanding_nanodollars=snapshot['outstanding_nanodollars'], new_allowance=0)), flush=True)
        return
    record = json.loads((output/'REFRESH.json').read_text())
    stage = refresh.RefreshedDevelopmentStage(config['policy']['run_directory'], materials, adapter, refresh=record, **args)
    stage.budget._history()
    print(json.dumps(dict(status='ACCOUNT_REFRESH_CHECKED', refresh_identity=record['identity'], new_allowance=0)), flush=True)
    if a.mode == 'check': return
    with stage.budget.legacy_lease():
        preflight = ensure_preflight(stage)
        transport = DeepSeekStageTransport(stage.root/'wire', timeout_seconds=adapter.config['timeout_seconds'],
            credential_fingerprint=preflight['credential_fingerprint'])
        while True:
            result = stage.advance(transport)
            print(json.dumps({k: result[k] for k in ('status','component','outcome','ordinal','physical_attempts','accounted_usd','unknown_liabilities') if k in result}), flush=True)
            if result['status'] == 'CLOSED_DEVELOPMENT_NOT_QUALIFIED': return
            if result['status'] == 'RECONCILIATION_REQUIRED': raise SystemExit(2)


if __name__ == '__main__': main()
