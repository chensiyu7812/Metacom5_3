#!/usr/bin/env python3
from pathlib import Path
import argparse

from metacom_pm.config import confirmatory_model_independence, load_config
from metacom_pm.freeze import create_study_freeze
from metacom_pm.io import read_json

ROOT = Path(__file__).resolve().parents[1]

parser = argparse.ArgumentParser()
parser.add_argument('--config', type=Path, default=ROOT / 'configs/experiment.yaml')
parser.add_argument('--checkpoint', type=Path, default=ROOT / 'outputs/final_model_m2b_stable/pm_final.joblib')
parser.add_argument('--selection', type=Path, default=ROOT / 'outputs/selection_stable.json')
parser.add_argument('--generation-freeze', type=Path, default=ROOT / 'outputs/study_freeze_stable.json')
parser.add_argument('--generation-attestation', type=Path,
                    default=ROOT / 'outputs/evoemo_selective/artifact_attestation.json')
parser.add_argument('--out', type=Path, default=ROOT / 'outputs/evoemo_pairwise_eval_freeze.json')
args = parser.parse_args()

generation_attestation = read_json(args.generation_attestation)
generation_freeze_sha256 = generation_attestation.get('study_freeze_sha256')
if not generation_freeze_sha256:
    raise RuntimeError(
        "generation attestation lacks study_freeze_sha256; cannot create "
        "evaluation freeze"
    )
generation_freeze = read_json(args.generation_freeze)
if generation_freeze.get('freeze_sha256') != generation_freeze_sha256:
    raise RuntimeError(
        "generation freeze hash does not match generation attestation: "
        f"{generation_freeze.get('freeze_sha256')} != {generation_freeze_sha256}"
    )

model_independence = confirmatory_model_independence(load_config(args.config))
if not model_independence.get("ok"):
    raise RuntimeError(
        "Confirmatory model-family independence check failed:\n- "
        + "\n- ".join(model_independence.get("errors") or ["unknown error"])
    )

checkpoint_attestation = args.checkpoint.with_suffix(args.checkpoint.suffix + ".attestation.json")
selection_attestation = args.selection.with_suffix(args.selection.suffix + ".attestation.json")

data_paths = [
    ROOT / 'data/external/evo_emo.json',
    ROOT / 'data/strategy/strategy_cards.jsonl',
    args.selection,
    selection_attestation,
    checkpoint_attestation,
    args.generation_freeze,
    args.generation_attestation,
    ROOT / 'outputs/evoemo_selective/generation_summary.json',
    ROOT / 'outputs/evoemo_selective/external_ood_preflight.json',
    ROOT / 'outputs/evoemo_fixed_tracks/fixed_seeker_tracks.jsonl',
    ROOT / 'outputs/evoemo_fixed_tracks/artifact_attestation.json',
]

print(create_study_freeze(
    release_root=ROOT,
    config_path=args.config,
    checkpoint_paths=[args.checkpoint],
    data_paths=data_paths,
    prompt_files=[ROOT / 'src/metacom_pm/prompts.py'],
    out_path=args.out,
    notes={
        'freeze_scope': 'evoemo_pairwise_response_evaluation',
        'generation_freeze_sha256': generation_freeze_sha256,
        'generation_attestation': str(args.generation_attestation),
        'evaluation_policy': (
            'This freeze binds the evaluator code/configuration used after '
            'EvoEmo generation was already completed and attested. It does '
            'not authorize regenerating dialogues.'
        ),
        'debug_exception': (
            'Unfrozen runs or --allow-unfrozen-debug outputs are non-reportable.'
        ),
        'model_family_independence': model_independence,
    },
))

