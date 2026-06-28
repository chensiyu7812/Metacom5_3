#!/usr/bin/env python3
if __name__ == "__main__":
    from pathlib import Path
    import argparse
    from metacom_pm.config import load_config, endpoint_from_config
    from metacom_pm.judging import run_judging
    ROOT = Path(__file__).resolve().parents[1]
    p = argparse.ArgumentParser()
    p.add_argument('--config', type=Path, default=ROOT/'configs/experiment.yaml')
    p.add_argument('--endpoint', default='training_judge')
    p.add_argument('--out-dir', type=Path, default=ROOT/'outputs/full_judging')
    p.add_argument('--pilot-gate', type=Path, default=ROOT/'outputs/judge_pilot/pilot_gate.json')
    p.add_argument('--overwrite', action='store_true')
    a = p.parse_args()
    ep = endpoint_from_config(load_config(a.config), a.endpoint)
    print(run_judging(
        ROOT/'data/synthetic/runtime_states.jsonl',
        ROOT/'data/synthetic/memory_backend.jsonl',
        ROOT/'outputs/synthetic_sweep/action_outcomes.jsonl',
        ROOT/'data/synthetic/pair_graph.jsonl',
        a.out_dir,
        endpoint=ep,
        mode='full',
        max_cards=None,
        pilot_gate_path=a.pilot_gate,
        overwrite=a.overwrite,
    ))
