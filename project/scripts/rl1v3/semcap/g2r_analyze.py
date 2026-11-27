#!/usr/bin/env python3
"""G2-R analysis over saved predictions (CPU). Public output = aggregates only; a private
error sheet keeps item text for review.

Arms: T0 (argmax), B_T0thr (T0 with the frozen .8/.1 thresholds used in earlier runs),
D (MiniCheck support + T0 thresholded contradiction), H (hypothesis-only), T1, T2.
"""
import argparse, json, math, sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'src'))
from metacom_pm.rl1v3.semcap.evidence_state import LABELS, UNPROCESSED, metrics, ece  # noqa: E402


def jl(p):
    return [json.loads(s) for s in Path(p).read_text().splitlines() if s.strip()] if Path(p).exists() else None


def thresholded(p):
    if p is None: return UNPROCESSED
    if p['supported'] >= .8 and p['contradicted'] <= .1: return 'supported'
    if p['contradicted'] >= .8 and p['supported'] <= .1: return 'contradicted'
    return 'not_established'


def temp_fit(probs, gold):
    """Grid temperature on log-probs (fit set only)."""
    def nll(T):
        s = 0.0
        for p, g in zip(probs, gold):
            z = {k: math.log(max(v, 1e-9)) / T for k, v in p.items()}; m = max(z.values())
            lse = m + math.log(sum(math.exp(v - m) for v in z.values())); s -= z[g] - lse
        return s / len(gold)
    return min((nll(T), T) for T in [x / 20 for x in range(10, 81)])[1]


def scale(p, T):
    z = {k: math.log(max(v, 1e-9)) / T for k, v in p.items()}; m = max(z.values())
    e = {k: math.exp(v - m) for k, v in z.items()}; s = sum(e.values())
    return {k: v / s for k, v in e.items()}


def main(a):
    data = Path(a.data); files = ['DEV_DCS', 'DEV_INLI', 'REG_event32_attributed', 'REG_event32_scoped',
                                  'REG_speaker32_attributed', 'REG_speaker32_scoped', 'PROBE_INLI_IMPLIED']
    items = {f: {r['item_id']: r for r in jl(data / f'{f}.private.jsonl')} for f in files}
    arms = {}
    for spec in a.arms:
        name, d = spec.split('=', 1)
        arms[name] = {f: {x['item_id']: x for x in (jl(Path(d) / f'PRED_{f}.private.jsonl') or [])} for f in files}
    for name in list(arms):
        if any(x.get('pred') == 'implied' or (x.get('probs') or {}).get('implied') is not None
               for f in files for x in arms[name][f].values()):
            for view, target in (('strict', 'not_established'), ('lenient', 'supported')):
                def conv(x, target=target):
                    pr = x.get('probs')
                    if pr is not None and 'implied' in pr:
                        pr = {k: v for k, v in pr.items() if k != 'implied'}; pr[target] = pr[target] + x['probs']['implied']
                    pred = target if x['pred'] == 'implied' else x['pred']
                    return dict(x, pred=pred, probs=pr, pred4=x['pred'])
                arms[f'{name}_{view}'] = {f: ({k: conv(v) for k, v in arms[name][f].items()} if f != 'PROBE_INLI_IMPLIED'
                                              else arms[name][f]) for f in files}
            del arms[name]
    t0 = arms['T0']
    arms['B_T0thr'] = {f: {k: dict(v, pred=thresholded(v['probs'])) for k, v in t0[f].items()} for f in files}
    if a.minicheck:
        arms['D_MiniCheck+T0thr'] = {}
        for f in files:
            mc = {x['item_id']: x for x in (jl(Path(a.minicheck) / f'MC_{f}.private.jsonl') or [])}
            if not mc: continue
            arms['D_MiniCheck+T0thr'][f] = {k: dict(item_id=k, gold=v['gold'], probs=None,
                pred='supported' if mc[k]['mc_supported'] else ('contradicted' if thresholded(t0[f][k]['probs']) == 'contradicted'
                                                                 else 'not_established')) for k, v in t0[f].items() if k in mc}
    res = dict(protocol='semcap-g2r-results-v1', arms=list(arms), sets={}, dcs_detail={}, implied_probe={}, calibration={})
    err_lines = ['# DEV_DCS errors (private)\n']
    for arm, by in arms.items():
        for f in files:
            P = by.get(f) or {}
            if not P: continue
            if f == 'PROBE_INLI_IMPLIED':
                res['implied_probe'][arm] = dict(Counter(x['pred'] for x in P.values())); continue
            ids = [k for k in items[f] if k in P]
            gold = [items[f][k]['label'] for k in ids]; pred = [P[k]['pred'] for k in ids]
            res['sets'].setdefault(f, {})[arm] = metrics(gold, pred)
        P = by.get('DEV_DCS') or {}
        if not P: continue
        it = items['DEV_DCS']; det = {}
        for key in ('kind', 'provenance'):
            g = defaultdict(list)
            for k, r in it.items():
                if k in P: g[r.get(key, '')].append(k)
            det[key] = {v: dict(n=len(ks), acc=round(sum(P[k]['pred'] == it[k]['label'] for k in ks) / len(ks), 4)) for v, ks in g.items()}
        tags = defaultdict(list)
        for k, r in it.items():
            if k in P and r['kind'] == 'pair':
                for t in r['tags'].split(','): tags[t].append(k)
        det['tag_pairs'] = {t: dict(n=len(ks), acc=round(sum(P[k]['pred'] == it[k]['label'] for k in ks) / len(ks), 4)) for t, ks in sorted(tags.items())}
        paras = [r for r in it.values() if r['kind'] == 'paraphrase' and r['item_id'] in P]
        det['paraphrase'] = dict(n=len(paras), same_prediction=sum(P[r['item_id']]['pred'] == P[r['paraphrase_of']]['pred'] for r in paras),
                                 both_correct=sum(P[r['item_id']]['pred'] == r['label'] == P[r['paraphrase_of']]['pred'] for r in paras))
        seqs = [r for r in it.values() if r['kind'] == 'sequence' and r['item_id'] in P]
        rev = []
        for r in seqs:
            b = it[r['before_item']]; pb = P[r['before_item']]['pred']; pa = P[r['item_id']]['pred']
            rev.append(dict(before_gold=b['label'], before_pred=pb, after_gold=r['label'], after_pred=pa,
                            correct_revision=pb == b['label'] and pa == r['label']))
        det['revision'] = dict(n=len(rev), before_correct=sum(x['before_pred'] == x['before_gold'] for x in rev),
                               after_correct=sum(x['after_pred'] == x['after_gold'] for x in rev),
                               both_correct=sum(x['correct_revision'] for x in rev))
        fam = defaultdict(list)
        for k, r in it.items():
            if k in P and r['kind'] == 'pair': fam[r['group']].append(P[k]['pred'] == r['label'])
        det['family_accuracy'] = dict(families=len(fam), mean=round(sum(sum(v) / len(v) for v in fam.values()) / len(fam), 4),
                                      per_family=sorted(round(sum(v) / len(v), 3) for v in fam.values()))
        res['dcs_detail'][arm] = det
        if arm in ('T0', 'T1', 'T2', 'T1i_strict'):
            err_lines.append(f'\n## {arm}\n')
            for k, r in it.items():
                if k in P and P[k]['pred'] != r['label']:
                    err_lines.append(f"- {k} [{r['kind']}/{r.get('tags','')}] gold={r['label']} pred={P[k]['pred']} :: H: {r['hypothesis']}\n  P: {r['premise'][-260:]!r}\n")
    # family-level paired comparison vs T0
    for arm in ('T1', 'T2', 'T1i_strict', 'T1i_lenient'):
        if arm in res['dcs_detail']:
            a0 = res['dcs_detail']['T0']['family_accuracy']; it = items['DEV_DCS']
            f0 = defaultdict(list); f1 = defaultdict(list)
            for k, r in it.items():
                if r['kind'] == 'pair' and k in arms[arm]['DEV_DCS']:
                    f0[r['group']].append(arms['T0']['DEV_DCS'][k]['pred'] == r['label'])
                    f1[r['group']].append(arms[arm]['DEV_DCS'][k]['pred'] == r['label'])
            diff = [sum(f1[g]) / len(f1[g]) - sum(f0[g]) / len(f0[g]) for g in f0]
            res['dcs_detail'][arm]['family_vs_T0'] = dict(better=sum(d > 0 for d in diff), worse=sum(d < 0 for d in diff),
                                                         same=sum(d == 0 for d in diff))
    # calibration: temperature fit on DEV_INLI even-index premises, evaluated on odd + DEV_DCS
    for arm in ('T0', 'T1', 'T2', 'T1i_strict'):
        if arm not in arms or not arms[arm]['DEV_INLI']: continue
        P = arms[arm]['DEV_INLI']; ids = sorted(P)
        fitA = [k for k in ids if int(k.split('-')[2]) % 2 == 0]; evB = [k for k in ids if int(k.split('-')[2]) % 2 == 1]
        T = temp_fit([P[k]['probs'] for k in fitA], [P[k]['gold'] for k in fitA])
        dcs = [x for x in arms[arm]['DEV_DCS'].values() if x['probs']]
        res['calibration'][arm] = dict(temperature=T,
            ece_inli_B_raw=ece([P[k]['probs'] for k in evB], [P[k]['gold'] for k in evB]),
            ece_inli_B_scaled=ece([scale(P[k]['probs'], T) for k in evB], [P[k]['gold'] for k in evB]),
            ece_dcs_raw=ece([x['probs'] for x in dcs], [x['gold'] for x in dcs]),
            ece_dcs_scaled=ece([scale(x['probs'], T) for x in dcs], [x['gold'] for x in dcs]))
    out = Path(a.output); out.mkdir(parents=True, exist_ok=True)
    (out / 'G2R_RESULTS_PUBLIC.json').write_text(json.dumps(res, indent=1) + '\n')
    Path(a.private_errors).write_text(''.join(err_lines))
    for f in ('DEV_DCS', 'DEV_INLI', 'REG_event32_scoped', 'REG_speaker32_scoped'):
        for arm, m in res['sets'].get(f, {}).items():
            print(f, arm, 'mF1', m['macro_f1'], 'BA', m['balanced_accuracy'], 'N->C', m['not_established_as_contradicted'],
                  'N->S', m['not_established_as_supported'], 'Smiss', m['supported_missed'], 'Cmiss', m['contradicted_missed'], 'unproc', m['unprocessed'])
    for arm, d in res['dcs_detail'].items():
        print(arm, 'para', d['paraphrase'], 'rev', d['revision'], 'fam', d['family_accuracy']['mean'], d.get('family_vs_T0'))
    print('implied', res['implied_probe']); print('calib', res['calibration'])


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--data', required=True); p.add_argument('--arms', nargs='+', required=True)
    p.add_argument('--minicheck'); p.add_argument('--output', required=True); p.add_argument('--private-errors', required=True)
    main(p.parse_args())
