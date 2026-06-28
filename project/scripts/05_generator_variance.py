#!/usr/bin/env python3
from pathlib import Path
import argparse
from metacom_pm.config import load_config, endpoint_from_config
from metacom_pm.variance import run_generation_variance_diagnostic, select_variance_card_ids
ROOT = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser()
p.add_argument('--config', type=Path, default=ROOT/'configs/experiment.yaml')
p.add_argument('--endpoint', default='generator')
p.add_argument('--out-dir', type=Path, default=ROOT/'outputs/generator_variance')
p.add_argument('--n-states', type=int, default=24, help='number of independent full-action states')
p.add_argument('--n-cards', type=int, help='legacy alias for --n-states')
p.add_argument('--overwrite', action='store_true')
a = p.parse_args()
n_states = a.n_states if a.n_cards is None else a.n_cards
cfg = load_config(a.config)
endpoint = endpoint_from_config(cfg, a.endpoint)
a.out_dir.mkdir(parents=True, exist_ok=True)
responses = a.out_dir/'responses.jsonl'
report = a.out_dir/'report.json'
if a.overwrite:
    for path in (responses, report):
        if path.exists():
            path.unlink()
card_ids = select_variance_card_ids(ROOT/'data/synthetic/runtime_states.jsonl', n_states=n_states)
action_ids = [
    'M0+R0', 'M0+RS',
    'MP+R0', 'MS+R0', 'ME+R0',
    'MP+RS', 'MS+RS', 'ME+RS',
    'MPMSME+RS',
]
print(run_generation_variance_diagnostic(
    ROOT/'data/synthetic/runtime_states.jsonl',
    ROOT/'data/synthetic/memory_backend.jsonl',
    ROOT/'data/strategy/strategy_cards.jsonl',
    responses,
    report,
    endpoint=endpoint,
    card_ids=card_ids,
    action_ids=action_ids,
))
