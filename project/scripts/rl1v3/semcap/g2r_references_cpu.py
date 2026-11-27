#!/usr/bin/env python3
"""CPU references for G2-R (no training of the evidence model here).

  minicheck   MiniCheck-FT5 P(supported) on every eval file (same premise text), so the
              existing combination D (MiniCheck support; contradicted only when the T0 NLI
              frozen threshold says so) can be scored against the 3-way references.
  hyponly     hypothesis-only TF-IDF logistic regression trained on the main training data
              (INLI + DCS-train), tested on every eval file: a label-shortcut control.
"""
import argparse, json, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'src'))


def jl(p):
    return [json.loads(s) for s in Path(p).read_text().splitlines() if s.strip()]


def minicheck(a):
    from metacom_pm.rl1v3.semcap.claim_support import MiniCheckFT5
    mc = MiniCheckFT5(a.minicheck); out = Path(a.output); out.mkdir(parents=True, exist_ok=False); cost = {}
    for f in a.files:
        name = Path(f).name.split('.')[0]; rows = jl(f); t0 = time.monotonic(); res = []
        for r in rows:
            s = mc.score(r['premise'], r['hypothesis'])
            res.append(dict(item_id=r['item_id'], gold=r['label'], mc_prob=s['support_prob'], mc_supported=s['supported']))
        (out / f'MC_{name}.private.jsonl').write_text(''.join(json.dumps(x) + '\n' for x in res))
        cost[name] = dict(items=len(rows), ms_per_item=round(1000 * (time.monotonic() - t0) / max(1, len(rows)), 1))
    (out / 'MC_COST.json').write_text(json.dumps(dict(snapshot=a.minicheck, per_file=cost), indent=1)); print(cost)


def hyponly(a):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    train = jl(a.train_inli) + jl(a.train_dcs) * 8
    vec = TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True)
    X = vec.fit_transform([r['hypothesis'] for r in train])
    clf = LogisticRegression(max_iter=2000, C=1.0).fit(X, [r['label'] for r in train])
    out = Path(a.output); out.mkdir(parents=True, exist_ok=False)
    for f in a.files:
        name = Path(f).name.split('.')[0]; rows = jl(f)
        pred = clf.predict(vec.transform([r['hypothesis'] for r in rows]))
        (out / f'PRED_{name}.private.jsonl').write_text(''.join(
            json.dumps(dict(item_id=r['item_id'], gold=r['label'], pred=p, probs=None)) + '\n' for r, p in zip(rows, pred)))
    print('hyponly done', len(train))


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('mode', choices=['minicheck', 'hyponly'])
    p.add_argument('--files', nargs='+', required=True); p.add_argument('--output', required=True)
    p.add_argument('--minicheck'); p.add_argument('--train-inli'); p.add_argument('--train-dcs')
    a = p.parse_args(); minicheck(a) if a.mode == 'minicheck' else hyponly(a)
