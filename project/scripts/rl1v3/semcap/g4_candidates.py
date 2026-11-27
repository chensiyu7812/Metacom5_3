#!/usr/bin/env python3
"""G4 candidate pool (CPU, before any prediction). Private output.

Eligibility
  ESConv: train split, fold != 6, not excluded_for_overlap / excluded family, and none of the
          already exposed families (GSWS, event32, speaker32, G1, DCS). Evidence = the imported
          earlier turns of the same conversation (situation A).
  EvoEmo: historical-train owners only, fold != 6; owners already used by GSWS (p13, family
          group p13/p18) and by event32/speaker32 (p5, p6) are excluded entirely so their
          sessions cannot re-enter as history. Evidence = up to two previous sessions of the
          same owner (with report dates) + the earlier turns of the current session
          (situation U: supporter author not established).
Cutoffs: EvoEmo -> first seeker turn of a later session with >= 25 chars ("opening") and the
first seeker turn at index >= 6 ("mid"); ESConv -> first seeker turn at index >= 10 with >= 40
chars. Candidates are ordered by a salted hash; group assignment is done afterwards by the
assistant in that order using written criteria (G4_STATES_FROZEN).
"""
import argparse, hashlib, json, re
from pathlib import Path

EXCLUDED_EVO_OWNERS = {'p5', 'p6', 'p13', 'p18'}


def main(a):
    meta = json.loads(Path(a.metadata).read_text())
    gsws = [json.loads(s) for s in Path(a.gsws_resources).read_text().splitlines() if s.strip()]
    blocked = {r['family_id'] for r in gsws} | {f for r in gsws for f in r.get('ancestor_family_ids', [])}
    for p in a.exposed:
        for s in Path(p).read_text().splitlines():
            if s.strip():
                blocked.add(json.loads(s)['family_id'])
    train_owners = {o for o, sp in meta['folds']['historical_rl1_split'].items()
                    if sp == 'train' and meta['folds']['fold_of_owner'][o] != 6} - EXCLUDED_EVO_OWNERS
    evo = {}; esc = []
    for raw in Path(a.registry).open():
        fold = re.search(r'"fold":(\d+)', raw); ds = re.search(r'"dataset":"([^"]+)"', raw)
        sp = re.search(r'"source_split":"([^"]+)"', raw)
        if (fold and int(fold[1]) == 6) or not ds: continue
        row = json.loads(raw); s = row['source']
        if ds[1] == 'es_memeval_evoemo_public_v1':
            if s['owner_id'] in train_owners:
                evo.setdefault(s['owner_id'], []).append(s)
        elif ds[1] == 'ESConv' and sp and sp[1] == 'train':
            if s['family_id'] in blocked or set(s['ancestor_family_ids']) & blocked: continue
            if s['excluded_for_overlap'] or s['family_id'] in meta['excluded_families']: continue
            esc.append(s)
    cands = []
    for owner, sess in evo.items():
        sess.sort(key=lambda s: s['chronological_rank'])
        for k in range(1, len(sess)):
            cur = sess[k]
            if cur['family_id'] in blocked: continue
            prev = sess[max(0, k - 2):k]
            if any(p['family_id'] in blocked for p in prev): continue
            t = cur['turns']; cuts = {}
            op = next((i for i, x in enumerate(t) if x['role'] == 'seeker' and len(x['text']) >= 25), None)
            if op is not None: cuts['opening'] = op
            mid = next((i for i, x in enumerate(t) if i >= 6 and x['role'] == 'seeker' and len(x['text']) >= 25), None)
            if mid is not None and mid != op: cuts['mid'] = mid
            for kind, i in cuts.items():
                key = hashlib.sha256(f"semcap-g4-v1|evo|{owner}|{cur['session_id']}|{kind}".encode()).hexdigest()
                ev = []
                for p in prev:
                    ev += [dict(evidence_id=f"H{p['chronological_rank']}.{j}", speaker=x['role'], text=x['text'],
                                reported_at=p['date'], origin='actually_read_history', session_id=p['session_id'])
                           for j, x in enumerate(p['turns'])]
                ev += [dict(evidence_id=f"C{j}", speaker=x['role'], text=x['text'], reported_at=cur['date'],
                            origin='current_visible', session_id=cur['session_id']) for j, x in enumerate(t[:i])]
                cands.append(dict(key=key, dataset='EvoEmo', situation='U_unknown_supporter_identity', owner_id=owner,
                                  family_id=cur['family_id'], history_family_ids=[p['family_id'] for p in prev],
                                  session_id=cur['session_id'], session_rank=cur['chronological_rank'], cut=kind,
                                  cutoff_turn=i, current_date=cur['date'], evidence=ev, user_turn=t[i]['text'],
                                  future_turns_read=False))
    for s in esc:
        t = s['turns']
        i = next((i for i, x in enumerate(t) if i >= 10 and x['role'] == 'seeker' and len(x['text']) >= 40), None)
        if i is None: continue
        key = hashlib.sha256(f"semcap-g4-v1|esc|{s['family_id']}".encode()).hexdigest()
        ev = [dict(evidence_id=f"C{j}", speaker=x['role'], text=x['text'], reported_at=None, origin='current_visible',
                   session_id=s['session_id']) for j, x in enumerate(t[:i])]
        cands.append(dict(key=key, dataset='ESConv', situation='A_imported_human_supporter', owner_id=None,
                          family_id=s['family_id'], history_family_ids=[], session_id=s['session_id'], session_rank=0,
                          cut='mid', cutoff_turn=i, current_date=None, evidence=ev, user_turn=t[i]['text'],
                          future_turns_read=False))
    cands.sort(key=lambda r: r['key'])
    out = Path(a.output); out.mkdir(parents=True, exist_ok=False)
    (out / 'CANDIDATES.private.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in cands))
    rep = dict(protocol='semcap-g4-candidates-v1', evoemo_owners=sorted(evo), excluded_evoemo_owners=sorted(EXCLUDED_EVO_OWNERS),
               candidates={d: sum(r['dataset'] == d for r in cands) for d in ('ESConv', 'EvoEmo')},
               fold6_included=False, exposed_families_blocked=len(blocked))
    (out / 'CANDIDATES_PUBLIC.json').write_text(json.dumps(rep, indent=2) + '\n'); print(json.dumps(rep))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    for n in ('registry', 'metadata', 'gsws-resources', 'output'): p.add_argument('--' + n, required=True)
    p.add_argument('--exposed', nargs='+', required=True)
    main(p.parse_args())
