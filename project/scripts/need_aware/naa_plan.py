#!/usr/bin/env python3
"""Reproducible GPU budget arithmetic for the joint NAA WP3+WP4 request (planning, not results).

Inputs are measured, not assumed: per-model prefill (input tokens / internal first-token time)
and decode rates, load and teardown from the WP2 exec-v2 ledger; per-arm input tokens from the
real WP3 CPU materialization. Counts not yet frozen by A are parameters with explicit ranges.
Worst case = every request emits max_new_tokens; caps are set from worst cases, never from
expected values.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

LEDGER = '/opt/tokkio-data0/naa/20261127/agent_b/runs/wp2-exec-v2-model/model/LEDGER.001.jsonl'


def measured():
    pre, dec, load = {}, {}, {}
    for line in open(LEDGER):
        e = json.loads(line)
        m = e.get('model_label')
        if e.get('event') == 'ATTEMPT_RESULT' and e.get('first_token_latency_ns') and e.get('generation_ns'):
            if e['input_tokens'] > 6000:
                pre.setdefault(m, []).append(e['input_tokens'] / (e['first_token_latency_ns'] / 1e9))
            dec.setdefault(m, []).append(e['output_tokens'] / (e['generation_ns'] / 1e9))
        if e.get('event') == 'LOAD_OK':
            load[m] = e['measurement']['supervisor_load_ns'] / 1e9
    med = lambda v: sorted(v)[len(v) // 2]
    return {m: dict(prefill_tok_s=round(med(pre[m])), decode_tok_s=round(med(dec[m]), 2), load_s=round(load[m], 1))
            for m in pre}


def per_request(rate, input_tokens, max_new, overhead=0.5):
    return input_tokens / rate['prefill_tok_s'] + max_new / rate['decode_tok_s'] + overhead


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--wp3-stats', required=True, help='WP3_STATS.json (real per-arm input tokens)')
    p.add_argument('--n-confirm', type=int, default=160)
    p.add_argument('--direct-missing-rate', type=float, default=33 / 240)
    p.add_argument('--wp4-eval-requests', type=int, default=400, help='WP4 dev open-response tasks (A)')
    p.add_argument('--wp4-max-new', type=int, default=384)
    p.add_argument('--train-tokens', type=int, default=8_800_000, help='per epoch, positives (A data)')
    p.add_argument('--out', required=True)
    a = p.parse_args()
    rate = measured()
    st = json.loads(Path(a.wp3_stats).read_text())['by_model_arm']
    tok = {k: v['input_tokens']['p95'] for k, v in st.items()}
    # E0/E0s share the B1/B1s caps (8192 / 1536); until the E0 supply finishes their p95 is bounded by B1/B1s.
    for m in ('Qwen35', 'G0e'):
        tok.setdefault(f'{m}|E0', tok[f'{m}|B1']); tok.setdefault(f'{m}|E0s', tok[f'{m}|B1s'])
    miss = math.ceil(a.n_confirm * a.direct_missing_rate)
    blocks = {
        'WP3 confirm, Qwen35 x 7 arms': ('Qwen35', {x: a.n_confirm - (miss if x in ('C', 'Cn') else 0)
                                                    for x in ('B0', 'B1', 'B1s', 'E0', 'E0s', 'C', 'Cn')}, 64),
        'WP3 protocol bridge, old-dev 60 x B0/C x Qwen35': ('Qwen35', {'B0': 60, 'C': 60}, 64),
        'WP3 protocol bridge, old-dev 60 x B0/C x G0e': ('G0e', {'B0': 60, 'C': 60}, 64),
        'WP3 Gemma replication, 60 confirm x B0/E0s/C/E0': ('G0e', {'B0': 60, 'E0s': 60, 'C': 60, 'E0': 60}, 64),
        'WP4 base-G open dev, U0/U1 x Qwen35': ('Qwen35', {'E0s': 2 * a.wp4_eval_requests}, a.wp4_max_new),
        'WP4 adapted-G open dev, U2/U3 x Qwen35': ('Qwen35', {'E0s': 2 * a.wp4_eval_requests}, a.wp4_max_new),
    }
    out = dict(measured=rate, input_tokens_p95=tok, blocks={})
    for name, (m, arms, max_new) in blocks.items():
        n = sum(arms.values())
        worst = sum(c * per_request(rate[m], tok[f'{m}|{x}'], max_new) for x, c in arms.items())
        out['blocks'][name] = dict(model=m, executable=n, max_new_tokens=max_new, worst_case_gpu_s=round(worst))
    tr = rate['Qwen35']['prefill_tok_s'] / 4
    out['training'] = dict(model='Qwen35', assumed_train_tok_s=tr,
                           sft_2epoch_s=round(2 * a.train_tokens / tr),
                           paired_2epoch_s=round(2 * 2 * a.train_tokens / tr),
                           note='4x prefill is a planning assumption; the approved 20-step technical smoke measures it')
    Path(a.out).write_text(json.dumps(out, indent=2) + '\n')
    print(json.dumps(out, indent=2))


if __name__ == '__main__':
    main()
