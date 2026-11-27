#!/usr/bin/env python3
"""Add the speaker-scoped arm to an existing claim-support run (same models, thresholds)."""
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'src'))
from metacom_pm.rl1v3.semcap.claim_support import render_scoped, structured_reporter, MiniCheckFT5, DebertaNLI, combine, metrics
p = argparse.ArgumentParser()
p.add_argument('--sets', nargs='+', required=True); p.add_argument('--nli', required=True)
p.add_argument('--minicheck', required=True); p.add_argument('--base', required=True); p.add_argument('--threads', type=int, default=8)
a = p.parse_args()
import torch; torch.set_num_threads(a.threads)
base = Path(a.base); nli = DebertaNLI(a.nli); mc = MiniCheckFT5(a.minicheck)
pred = base / 'PREDICTIONS_SCOPED_BEFORE_REFERENCE_JOIN.private.jsonl'
with pred.open('x') as f:
    for spec in a.sets:
        name, d = spec.split('=', 1)
        for line in open(Path(d) / 'CLAIM_INPUTS.private.jsonl'):
            it = json.loads(line); rep = structured_reporter(it['proposition']); prem = render_scoped(it['evidence'], rep)
            row = dict(set=name, item_id=it['item_id'], reporter=rep, scoped_turns=prem.count('\n') + 1 if prem else 0)
            row['nli'] = nli.score(prem, it['proposition']) if prem else dict(verdict='unknown', status='no_reporter_turns')
            row['mc'] = mc.score(prem, it['proposition']) if prem else dict(supported=False, support_prob=0.0, elapsed_ns=0)
            f.write(json.dumps(row) + '\n')
joined = [json.loads(l) for l in (base / 'RESULTS_PRIVATE.jsonl').open()]
sc = {(r['set'], r['item_id']): r for r in map(json.loads, pred.open())}
for j in joined:
    r = sc[(j['set'], j['item_id'])]
    j['B_nli_scoped'] = r['nli']['verdict']; j['C_minicheck_scoped'] = 'supported' if r['mc']['supported'] else 'unknown'
    j['D_mc+nli_scoped'] = combine(r['mc'], r['nli']); j['reporter'] = r['reporter']
(base / 'RESULTS_WITH_SCOPED_PRIVATE.jsonl').write_text(''.join(json.dumps(j) + '\n' for j in joined))
s = json.loads((base / 'SUMMARY_PUBLIC.json').read_text())
for name in s['by_set']:
    sub = [j for j in joined if j['set'] == name]
    for k in ('B_nli_scoped', 'C_minicheck_scoped', 'D_mc+nli_scoped'):
        s['by_set'][name][k] = metrics(sub, k)
        m = s['by_set'][name][k]
        print(name, f"{k:22s} BA={m['balanced_accuracy']:.3f} mF1={m['macro_f1']:.3f} falsepass={m['false_pass']} swapFP={m['subject_swap_false_pass']} abs->neg={m['absence_as_negation']} supRec={m['supported']['recall']}")
s['scoped_arm'] = 'self-report claims checked only against reporter turns (structured reporter = host-known speaker)'
(base / 'SUMMARY_PUBLIC.json').write_text(json.dumps(s, indent=1) + '\n')
