#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import argparse

from metacom_pm.config import endpoint_from_config, load_config
from metacom_pm.evo_response_v4 import (
    DEFAULT_RESPONSE_V4_CONDITIONS,
    DEFAULT_RESPONSE_V4_TURNS,
    run_evoemo_response_v4,
)
from metacom_pm.freeze import require_study_freeze
from metacom_pm.io import read_json, write_json


ROOT = Path(__file__).resolve().parents[1]


def _csv(value: str) -> list[str]:
    return [x.strip() for x in value.split(",") if x.strip()]


def _int_csv(value: str) -> list[int]:
    return [int(x.strip()) for x in value.split(",") if x.strip()]


parser = argparse.ArgumentParser(
    description="EvoEmo Response Evaluation V4: dry-run, pilot, then full sampled scoring."
)
mode = parser.add_mutually_exclusive_group(required=True)
mode.add_argument("--dry-run", action="store_true", help="No API calls; write sample and cost estimate.")
mode.add_argument("--pilot", action="store_true", help="Run small two-order stability pilot.")
mode.add_argument("--full-run", action="store_true", help="Run confirmatory sampled response scoring.")

parser.add_argument("--config", type=Path, default=ROOT / "configs/experiment.yaml")
parser.add_argument("--endpoint", default="final_judge")
parser.add_argument("--freeze", type=Path, default=ROOT / "outputs/evoemo_response_v4_eval_freeze.json")
parser.add_argument("--allow-unfrozen-debug", action="store_true")
parser.add_argument("--generation-attestation", type=Path, default=ROOT / "outputs/evoemo_selective/artifact_attestation.json")
parser.add_argument("--dialogues", type=Path, default=ROOT / "outputs/evoemo_selective/dialogues.jsonl")
parser.add_argument("--evoemo", type=Path, default=ROOT / "data/external/evo_emo.json")
parser.add_argument("--out-dir", type=Path, default=ROOT / "outputs/evoemo_response_v4")
parser.add_argument(
    "--conditions",
    default=",".join(DEFAULT_RESPONSE_V4_CONDITIONS),
    help="Comma-separated condition names. Must include pm.",
)
parser.add_argument(
    "--turn-indices",
    default=",".join(str(x) for x in DEFAULT_RESPONSE_V4_TURNS),
    help="Comma-separated fixed-context turn indices.",
)
parser.add_argument(
    "--ground-truth-mode",
    choices=["full", "compact_related"],
    default="full",
    help="Evaluator-only authorized context. Use compact_related only after freezing that choice.",
)
parser.add_argument(
    "--dry-run-target",
    choices=["pilot", "full"],
    default="full",
    help="Which API mode the dry-run cost estimate is for.",
)
parser.add_argument("--pilot-units", type=int, default=12)
parser.add_argument("--pilot-summary", type=Path, default=ROOT / "outputs/evoemo_response_v4/pilot_summary.json")
parser.add_argument("--accept-cost-estimate-sha256")
parser.add_argument("--max-api-calls", type=int, default=250)
parser.add_argument("--max-estimated-usd", type=float, default=6.0)
parser.add_argument("--max-input-tokens-per-call", type=int, default=12000)
parser.add_argument("--estimated-output-tokens-per-call", type=int, default=1000)
parser.add_argument("--input-usd-per-mtok", type=float, default=2.50)
parser.add_argument("--output-usd-per-mtok", type=float, default=10.0)
parser.add_argument("--max-tokens", type=int, default=1400)
parser.add_argument("--max-order-mean-abs-diff", type=float, default=0.75)
parser.add_argument("--max-position-mean-shift", type=float, default=0.50)
parser.add_argument("--overwrite", action="store_true")
args = parser.parse_args()

if not args.dialogues.is_file():
    raise FileNotFoundError(args.dialogues)
if not args.generation_attestation.is_file():
    raise FileNotFoundError(args.generation_attestation)

generation_attestation = read_json(args.generation_attestation)
generation_freeze_sha256 = generation_attestation.get("study_freeze_sha256")
if not generation_freeze_sha256:
    raise RuntimeError("generation attestation lacks study_freeze_sha256")

api_mode = "dry_run" if args.dry_run else "pilot" if args.pilot else "full"
freeze_verification = {
    "status": "UNFROZEN_DRY_RUN",
    "freeze_path": str(args.freeze),
}
if args.freeze.is_file():
    freeze_verification = require_study_freeze(
        args.freeze,
        release_root=ROOT,
        config_path=args.config,
        required_files=[args.evoemo, args.dialogues, args.generation_attestation],
        allow_unfrozen_debug=args.allow_unfrozen_debug,
    )
elif api_mode != "dry_run" and not args.allow_unfrozen_debug:
    raise FileNotFoundError(
        f"Missing V4 evaluation freeze: {args.freeze}. "
        "Create/freeze the V4 evaluator first, or pass --allow-unfrozen-debug for non-reportable debugging."
    )
elif api_mode != "dry_run":
    freeze_verification = {
        "status": "UNFROZEN_API_DEBUG",
        "freeze_path": str(args.freeze),
        "reportable": False,
    }

args.out_dir.mkdir(parents=True, exist_ok=True)
write_json(args.out_dir / "freeze_verification.json", freeze_verification)

summary = run_evoemo_response_v4(
    evoemo_path=args.evoemo,
    dialogues_path=args.dialogues,
    out_dir=args.out_dir,
    judge_endpoint=endpoint_from_config(load_config(args.config), args.endpoint),
    mode=api_mode,
    dry_run_target=args.dry_run_target,
    generation_attestation_path=args.generation_attestation,
    expected_generation_freeze_sha256=str(generation_freeze_sha256),
    evaluation_freeze_sha256=freeze_verification.get("freeze_sha256"),
    conditions=_csv(args.conditions),
    turn_indices=_int_csv(args.turn_indices),
    ground_truth_mode=args.ground_truth_mode,
    pilot_units=args.pilot_units,
    accept_cost_estimate_sha256=args.accept_cost_estimate_sha256,
    pilot_summary_path=args.pilot_summary,
    max_api_calls=args.max_api_calls,
    max_estimated_usd=args.max_estimated_usd,
    max_input_tokens_per_call=args.max_input_tokens_per_call,
    estimated_output_tokens_per_call=args.estimated_output_tokens_per_call,
    input_usd_per_mtok=args.input_usd_per_mtok,
    output_usd_per_mtok=args.output_usd_per_mtok,
    max_tokens=args.max_tokens,
    max_order_mean_abs_diff=args.max_order_mean_abs_diff,
    max_position_mean_shift=args.max_position_mean_shift,
    overwrite=args.overwrite,
)
print(summary)
