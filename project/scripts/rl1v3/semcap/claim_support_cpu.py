#!/usr/bin/env python3
"""CPU comparison B (existing NLI) vs C (MiniCheck-FT5) vs D (MiniCheck+NLI) on frozen
claim sets, with tagged vs host-attributed premise rendering. Predictions are written
before references are joined. Development diagnostics only; no threshold tuning."""
import argparse, json, os, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'src'))
from metacom_pm.rl1v3.semcap.claim_support import RENDERERS, MiniCheckFT5, DebertaNLI, combine, metrics

p = argparse.ArgumentParser()
p.add_argument('--sets', nargs='+', required=True, help='name=dir with CLAIM_INPUTS/CLAIM_REFERENCES')
p.add_argument('--nli', required=True); p.add_argument('--minicheck', required=True)
p.add_argument('--output', required=True); p.add_argument('--threads', type=int, default=8)
a = p.parse_args()
out = Path(a.output); out.mkdir(parents=True, exist_ok=False)
import torch; torch.set_num_threads(a.threads)
nli = DebertaNLI(a.nli); mc = MiniCheckFT5(a.minicheck)
loads = dict(nli_load_ns=nli.load_ns, minicheck_load_ns=mc.load_ns)
pred_path = out / 'PREDICTIONS_BEFORE_REFERENCE_JOIN.private.jsonl'
with pred_path.open('x') as f:
    for spec in a.sets:
        name, d = spec.split('=', 1)
        for line in open(Path(d) / 'CLAIM_INPUTS.private.jsonl'):
            item = json.loads(line); row = dict(set=name, item_id=item['item_id'])
            for rname, render in RENDERERS.items():
                prem = render(item['evidence'])
                row[f'nli_{rname}'] = nli.score(prem, item['proposition'])
                row[f'mc_{rname}'] = mc.score(prem, item['proposition'])
            f.write(json.dumps(row) + '\n')
rows = [json.loads(l) for l in pred_path.open()]
refs = {}
for spec in a.sets:
    name, d = spec.split('=', 1)
    for line in open(Path(d) / 'CLAIM_REFERENCES.private.jsonl'):
        r = json.loads(line); refs[(name, r['item_id'])] = r
joined = []
for r in rows:
    ref = refs[(r['set'], r['item_id'])]
    j = dict(set=r['set'], item_id=r['item_id'], reference=ref['reference'], factor=ref['factor'])
    for rn in RENDERERS:
        j[f'B_nli_{rn}'] = r[f'nli_{rn}']['verdict']
        j[f'C_minicheck_{rn}'] = 'supported' if r[f'mc_{rn}']['supported'] else 'unknown'
        j[f'D_mc+nli_{rn}'] = combine(r[f'mc_{rn}'], r[f'nli_{rn}'])
        j[f'mc_prob_{rn}'] = round(r[f'mc_{rn}']['support_prob'], 4)
    joined.append(j)
(out / 'RESULTS_PRIVATE.jsonl').write_text(''.join(json.dumps(j) + '\n' for j in joined))
keys = [k for k in joined[0] if k[:2] in ('B_', 'C_', 'D_')]
summary = dict(protocol='semcap-claim-support-cpu-v1', loads=loads, device='cpu', threads=a.threads,
    thresholds=dict(nli='entail>=.8&contra<=.1 / contra>=.8&entail<=.1 (frozen)', minicheck='prob>.5 (official default)'),
    note='development diagnostics on exposed/assistant-annotated material; not validation, reward or Judge qualification',
    by_set={})
for name in sorted({j['set'] for j in joined}):
    sub = [j for j in joined if j['set'] == name]
    summary['by_set'][name] = {k: metrics(sub, k) for k in keys}
    summary['by_set'][name]['minicheck_ms_per_item'] = {rn: sum(r[f'mc_{rn}']['elapsed_ns'] for r in rows if r['set']==name)/len(sub)/1e6 for rn in RENDERERS}
    summary['by_set'][name]['nli_ms_per_item'] = {rn: sum(r[f'nli_{rn}']['elapsed_ns'] for r in rows if r['set']==name)/len(sub)/1e6 for rn in RENDERERS}
(out / 'SUMMARY_PUBLIC.json').write_text(json.dumps(summary, indent=1) + '\n')
for name, s in summary['by_set'].items():
    print('==', name)
    for k in keys:
        m = s[k]; print(f"{k:24s} BA={m['balanced_accuracy']:.3f} mF1={m['macro_f1']:.3f} falsepass={m['false_pass']} swapFP={m['subject_swap_false_pass']} abs->neg={m['absence_as_negation']} supRec={m['supported']['recall']}")
    print('ms/item mc', s['minicheck_ms_per_item'], 'nli', s['nli_ms_per_item'])
print(loads)
