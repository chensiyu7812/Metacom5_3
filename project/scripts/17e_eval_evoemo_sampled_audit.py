#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import argparse

from metacom_pm.config import endpoint_from_config, load_config
from metacom_pm.evo_sampled_audit import run_evoemo_sampled_audit
from metacom_pm.freeze import require_study_freeze
from metacom_pm.io import write_json


ROOT = Path(__file__).resolve().parents[1]


parser = argparse.ArgumentParser(
    description="EvoEmo sampled memory/strategy audit: dry-run, pilot, then optional full sampled audit."
)
mode = parser.add_mutually_exclusive_group(required=True)
mode.add_argument("--dry-run", action="store_true", help="No API calls; write call plan and cost estimate.")
mode.add_argument("--pilot", action="store_true", help="Run a small sampled audit pilot.")
mode.add_argument("--full-run", action="store_true", help="Run the full sampled audit plan.")

parser.add_argument("--config", type=Path, default=ROOT / "configs/experiment.yaml")
parser.add_argument("--endpoint", default="final_judge")
parser.add_argument("--freeze", type=Path, default=ROOT / "outputs/evoemo_sampled_audit_eval_freeze.json")
parser.add_argument("--allow-unfrozen-debug", action="store_true")
parser.add_argument("--sample-plan", type=Path, default=ROOT / "outputs/evoemo_sampled_audit_plan/audit_sample_plan.json")
parser.add_argument("--turns", type=Path, default=ROOT / "outputs/evoemo_selective/turns.jsonl")
parser.add_argument("--evoemo", type=Path, default=ROOT / "data/external/evo_emo.json")
parser.add_argument("--response-attestation", type=Path, default=ROOT / "outputs/evoemo_response_v4/artifact_attestation.json")
parser.add_argument("--out-dir", type=Path, default=ROOT / "outputs/evoemo_sampled_audit")
parser.add_argument("--dry-run-target", choices=["pilot", "full"], default="pilot")
parser.add_argument("--pilot-items", type=int, default=8)
parser.add_argument("--pilot-summary", type=Path, default=ROOT / "outputs/evoemo_sampled_audit/pilot_summary.json")
parser.add_argument("--max-omission-calls", type=int, default=10)
parser.add_argument("--max-memory-chars", type=int, default=1000)
parser.add_argument("--max-strategy-chars", type=int, default=700)
parser.add_argument("--accept-cost-estimate-sha256")
parser.add_argument("--max-api-calls", type=int, default=90)
parser.add_argument("--max-estimated-usd", type=float, default=2.0)
parser.add_argument("--max-input-tokens-per-call", type=int, default=8000)
parser.add_argument("--estimated-output-tokens-per-call", type=int, default=450)
parser.add_argument("--input-usd-per-mtok", type=float, default=2.50)
parser.add_argument("--output-usd-per-mtok", type=float, default=10.0)
parser.add_argument("--max-tokens", type=int, default=900)
parser.add_argument("--max-raw-rows-multiplier", type=float, default=1.10)
parser.add_argument("--overwrite", action="store_true")
args = parser.parse_args()

for path in (args.sample_plan, args.turns, args.evoemo, args.response_attestation):
    if not path.is_file():
        raise FileNotFoundError(path)

api_mode = "dry_run" if args.dry_run else "pilot" if args.pilot else "full"
freeze_verification = {
    "status": "UNFROZEN_DRY_RUN",
    "freeze_path": str(args.freeze),
}
required_files = [
    args.sample_plan,
    args.turns,
    args.evoemo,
    args.response_attestation,
]
if args.freeze.is_file():
    freeze_verification = require_study_freeze(
        args.freeze,
        release_root=ROOT,
        config_path=args.config,
        required_files=required_files,
        allow_unfrozen_debug=args.allow_unfrozen_debug,
    )
elif api_mode != "dry_run" and not args.allow_unfrozen_debug:
    raise FileNotFoundError(
        f"Missing sampled audit evaluation freeze: {args.freeze}. "
        "Run scripts/20d_freeze_evoemo_sampled_audit_eval.py first, "
        "or pass --allow-unfrozen-debug for non-reportable debugging."
    )
elif api_mode != "dry_run":
    freeze_verification = {
        "status": "UNFROZEN_API_DEBUG",
        "freeze_path": str(args.freeze),
        "reportable": False,
    }

args.out_dir.mkdir(parents=True, exist_ok=True)
write_json(args.out_dir / "freeze_verification.json", freeze_verification)

summary = run_evoemo_sampled_audit(
    sample_plan_path=args.sample_plan,
    turns_path=args.turns,
    evoemo_path=args.evoemo,
    out_dir=args.out_dir,
    judge_endpoint=endpoint_from_config(load_config(args.config), args.endpoint),
    mode=api_mode,  # type: ignore[arg-type]
    dry_run_target=args.dry_run_target,  # type: ignore[arg-type]
    response_attestation_path=args.response_attestation,
    evaluation_freeze_sha256=freeze_verification.get("freeze_sha256"),
    pilot_items=args.pilot_items,
    max_omission_calls=args.max_omission_calls,
    max_memory_chars=args.max_memory_chars,
    max_strategy_chars=args.max_strategy_chars,
    accept_cost_estimate_sha256=args.accept_cost_estimate_sha256,
    pilot_summary_path=args.pilot_summary,
    max_api_calls=args.max_api_calls,
    max_estimated_usd=args.max_estimated_usd,
    max_input_tokens_per_call=args.max_input_tokens_per_call,
    estimated_output_tokens_per_call=args.estimated_output_tokens_per_call,
    input_usd_per_mtok=args.input_usd_per_mtok,
    output_usd_per_mtok=args.output_usd_per_mtok,
    max_tokens=args.max_tokens,
    max_raw_rows_multiplier=args.max_raw_rows_multiplier,
    overwrite=args.overwrite,
)
print(summary)
