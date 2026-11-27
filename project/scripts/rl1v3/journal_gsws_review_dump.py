#!/usr/bin/env python3
"""Private per-state review sheet from actually collected GSWS outputs (no scoring).

For each goal/stage: visible current dialogue, actually read historical evidence,
the frozen semantic checks, the A1 notes and A2 GSWS interpretations, and the three
terminal replies with finish reason and token/latency facts. Output stays local.
"""
import argparse, json
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--collected', required=True); p.add_argument('--contract', required=True); p.add_argument('--output', required=True); p.add_argument('--evidence-chars', type=int, default=0)
    a = p.parse_args()
    c = Path(a.collected)
    terms = [json.loads(l) for l in (c / 'TERMINALS_RAW.private.jsonl').open()]
    interp = [json.loads(l) for l in (c / 'INTERPRETERS_RAW.private.jsonl').open()]
    spec = {}
    for l in Path(a.contract).open():
        r = json.loads(l); spec[(r['goal_alias'], r['stage'])] = r
    out = []
    for (task, stage) in sorted({(t['task'], t['stage']) for t in terms}):
        s = spec.get((task, stage), {})
        out.append(f'\n\n## {task}-S{stage}  fact_goal={s.get("fact_goal")} support_goal={s.get("support_goal")} recite={s.get("historical_facts_must_be_recited")}')
        out.append('**Semantic checks (frozen):** ' + ' / '.join(s.get('semantic_checks', [])))
        t0 = next(t for t in terms if t['task'] == task and t['stage'] == stage)
        obs = t0['request']['binding']['observation']
        out.append('\n**Evidence actually visible:**')
        for e in obs['evidence']:
            out.append(f"- {e['evidence_id']} [{e['kind']}; {e['speaker']}; report {e['report_time']}] {e['text'][:a.evidence_chars] if a.evidence_chars else e['text']}")
        for i in [x for x in interp if x['task'] == task and x['stage'] == stage]:
            o = i['raw_output']
            out.append(f"\n**Interpreter {i['arm']}** (in {o.get('input_tokens')} tok, out {len(o.get('token_ids') or [])} tok, {o.get('seconds'):.2f}s, {o.get('finish_reason')}):\n```\n{o.get('text')}\n```")
        for t in sorted([x for x in terms if x['task'] == task and x['stage'] == stage], key=lambda x: x['arm']):
            o = t['raw_output']
            out.append(f"\n**Terminal {t['arm']}** (in {o.get('input_tokens')} tok, out {len(o.get('token_ids') or [])} tok, {o.get('seconds'):.2f}s, {o.get('finish_reason')}):\n> " + (o.get('text') or '').replace('\n', '\n> '))
    Path(a.output).write_text('# GSWS v3 actual outputs — private development review sheet\n' + '\n'.join(out) + '\n')
    print(a.output, len(terms), 'terminals', len(interp), 'interpretations')


if __name__ == '__main__':
    main()
