#!/usr/bin/env python3
"""Dialogue contrast set (DCS) seeds: natural ESConv seeker utterances reporting an event,
plan, attempt, third-party action or state, from training families only.

Fold 6 sealed; train split; ESConv overlap/excluded families removed; GSWS, event32,
speaker32 and G1 families blocked. Families are split train/dev by salted hash *before*
any item is written, so no family appears in both. The regex is a selection filter for
candidate utterances, never a label.
"""
import argparse, hashlib, json, re
from pathlib import Path

EVENTISH = re.compile(r"\b(?:I (?:went|tried|talked|told|asked|called|started|quit|stopped|applied|decided|planned|plan|"
                      r"am going to|'m going to|will|want to|have been|did|didn't|haven't|never|already|finally|got|lost|"
                      r"moved|broke|signed|joined|left|visited|met)|my (?:mom|mother|dad|father|wife|husband|boyfriend|"
                      r"girlfriend|friend|boss|sister|brother|son|daughter|parents|partner|roommate|manager|coworker)\b)", re.I)


def main(a):
    meta = json.loads(Path(a.metadata).read_text())
    gsws = [json.loads(s) for s in Path(a.gsws_resources).read_text().splitlines() if s.strip()]
    blocked = {r['family_id'] for r in gsws} | {f for r in gsws for f in r.get('ancestor_family_ids', [])}
    for p in a.exposed:
        blocked |= {json.loads(s)['family_id'] for s in Path(p).read_text().splitlines() if s.strip()}
    pools = {'train': [], 'dev': []}
    for raw in Path(a.registry).open():
        fold = re.search(r'"fold":(\d+)', raw); ds = re.search(r'"dataset":"([^"]+)"', raw)
        sp = re.search(r'"source_split":"([^"]+)"', raw)
        if (fold and int(fold[1]) == 6) or not sp or sp[1] != 'train' or not ds or ds[1] != 'ESConv': continue
        row = json.loads(raw); s = row['source']; assert row['fold'] != 6
        if s['family_id'] in blocked or set(s['ancestor_family_ids']) & blocked: continue
        if s['excluded_for_overlap'] or s['family_id'] in meta['excluded_families']: continue
        fam_key = hashlib.sha256(('semcap-dcs-v1-split|' + s['family_id']).encode()).hexdigest()
        split = 'dev' if int(fam_key[:8], 16) % 4 == 0 else 'train'
        turns = s['turns']
        for i, t in enumerate(turns):
            if i < 2 or t['role'] != 'seeker' or not (50 <= len(t['text']) <= 260) or not EVENTISH.search(t['text']): continue
            key = hashlib.sha256(('semcap-dcs-v1-seed|' + s['family_id'] + '|' + str(i)).encode()).hexdigest()
            pools[split].append(dict(key=key, split=split, family_id=s['family_id'], session_id=s['session_id'],
                                     fold=row['fold'], turn_index=i, date=s.get('date'),
                                     context=dict(role=turns[i - 1]['role'], text=turns[i - 1]['text']),
                                     utterance=t['text']))
    out = Path(a.output); out.mkdir(parents=True, exist_ok=False); chosen = []
    for split, n in (('train', a.train), ('dev', a.dev)):
        seen = set()
        for r in sorted(pools[split], key=lambda r: r['key']):
            if r['family_id'] in seen: continue
            seen.add(r['family_id']); chosen.append(r)
            if len(seen) >= n: break
    for k, r in enumerate(chosen, 1): r['seed_id'] = f"{'T' if r['split'] == 'train' else 'D'}{k:03}"
    (out / 'SEEDS.private.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in chosen))
    rep = dict(protocol='semcap-dcs-v1', candidate_utterances={k: len(v) for k, v in pools.items()},
               selected={s: sum(r['split'] == s for r in chosen) for s in ('train', 'dev')},
               family_disjoint=not ({r['family_id'] for r in chosen if r['split'] == 'train'} &
                                    {r['family_id'] for r in chosen if r['split'] == 'dev'}), fold6_included=False)
    (out / 'SELECTION_PUBLIC.json').write_text(json.dumps(rep, indent=2) + '\n'); print(json.dumps(rep))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    for n in ('registry', 'metadata', 'gsws-resources', 'output'): p.add_argument('--' + n, required=True)
    p.add_argument('--exposed', nargs='+', required=True)
    p.add_argument('--train', type=int, default=48); p.add_argument('--dev', type=int, default=16)
    main(p.parse_args())
