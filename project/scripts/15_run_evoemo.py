#!/usr/bin/env python3
from pathlib import Path
import argparse
from metacom_pm.config import load_config, endpoint_from_config
from metacom_pm.evoemo import run_evoemo_dialogues
from metacom_pm.freeze import require_study_freeze
from metacom_pm.io import write_json

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--config', type=Path, default=ROOT / 'configs/experiment.yaml')
parser.add_argument('--generator-endpoint', default='generator')
parser.add_argument('--seeker-endpoint', default='seeker')
parser.add_argument('--checkpoint', type=Path, required=True)
parser.add_argument('--selection', type=Path, default=ROOT / 'outputs/selection.json')
parser.add_argument('--protocol', choices=['official', 'selective'], required=True)
parser.add_argument('--interaction-mode', choices=['fixed', 'interactive'], default='fixed')
parser.add_argument('--simulator-id', default='seeker_main')
parser.add_argument('--fixed-tracks-path', type=Path,
                    default=ROOT / 'outputs/evoemo_fixed_tracks/fixed_seeker_tracks.jsonl')
parser.add_argument('--fixed-tracks-attestation', type=Path,
                    default=ROOT / 'outputs/evoemo_fixed_tracks/artifact_attestation.json')
parser.add_argument('--max-turns', type=int, default=10)
parser.add_argument('--max-scenarios', type=int)
parser.add_argument('--seeds', type=int, nargs='+')
parser.add_argument('--overwrite', action='store_true')
parser.add_argument('--freeze', type=Path, default=ROOT / 'outputs/study_freeze.json')
parser.add_argument('--allow-unfrozen-debug', action='store_true', help='Non-reportable debugging only')
args = parser.parse_args()

config = load_config(args.config)
configured_seeds = [int(x) for x in (config.get('protocol') or {}).get('robustness_seeds', [])]
if args.seeds is None:
    args.seeds = configured_seeds
if not args.allow_unfrozen_debug:
    if args.max_scenarios is not None:
        raise RuntimeError(
            "--max-scenarios is forbidden for confirmatory EvoEmo runs. "
            "Use --allow-unfrozen-debug for non-reportable debugging."
        )
    if not configured_seeds:
        raise RuntimeError("configs/experiment.yaml protocol.robustness_seeds is empty")
    if [int(x) for x in args.seeds] != configured_seeds:
        raise RuntimeError(
            f"Confirmatory EvoEmo seeds must match frozen config robustness_seeds: "
            f"{configured_seeds}; got {args.seeds}"
        )
evoemo_path = ROOT / 'data/external/evo_emo.json'
strategy_path = ROOT / 'data/strategy/strategy_cards.jsonl'
freeze = require_study_freeze(
    args.freeze,
    release_root=ROOT,
    config_path=args.config,
required_files=[
        evoemo_path,
        strategy_path,
        args.checkpoint,
        args.selection,
        *(
            [args.fixed_tracks_path, args.fixed_tracks_attestation]
            if args.interaction_mode == 'fixed' else []
        ),
    ],
    allow_unfrozen_debug=args.allow_unfrozen_debug,
)
out_dir = ROOT / f'outputs/evoemo_{args.protocol}'
out_dir.mkdir(parents=True, exist_ok=True)
write_json(out_dir / 'freeze_verification.json', freeze)

print(run_evoemo_dialogues(
    evoemo_path,
    strategy_path,
    args.checkpoint,
    args.selection,
    out_dir,
    generator_endpoint=endpoint_from_config(config, args.generator_endpoint),
    seeker_endpoint=endpoint_from_config(config, args.seeker_endpoint),
    simulator_id=args.simulator_id,
    protocol=args.protocol,
    interaction_mode=args.interaction_mode,
    fixed_tracks_path=(args.fixed_tracks_path if args.interaction_mode == 'fixed' else None),
    fixed_tracks_attestation_path=(
        args.fixed_tracks_attestation if args.interaction_mode == 'fixed' else None
    ),
    seeds=args.seeds,
    max_turns=args.max_turns,
    max_scenarios=args.max_scenarios,
    overwrite=args.overwrite,
    study_freeze_sha256=freeze.get('freeze_sha256'),
))
