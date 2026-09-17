#!/usr/bin/env python3
"""Run the researcher-authorized active 401-session MP/ME compiler."""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

from transformers import AutoTokenizer


PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.api import Endpoint, OpenAICompatibleClient
from metacom_pm.config import load_config
from metacom_pm.io import canonical_json, read_json, sha256_file
from metacom_pm.paper1.api_budget import CumulativePaper1ApiBudgetLedger
from metacom_pm.paper1.data.memory_source import load_sanitized_runtime_users
from metacom_pm.paper1.multi_view_memory.batch import run_session_prefix
from metacom_pm.paper1.multi_view_memory.runtime import (
    CallParameters,
    MultiViewMemoryCompiler,
    PriceSnapshot,
    RuntimeBinding,
    compiler_identity_sha256,
)
from metacom_pm.paper1.outcome_lock import assert_pre_outcome_locked, load_public_only_config


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config",
        type=Path,
        default=PROJECT / "configs" / "paper1_multi_view_compiler_v7.yaml",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=(
            PROJECT
            / "data"
            / "paper1_public_memory"
            / "es_memeval_public_sanitized_runtime_artifact_v1.json"
        ),
    )
    parser.add_argument(
        "--manifest-summary",
        type=Path,
        default=(
            PROJECT
            / "data"
            / "paper1_authority"
            / "paper1_multi_view_401_call_manifest_preflight_20260903_v8.json"
        ),
    )
    parser.add_argument("--tokenizer-dir", type=Path, required=True)
    parser.add_argument("--authorization", type=Path)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT / "outputs" / "paper1_multi_view_compiler_v7",
    )
    parser.add_argument("--maximum-sessions", type=int, default=401)
    parser.add_argument("--live", action="store_true")
    return parser.parse_args()


def _runtime(config: dict, tokenizer_dir: Path):
    endpoint_raw = config["endpoint"]
    limits = config["limits"]
    endpoint = Endpoint(
        base_url=str(endpoint_raw["base_url"]),
        model=str(endpoint_raw["model"]),
        api_key_env=str(endpoint_raw["api_key_env"]),
        timeout_seconds=240.0,
        family="qwen3_235b_dashscope_intl",
        transport=str(endpoint_raw["transport"]),
        supports_strict_json_schema=bool(endpoint_raw["supports_strict_json_schema"]),
        enable_thinking=bool(endpoint_raw["enable_thinking"]),
    )
    common = {
        "temperature": float(endpoint_raw["temperature"]),
        "maximum_prompt_tokens": int(limits["maximum_prompt_tokens_per_call"]),
        "prompt_token_safety_margin": int(limits["prompt_token_safety_margin_per_call"]),
        "seed": int(endpoint_raw["seed"]),
    }
    tokenizer_hashes = {
        name: sha256_file(tokenizer_dir / name)
        for name in ("tokenizer.json", "tokenizer_config.json", "config.json")
    }
    tokenizer_identity = sha256_file(tokenizer_dir / "tokenizer.json") + ":" + sha256_file(
        tokenizer_dir / "tokenizer_config.json"
    )
    binding = RuntimeBinding(
        provider=str(endpoint_raw["provider"]),
        region=str(endpoint_raw["region"]),
        endpoint=endpoint,
        extractor=CallParameters(
            max_tokens=int(limits["extractor_max_output_tokens"]),
            **common,
        ),
        verifier=CallParameters(
            max_tokens=int(limits["verifier_max_output_tokens"]),
            **common,
        ),
        tokenizer_identity=tokenizer_identity,
        prior_profile_allowance_tokens=int(
            limits["prior_current_profile_allowance_tokens_per_call"]
        ),
    )
    price_raw = config["price_snapshot"]
    price = PriceSnapshot(
        snapshot_id=str(price_raw["snapshot_id"]),
        provider=binding.provider,
        region=binding.region,
        input_usd_per_million_tokens=Decimal(
            str(price_raw["input_usd_per_million_tokens"])
        ),
        output_usd_per_million_tokens=Decimal(
            str(price_raw["output_usd_per_million_tokens"])
        ),
    )
    tokenizer = AutoTokenizer.from_pretrained(tokenizer_dir, local_files_only=True)

    def count(messages: list[dict[str, str]]) -> int:
        return len(
            tokenizer.apply_chat_template(
                messages,
                tokenize=True,
                add_generation_prompt=True,
            )
        )

    return endpoint, binding, price, count, tokenizer_hashes


def _validate_authorization(
    args, config, manifest, binding, price, tokenizer_hashes
) -> dict:
    if args.authorization is None:
        raise RuntimeError("--live requires --authorization")
    authorization = read_json(args.authorization)
    if authorization.get("status") != "RESEARCHER_AUTHORIZED_ZERO_OUTCOME_COMPILATION":
        raise RuntimeError("active compiler authorization status mismatch")
    exact = {
        "config_sha256": sha256_file(args.config.resolve()),
        "source_sha256": sha256_file(args.source.resolve()),
        "manifest_summary_sha256": sha256_file(args.manifest_summary.resolve()),
        "runner_sha256": sha256_file(Path(__file__).resolve()),
        "runtime_sha256": sha256_file(
            PROJECT / "src/metacom_pm/paper1/multi_view_memory/runtime.py"
        ),
        "batch_sha256": sha256_file(
            PROJECT / "src/metacom_pm/paper1/multi_view_memory/batch.py"
        ),
        "prompts_sha256": sha256_file(
            PROJECT / "src/metacom_pm/paper1/multi_view_memory/prompts.py"
        ),
        "input_projection_sha256": sha256_file(
            PROJECT / "src/metacom_pm/paper1/multi_view_memory/input_projection.py"
        ),
        "compiler_identity_sha256": compiler_identity_sha256(binding, price),
        "price_snapshot_sha256": price.identity_sha256,
        "tokenizer_file_sha256": tokenizer_hashes,
    }
    for field, observed in exact.items():
        if authorization.get(field) != observed:
            raise RuntimeError(f"authorization does not bind exact {field}")
    if int(authorization.get("maximum_sessions", 0)) != 401:
        raise RuntimeError("authorization maximum session count mismatch")
    if int(authorization.get("maximum_provider_calls", 0)) != int(
        config["limits"]["maximum_provider_calls"]
    ):
        raise RuntimeError("authorization maximum provider calls mismatch")
    if args.maximum_sessions > 401:
        raise RuntimeError("requested session prefix exceeds authorization")
    historical_settled = Decimal(str(authorization["historical_settled_cost_usd"]))
    aggregate_planning_ceiling = Decimal(
        str(manifest["budget"]["aggregate_maximum_cost_usd"])
    )
    maximum_single_call = Decimal(
        str(manifest["budget"]["maximum_single_call_reservation_usd"])
    )
    approved = Decimal(str(authorization["researcher_authorized_total_usd"]))
    if Decimal(
        str(authorization["aggregate_planning_ceiling_usd"])
    ) != aggregate_planning_ceiling:
        raise RuntimeError("authorization planning ceiling does not match manifest")
    if Decimal(
        str(authorization["maximum_single_call_reservation_usd"])
    ) != maximum_single_call:
        raise RuntimeError("authorization single-call maximum does not match manifest")
    if Decimal(str(config["budget"]["researcher_authorized_total_usd"])) != approved:
        raise RuntimeError("config and authorization researcher limits differ")
    if Decimal(str(config["budget"]["stage_hard_cap_usd"])) != approved:
        raise RuntimeError("rolling stage cap must equal researcher authorization")
    if historical_settled + maximum_single_call > approved:
        raise RuntimeError("next worst-case call cannot fit researcher authorization")
    return authorization


def main() -> int:
    args = _args()
    args.config = args.config.resolve()
    args.source = args.source.resolve()
    args.manifest_summary = args.manifest_summary.resolve()
    args.tokenizer_dir = args.tokenizer_dir.resolve()
    args.output_dir = args.output_dir.resolve()
    config = load_config(args.config)
    public_config = load_public_only_config(PROJECT / "configs" / "paper1_public_only.yaml")
    assert_pre_outcome_locked(public_config)
    manifest = read_json(args.manifest_summary)
    endpoint, binding, price, token_counter, tokenizer_hashes = _runtime(
        config, args.tokenizer_dir
    )
    plan = {
        "protocol": "paper1-multi-view-401-live-run-plan-v1",
        "mode": "LIVE" if args.live else "DRY_RUN",
        "maximum_sessions": args.maximum_sessions,
        "manifest_status": manifest["status"],
        "manifest_maximum_cost_usd": manifest["budget"]["aggregate_maximum_cost_usd"],
        "stage_hard_cap_usd": config["budget"]["stage_hard_cap_usd"],
        "compiler_identity_sha256": compiler_identity_sha256(binding, price),
        "price_snapshot_sha256": price.identity_sha256,
        "formal_outcome_calls": 0,
        "pm_training_runs": 0,
    }
    if not args.live:
        print(json.dumps(plan, ensure_ascii=False, indent=2, default=str))
        return 0
    _validate_authorization(args, config, manifest, binding, price, tokenizer_hashes)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    client = OpenAICompatibleClient(endpoint)
    try:
        compiler = MultiViewMemoryCompiler(
            binding=binding,
            price=price,
            client=client,
            prompt_token_counter=token_counter,
            cache_root=args.output_dir / "success_cache",
            attempt_ledger_root=args.output_dir / "attempts",
            cumulative_budget=CumulativePaper1ApiBudgetLedger(
                PROJECT
                / "outputs"
                / "paper1_api_budget"
                / "cumulative_paid_api_budget.jsonl"
            ),
        )
        report = run_session_prefix(
            users=load_sanitized_runtime_users(args.source),
            compiler=compiler,
            maximum_sessions=args.maximum_sessions,
            results_path=args.output_dir / "session_results.jsonl",
            report_path=args.output_dir / "batch_report.json",
        )
    finally:
        client.close()
    print(canonical_json({**plan, "batch_report": report}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
