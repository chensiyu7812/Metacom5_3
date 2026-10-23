#!/usr/bin/env python3
"""Freeze the base comparison inputs before observing the new executor pool."""
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'src'))
from metacom_pm.io import sha256_file
OUT = PROJECT / 'outputs/pm_rl1/completion_20260930_v2/P2/common_pool'


def main():
    target = OUT / 'secondary_inputs_private.json'
    if target.exists():
        raise RuntimeError('secondary inputs already frozen')
    freeze = json.loads((OUT / 'input_freeze.json').read_text())
    for name, expected in freeze['files'].items():
        assert sha256_file(OUT / name) == expected, name
    slots = json.loads((OUT / 'slots_private.json').read_text())
    plans = [[0, 0, 0, 0], [1, 0, 0, 0], [0, 0, 1, 1]]
    rows = [r for r in slots['rows'] if r['split'] == 'dev' and r['counts'] in plans]
    missing = [r for r in slots['unavailable'] if r['split'] == 'dev' and r['counts'] in plans]
    assert len(rows) + len(missing) == 54
    result = dict(status='INPUTS_ONLY_CONDITIONAL_ON_PRIMARY_ADAPTER_SELECTION',
        plans=plans, selection='OFF, one RS, first memory-only mixed plan in the frozen global menu (one MS plus one ME); no quality selection or unavailable replacement',
        rows=rows, unavailable=missing, legal_slots=len(rows), nominal_slots=54,
        generation_calls=0, API_usd=0,
        source_files={str(p.relative_to(PROJECT)): sha256_file(p) for p in
            [OUT / 'input_freeze.json', OUT / 'slots_private.json', Path(__file__)]})
    with target.open('x') as f:
        f.write(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(dict(legal=len(rows), unavailable=len(missing), generated=0)))


if __name__ == '__main__':
    main()
