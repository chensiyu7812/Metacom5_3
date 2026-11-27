#!/usr/bin/env python3
"""G6 state selection (CPU, before any prediction) with an explicit isolation report.

Pool = the G4 candidate pool (same eligibility: train only, fold 6 sealed, GSWS / event32 /
speaker32 / G1 / DCS families blocked, EvoEmo owners p5/p6/p13/p18 excluded) minus everything
G4 used. No curation into groups: natural states in salted-hash order (the screen is meant to
measure the real failure base rate, not to hunt for favourable cases).

Isolation levels
  state    every G6 state is new.
  session  no G6 current or history session overlaps any G4 session (current or history);
           two G6 states never share a session.
  owner    ESConv: no user IDs exist (one conversation = one family; owner unknown).
           EvoEmo: only 9 eligible owners exist and G4 used 8 -> owners are REUSED; G6 is not
           a new-user test. Screening and hold-out EvoEmo owners are disjoint.
  dataset  ESConv (situation A) and EvoEmo (situation U) both kept.
Split: ESConv family hash -> hold-out if h % 3 == 0; EvoEmo owners -> the 3 smallest owner
hashes are hold-out. Screening 20 ESConv + 12 EvoEmo (6 owners x 2); hold-out 10 + 6 (3 x 2).
"""
import argparse, hashlib, json
from pathlib import Path

SALT = 'semcap-g6-v1'


def h(s):
    return hashlib.sha256(f'{SALT}|{s}'.encode()).hexdigest()


def sessions_of(c):
    s = {(c['owner_id'], e['session_id']) for e in c['evidence'] if e.get('session_id')}
    return s | {(c['owner_id'], c['session_id'])}


def main(a):
    cands = [json.loads(s) for s in Path(a.candidates).read_text().splitlines() if s.strip()]
    g4 = [json.loads(s) for s in Path(a.g4_states).read_text().splitlines() if s.strip()]
    by_key = {c['key']: c for c in cands}
    g4c = [by_key[s['candidate_key']] for s in g4]
    g4_fam = {c['family_id'] for c in g4c} | {f for c in g4c for f in c['history_family_ids']}
    g4_sess = set().union(*[sessions_of(c) for c in g4c if c['dataset'] == 'EvoEmo'])
    g4_owners = {c['owner_id'] for c in g4c if c['dataset'] == 'EvoEmo'}
    esc = [c for c in cands if c['dataset'] == 'ESConv' and c['family_id'] not in g4_fam]
    esc.sort(key=lambda c: h('order|' + c['family_id']))
    pick = dict(screen=[], holdout=[])
    for c in esc:
        part = 'holdout' if int(h('split|' + c['family_id'])[:8], 16) % 3 == 0 else 'screen'
        if len([x for x in pick[part] if x['dataset'] == 'ESConv']) < (10 if part == 'holdout' else 20):
            pick[part].append(c)
    evo = [c for c in cands if c['dataset'] == 'EvoEmo']
    owners = sorted({c['owner_id'] for c in evo}, key=lambda o: h('owner|' + o))
    hold_owners = set(owners[:3])
    used = set(); shortfall = {}
    def eligible(o):
        for c in sorted([c for c in evo if c['owner_id'] == o], key=lambda c: h('evo|' + c['key'])):
            s = sessions_of(c)
            if s & g4_sess or s & used or c['family_id'] in g4_fam: continue
            yield c, s
    for rnd in (1, 2, 3):   # round-robin: at most one state per owner per round; targets 12 / 6
        for o in owners:
            part = 'holdout' if o in hold_owners else 'screen'
            target = 6 if part == 'holdout' else 12
            have = [x for x in pick[part] if x['dataset'] == 'EvoEmo']
            if len(have) >= target or sum(x['owner_id'] == o for x in have) >= rnd: continue
            if rnd == 3 and any(sum(x['owner_id'] == q for x in have) < 2 for q in owners
                                if (q in hold_owners) == (o in hold_owners) and q not in shortfall): continue
            got = next(eligible(o), None)
            if got is None:
                shortfall[o] = sum(x['owner_id'] == o for x in have); continue
            pick[part].append(got[0]); used |= got[1]
    for part, target in (('screen', 12), ('holdout', 6)):
        assert sum(x['dataset'] == 'EvoEmo' for x in pick[part]) == target, (part, shortfall)
    out = Path(a.output); out.mkdir(parents=True, exist_ok=False); rows = []
    for part in ('screen', 'holdout'):
        for k, c in enumerate(sorted(pick[part], key=lambda c: c['key']), 1):
            rows.append(dict(state_id=('S' if part == 'screen' else 'H') + f'{k:02}', part=part, candidate_key=c['key'],
                             dataset=c['dataset'], owner_id=c['owner_id'], family_id=c['family_id'],
                             history_family_ids=c['history_family_ids'], session_id=c['session_id'], cut=c['cut']))
    (out / 'G6_SELECTION.private.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows))
    scr = [r for r in rows if r['part'] == 'screen']; hol = [r for r in rows if r['part'] == 'holdout']
    rep = dict(protocol='semcap-g6-selection-v1', screen=len(scr), holdout=len(hol),
               datasets={p: {d: sum(r['dataset'] == d for r in rs) for d in ('ESConv', 'EvoEmo')} for p, rs in (('screen', scr), ('holdout', hol))},
               isolation=dict(
                   state='all new',
                   session=dict(overlap_with_g4_sessions=0, shared_sessions_within_g6=0),
                   family=dict(current_family_overlap_with_g4=0, all_exposed_sets_blocked=True),
                   owner=dict(esconv='owner unknown (no user ids); each conversation a distinct family',
                              evoemo_owners_screen=sorted({r['owner_id'] for r in scr if r['owner_id']}),
                              evoemo_owners_holdout=sorted({r['owner_id'] for r in hol if r['owner_id']}),
                              evoemo_owners_reused_from_g4=sorted({r['owner_id'] for r in rows if r['owner_id']} & g4_owners),
                              screen_holdout_owner_overlap=sorted({r['owner_id'] for r in scr if r['owner_id']} & {r['owner_id'] for r in hol if r['owner_id']}),
                              statement='EvoEmo has 9 eligible owners and G4 used 8: G6 is NOT an independent-new-user test'),
                   fold6_included=False), owner_shortfall=shortfall)
    (out / 'G6_SELECTION_PUBLIC.json').write_text(json.dumps(rep, indent=1) + '\n'); print(json.dumps(rep, indent=1))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    for n in ('candidates', 'g4-states', 'output'): p.add_argument('--' + n, required=True)
    main(p.parse_args())
