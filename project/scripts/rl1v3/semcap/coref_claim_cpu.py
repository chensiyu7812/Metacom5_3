#!/usr/bin/env python3
"""Arm E-collab: host speaker anchor + Maverick coref -> person-resolved, speaker-scoped
premise -> NLI / MiniCheck (same models and frozen thresholds). Also reports Maverick's
agreement with the deterministic I/you reading. Development diagnostics only."""
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'src'))
from metacom_pm.rl1v3.semcap.claim_support import render_scoped, structured_reporter, MiniCheckFT5, DebertaNLI, combine, metrics
from metacom_pm.rl1v3.semcap.coref import SpeakerCoref
p = argparse.ArgumentParser()
p.add_argument('--sets', nargs='+', required=True); p.add_argument('--nli', required=True)
p.add_argument('--minicheck', required=True); p.add_argument('--maverick', required=True)
p.add_argument('--base', required=True); p.add_argument('--threads', type=int, default=8)
a = p.parse_args()
import torch; torch.set_num_threads(a.threads)
base = Path(a.base); co = SpeakerCoref(a.maverick); nli = DebertaNLI(a.nli); mc = MiniCheckFT5(a.minicheck)
pred = base / 'PREDICTIONS_COREF_BEFORE_REFERENCE_JOIN.private.jsonl'
agree = {}; cache = {}; coref_ns = []
with pred.open('x') as f:
    for spec in a.sets:
        name, d = spec.split('=', 1); ag = dict(agree=0, disagree=0, merged_speaker_clusters=0, prefixes=0, rewritten=0)
        for line in open(Path(d) / 'CLAIM_INPUTS.private.jsonl'):
            it = json.loads(line); key = json.dumps(it['evidence'], sort_keys=True)
            if key not in cache:
                an = co.analyse(it['evidence']); coref_ns.append(an['elapsed_ns'])
                res, n = SpeakerCoref.resolve_person_pronouns(it['evidence'], an)
                b = SpeakerCoref.binding_agreement(it['evidence'], an)
                for k in ('agree', 'disagree', 'merged_speaker_clusters'): ag[k] += b[k]
                ag['prefixes'] += 1; ag['rewritten'] += n
                cache[key] = (res, [dict(entity=c['entity'], mentions=[m['text'] for m in c['mentions']]) for c in an['clusters']])
            res, clusters = cache[key]
            rep = structured_reporter(it['proposition']); prem = render_scoped(res, rep)
            row = dict(set=name, item_id=it['item_id'], reporter=rep, clusters=clusters)
            row['nli'] = nli.score(prem, it['proposition']) if prem else dict(verdict='unknown')
            row['mc'] = mc.score(prem, it['proposition']) if prem else dict(supported=False, support_prob=0.0)
            f.write(json.dumps(row) + '\n')
        agree[name] = ag
joined = [json.loads(l) for l in (base / 'RESULTS_WITH_SCOPED_PRIVATE.jsonl').open()]
cr = {(r['set'], r['item_id']): r for r in map(json.loads, pred.open())}
for j in joined:
    r = cr[(j['set'], j['item_id'])]
    j['B_nli_scoped+coref'] = r['nli']['verdict']; j['C_minicheck_scoped+coref'] = 'supported' if r['mc']['supported'] else 'unknown'
    j['D_mc+nli_scoped+coref'] = combine(r['mc'], r['nli'])
(base / 'RESULTS_ALL_PRIVATE.jsonl').write_text(''.join(json.dumps(j) + '\n' for j in joined))
s = json.loads((base / 'SUMMARY_PUBLIC.json').read_text())
for name in s['by_set']:
    sub = [j for j in joined if j['set'] == name]
    for k in ('B_nli_scoped+coref', 'C_minicheck_scoped+coref', 'D_mc+nli_scoped+coref'):
        s['by_set'][name][k] = m = metrics(sub, k)
        print(name, f"{k:26s} BA={m['balanced_accuracy']:.3f} mF1={m['macro_f1']:.3f} falsepass={m['false_pass']} swapFP={m['subject_swap_false_pass']} abs->neg={m['absence_as_negation']} supRec={m['supported']['recall']}")
    s['by_set'][name]['maverick_binding_agreement'] = agree[name]
s['maverick'] = dict(load_ns=co.load_ns, mean_prefix_ms=sum(coref_ns) / len(coref_ns) / 1e6, prefixes=len(coref_ns))
(base / 'SUMMARY_PUBLIC.json').write_text(json.dumps(s, indent=1) + '\n')
print(json.dumps(agree), s['maverick'])
