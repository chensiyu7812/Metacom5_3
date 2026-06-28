#!/usr/bin/env python3
from pathlib import Path
import argparse
from metacom_pm.config import load_config, endpoint_from_config
from metacom_pm.esconv import run_esconv_policy_evaluation
from metacom_pm.freeze import require_study_freeze
from metacom_pm.io import write_json

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--config', type=Path, default=ROOT / 'configs/experiment.yaml')
parser.add_argument('--endpoint', default='final_judge')
parser.add_argument('--checkpoint', type=Path, required=True)
parser.add_argument('--selection', type=Path, default=ROOT / 'outputs/selection.json')
parser.add_argument('--outcomes-attestation', type=Path,
                    default=ROOT / 'outputs/esconv_sweep/artifact_attestation.json')
parser.add_argument('--overwrite', action='store_true')
parser.add_argument('--freeze', type=Path, default=ROOT / 'outputs/study_freeze.json')
parser.add_argument('--allow-unfrozen-debug', action='store_true', help='Non-reportable debugging only')
args = parser.parse_args()

runtime_path = ROOT / 'data/esconv_test/runtime_states.jsonl'
audit_path = ROOT / 'data/esconv_test/audit_only.jsonl'
strategy_path = ROOT / 'data/strategy/strategy_cards.jsonl'
outcomes_path = ROOT / 'outputs/esconv_sweep/action_outcomes.jsonl'
freeze = require_study_freeze(
    args.freeze,
    release_root=ROOT,
    config_path=args.config,
    required_files=[
        runtime_path,
        audit_path,
        strategy_path,
        args.checkpoint,
        args.selection,
    ],
    allow_unfrozen_debug=args.allow_unfrozen_debug,
)
if not outcomes_path.is_file():
    raise FileNotFoundError(
        f"Missing ESConv action outcomes: {outcomes_path}. "
        "Run scripts/13_run_esconv_sweep.py under the same study freeze first."
    )
if not args.outcomes_attestation.is_file():
    raise FileNotFoundError(
        f"Missing ESConv sweep attestation: {args.outcomes_attestation}. "
        "Run scripts/13_run_esconv_sweep.py under the same study freeze first."
    )
out_dir = ROOT / 'outputs/esconv_eval'
out_dir.mkdir(parents=True, exist_ok=True)
write_json(out_dir / 'freeze_verification.json', freeze)
endpoint = endpoint_from_config(load_config(args.config), args.endpoint)

print(run_esconv_policy_evaluation(
    runtime_path,
    audit_path,
    outcomes_path,
    strategy_path,
    args.checkpoint,
    args.selection,
    out_dir,
    judge_endpoint=endpoint,
    overwrite=args.overwrite,
    outcomes_attestation_path=args.outcomes_attestation,
    study_freeze_sha256=freeze.get('freeze_sha256'),
))
