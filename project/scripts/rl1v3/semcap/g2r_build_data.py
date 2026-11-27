#!/usr/bin/env python3
"""G2-R data: dialogue evidence-state supervision and evaluation files (CPU, private outputs).

Main task labels: supported / contradicted / not_established.
  INLI (google-deepmind/inli, CC BY-SA 4.0): explicit_entailment -> supported,
       contradiction -> contradicted, neutral -> not_established. implied_entailment is NOT
       mapped to supported (implication is not a confirmed fact); it is kept as a probe.
  DCS  (assistant-authored weak supervision over natural ESConv training-family utterances):
       natural utterance + minimal variants, same claim under different evidence; sequences
       (earlier + later session) for revision; dev paraphrases for consistency.
  event32 / speaker32: exposed development regression sets (never trained on).
"""
import argparse, ast, csv, hashlib, json, sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'src'))
from metacom_pm.rl1v3.semcap.evidence_state import render  # noqa: E402
from metacom_pm.rl1v3.semcap import claim_support as CS  # noqa: E402

MAP = dict(S='supported', C='contradicted', N='not_established')
REF = dict(supported='supported', unknown='not_established', contradicted='contradicted')


def fsha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def write(path, rows):
    path.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows))
    return dict(rows=len(rows), labels=dict(Counter(r['label'] for r in rows)), sha256=fsha(path))


def inli(path, split):
    main, implied = [], []
    for r in csv.DictReader(open(path)):
        base = dict(source='inli', split=split, group='inli:' + r[''], dataset=r['dataset'])
        for col, lab in (('explicit_entailment', 'supported'), ('contradiction', 'contradicted'), ('neutral', 'not_established')):
            main.append(dict(base, item_id=f"inli-{split}-{r['']}-{col}", premise=r['premise'], hypothesis=r[col], label=lab,
                             kind='pair', tags=col))
        implied.append(dict(base, item_id=f"inli-{split}-{r['']}-implied", premise=r['premise'],
                            hypothesis=r['implied_entailment'], label='implied_entailment', kind='probe', tags='implied'))
    return main, implied


def dcs(seeds_path, authored_path, para_path):
    seeds = {json.loads(s)['seed_id']: json.loads(s) for s in Path(seeds_path).read_text().splitlines() if s.strip()}
    authored = ast.literal_eval(Path(authored_path).read_text())
    para = ast.literal_eval(Path(para_path).read_text())
    rows = {'train': [], 'dev': []}
    for sid, variants, claims, seqs in authored:
        s = seeds[sid]; split = s['split']
        ctx = dict(speaker=s['context']['role'], text=s['context']['text'])
        ev = {'n': ('seeker', s['utterance'])}
        ev.update({k: ('seeker' if who == 'user' else 'supporter', t) for k, (who, t) in variants.items()})
        base = dict(source='dcs', split=split, group='esconv:' + s['family_id'], seed_id=sid)
        for ci, (claim, labels, tags) in enumerate(claims):
            for v, lab in labels.items():
                if lab == '?': continue
                evidence = [ctx, dict(speaker=ev[v][0], text=ev[v][1])]
                item = dict(base, item_id=f'{sid}-c{ci}-{v}', premise=render(evidence), hypothesis=claim, label=MAP[lab],
                            kind='pair', variant=v, claim_index=ci, tags=tags,
                            provenance='natural_utterance' if v == 'n' else 'authored_variant')
                rows[split].append(item)
                if split == 'dev' and (sid, ci) in para:
                    rows[split].append(dict(item, item_id=item['item_id'] + '-para', hypothesis=para[(sid, ci)],
                                            kind='paraphrase', paraphrase_of=item['item_id']))
        for k, (order, ci, lab) in enumerate(seqs):
            evidence = [dict(ctx, session=1)] + [dict(speaker=ev[v][0], text=ev[v][1], session=1 if j == 0 else 2)
                                                for j, v in enumerate(order)]
            rows[split].append(dict(base, item_id=f'{sid}-seq{k}', premise=render(evidence), hypothesis=claims[ci][0],
                                    label=MAP[lab], kind='sequence', claim_index=ci, sequence=order, tags=claims[ci][2],
                                    before_item=f"{sid}-c{ci}-{order[0]}", provenance='authored_sequence'))
    return rows


def claim_set(d, name):
    inputs = [json.loads(s) for s in (Path(d) / 'CLAIM_INPUTS.private.jsonl').read_text().splitlines() if s.strip()]
    refs = {json.loads(s)['item_id']: json.loads(s) for s in (Path(d) / 'CLAIM_REFERENCES.private.jsonl').read_text().splitlines() if s.strip()}
    out = {'attributed': [], 'scoped': []}
    for r in inputs:
        ref = refs[r['item_id']]
        base = dict(source=name, split='regression', group=ref.get('family_group', r['item_id']), item_id=r['item_id'],
                    hypothesis=r['proposition'], label=REF[ref['reference']], kind='pair', tags=ref.get('factor', ''))
        out['attributed'].append(dict(base, premise=CS.render_attributed(r['evidence']), rendering='attributed'))
        out['scoped'].append(dict(base, premise=CS.render_scoped(r['evidence'], CS.structured_reporter(r['proposition'])),
                                  rendering='scoped'))
    return out


def main(a):
    out = Path(a.output); out.mkdir(parents=True, exist_ok=False); card = dict(protocol='semcap-g2r-data-v1', files={})
    tr, tr_imp = inli(Path(a.inli) / 'train.csv', 'train'); va, va_imp = inli(Path(a.inli) / 'val.csv', 'val')
    d = dcs(a.seeds, a.authored, a.paraphrases)
    card['files']['TRAIN_INLI'] = write(out / 'TRAIN_INLI.private.jsonl', tr)
    card['files']['TRAIN_DCS'] = write(out / 'TRAIN_DCS.private.jsonl', d['train'])
    card['files']['TRAIN_INLI_IMPLIED'] = write(out / 'TRAIN_INLI_IMPLIED.private.jsonl', tr_imp)  # only for the T1i arm
    card['files']['DEV_INLI'] = write(out / 'DEV_INLI.private.jsonl', va)
    card['files']['PROBE_INLI_IMPLIED'] = write(out / 'PROBE_INLI_IMPLIED.private.jsonl', va_imp)
    card['files']['DEV_DCS'] = write(out / 'DEV_DCS.private.jsonl', d['dev'])
    for name, path in (('event32', a.event32), ('speaker32', a.speaker32)):
        for rend, rows in claim_set(path, name).items():
            card['files'][f'REG_{name}_{rend}'] = write(out / f'REG_{name}_{rend}.private.jsonl', rows)
    tg = {r['group'] for r in d['train']}; dg = {r['group'] for r in d['dev']}
    card['dcs'] = dict(train_seeds=len({r['seed_id'] for r in d['train']}), dev_seeds=len({r['seed_id'] for r in d['dev']}),
                       family_overlap=len(tg & dg),
                       kinds={s: dict(Counter(r['kind'] for r in d[s])) for s in d},
                       provenance={s: dict(Counter(r.get('provenance', '') for r in d[s])) for s in d})
    card['sources'] = dict(inli=dict(path=a.inli, license='CC BY-SA 4.0 (repo LICENSE)', implied_mapped_to_supported=False),
                           dcs=dict(seeds_sha256=fsha(a.seeds), authored_sha256=fsha(a.authored), paraphrases_sha256=fsha(a.paraphrases),
                                    author='Claude Code (assistant) weak supervision; no independent human'))
    (out / 'DATA_CARD_PUBLIC.json').write_text(json.dumps(card, indent=2) + '\n'); print(json.dumps(card, indent=1))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    for n in ('inli', 'seeds', 'authored', 'paraphrases', 'event32', 'speaker32', 'output'): p.add_argument('--' + n, required=True)
    main(p.parse_args())
