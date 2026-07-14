#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from metacom_pm.config import endpoint_from_config, load_config
from metacom_pm.freeze import require_study_freeze
from metacom_pm.pm_v2_evoemo import run_pmv2_fixed_evoemo

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=ROOT / "configs" / "experiment.yaml")
    parser.add_argument("--generator-endpoint", default="generator")
    parser.add_argument("--checkpoint", type=Path, default=ROOT / "outputs" / "pm_v2_model" / "pm_v2.joblib")
    parser.add_argument("--fixed-tracks", type=Path, default=ROOT / "outputs" / "evoemo_fixed_tracks" / "fixed_seeker_tracks.jsonl")
    parser.add_argument("--fixed-tracks-attestation", type=Path, default=ROOT / "outputs" / "evoemo_fixed_tracks" / "artifact_attestation.json")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "outputs" / "evoemo_pm_v2")
    parser.add_argument("--simulator-id", default="seeker_main")
    parser.add_argument("--protocol", choices=["official", "selective"], default="selective")
    parser.add_argument("--max-turns", type=int, default=10)
    parser.add_argument("--seeds", type=int, nargs="+")
    parser.add_argument("--max-scenarios", type=int)
    parser.add_argument("--max-ood-fallback-rate", type=float, default=0.25)
    parser.add_argument("--strategy-action-tokens", type=int, default=260)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--freeze", type=Path)
    parser.add_argument("--allow-unfrozen-debug", action="store_true")
    args = parser.parse_args()

    config = load_config(args.config)
    configured_seeds = [
        int(value) for value in (config.get("protocol") or {}).get("robustness_seeds", [])
    ]
    if args.seeds is None:
        args.seeds = configured_seeds or [101]
    if args.max_scenarios is not None and not args.allow_unfrozen_debug:
        raise RuntimeError("--max-scenarios is debug-only")
    evoemo_path = ROOT / "data" / "external" / "evo_emo.json"
    strategy_path = ROOT / "data" / "strategy" / "strategy_cards.jsonl"
    freeze_sha = None
    if args.freeze is not None:
        verification = require_study_freeze(
            args.freeze,
            release_root=ROOT,
            config_path=args.config,
            required_files=[
                evoemo_path,
                strategy_path,
                args.checkpoint,
                args.fixed_tracks,
                args.fixed_tracks_attestation,
            ],
            allow_unfrozen_debug=args.allow_unfrozen_debug,
        )
        freeze_sha = verification.get("freeze_sha256")
    elif not args.allow_unfrozen_debug:
        raise RuntimeError(
            "A PM-v2 study freeze is required for reportable generation. "
            "Use --allow-unfrozen-debug only for non-reportable testing."
        )

    result = run_pmv2_fixed_evoemo(
        evoemo_path,
        strategy_path,
        args.checkpoint,
        args.fixed_tracks,
        args.out_dir,
        generator_endpoint=endpoint_from_config(config, args.generator_endpoint),
        simulator_id=args.simulator_id,
        fixed_tracks_attestation_path=args.fixed_tracks_attestation,
        protocol=args.protocol,
        max_turns=args.max_turns,
        seeds=args.seeds,
        max_scenarios=args.max_scenarios,
        overwrite=args.overwrite,
        strategy_action_tokens=args.strategy_action_tokens,
        max_ood_fallback_rate=args.max_ood_fallback_rate,
        study_freeze_sha256=freeze_sha,
    )
    print(result)


if __name__ == "__main__":
    main()
