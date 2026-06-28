#!/usr/bin/env python3
from pathlib import Path
import argparse
from metacom_pm.config import load_config, endpoint_from_config
from metacom_pm.freeze import require_study_freeze
from metacom_pm.io import write_json
from metacom_pm.sweep import run_action_sweep

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--config', type=Path, default=ROOT / 'configs/experiment.yaml')
parser.add_argument('--endpoint', default='generator')
parser.add_argument('--max-cards', type=int)
parser.add_argument('--overwrite', action='store_true')
parser.add_argument('--freeze', type=Path, default=ROOT / 'outputs/study_freeze.json')
parser.add_argument('--allow-unfrozen-debug', action='store_true', help='Non-reportable debugging only')
args = parser.parse_args()

runtime_path = ROOT / 'data/esconv_test/runtime_states.jsonl'
backend_path = ROOT / 'data/esconv_test/memory_backend.jsonl'
strategy_path = ROOT / 'data/strategy/strategy_cards.jsonl'
freeze = require_study_freeze(
    args.freeze,
    release_root=ROOT,
    config_path=args.config,
    required_files=[runtime_path, backend_path, strategy_path],
    allow_unfrozen_debug=args.allow_unfrozen_debug,
)
endpoint = endpoint_from_config(load_config(args.config), args.endpoint)
out_dir = ROOT / 'outputs/esconv_sweep'
out_dir.mkdir(parents=True, exist_ok=True)
write_json(out_dir / 'freeze_verification.json', freeze)

print(run_action_sweep(
    runtime_path,
    backend_path,
    strategy_path,
    out_dir / 'action_outcomes.jsonl',
    out_dir / 'raw_api_calls.jsonl',
    out_dir / 'summary.json',
    endpoint=endpoint,
    max_cards=args.max_cards,
    overwrite=args.overwrite,
    study_freeze_sha256=freeze.get('freeze_sha256'),
))
