#!/usr/bin/env python3
"""Run the authorized public-EvoEmo Qwen semantic-compiler smoke.

This script never sources a secret file. The caller must export the configured
API-key environment variable in the same shell. No request is possible unless
``--live`` and a researcher-reviewed authorization artifact are both supplied.
"""

from __future__ import annotations

import argparse
from decimal import Decimal
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from metacom_pm.api import OpenAICompatibleClient  # noqa: E402
from metacom_pm.config import endpoint_from_config, load_config  # noqa: E402
from metacom_pm.io import canonical_json, iter_jsonl, sha256_file  # noqa: E402
from metacom_pm.paper1.data.memory_source import load_sanitized_runtime_users  # noqa: E402
from metacom_pm.paper1.semantic_memory.authorization import (  # noqa: E402
    FULL_SCOPE,
    load_live_authorization,
)
from metacom_pm.paper1.semantic_memory.batch import (  # noqa: E402
    ordered_public_sessions,
    run_session_prefix,
)
from metacom_pm.paper1.semantic_memory.budget import PriceSnapshot  # noqa: E402
from metacom_pm.paper1.semantic_memory.runtime import (  # noqa: E402
    CallParameters,
    RuntimeBinding,
    SemanticMemoryCompiler,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--sanitized-runtime-artifact", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--maximum-sessions", type=int, default=20)
    parser.add_argument("--authorization", type=Path)
    parser.add_argument(
        "--aggregate-budget-ledger",
        type=Path,
        help="Required for live runs: the one cross-version aggregate USD 5 ledger.",
    )
    parser.add_argument("--live", action="store_true")
    return parser.parse_args()


def _binding_and_price(config_path: Path) -> tuple[RuntimeBinding, PriceSnapshot]:
    config = load_config(config_path)
    raw = config.get("semantic_memory_compiler")
    if not isinstance(raw, dict):
        raise KeyError("config missing semantic_memory_compiler mapping")
    binding = RuntimeBinding(
        provider=str(raw["provider"]),
        region=str(raw["region"]),
        endpoint=endpoint_from_config(config, str(raw["endpoint_name"])),
        extractor=CallParameters.model_validate(raw["extractor"]),
        verifier=CallParameters.model_validate(raw["verifier"]),
        compiler_version=str(raw["compiler_version"]),
    )
    price_raw = raw["price_snapshot"]
    price = PriceSnapshot(
        snapshot_id=str(price_raw["snapshot_id"]),
        provider=binding.provider,
        region=binding.region,
        currency="USD",
        input_usd_per_million_tokens=Decimal(
            str(price_raw["input_usd_per_million_tokens"])
        ),
        output_usd_per_million_tokens=Decimal(
            str(price_raw["output_usd_per_million_tokens"])
        ),
    )
    binding.checked_endpoint
    return binding, price


def main() -> int:
    args = parse_args()
    binding, price = _binding_and_price(args.config)
    users = load_sanitized_runtime_users(args.sanitized_runtime_artifact)
    ordered = ordered_public_sessions(users)
    if not args.live:
        print(
            canonical_json(
                {
                    "status": "DRY_PLAN_NO_API_CALL",
                    "available_sessions": len(ordered),
                    "selected_sessions": min(args.maximum_sessions, len(ordered)),
                    "model": binding.endpoint.model,
                    "provider": binding.provider,
                    "region": binding.region,
                    "hard_budget_usd": "5.00",
                    "outcome_calls": 0,
                    "outcome_lock": "LOCKED_PRE_ZERO_OUTCOME_FREEZE",
                }
            )
        )
        return 0
    if args.authorization is None:
        raise RuntimeError("--live requires an explicit authorization artifact")
    if args.aggregate_budget_ledger is None:
        raise RuntimeError("--live requires the cross-version --aggregate-budget-ledger")
    authorization = load_live_authorization(args.authorization)
    if args.maximum_sessions > authorization.maximum_sessions:
        raise RuntimeError("requested session count exceeds live authorization")
    if authorization.runtime_binding_sha256 != binding.identity_sha256:
        raise RuntimeError("live authorization does not bind this exact runtime configuration")
    if authorization.sanitized_runtime_sha256 != sha256_file(
        args.sanitized_runtime_artifact
    ):
        raise RuntimeError("live authorization does not bind this sanitized runtime artifact")
    if authorization.price_snapshot_id != price.snapshot_id:
        raise RuntimeError("live authorization does not bind this price snapshot")
    if authorization.price_snapshot_sha256 != price.identity_sha256:
        raise RuntimeError("live authorization does not bind the exact frozen prices")
    if authorization.scope == FULL_SCOPE and args.maximum_sessions != len(ordered):
        raise RuntimeError("full-resume authorization requires selecting all public sessions")
    results_path = args.output_dir / "session_results.jsonl"
    if authorization.scope == FULL_SCOPE:
        existing_rows = list(iter_jsonl(results_path)) if results_path.exists() else []
        if len(existing_rows) < 20:
            raise RuntimeError(
                "full-resume authorization requires the successful 20-session v6 smoke "
                "prefix in the same output directory"
            )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    client = OpenAICompatibleClient(binding.endpoint)
    try:
        compiler = SemanticMemoryCompiler(
            binding=binding,
            price=price,
            client=client,
            cache_root=args.output_dir / "success_cache",
            attempt_ledger_root=args.output_dir / "attempt_ledgers",
            budget_ledger_path=args.aggregate_budget_ledger,
        )
        report = run_session_prefix(
            users=users,
            compiler=compiler,
            maximum_sessions=args.maximum_sessions,
            results_path=results_path,
            report_path=args.output_dir / "batch_report.json",
        )
    finally:
        client.close()
    print(canonical_json(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
