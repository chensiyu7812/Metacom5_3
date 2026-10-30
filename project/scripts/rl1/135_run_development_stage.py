#!/usr/bin/env python3
"""Check offline, or explicitly run the finite S/A/R development stage.

This does not run selected-route qualification, issue a qualified receipt, or
assign humans. No credential, public pricing or management query on check.
"""
import argparse
import json
from pathlib import Path
import sys

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.development_feedback import thaw_inputs
from metacom_pm.rl1.development_dispatch import PaidDevelopmentStage, DeepSeekStageTransport, require_approval
from metacom_pm.rl1.development_preflight import ensure_preflight
from metacom_pm.rl1 import diagnostic_support as money


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--package',required=True,type=Path)
    p.add_argument('--execute',action='store_true')
    p.add_argument('--approval',type=Path)
    a=p.parse_args();root=a.package.resolve()
    manifest=json.loads((root/'PACKAGE_MANIFEST.json').read_text())
    for name,h in manifest.items():
        if Path(name).is_absolute() or '..' in Path(name).parts or sha256_file(root/name)!=h:
            raise ValueError('fixed package changed')
    c=json.loads((root/'J_CONFIG_PRIVATE.json').read_text())
    approval=json.loads(a.approval.read_text()) if a.approval else None
    if a.execute:require_approval(c['protocol_identity'],c['policy'],approval)
    materials,adapter=thaw_inputs(c['inputs'])
    stage=PaidDevelopmentStage(root/'live_J',materials,adapter,ledger=c['ledger'],policy=c['policy'],approval=approval)
    if stage.identity!=c['protocol_identity']:raise ValueError('stage identity changed')
    stage.budget._history()
    _,trial,reserved,settled=stage.budget._totals(stage.budget.events())
    print(json.dumps(dict(status='STATIC_CHECKED',protocol_identity=stage.identity,materials=len(materials),
        max_attempts=stage.policy['max_attempts'],trial_accounted_usd=money.usd(trial),
        unresolved_liabilities=len(set(reserved)-set(settled)),network_requests=0,qualification_granted=False)),flush=True)
    if not a.execute:return
    if (stage.root/'CLOSED.json').exists():
        print(json.dumps(dict(status='ALREADY_CLOSED',network_requests=0)),flush=True);return
    with stage.budget.legacy_lease():
        receipt=ensure_preflight(stage)
        transport=DeepSeekStageTransport(stage.root/'wire',timeout_seconds=adapter.config['timeout_seconds'],
            credential_fingerprint=receipt['credential_fingerprint'])
        while True:
            result=stage.advance(transport)
            # Replies, evidence and provisional scores remain in private files.
            print(json.dumps({k:result[k] for k in ('status','component','outcome','ordinal','physical_attempts',
                'accounted_usd','qualified_receipt') if k in result}),flush=True)
            if result['status']=='CLOSED_DEVELOPMENT_NOT_QUALIFIED':return
            if result['status']=='RECONCILIATION_REQUIRED':raise SystemExit(2)


if __name__=='__main__':main()
