#!/usr/bin/env python3
"""Carry-forward repair for a completed RS atomic-move run's call_failure_phase rows.

Does NOT resume via run_source_card_prefix's ordinary prefix-matching (that
requires every row bound to one uniform run_manifest_sha256, which no longer
holds once a code fix changes run_identity_sha256 after a live run already
completed). Instead: copies every already-successful row from the source
run's results file UNCHANGED (preserving its original run_manifest_sha256,
since it really was produced under that identity -- rewriting it would be
dishonest), and only makes fresh live calls for the rows the source run
recorded a call_failure_phase for. The merged output is a new file; the
source run's results/report/ledger are never modified.
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
from metacom_pm.io import canonical_json, iter_jsonl, read_json, sha256_file, write_json  # noqa: E402
from metacom_pm.paper1.rs.strategy_bank import EXPECTED_ESCONV_SHA256, build_strategy_source_catalog  # noqa: E402
from metacom_pm.paper1.rs_atomic_move.authorization import load_live_authorization  # noqa: E402
from metacom_pm.paper1.rs_atomic_move.budget import PriceSnapshot  # noqa: E402
from metacom_pm.paper1.rs_atomic_move.runtime import (  # noqa: E402
    CallParameters,
    RsAtomicMoveCompiler,
    RuntimeBinding,
    source_sha256,
)
from metacom_pm.paper1.rs_atomic_move.source_adapter import (  # noqa: E402
    build_source_card_compile_input,
    load_esconv_data,
)


def detect_failed_card_ids(source_rows: list[dict]) -> set[str]:
    """Cards the source run recorded a ``call_failure_phase`` for -- the only
    ones a repair run may touch."""

    return {row["source_card_id"] for row in source_rows if row.get("call_failure_phase")}


def check_catalog_not_drifted(*, live_catalog_size: int, source_rows_count: int) -> None:
    """Refuse to repair against a catalog that no longer matches the source
    run's row count -- a drifted catalog would silently repair the wrong
    cards or miss some entirely."""

    if live_catalog_size != source_rows_count:
        raise RuntimeError(
            f"live catalog has {live_catalog_size} cards but source results has "
            f"{source_rows_count} rows -- catalog drifted since the source run, "
            "refusing to repair"
        )


def merge_repaired_rows(
    source_rows: list[dict], repaired_rows: dict[str, dict]
) -> tuple[list[dict], list[str], int]:
    """Carry-forward merge: every source row not repaired this round passes
    through byte-for-byte (keeping its original run identity); only rows in
    ``repaired_rows`` are replaced. Returns (merged rows in source order,
    still-failed card ids, total accepted units across the merged set)."""

    merged_rows: list[dict] = []
    still_failed: list[str] = []
    accepted_total = 0
    for row in source_rows:
        card_id = row["source_card_id"]
        final_row = repaired_rows.get(card_id, row)
        if final_row.get("call_failure_phase"):
            still_failed.append(card_id)
        accepted_total += len(final_row.get("accepted_units") or [])
        merged_rows.append(final_row)
    return merged_rows, still_failed, accepted_total


def build_repair_report(
    *,
    source_results_path: Path,
    source_results_sha256: str,
    source_report_path: Path,
    source_report_complete: bool | None,
    source_run_manifest_sha256: str | None,
    repair_run_manifest_sha256: str,
    cards_attempted_for_repair: int,
    cards_still_failed: list[str],
    merged_results_path: Path,
    merged_results_sha256: str,
    merged_rows: int,
    accepted_units_total_after_repair: int,
) -> dict:
    return {
        "protocol": "paper1-rs-atomic-move-repair-report-v1",
        "source_results_path": str(source_results_path),
        "source_results_sha256": source_results_sha256,
        "source_report_path": str(source_report_path),
        "source_report_complete": source_report_complete,
        "source_run_manifest_sha256": source_run_manifest_sha256,
        "repair_run_manifest_sha256": repair_run_manifest_sha256,
        "cards_attempted_for_repair": cards_attempted_for_repair,
        "cards_repaired_successfully": cards_attempted_for_repair - len(cards_still_failed),
        "cards_still_failed": cards_still_failed,
        "merged_results_path": str(merged_results_path),
        "merged_results_sha256": merged_results_sha256,
        "merged_rows": merged_rows,
        "accepted_units_total_after_repair": accepted_units_total_after_repair,
        "note": (
            "merged_results_path mixes rows from two run identities: rows not in "
            "cards_attempted_for_repair keep source_run_manifest_sha256; repaired "
            "rows carry repair_run_manifest_sha256. This is disclosed here, not "
            "silently unified -- do not treat merged_results as a single-identity "
            "run_source_card_prefix-resumable file."
        ),
        "outcome_calls": 0,
        "outcome_lock": "LOCKED_PRE_ZERO_OUTCOME_FREEZE",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--esconv-path", type=Path, required=True)
    parser.add_argument("--split-manifest-path", type=Path, required=True)
    parser.add_argument("--source-results", type=Path, required=True)
    parser.add_argument("--source-report", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--preceding-turns", type=int, default=6)
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--budget-ledger", type=Path, required=True)
    parser.add_argument("--hard-budget-usd", type=str, required=True)
    parser.add_argument("--live", action="store_true")
    return parser.parse_args()


def _binding_and_price(config_path: Path) -> tuple[RuntimeBinding, PriceSnapshot]:
    config = load_config(config_path)
    raw = config["rs_atomic_move_compiler"]
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


def main() -> int:
    args = parse_args()
    binding, price = _binding_and_price(args.config)

    source_results_sha256 = sha256_file(args.source_results)
    source_report = read_json(args.source_report)
    if source_report.get("complete") is not True:
        raise RuntimeError("source report is not marked complete -- this is not a finished run to repair")

    source_rows = list(iter_jsonl(args.source_results))
    failed_card_ids = detect_failed_card_ids(source_rows)
    if not failed_card_ids:
        raise RuntimeError("source run has no call_failure_phase rows -- nothing to repair")

    cards = build_strategy_source_catalog(
        esconv_path=args.esconv_path, split_manifest_path=args.split_manifest_path
    )
    check_catalog_not_drifted(live_catalog_size=len(cards), source_rows_count=len(source_rows))
    cards_by_id = {c.card_id: c for c in cards}
    esconv_data = load_esconv_data(args.esconv_path)

    if not args.live:
        print(
            canonical_json(
                {
                    "status": "DRY_PLAN_NO_API_CALL",
                    "source_results_sha256": source_results_sha256,
                    "failed_cards_to_repair": len(failed_card_ids),
                    "failed_card_ids": sorted(failed_card_ids),
                }
            )
        )
        return 0

    authorization = load_live_authorization(args.authorization)
    if authorization.maximum_cards != len(failed_card_ids):
        raise RuntimeError(
            f"authorization maximum_cards ({authorization.maximum_cards}) must exactly match "
            f"the number of failed cards being repaired ({len(failed_card_ids)})"
        )
    if authorization.esconv_sha256 != EXPECTED_ESCONV_SHA256:
        raise RuntimeError("live authorization does not bind the frozen ESConv artifact")
    if authorization.esconv_sha256 != sha256_file(args.esconv_path):
        raise RuntimeError("live authorization does not match the ESConv file on disk")
    if authorization.price_snapshot_id != price.snapshot_id:
        raise RuntimeError("live authorization does not bind this price snapshot")
    if authorization.price_snapshot_sha256 != price.identity_sha256:
        raise RuntimeError("live authorization does not bind the exact frozen prices")
    hard_budget_usd = Decimal(args.hard_budget_usd)
    if authorization.hard_budget_usd != hard_budget_usd:
        raise RuntimeError("live authorization does not match --hard-budget-usd")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    client = OpenAICompatibleClient(binding.endpoint)
    repaired_rows: dict[str, dict] = {}
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
        new_manifest_sha256 = compiler.run_identity_sha256

        for card_id in sorted(failed_card_ids):
            card = cards_by_id[card_id]
            source = build_source_card_compile_input(
                card, esconv_data=esconv_data, preceding_turns=args.preceding_turns
            )
            result = compiler.compile_source_card(source)
            repaired_rows[card_id] = {
                "run_manifest_sha256": new_manifest_sha256,
                "source_card_id": card.card_id,
                "source_dialogue_id": card.source_dialogue_id,
                "source_turn_index": card.source_turn_index,
                "source_sha256": source_sha256(source),
                "accepted_units": [u.model_dump(mode="json") for u in result.accepted_units],
                "extractor_proposal_count": result.extractor_proposal_count,
                "structurally_invalid_proposals": result.structurally_invalid_proposals,
                "verifier_rejections": result.verifier_rejections,
                "duplicate_semantic_content_count": result.duplicate_semantic_content_count,
                "call_failure_phase": result.call_failure_phase,
            }
    finally:
        client.close()

    merged_path = args.output_dir / "session_results_repaired_v1.jsonl"
    merged_rows, still_failed, accepted_total_new = merge_repaired_rows(source_rows, repaired_rows)
    with merged_path.open("w", encoding="utf-8") as handle:
        for row in merged_rows:
            handle.write(canonical_json(row) + "\n")

    repair_report = build_repair_report(
        source_results_path=args.source_results,
        source_results_sha256=source_results_sha256,
        source_report_path=args.source_report,
        source_report_complete=source_report.get("complete"),
        source_run_manifest_sha256=source_report.get("run_manifest_sha256"),
        repair_run_manifest_sha256=new_manifest_sha256,
        cards_attempted_for_repair=len(failed_card_ids),
        cards_still_failed=still_failed,
        merged_results_path=merged_path,
        merged_results_sha256=sha256_file(merged_path),
        merged_rows=len(source_rows),
        accepted_units_total_after_repair=accepted_total_new,
    )
    write_json(args.output_dir / "repair_report.json", repair_report)
    print(canonical_json(repair_report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
