#!/usr/bin/env python3
"""CPU mechanism trace: INSPECT_CLAIM inside a minimal acquire -> inspect -> revise loop.

Uses DEV_DCS sequence items (family-disjoint from training): session 1 (context + earlier
utterance) is visible; session 2 is an unread history window the agent may acquire.
  fixed      always acquire session 2, then inspect once on everything
  on_demand  inspect session 1; acquire + re-inspect only if not_established
Claims are the assistant-authored DCS claims (claim *formation* by the system is NOT tested
here). This demonstrates the interface, revision bookkeeping and call savings; it is not a
reply-quality or user-outcome experiment.
"""
import argparse, json, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'src'))
from metacom_pm.rl1v3.semcap.evidence_state import InspectClaim  # noqa: E402
from metacom_pm.rl1v3.semcap.agent_skill import InspectClaimSkill  # noqa: E402
from metacom_pm.rl1v3.semcap import identity as I  # noqa: E402
import ast  # noqa: E402


def main(a):
    import torch; torch.set_num_threads(a.threads)
    rows = [json.loads(s) for s in Path(a.dev).read_text().splitlines() if s.strip()]
    seeds = {json.loads(s)['seed_id']: json.loads(s) for s in Path(a.seeds).read_text().splitlines() if s.strip()}
    authored = {x[0]: x for x in ast.literal_eval(Path(a.authored).read_text())}
    insp = InspectClaim(a.checkpoint, device='cpu')
    traces = []; agg = dict(fixed=dict(correct=0, model_calls=0, acquisitions=0, seconds=0.0),
                            on_demand=dict(correct=0, model_calls=0, acquisitions=0, seconds=0.0))
    for r in [x for x in rows if x['kind'] == 'sequence']:
        s = seeds[r['seed_id']]; sid, variants, claims, _ = authored[r['seed_id']]
        ev = {'n': ('seeker', s['utterance'])}; ev.update({k: ('seeker' if w == 'user' else 'supporter', t) for k, (w, t) in variants.items()})
        first, later = r['sequence']
        vis = [dict(evidence_id='H1a', speaker=s['context']['role'], text=s['context']['text'], reported_at='session-1', origin='actually_read_history'),
               dict(evidence_id='H1b', speaker=ev[first][0], text=ev[first][1], reported_at='session-1', origin='actually_read_history')]
        unread = dict(evidence_id='H2', speaker=ev[later][0], text=ev[later][1], reported_at='session-2', origin='actually_read_history')
        claim = r['hypothesis']; gold_after = r['label']
        sk = InspectClaimSkill(insp, I.IMPORTED_HUMAN)
        act = lambda ids: dict(action='INSPECT_CLAIM', claim=claim, evidence_ids=ids, subject='user', time_scope='as_of_latest_evidence')
        # fixed
        t0 = time.perf_counter(); res, wm, tr = sk.invoke(vis + [unread], act(['H1a', 'H1b', 'H2']), {})
        f = dict(actions=['ACQUIRE(H2)', 'INSPECT_CLAIM'], final=res['judgement'], seconds=time.perf_counter() - t0,
                 model_calls=res['cost']['model_calls'], acquisitions=1)
        # on demand
        t0 = time.perf_counter(); res1, wm, tr1 = sk.invoke(vis, act(['H1a', 'H1b']), {}); steps = [tr1]; calls = res1['cost']['model_calls']; acq = 0
        actions = ['INSPECT_CLAIM']
        if res1['judgement'] == 'not_established':
            acq = 1; actions += ['ACQUIRE(H2)', 'INSPECT_CLAIM']
            res2, wm, tr2 = sk.invoke(vis + [unread], act(['H1a', 'H1b', 'H2']), wm); steps.append(tr2); calls += res2['cost']['model_calls']
        o = dict(actions=actions, before=res1['judgement'], final=wm[claim]['judgement'], transition=wm[claim].get('transition'),
                 conflict=wm[claim].get('conflict'), seconds=time.perf_counter() - t0, model_calls=calls, acquisitions=acq)
        for k, v in (('fixed', f), ('on_demand', o)):
            agg[k]['correct'] += v['final'] == gold_after; agg[k]['model_calls'] += v['model_calls']
            agg[k]['acquisitions'] += v['acquisitions']; agg[k]['seconds'] += v['seconds']
        traces.append(dict(item_id=r['item_id'], gold_before=next(x['label'] for x in rows if x['item_id'] == r['before_item']),
                           gold_after=gold_after, fixed=f, on_demand=o))
    for k in agg: agg[k]['seconds'] = round(agg[k]['seconds'], 3)
    out = Path(a.output); out.mkdir(parents=True, exist_ok=False)
    (out / 'TRACES.private.json').write_text(json.dumps(traces, indent=1))
    pub = dict(protocol='semcap-inspect-claim-trace-v1', checkpoint=a.checkpoint, items=len(traces), aggregate=agg,
               on_demand_transitions=[t['on_demand']['transition'] for t in traces],
               scope='mechanism trace on 6 assistant-authored dev sequences; claim formation not tested; not reply quality')
    (out / 'TRACE_SUMMARY_PUBLIC.json').write_text(json.dumps(pub, indent=1) + '\n'); print(json.dumps(pub, indent=1))


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    for n in ('checkpoint', 'dev', 'seeds', 'authored', 'output'): p.add_argument('--' + n, required=True)
    p.add_argument('--threads', type=int, default=8)
    main(p.parse_args())
