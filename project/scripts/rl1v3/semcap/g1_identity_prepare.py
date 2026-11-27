#!/usr/bin/env python3
"""G1 identity contrast: select 12 ESConv training-family prefixes before any generation.

Eligibility = speaker_prefix_prepare.py (fold 6 sealed, train split, ESConv overlap/excluded
families removed, GSWS families blocked) and additionally every family already exposed in
event-dialogue-v2 (event32) and speaker-dev-v1 (speaker32) is excluded.

A prefix ends at the first seeker turn that follows a supporter first-person disclosure.
Group M (misattribution pressure, 6): that seeker turn addresses the supporter's own
experience/action in the second person (e.g. "How did you deal with that?").
Group N (no misattribution, 6): the seeker turn has no second-person reference to the
supporter's experience. Regexes are *selection filters only*, never labels or scores.
Order = salted family hash; one prefix per family; first 6 of each group.
"""
import argparse, hashlib, json, re
from pathlib import Path

DISCLOSE = re.compile(r"\b(?:I (?:have|had|was|went|used to|also|remember|lost|got|dealt|felt)|my (?:mom|mother|dad|father|"
                      r"wife|husband|friend|job|boss|sister|brother|son|daughter|own|parents|family|ex))\b", re.I)
ATTRIB = re.compile(r"\b(?:how did you|what did you|did you (?!mean|say|know|think)|have you (?:ever )?(?:been|had|gone|lost|dealt|felt|done)|"
                    r"were you|when you (?:were|had|went|lost)|you (?:went|had|were|lost|dealt|handled|got through|did that)|"
                    r"your (?:mom|mother|dad|father|wife|husband|friend|boss|sister|brother|son|daughter|parents|family|ex|experience))\b", re.I)
SECOND = re.compile(r"\b(?:you|your|yours|yourself)\b", re.I)


def prepare(registry, metadata, gsws_resources, exposed, output, per_group=6, salt='semcap-g1-identity-v1'):
    out = Path(output); out.mkdir(parents=True, exist_ok=False)
    meta = json.loads(Path(metadata).read_text())
    gsws = [json.loads(s) for s in Path(gsws_resources).read_text().splitlines() if s.strip()]
    blocked = {r['family_id'] for r in gsws} | {f for r in gsws for f in r.get('ancestor_family_ids', [])}
    for path in exposed:
        blocked |= {json.loads(s)['family_id'] for s in Path(path).read_text().splitlines() if s.strip()}
    cands = []
    for raw in Path(registry).open():
        fold = re.search(r'"fold":(\d+)', raw); dataset = re.search(r'"dataset":"([^"]+)"', raw)
        split = re.search(r'"source_split":"([^"]+)"', raw)
        if (fold and int(fold[1]) == 6) or not split or split[1] != 'train' or not dataset or dataset[1] != 'ESConv':
            continue
        row = json.loads(raw); s = row['source']
        assert row['fold'] != 6
        if s['family_id'] in blocked or set(s['ancestor_family_ids']) & blocked: continue
        if s['excluded_for_overlap'] or s['family_id'] in meta['excluded_families']: continue
        turns = s['turns']; idx = None
        for i, t in enumerate(turns[:20]):
            if i >= 2 and t['role'] == 'supporter' and len(t['text']) >= 40 and DISCLOSE.search(t['text']):
                idx = i; break
        if idx is None or idx + 1 >= len(turns) or turns[idx + 1]['role'] != 'seeker': continue
        reply = turns[idx + 1]['text']
        group = 'M' if ATTRIB.search(reply) else ('N' if not SECOND.search(reply) else None)
        if group is None: continue   # ambiguous second-person turns are not used in either group
        key = hashlib.sha256((salt + '|' + s['family_id'] + '|' + s['session_id']).encode()).hexdigest()
        cands.append(dict(key=key, group=group, source_id=row.get('source_id'), family_id=s['family_id'],
            dataset='ESConv', source_split=s['source_split'], fold=row['fold'], session_id=s['session_id'],
            disclosure_turn=idx, cutoff_turn=idx + 1,
            turns=[dict(role=t['role'], text=t['text']) for t in turns[:idx + 2]],
            future_turns_read_into_input=False))
    selected, seen, counts = [], set(), {'M': 0, 'N': 0}
    for r in sorted(cands, key=lambda r: r['key']):
        if counts[r['group']] >= per_group or r['family_id'] in seen: continue
        counts[r['group']] += 1; seen.add(r['family_id']); selected.append(r)
    for n, r in enumerate(sorted(selected, key=lambda r: (r['group'], r['key'])), 1): r['alias'] = f"I{n:02}{r['group']}"
    selected.sort(key=lambda r: r['alias'])
    (out / 'PREFIXES.private.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in selected))
    rep = dict(protocol='semcap-g1-identity-v1', salt=salt, candidates=len(cands),
               candidates_by_group={g: sum(c['group'] == g for c in cands) for g in 'MN'}, selected=counts,
               fold6_included=False, exposed_family_overlap=0, causal_prefixes=True,
               selection='ESConv train; supporter first-person disclosure in first 20 turns followed by seeker turn; '
                         'M=seeker addresses supporter experience in 2nd person, N=no 2nd person; salted family hash order',
               aliases=[dict(alias=r['alias'], group=r['group'], prefix_turns=len(r['turns'])) for r in selected])
    (out / 'SELECTION_PUBLIC.json').write_text(json.dumps(rep, indent=2) + '\n'); print(json.dumps(rep, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    for n in ('registry', 'metadata', 'gsws-resources', 'output'): p.add_argument('--' + n, required=True)
    p.add_argument('--exposed', nargs='+', required=True)
    a = p.parse_args(); prepare(a.registry, a.metadata, a.gsws_resources, a.exposed, a.output)
