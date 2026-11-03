#!/usr/bin/env python3
"""Freeze/check/execute a single known-unknown isolation within the old scope.

No new allowance, no request retry, no zero-charge settlement. Execute requires
the original stage approval; all old paid/source/protocol identities persist.
"""
import argparse
import json
from pathlib import Path
import sqlite3
import sys

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.rl1.calibration_workflow import stamp
from metacom_pm.rl1.development_feedback import thaw_inputs
from metacom_pm.rl1.development_dispatch import PaidDevelopmentStage,DeepSeekStageTransport,require_approval,sha
from metacom_pm.rl1.development_preflight import ensure_preflight
from metacom_pm.rl1 import retained_liability_continuation as continuation
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.supervised_learning import save_json


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=['prepare','check','execute'])
    p.add_argument('--package',type=Path,required=True);p.add_argument('--approval',type=Path,required=True)
    p.add_argument('--record',type=Path,required=True);p.add_argument('--attempt-id')
    a=p.parse_args();package=a.package.resolve()
    for name,h in json.loads((package/'PACKAGE_MANIFEST.json').read_text()).items():
        if Path(name).is_absolute() or '..' in Path(name).parts or sha(package/name)!=h:raise ValueError('original package changed')
    c=json.loads((package/'J_CONFIG_PRIVATE.json').read_text());approval=json.loads(a.approval.read_text())
    require_approval(c['protocol_identity'],c['policy'],approval)
    materials,adapter=thaw_inputs(c['inputs']);root=Path(c['policy']['run_directory'])
    if a.mode=='prepare':
        old=PaidDevelopmentStage(root,materials,adapter,ledger=c['ledger'],policy=c['policy'],approval=approval)
        with old.budget.legacy_lease():
            old.budget._history();found=[]
            for component in ('S','A','R'):
                dbpath=root/component/'attempts.sqlite'
                if not dbpath.exists():continue
                with sqlite3.connect('file:'+str(dbpath)+'?mode=ro',uri=True) as db:
                    found += [(component,json.loads(v)) for (v,) in db.execute('SELECT claim FROM attempts WHERE result IS NULL')]
            if len(found)!=1 or found[0][1]['attempt_id']!=a.attempt_id:raise ValueError('exactly the reviewed unknown attempt required')
            component,claim=found[0];aid=claim['attempt_id']
            paths=[root/'wire'/(aid+'.sse'),Path(continuation.__file__),Path(__file__),a.approval,
                   package/'J_CONFIG_PRIVATE.json',package/'J_EXECUTION_20261103.log']
            record=stamp(dict(status=continuation.STATUS,stage_identity=old.identity,
                financial_policy_identity=digest(c['policy']),run_directory=str(root.resolve()),
                component=component,attempt_id=aid,claim_identity=digest(claim),logical_slot=claim['slot_id'],
                source_hashes={str(x.resolve()):sha(x) for x in paths},new_allowance=0,retry_isolated_request=False,
                implementation_scope='continue other frozen independent slots under the existing 82-attempt/shared-$6 authorization; hold all unknown liability',
                original_authorization_record=approval['researcher_authorization_record'],
                original_authorization_sha256=approval['researcher_record_sha256']))
            continuation.validate_isolation(record,stage_identity=old.identity,policy=c['policy'])
            save_json(a.record,record)
        print(json.dumps(dict(status='ISOLATION_PREPARED',identity=record['identity'],new_calls=0,new_allowance=0)),flush=True)
        return
    record=json.loads(a.record.read_text())
    stage=continuation.RetainedDevelopmentStage(root,materials,adapter,ledger=c['ledger'],policy=c['policy'],approval=approval,isolation=record)
    stage.budget._history()
    print(json.dumps(dict(status='RETAINED_LIABILITY_CHECKED',same_stage_identity=stage.identity,
        continuation_identity=record['identity'],max_attempts=stage.policy['max_attempts'],new_allowance=0)),flush=True)
    if a.mode=='check':return
    with stage.budget.legacy_lease():
        preflight=ensure_preflight(stage)
        transport=DeepSeekStageTransport(root/'wire',timeout_seconds=adapter.config['timeout_seconds'],
            credential_fingerprint=preflight['credential_fingerprint'])
        while True:
            result=stage.advance(transport)
            print(json.dumps({k:result[k] for k in ('status','component','outcome','ordinal','physical_attempts','accounted_usd','unknown_liabilities') if k in result}),flush=True)
            if result['status']=='CLOSED_DEVELOPMENT_NOT_QUALIFIED':return
            if result['status']=='RECONCILIATION_REQUIRED':raise SystemExit(2)


if __name__=='__main__':main()
