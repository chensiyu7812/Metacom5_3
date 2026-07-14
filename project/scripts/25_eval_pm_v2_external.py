#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from metacom_pm.config import endpoint_from_config, load_config
from metacom_pm.pm_v2_external_eval import run_external_response_evaluation

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=ROOT / "configs" / "experiment.yaml")
    parser.add_argument("--evoemo", type=Path, default=ROOT / "data" / "external" / "evo_emo.json")
    parser.add_argument(
        "--turn-paths",
        type=Path,
        nargs="+",
        default=[
            ROOT / "outputs" / "evoemo_selective" / "turns.jsonl",
            ROOT / "outputs" / "evoemo_pm_v2" / "turns.jsonl",
            ROOT / "outputs" / "evoemo_pm_v2_cost_matched_fixed" / "turns.jsonl",
            ROOT / "outputs" / "evoemo_pm_v2_me_r0_fixed" / "turns.jsonl",
        ],
    )
    parser.add_argument(
        "--conditions",
        nargs="+",
        default=[
            "pm_v2",
            "pm_v2_cost_matched_fixed",
            "pm_v2_me_r0_fixed",
            "no_memory_r0",
            "session_rag_rs",
            "best_fixed",
            "full_history_rs",
        ],
    )
    parser.add_argument("--treatment", default="pm_v2")
    parser.add_argument("--turn-indices", type=int, nargs="+", default=[3, 8])
    parser.add_argument(
        "--judge-endpoints",
        required=True,
        help="comma-separated configured endpoints from at least two independent families",
    )
    parser.add_argument("--out-dir", type=Path, default=ROOT / "outputs" / "pm_v2_external_response")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--max-api-calls", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=3701)
    args = parser.parse_args()

    config = load_config(args.config)
    endpoint_names = [
        value.strip() for value in args.judge_endpoints.split(",") if value.strip()
    ]
    endpoints = [endpoint_from_config(config, name) for name in endpoint_names]
    result = run_external_response_evaluation(
        evoemo_path=args.evoemo,
        turn_paths=args.turn_paths,
        conditions=args.conditions,
        treatment=args.treatment,
        turn_indices=args.turn_indices,
        endpoints=endpoints,
        out_dir=args.out_dir,
        run=args.run,
        max_api_calls=args.max_api_calls,
        seed=args.seed,
    )
    print(result)


if __name__ == "__main__":
    main()
