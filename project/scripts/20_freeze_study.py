#!/usr/bin/env python3
from pathlib import Path
import argparse
from metacom_pm.freeze import create_study_freeze

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--config', type=Path, default=ROOT / 'configs/experiment.yaml')
parser.add_argument('--checkpoint', type=Path, required=True)
parser.add_argument('--checkpoint-attestation', type=Path)
parser.add_argument('--selection', type=Path, default=ROOT / 'outputs/selection.json')
parser.add_argument('--selection-attestation', type=Path)
parser.add_argument('--evoemo-fixed-tracks', type=Path,
                    default=ROOT / 'outputs/evoemo_fixed_tracks/fixed_seeker_tracks.jsonl')
parser.add_argument('--evoemo-fixed-tracks-attestation', type=Path,
                    default=ROOT / 'outputs/evoemo_fixed_tracks/artifact_attestation.json')
parser.add_argument('--out', type=Path, default=ROOT / 'outputs/study_freeze.json')
args = parser.parse_args()
checkpoint_attestation = (
    args.checkpoint_attestation
    or args.checkpoint.with_suffix(args.checkpoint.suffix + ".attestation.json")
)
selection_attestation = (
    args.selection_attestation
    or args.selection.with_suffix(args.selection.suffix + ".attestation.json")
)

data_paths = [
    ROOT / 'data/synthetic/runtime_states.jsonl',
    ROOT / 'data/synthetic/memory_backend.jsonl',
    ROOT / 'data/synthetic/folds.jsonl',
    ROOT / 'data/synthetic/pair_graph.jsonl',
    ROOT / 'data/strategy/strategy_cards.jsonl',
    ROOT / 'data/strategy/strategy_bank_audit.json',
    ROOT / 'data/strategy/esconv_split_manifest.jsonl',
    ROOT / 'data/external/ESConv.json',
    ROOT / 'data/external/evo_emo.json',
    ROOT / 'data/esconv_test/runtime_states.jsonl',
    ROOT / 'data/esconv_test/memory_backend.jsonl',
    ROOT / 'data/esconv_test/audit_only.jsonl',
    args.selection,
    checkpoint_attestation,
    selection_attestation,
    args.evoemo_fixed_tracks,
    args.evoemo_fixed_tracks_attestation,
]

print(create_study_freeze(
    release_root=ROOT,
    config_path=args.config,
    checkpoint_paths=[args.checkpoint],
    data_paths=data_paths,
    prompt_files=[ROOT / 'src/metacom_pm/prompts.py'],
    out_path=args.out,
    notes={
        'external_test_policy': 'ESConv test and all 18 EvoEmo users are evaluation-only',
        'tuning_policy': 'All thresholds, baselines, prompts, generator and judge models are frozen before external evaluation',
        'debug_exception': 'Unfrozen runs are non-reportable and require explicit --allow-unfrozen-debug',
    },
))
