#!/usr/bin/env python3
"""Check offline, or explicitly execute the fixed G-only comparison package."""
import argparse
import json
from pathlib import Path
import sys

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.resource_comparison_runner import FixedResourceComparison, authorize
from metacom_pm.rl1.local_backend import check_static


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
    protocol=json.loads((root/'G_PROTOCOL.json').read_text())
    requests=json.loads((root/'G_REQUESTS_PRIVATE.json').read_text())
    approval=json.loads(a.approval.read_text()) if a.approval else None
    if a.execute:authorize(protocol,approval)  # Before hardware/model work.
    runner=FixedResourceComparison(protocol,requests,root/'live_G',approval=approval)
    checked=check_static(protocol)
    print(json.dumps(dict(status='STATIC_CHECKED',protocol_identity=protocol['identity'],requests=len(requests),
        reused_OFF=6,API_calls=0,**checked)),flush=True)
    if not a.execute:return
    while True:
        result=runner.step();print(json.dumps(result),flush=True)
        if result['status']=='CLOSED_FIXED_COMPARISON':return
        if result['status']=='RECONCILIATION_REQUIRED':raise SystemExit(2)


if __name__=='__main__':main()
