#!/usr/bin/env python3
from pathlib import Path
import argparse
from metacom_pm.config import load_config, endpoint_from_config
from metacom_pm.evo_metrics import run_selective_evoemo_metrics
from metacom_pm.freeze import require_study_freeze
from metacom_pm.io import write_json

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--config', type=Path, default=ROOT / 'configs/experiment.yaml')
parser.add_argument('--endpoint', default='final_judge')
parser.add_argument('--generation-attestation', type=Path,
                    default=ROOT / 'outputs/evoemo_selective/artifact_attestation.json')
parser.add_argument('--overwrite', action='store_true')
parser.add_argument('--freeze', type=Path, default=ROOT / 'outputs/study_freeze.json')
parser.add_argument('--allow-unfrozen-debug', action='store_true', help='Non-reportable debugging only')
parser.add_argument(
    '--pairs-only',
    action='store_true',
    help='Run only dialogue pairwise response-quality evaluation; skip memory/strategy audits.',
)
args = parser.parse_args()

evoemo_path = ROOT / 'data/external/evo_emo.json'
dialogues_path = ROOT / 'outputs/evoemo_selective/dialogues.jsonl'
freeze = require_study_freeze(
    args.freeze,
    release_root=ROOT,
    config_path=args.config,
    required_files=[evoemo_path],
    allow_unfrozen_debug=args.allow_unfrozen_debug,
)
if not dialogues_path.is_file():
    raise FileNotFoundError(
        f"Missing EvoEmo selective dialogues: {dialogues_path}. "
        "Run scripts/15_run_evoemo.py --protocol selective under the same study freeze first."
    )
if not args.generation_attestation.is_file():
    raise FileNotFoundError(
        f"Missing EvoEmo selective generation attestation: {args.generation_attestation}"
    )
out_dir = ROOT / 'outputs/evoemo_selective_metrics'
out_dir.mkdir(parents=True, exist_ok=True)
write_json(out_dir / 'freeze_verification.json', freeze)

print(run_selective_evoemo_metrics(
    evoemo_path,
    dialogues_path,
    out_dir,
    judge_endpoint=endpoint_from_config(load_config(args.config), args.endpoint),
    generation_attestation_path=args.generation_attestation,
    expected_freeze_sha256=freeze.get('freeze_sha256'),
    overwrite=args.overwrite,
    pairs_only=args.pairs_only,
))
