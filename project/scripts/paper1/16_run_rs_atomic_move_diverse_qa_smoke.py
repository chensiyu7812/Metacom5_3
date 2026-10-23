#!/usr/bin/env python3
"""Run the RS atomic-move compiler over a fixed, hash-bound, stratified
cross-dialogue selection -- diverse compiler QA, not a full-catalog compile.

The 2026-08-18 initial live smoke (see
``15_run_rs_atomic_move_compiler.py``) validated the pipeline end-to-end but
drew all 10 source cards from a single dialogue (esconv_0002); it is
engineering evidence, not evidence of cross-dialogue quality stability. This
script instead compiles an explicit ``--selection-manifest`` (a fixed list of
``card_id`` values spanning multiple ESConv strategy families, many distinct
dialogues, short/medium/long turns, and cards flagged by the prior renderer
leak-proxy audit for capitalized-token/kinship/time-or-number/first-person
content) so the same fail-closed authorization/budget/cache machinery as the
full compiler can be reused for a deliberately small, deliberately diverse
QA pass.

This script never sources a secret file and never touches the outcome lock
-- it only measures compiler behavior (grounding, verifier decisions,
duplication, token length), not any ON/OFF effect.
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
from metacom_pm.io import canonical_json, read_json, sha256_file  # noqa: E402
from metacom_pm.paper1.rs.strategy_bank import EXPECTED_ESCONV_SHA256, build_strategy_source_catalog  # noqa: E402
from metacom_pm.paper1.rs_atomic_move.authorization import (  # noqa: E402
    FULL_SCOPE,
    load_live_authorization,
)
from metacom_pm.paper1.rs_atomic_move.batch import run_source_card_prefix  # noqa: E402
from metacom_pm.paper1.rs_atomic_move.budget import PriceSnapshot  # noqa: E402
from metacom_pm.paper1.rs_atomic_move.runtime import (  # noqa: E402
    CallParameters,
    RsAtomicMoveCompiler,
    RuntimeBinding,
)
from metacom_pm.paper1.rs_atomic_move.source_adapter import load_esconv_data  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--esconv-path", type=Path, required=True)
    parser.add_argument("--split-manifest-path", type=Path, required=True)
    parser.add_argument("--selection-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--preceding-turns", type=int, default=6)
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--budget-ledger", type=Path)
    parser.add_argument("--hard-budget-usd", type=str)
    parser.add_argument("--live", action="store_true")
    return parser.parse_args()


def _binding_and_price(config_path: Path) -> tuple[RuntimeBinding, PriceSnapshot]:
    config = load_config(config_path)
    raw = config.get("rs_atomic_move_compiler")
    if not isinstance(raw, dict):
        raise KeyError("config missing rs_atomic_move_compiler mapping")
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
        input_usd_per_million_tokens=Decimal(str(price_raw["input_usd_per_million_tokens"])),
        output_usd_per_million_tokens=Decimal(str(price_raw["output_usd_per_million_tokens"])),
    )
    binding.checked_endpoint
    return binding, price


def _select_diverse_cards(*, cards, manifest: dict) -> tuple:
    by_id = {c.card_id: c for c in cards}
    selected_ids = manifest["selected_card_ids"]
    if len(set(selected_ids)) != len(selected_ids):
        raise ValueError("selection manifest has duplicate card_ids")
    missing = [cid for cid in selected_ids if cid not in by_id]
    if missing:
        raise ValueError(f"selection manifest references cards not in the live catalog: {missing[:5]}")
    return tuple(by_id[cid] for cid in selected_ids)


def main() -> int:
    args = parse_args()
    binding, price = _binding_and_price(args.config)
    manifest = read_json(args.selection_manifest)
    full_catalog = build_strategy_source_catalog(
        esconv_path=args.esconv_path, split_manifest_path=args.split_manifest_path
    )
    cards = _select_diverse_cards(cards=full_catalog, manifest=manifest)
    esconv_data = load_esconv_data(args.esconv_path)

    if not args.live:
        print(
            canonical_json(
                {
                    "status": "DRY_PLAN_NO_API_CALL",
                    "diverse_selection_cards": len(cards),
                    "distinct_dialogues": len({c.source_dialogue_id for c in cards}),
                    "model": binding.endpoint.model,
                    "provider": binding.provider,
                    "region": binding.region,
                    "outcome_calls": 0,
                    "outcome_lock": "LOCKED_PRE_ZERO_OUTCOME_FREEZE",
                }
            )
        )
        return 0

    if args.authorization is None:
        raise RuntimeError("--live requires an explicit authorization artifact")
    if args.budget_ledger is None or args.hard_budget_usd is None:
        raise RuntimeError("--live requires --budget-ledger and --hard-budget-usd")
    hard_budget_usd = Decimal(args.hard_budget_usd)

    authorization = load_live_authorization(args.authorization)
    if authorization.scope == FULL_SCOPE:
        raise RuntimeError("diverse QA smoke must not use the full-catalog authorization scope")
    if authorization.maximum_cards != len(cards):
        raise RuntimeError("authorization maximum_cards must exactly match the diverse selection size")
    if authorization.esconv_sha256 != EXPECTED_ESCONV_SHA256:
        raise RuntimeError("live authorization does not bind the frozen ESConv artifact")
    if authorization.esconv_sha256 != sha256_file(args.esconv_path):
        raise RuntimeError("live authorization does not match the ESConv file on disk")
    if authorization.price_snapshot_id != price.snapshot_id:
        raise RuntimeError("live authorization does not bind this price snapshot")
    if authorization.price_snapshot_sha256 != price.identity_sha256:
        raise RuntimeError("live authorization does not bind the exact frozen prices")
    if authorization.hard_budget_usd != hard_budget_usd:
        raise RuntimeError("live authorization does not match --hard-budget-usd")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    client = OpenAICompatibleClient(binding.endpoint)
    try:
        compiler = RsAtomicMoveCompiler(
            binding=binding,
            price=price,
            client=client,
            cache_root=args.output_dir / "success_cache",
            attempt_ledger_root=args.output_dir / "attempt_ledgers",
            budget_ledger_path=args.budget_ledger,
            hard_budget_usd=hard_budget_usd,
        )
        if authorization.run_identity_sha256 != compiler.run_identity_sha256:
            raise RuntimeError("live authorization does not bind this exact compiler identity")
        report = run_source_card_prefix(
            cards=cards,
            esconv_data=esconv_data,
            compiler=compiler,
            maximum_cards=len(cards),
            preceding_turns=args.preceding_turns,
            run_scope="smoke",
            results_path=args.output_dir / "session_results.jsonl",
            report_path=args.output_dir / "batch_report.json",
        )
    finally:
        client.close()
    print(canonical_json(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
