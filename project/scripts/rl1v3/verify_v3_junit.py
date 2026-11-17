#!/usr/bin/env python3
"""Fail closed on missing/failing/skipped V3 acceptance, including pytest xfail."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def verify(path: Path) -> dict:
    cases = list(ET.parse(path).getroot().iter('testcase'))
    if not cases:
        raise ValueError('V3 acceptance report has no test cases')
    identities = []
    for case in cases:
        classname = case.get('classname', '')
        if not any(part.startswith('test_rl1v3_') for part in classname.split('.')):
            raise ValueError('unexpected or collection-error testcase: ' + classname)
        identity = classname + '::' + case.get('name', '')
        identities.append(identity)
        if any(case.find(tag) is not None for tag in ('failure', 'error', 'skipped')):
            raise ValueError('V3 test did not pass (skip/xfail forbidden): ' + identity)
    if len(set(identities)) != len(identities):
        raise ValueError('duplicate V3 testcase identity')
    return dict(protocol='pmrl1v3-integration-junit-gate-v1', tests=len(cases), passed=len(cases),
        failures=0, errors=0, skipped=0, xfailed=0,
        junit_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        testcase_ids_sha256=hashlib.sha256(json.dumps(sorted(identities),ensure_ascii=False,separators=(',',':')).encode()).hexdigest())


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report',type=Path)
    parser.add_argument('--out',type=Path)
    args=parser.parse_args()
    result=verify(args.report)
    encoded=json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2)+'\n'
    if args.out:
        args.out.write_text(encoded)
    print(encoded,end='')


if __name__ == '__main__':
    main()
