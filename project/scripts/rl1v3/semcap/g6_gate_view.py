#!/usr/bin/env python3
"""Compact private view of screening replies next to the frozen checks (for the gate review)."""
import json, sys
from pathlib import Path

run, checks = Path(sys.argv[1]), Path(sys.argv[2])
ck = {c['state_id']: c for c in json.loads(checks.read_text())['checks']}
for l in (run / 'RESULTS.private.jsonl').read_text().splitlines():
    r = json.loads(l)
    if r['phase'] != 'screen' or (len(sys.argv) > 3 and r['state_id'] not in sys.argv[3:]): continue
    c = ck[r['state_id']]
    print(f"== {r['state_id']} {c['dataset']} {c['owner_id'] or ''} {c['family_id']}  finish={r.get('reply_finish')} err={r['error']}")
    print('   NOT:', ' | '.join(c['must_not']))
    print('   SHOULD:', ' | '.join(c['should']))
    print('   A:', (r.get('reply') or '').replace('\n', ' '))
