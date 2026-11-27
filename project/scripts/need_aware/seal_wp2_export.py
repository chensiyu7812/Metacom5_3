#!/usr/bin/env python3
"""Seal a read-only snapshot of B outputs for A, without loading gold or models."""
import argparse
import json
import os
from metacom_pm.need_aware.evaluation.export import seal_export

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('manifest-dir', 'ledger-root', 'out'):
        p.add_argument('--'+name, required=True)
    p.add_argument('--kind', choices=['model', 'plumbing'], required=True)
    p.add_argument('--final', action='store_true', help='terminal run summary required; otherwise an intermediate snapshot')
    a = p.parse_args(); os.umask(0o077)
    s = seal_export(a.manifest_dir, a.ledger_root, a.out, kind=a.kind, final=a.final)
    print(json.dumps({k: s[k] for k in ('result_kind', 'final', 'manifest_sha256', 'ledger_head_sha256', 'physical_calls', 'failed_attempt_events')}, indent=2))
