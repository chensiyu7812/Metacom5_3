#!/usr/bin/env python3
"""G4 post-run analysis (CPU). Public outputs contain aggregates only.

  stats    calls, tokens, per-role time, end-to-end agent time, C decisions by group,
           claim parsing, INSPECT outcomes, technical failures; joins the assistant's
           post-run development review (if given) for reliability/support/attribution.
  t0       re-judge every runtime-formed claim on the same legal items with frozen T0
           (and T1i again) on CPU: no Generator call.
  blind    build the 8 pre-fixed B-vs-A pairs as a blind packet (order by salted hash).
"""
import argparse, hashlib, json, sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src'))


def jl(p):
    return [json.loads(s) for s in Path(p).read_text().splitlines() if s.strip()]


def q(xs, p):
    xs = sorted(xs)
    return None if not xs else xs[min(len(xs) - 1, int(round(p * (len(xs) - 1))))]


def stats(a):
    res = jl(Path(a.run) / 'RESULTS.private.jsonl'); calls = jl(Path(a.run) / 'CALLS.private.jsonl')
    checks = {c['state_id']: c for c in json.loads(Path(a.checks).read_text())['checks']}
    review = {(r['state_id'], r['arm']): r for r in json.loads(Path(a.review).read_text())['items']} if a.review else {}
    out = dict(protocol='semcap-g4-stats-v1', run_summary=json.loads((Path(a.run) / 'RUN_SUMMARY.json').read_text())
               if (Path(a.run) / 'RUN_SUMMARY.json').exists() else None, arms={}, roles={}, c_decisions={}, review={})
    by_call = {c['call']: c for c in calls}
    for c in calls:
        r = out['roles'].setdefault(f"{c['arm']}/{c['role']}", dict(n=0, seconds=[], in_tok=[], out_tok=[], length=0, leak=0))
        r['n'] += 1; r['seconds'].append(c['seconds']); r['in_tok'].append(c['input_tokens']); r['out_tok'].append(c['output_tokens'])
        r['length'] += c['finish'] == 'length'; r['leak'] += c['thinking_leak']
    for k, r in out['roles'].items():
        out['roles'][k] = dict(n=r['n'], seconds_p50=q(r['seconds'], .5), seconds_p95=q(r['seconds'], .95),
                               seconds_total=round(sum(r['seconds']), 2), input_tokens_mean=round(sum(r['in_tok']) / r['n'], 1),
                               output_tokens_mean=round(sum(r['out_tok']) / r['n'], 1), length_finishes=r['length'], thinking_leaks=r['leak'])
    for arm in ('A', 'N', 'B', 'C'):
        rs = [r for r in res if r['arm'] == arm]
        if not rs: continue
        llm = [sum(by_call[i]['seconds'] for i in r['llm_calls']) for r in rs]
        insp = [r.get('inspect_seconds') or 0.0 for r in rs]
        ins = [t for r in rs for t in (r.get('inspect') or [])]
        out['arms'][arm] = dict(states=len(rs), errors=sum(bool(r['error']) for r in rs),
            llm_calls=sum(len(r['llm_calls']) for r in rs),
            agent_seconds_p50=q([r['agent_seconds'] for r in rs], .5), agent_seconds_p95=q([r['agent_seconds'] for r in rs], .95),
            agent_seconds_total=round(sum(r['agent_seconds'] for r in rs), 2),
            llm_seconds_total=round(sum(llm), 2), inspect_seconds_total=round(sum(insp), 3),
            claims=sum(len(r.get('claims') or []) for r in rs), claim_rejects=sum(len(r.get('claim_rejects') or []) for r in rs),
            parse_failures=sum(bool(r.get('parse_failure')) for r in rs),
            illegal_ids_dropped=sum(len(c.get('dropped_illegal_ids') or []) for r in rs for c in (r.get('claims') or [])),
            inspect_judgements=dict(Counter(t.get('result_judgement') for t in ins)),
            inspect_chunked=sum(bool((t.get('result') or {}).get('chunked_windows')) for t in ins),
            inspect_conflicts=dict(Counter((t.get('conflict') or {}).get('kind') for t in ins if t.get('conflict'))),
            inspect_model_calls=sum((t.get('cost') or {}).get('model_calls', 0) for t in ins),
            reply_length_finishes=sum(r.get('reply_finish') == 'length' for r in rs),
            reply_thinking_leaks_filtered=sum(bool(r.get('reply_thinking_leak')) for r in rs))
    rc = [r for r in res if r['arm'] == 'C']
    for g in 'SUHO':
        ids = [s for s, c in checks.items() if c['group'] == g]
        out['c_decisions'][g] = dict(Counter(r.get('decision') for r in rc if r['state_id'] in ids))
    # paired latency vs A
    a_t = {r['state_id']: r['agent_seconds'] for r in res if r['arm'] == 'A'}
    for arm in ('N', 'B', 'C'):
        d = [r['agent_seconds'] - a_t[r['state_id']] for r in res if r['arm'] == arm and r['state_id'] in a_t]
        if d: out['arms'][arm]['paired_extra_vs_A_p50'] = q(d, .5); out['arms'][arm]['paired_extra_vs_A_p95'] = q(d, .95)
    if review:
        for arm in ('A', 'N', 'B', 'C'):
            items = [v for (s, ar), v in review.items() if ar == arm]
            if not items: continue
            out['review'][arm] = dict(n=len(items), reliable=sum(v['must_not_violations'] == 0 for v in items),
                must_not_violations=sum(v['must_not_violations'] for v in items),
                should_met=sum(v['should_met'] for v in items), should_total=sum(len(checks[v['state_id']]['should']) for v in items),
                support=dict(Counter(v['support'] for v in items)), naturalness=dict(Counter(v['naturalness'] for v in items)),
                identity_issues=sum(v.get('identity_issue', False) for v in items),
                by_group={g: dict(reliable=sum(v['must_not_violations'] == 0 for v in items if checks[v['state_id']]['group'] == g),
                                  n=sum(checks[v['state_id']]['group'] == g for v in items)) for g in 'SUHO'})
        att = Counter(x for v in review.values() for x in v.get('attribution', []))
        out['review']['attribution'] = dict(att)
    Path(a.output).write_text(json.dumps(out, indent=1) + '\n'); print(json.dumps(out, indent=1)[:6000])


def t0(a):
    import torch; torch.set_num_threads(8)
    from metacom_pm.rl1v3.semcap.evidence_state import InspectClaim
    from metacom_pm.rl1v3.semcap.agent_skill import evidence_items
    from metacom_pm.rl1v3.semcap import identity as I
    states = {s['state_id']: s for s in jl(a.states)}
    models = {'T0': InspectClaim(a.t0), 'T1i': InspectClaim(a.t1i)}
    rows = []
    for r in jl(Path(a.run) / 'RESULTS.private.jsonl'):
        for k, c in enumerate(r.get('claims') or []):
            st = states[r['state_id']]
            ids = [i for i in c['evidence_ids'] if next(e for e in st['evidence'] if e['evidence_id'] == i).get('situation') != I.EXTERNAL_CASE]
            items = evidence_items(st['evidence'], ids)
            out = dict(state_id=r['state_id'], arm=r['arm'], k=k, claim=c['claim'], evidence_ids=ids,
                       runtime=(r['inspect'][k] or {}).get('result_judgement'))
            for name, m in models.items():
                out[name] = m(items, c['claim'])['judgement']
            rows.append(out)
    Path(a.output).write_text(''.join(json.dumps(x, ensure_ascii=False) + '\n' for x in rows))
    print(len(rows), 'claims;', 'T1i==runtime', sum(x['T1i'] == x['runtime'] for x in rows), 'T0==T1i', sum(x['T0'] == x['T1i'] for x in rows))
    print(Counter((x['T0'], x['T1i']) for x in rows))


def blind(a):
    res = {(r['state_id'], r['arm']): r for r in jl(Path(a.run) / 'RESULTS.private.jsonl')}
    states = {s['state_id']: s for s in jl(a.states)}
    pairs = json.loads(Path(a.checks).read_text())['blind_pairs']['states']
    packet, key = [], []
    for n, sid in enumerate(pairs, 1):
        flip = int(hashlib.sha256(f'semcap-g4-blind-v1|{sid}'.encode()).hexdigest(), 16) % 2 == 1
        x, y = res[(sid, 'B')], res[(sid, 'A')]
        first, second = (x, y) if flip else (y, x)
        st = states[sid]
        packet.append(dict(pair=f'P{n}', records=[{k: e[k] for k in ('evidence_id', 'speaker', 'text', 'reported_at')} for e in st['evidence']],
                           latest_user_message=st['user_turn'], reply_1=first.get('reply'), reply_2=second.get('reply')))
        key.append(dict(pair=f'P{n}', state_id=sid, reply_1=first['arm'], reply_2=second['arm']))
    out = Path(a.output); out.mkdir(parents=True, exist_ok=False)
    (out / 'BLIND_PACKET.private.json').write_text(json.dumps(dict(instructions='For each pair, which reply is more reliable about what the records establish, and which is more supportive and natural? You may answer "same".', pairs=packet), indent=1, ensure_ascii=False))
    (out / 'BLIND_KEY.private.json').write_text(json.dumps(key, indent=1))
    (out / 'STATUS_PUBLIC.json').write_text(json.dumps(dict(pairs=len(packet), comparison='B vs A', status='pending independent human reviewer'), indent=1))
    print('blind packet', len(packet))


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('mode', choices=['stats', 't0', 'blind'])
    for n in ('run', 'checks', 'states', 'review', 't0', 't1i', 'output'): p.add_argument('--' + n)
    a = p.parse_args(); dict(stats=stats, t0=t0, blind=blind)[a.mode](a)
