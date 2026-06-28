#!/usr/bin/env python3
from pathlib import Path
import argparse

from metacom_pm.config import load_config, endpoint_from_config
from metacom_pm.evoemo import build_fixed_seeker_tracks


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, default=ROOT / 'configs/experiment.yaml')
    parser.add_argument('--seeker-endpoint', default='seeker')
    parser.add_argument('--simulator-id', default='seeker_main')
    parser.add_argument('--out-dir', type=Path, default=ROOT / 'outputs/evoemo_fixed_tracks')
    parser.add_argument('--max-turns', type=int, default=10)
    parser.add_argument('--seeds', type=int, nargs='+')
    parser.add_argument('--max-scenarios', type=int)
    parser.add_argument('--overwrite', action='store_true')
    args = parser.parse_args()

    config = load_config(args.config)
    seeds = args.seeds
    if seeds is None:
        seeds = [int(x) for x in (config.get('protocol') or {}).get('robustness_seeds', [])]
    if not seeds:
        raise RuntimeError("configs/experiment.yaml protocol.robustness_seeds is empty")
    if args.max_scenarios is not None:
        raise RuntimeError(
            "--max-scenarios is for non-reportable debugging only. "
            "Do not include a subset fixed-track file in study freeze."
        )

    print(build_fixed_seeker_tracks(
        ROOT / 'data/external/evo_emo.json',
        args.out_dir,
        seeker_endpoint=endpoint_from_config(config, args.seeker_endpoint),
        simulator_id=args.simulator_id,
        max_turns=args.max_turns,
        seeds=seeds,
        max_scenarios=args.max_scenarios,
        overwrite=args.overwrite,
    ))


if __name__ == '__main__':
    main()
