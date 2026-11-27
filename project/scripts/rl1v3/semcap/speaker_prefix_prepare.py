#!/usr/bin/env python3
"""Select causal training-family prefixes where the *supporter* discloses a first-person
experience, fixed before any tool prediction (speaker/subject-binding development set).

Same eligibility as journal_event_dialogue_prepare.py: fold 6 sealed, train split only,
EvoEmo owners p5/p6 only, GSWS families blocked, ESConv overlap excluded. Additionally the
8 families already exposed in event-dialogue-v2 are excluded. The regex below is only a
*selection* filter for candidate prefixes, not a capability or label.
"""
import argparse, hashlib, json, re
from pathlib import Path

DISCLOSE = re.compile(r"\b(?:I|I've|I'm|I was|I had|my)\b", re.I)


def prepare(registry, metadata, gsws_resources, exposed, output, per_group):
    out = Path(output); out.mkdir(parents=True, exist_ok=False)
    meta = json.loads(Path(metadata).read_text())
    gsws = [json.loads(s) for s in Path(gsws_resources).read_text().splitlines() if s.strip()]
    blocked = {r['family_id'] for r in gsws} | {f for r in gsws for f in r.get('ancestor_family_ids', [])}
    blocked |= {json.loads(s)['family_id'] for s in Path(exposed).read_text().splitlines() if s.strip()}
    train_owners = {'p5', 'p6'}
    for owner in train_owners:
        assert meta['folds']['historical_rl1_split'][owner] == 'train' and meta['folds']['fold_of_owner'][owner] != 6
    cands = []
    for raw in Path(registry).open():
        fold = re.search(r'"fold":(\d+)', raw); owner = re.search(r'"owner_id":"([^"]+)"', raw)
        dataset = re.search(r'"dataset":"([^"]+)"', raw); split = re.search(r'"source_split":"([^"]+)"', raw)
        if (fold and int(fold[1]) == 6) or not split or split[1] != 'train': continue
        if dataset[1] == 'es_memeval_evoemo_public_v1' and owner[1] not in train_owners: continue
        if dataset[1] not in ('ESConv', 'es_memeval_evoemo_public_v1'): continue
        row = json.loads(raw); s = row['source']
        if s['family_id'] in blocked or set(s['ancestor_family_ids']) & blocked: continue
        if dataset[1] == 'ESConv' and (s['excluded_for_overlap'] or s['family_id'] in meta['excluded_families']): continue
        turns = s['turns']; idx = None
        for i, t in enumerate(turns[:16]):
            if i >= 2 and t['role'] == 'supporter' and len(t['text']) >= 60 and DISCLOSE.search(t['text']) \
               and re.search(r"\b(?:I (?:have|had|was|went|used to|also|remember|lost|got)|my (?:mom|mother|dad|father|wife|husband|friend|job|boss|sister|brother|son|daughter|own))\b", t['text'], re.I):
                idx = i; break
        if idx is None or idx + 1 >= len(turns) or turns[idx + 1]['role'] != 'seeker': continue
        key = hashlib.sha256(('semcap-speaker-dev-v1|' + s['family_id'] + '|' + s['session_id']).encode()).hexdigest()
        cands.append(dict(key=key, source_id=row.get('source_id'), owner_id=s['owner_id'], family_id=s['family_id'],
            dataset=s['dataset'], source_split=s['source_split'], fold=row['fold'], session_id=s['session_id'],
            disclosure_turn=idx, cutoff_turn=idx + 1, report_time=s['date'],
            prefix=[dict(evidence_id=f'C{j}', speaker=t['role'], text=t['text'], reported_at=s['date'], origin='current_visible')
                    for j, t in enumerate(turns[:idx + 2])],
            future_turns_read_into_input=False))
    selected, seen, counts = [], set(), {}
    for r in sorted(cands, key=lambda r: r['key']):
        g = 'ESConv' if r['dataset'] == 'ESConv' else r['owner_id']; cap = per_group[g]
        if counts.get(g, 0) >= cap or r['family_id'] in seen: continue
        counts[g] = counts.get(g, 0) + 1; seen.add(r['family_id']); selected.append(r)
    for n, r in enumerate(selected, 1): r['alias'] = f'S{n:02}'
    (out / 'PREFIXES.private.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in selected))
    rep = dict(protocol='semcap-speaker-dev-v1', candidates=len(cands), selected=len(selected), groups=counts,
               fold6_included=False, gsws_family_overlap=0, event_dialogue_v2_overlap=0, causal_prefixes=True,
               selection='supporter first-person disclosure within first 16 turns, followed by seeker turn; salted family hash order; fixed before predictions',
               aliases=[dict(alias=r['alias'], dataset=r['dataset'], fold=r['fold'], prefix_turns=len(r['prefix'])) for r in selected])
    (out / 'SELECTION_PUBLIC.json').write_text(json.dumps(rep, indent=2) + '\n'); print(json.dumps(rep, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    for n in ('registry', 'metadata', 'gsws-resources', 'exposed', 'output'): p.add_argument('--' + n, required=True)
    p.add_argument('--esconv', type=int, default=4)
    a = p.parse_args(); prepare(a.registry, a.metadata, a.gsws_resources, a.exposed, a.output, {'ESConv': a.esconv, 'p5': 2, 'p6': 2})
