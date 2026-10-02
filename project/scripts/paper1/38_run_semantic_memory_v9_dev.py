#!/usr/bin/env python3
"""Run only the authorized 29-call Semantic Memory v9 DEV requalification."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from decimal import Decimal
import json
from pathlib import Path
import sys
from typing import Any

from pydantic import ValidationError


PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.api import OpenAICompatibleClient  # noqa: E402
from metacom_pm.config import endpoint_from_config, load_config  # noqa: E402
from metacom_pm.io import append_jsonl, canonical_json, iter_jsonl, read_json, sha256_file, write_json  # noqa: E402
from metacom_pm.paper1.outcome_lock import assert_pre_outcome_locked, load_public_only_config  # noqa: E402
from metacom_pm.paper1.semantic_memory.budget import PriceSnapshot  # noqa: E402
from metacom_pm.paper1.semantic_memory.contracts import ExtractorSessionOutput, SessionCompileInput  # noqa: E402
from metacom_pm.paper1.semantic_memory.evidence_v9 import V9_EVIDENCE_SCHEMA_VERSION  # noqa: E402
from metacom_pm.paper1.semantic_memory.grounding import source_sha256  # noqa: E402
from metacom_pm.paper1.semantic_memory.runtime_v9_live import (  # noqa: E402
    RuntimeBindingV9Dev,
    SemanticMemoryV9DevVerifier,
    V9_DEV_HARD_BUDGET_USD,
    V9_DEV_SCOPE,
    V9DevAuthorization,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--package-report", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--budget-ledger", type=Path)
    parser.add_argument("--matrix-out", type=Path)
    parser.add_argument("--summary-out", type=Path)
    parser.add_argument("--live", action="store_true")
    return parser.parse_args()


def binding_and_price(config_path: Path) -> tuple[RuntimeBindingV9Dev, PriceSnapshot]:
    config = load_config(config_path)
    raw = config.get("semantic_memory_v9_dev")
    if not isinstance(raw, dict):
        raise KeyError("config missing semantic_memory_v9_dev mapping")
    binding = RuntimeBindingV9Dev(
        provider=str(raw["provider"]),
        region=str(raw["region"]),
        endpoint=endpoint_from_config(config, str(raw["endpoint_name"])),
        verifier=raw["verifier"],
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


def load_package(path: Path) -> list[dict[str, Any]]:
    rows = list(iter_jsonl(path))
    if len(rows) != 29 or sum(len(row.get("old_dev", [])) for row in rows) != 32:
        raise RuntimeError("v9 DEV package must remain exact 29 sessions / 32 items")
    identities: set[tuple[str, str]] = set()
    item_ids: set[str] = set()
    for row in rows:
        if row.get("protocol") != "paper1-semantic-memory-v9-dev-package-row-v1":
            raise RuntimeError("v9 DEV package protocol drifted")
        if row.get("outcome_calls") != 0:
            raise RuntimeError("v9 DEV package violates zero-outcome boundary")
        source = SessionCompileInput.model_validate(row["source"])
        extractor = ExtractorSessionOutput.model_validate(row["extractor"])
        identity = (source.owner_id, source.session_id)
        if identity in identities or identity != (extractor.owner_id, extractor.session_id):
            raise RuntimeError("v9 DEV package session identity drifted or duplicated")
        identities.add(identity)
        proposed = {item.proposal_id for item in extractor.proposals}
        old = {item["memory_id"] for item in row["old_dev"]}
        if proposed != old or item_ids & old:
            raise RuntimeError("v9 DEV package proposal identity drifted or duplicated")
        item_ids.update(old)
    return rows


def validate_live_gate(
    *, args: argparse.Namespace, binding: RuntimeBindingV9Dev, price: PriceSnapshot,
) -> V9DevAuthorization:
    if args.authorization is None or args.budget_ledger is None:
        raise RuntimeError("--live requires --authorization and --budget-ledger")
    try:
        authorization = V9DevAuthorization.model_validate(read_json(args.authorization))
    except ValidationError as exc:
        raise RuntimeError(f"invalid v9 DEV authorization: {exc}") from exc
    exact = {
        "runtime_binding_sha256": binding.identity_sha256,
        "runner_sha256": sha256_file(Path(__file__).resolve()),
        "live_runtime_module_sha256": sha256_file(
            PROJECT / "src/metacom_pm/paper1/semantic_memory/runtime_v9_live.py"
        ),
        "offline_gate_module_sha256": sha256_file(
            PROJECT / "src/metacom_pm/paper1/semantic_memory/runtime_v9_dev.py"
        ),
        "frozen_package_sha256": sha256_file(args.package),
        "package_report_sha256": sha256_file(args.package_report),
        "price_snapshot_sha256": price.identity_sha256,
    }
    for field, observed in exact.items():
        if getattr(authorization, field) != observed:
            raise RuntimeError(f"authorization does not bind exact {field}")
    return authorization


def existing_rows(results_path: Path, package: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = list(iter_jsonl(results_path)) if results_path.exists() else []
    if len(rows) > len(package):
        raise RuntimeError("v9 DEV result file exceeds fixed 29-session scope")
    for index, row in enumerate(rows):
        source = SessionCompileInput.model_validate(package[index]["source"])
        extractor = ExtractorSessionOutput.model_validate(package[index]["extractor"])
        if (row.get("owner_id"), row.get("session_id")) != (source.owner_id, source.session_id):
            raise RuntimeError("v9 DEV resume rows are not an exact package prefix")
        if row.get("source_sha256") != source_sha256(source):
            raise RuntimeError("v9 DEV resume source identity mismatch")
        if row.get("proposal_ids") != [item.proposal_id for item in extractor.proposals]:
            raise RuntimeError("v9 DEV resume proposal identity mismatch")
    return rows


def run_sessions(
    *, verifier: SemanticMemoryV9DevVerifier, package: list[dict[str, Any]], results_path: Path,
) -> list[dict[str, Any]]:
    rows = existing_rows(results_path, package)
    for package_row in package[len(rows):]:
        source = SessionCompileInput.model_validate(package_row["source"])
        extractor = ExtractorSessionOutput.model_validate(package_row["extractor"])
        row: dict[str, Any] = {
            "protocol": "paper1-semantic-memory-v9-dev-session-result-v1",
            "runtime_binding_sha256": verifier.binding.identity_sha256,
            "owner_id": source.owner_id,
            "session_id": source.session_id,
            "source_sha256": source_sha256(source),
            "proposal_ids": [item.proposal_id for item in extractor.proposals],
            "evidence_schema_version": V9_EVIDENCE_SCHEMA_VERSION,
            "outcome_calls": 0,
        }
        try:
            evidence, rejected, decisions = verifier.verify_existing_proposals(
                source=source, extractor=extractor
            )
            row.update(
                {
                    "call_status": "SUCCEEDED",
                    "typed_evidence": [item.model_dump(mode="json") for item in evidence.evidence],
                    "schema_rejections": [item.model_dump(mode="json") for item in rejected],
                    "deterministic_decisions": [item.model_dump(mode="json") for item in decisions],
                }
            )
        except Exception as exc:  # fail closed; a physical call is never retried
            row.update(
                {
                    "call_status": "FAILED_NO_RETRY",
                    "failure_type": type(exc).__name__,
                    "failure_message": str(exc),
                    "typed_evidence": [],
                    "schema_rejections": [],
                    "deterministic_decisions": [],
                }
            )
        append_jsonl(results_path, row)
        rows.append(row)
        print(f"v9 DEV session {len(rows)}/29: {row['call_status']}", flush=True)
    return rows


def build_matrix(
    *, package: list[dict[str, Any]], session_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    old_by_id = {
        item["memory_id"]: item for row in package for item in row["old_dev"]
    }
    evidence_by_id: dict[str, dict[str, Any]] = {}
    decision_by_id: dict[str, dict[str, Any]] = {}
    schema_by_id: dict[str, list[str]] = defaultdict(list)
    failed_ids: set[str] = set()
    for session in session_rows:
        if session["call_status"] != "SUCCEEDED":
            failed_ids.update(session["proposal_ids"])
        for item in session["typed_evidence"]:
            evidence_by_id[item["proposal_id"]] = item
        for item in session["deterministic_decisions"]:
            decision_by_id[item["proposal_id"]] = item
        for item in session["schema_rejections"]:
            if item.get("proposal_id"):
                schema_by_id[item["proposal_id"]].extend(item.get("violations", []))
    matrix = []
    for memory_id, old in old_by_id.items():
        decision = decision_by_id.get(memory_id)
        accepted = bool(decision and decision["accepted"])
        if decision is None:
            mismatch = "CALL_FAILURE" if memory_id in failed_ids else "SCHEMA_REJECT"
            reasons = schema_by_id.get(memory_id) or [mismatch.lower()]
        else:
            reasons = [
                *decision["gate_reasons"],
                *decision["binding_violations"],
                *decision["internal_contradictions"],
            ]
            human_positive = old["old_human_label"] == "PASS"
            mismatch = "MATCH" if accepted == human_positive else (
                "SEMANTIC_FALSE_ACCEPT" if accepted else "SEMANTIC_FALSE_REJECT"
            )
        matrix.append(
            {
                "protocol": "paper1-semantic-memory-v9-dev-item-matrix-v1",
                **old,
                "v9_typed_evidence": evidence_by_id.get(memory_id),
                "deterministic_v9_verdict": "ACCEPT" if accepted else "REJECT_FAIL_CLOSED",
                "mismatch_reason": mismatch,
                "local_reasons": reasons,
                "outcome_calls": 0,
            }
        )
    fail_rows = [row for row in matrix if row["old_human_label"] != "PASS"]
    pass_rows = [row for row in matrix if row["old_human_label"] == "PASS"]
    counts = {
        "items": len(matrix),
        "source_sessions": len(session_rows),
        "provider_call_successes": sum(row["call_status"] == "SUCCEEDED" for row in session_rows),
        "provider_call_failures": sum(row["call_status"] != "SUCCEEDED" for row in session_rows),
        "known_fail_or_review_rejection": sum(row["deterministic_v9_verdict"] == "REJECT_FAIL_CLOSED" for row in fail_rows),
        "known_fail_or_review_total": len(fail_rows),
        "old_pass_retention": sum(row["deterministic_v9_verdict"] == "ACCEPT" for row in pass_rows),
        "old_pass_total": len(pass_rows),
        "semantic_false_accept": sum(row["mismatch_reason"] == "SEMANTIC_FALSE_ACCEPT" for row in matrix),
        "semantic_false_reject": sum(row["mismatch_reason"] == "SEMANTIC_FALSE_REJECT" for row in matrix),
        "schema_reject": sum(row["mismatch_reason"] == "SCHEMA_REJECT" for row in matrix),
        "call_failure_items": sum(row["mismatch_reason"] == "CALL_FAILURE" for row in matrix),
    }
    return matrix, counts


def main() -> int:
    args = parse_args()
    locks = load_public_only_config(PROJECT / "configs/paper1_public_only.yaml")
    assert_pre_outcome_locked(locks)
    binding, price = binding_and_price(args.config)
    package = load_package(args.package)
    report = read_json(args.package_report)
    if report.get("package_sha256") != sha256_file(args.package):
        raise RuntimeError("v9 package report does not bind exact package")
    dry_plan = {
        "protocol": "paper1-semantic-memory-v9-dev-plan-v1",
        "status": "DRY_PLAN_NO_API_CALL",
        "scope": V9_DEV_SCOPE,
        "items": 32,
        "source_sessions": 29,
        "maximum_provider_calls": 29,
        "model": binding.endpoint.model,
        "runtime_binding_sha256": binding.identity_sha256,
        "runner_sha256": sha256_file(Path(__file__).resolve()),
        "live_runtime_module_sha256": sha256_file(
            PROJECT / "src/metacom_pm/paper1/semantic_memory/runtime_v9_live.py"
        ),
        "offline_gate_module_sha256": sha256_file(
            PROJECT / "src/metacom_pm/paper1/semantic_memory/runtime_v9_dev.py"
        ),
        "frozen_package_sha256": sha256_file(args.package),
        "package_report_sha256": sha256_file(args.package_report),
        "price_snapshot_sha256": price.identity_sha256,
        "hard_budget_usd": str(V9_DEV_HARD_BUDGET_USD),
        "full_401_compile_authorized": False,
        "outcome_calls": 0,
        "locks": {key: value["status"] for key, value in locks.items() if key.endswith("OUTCOME_LOCK")},
    }
    if not args.live:
        print(canonical_json(dry_plan))
        return 0
    validate_live_gate(args=args, binding=binding, price=price)
    if args.matrix_out is None or args.summary_out is None:
        raise RuntimeError("live v9 DEV requires --matrix-out and --summary-out")
    if args.matrix_out.exists() or args.summary_out.exists():
        raise RuntimeError("refusing to overwrite v9 DEV result evidence")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    client = OpenAICompatibleClient(binding.endpoint)
    try:
        verifier = SemanticMemoryV9DevVerifier(
            binding=binding,
            price=price,
            client=client,
            cache_root=args.output_dir / "success_cache",
            attempt_ledger_root=args.output_dir / "attempt_ledgers",
            budget_ledger_path=args.budget_ledger,
        )
        session_rows = run_sessions(
            verifier=verifier,
            package=package,
            results_path=args.output_dir / "session_results.jsonl",
        )
        accounted = verifier.budget.accounted_cost_usd
    finally:
        client.close()
    matrix, counts = build_matrix(package=package, session_rows=session_rows)
    args.matrix_out.parent.mkdir(parents=True, exist_ok=True)
    for row in matrix:
        append_jsonl(args.matrix_out, row)
    summary = {
        "protocol": "paper1-semantic-memory-v9-dev-results-v1",
        "status": "DEV_COMPLETE_STOP_FOR_RESEARCHER_REVIEW_401_NOT_AUTHORIZED",
        "scope": V9_DEV_SCOPE,
        "identity": {
            **{key: value for key, value in dry_plan.items() if key.endswith("sha256")},
            "session_results_sha256": sha256_file(args.output_dir / "session_results.jsonl"),
            "matrix_sha256": sha256_file(args.matrix_out),
        },
        "counts": counts,
        "mismatch_distribution": dict(Counter(row["mismatch_reason"] for row in matrix)),
        "cost": {
            "accounted_usd": str(accounted),
            "hard_cap_usd": str(V9_DEV_HARD_BUDGET_USD),
            "remaining_usd": str(V9_DEV_HARD_BUDGET_USD - accounted),
        },
        "full_401_started": False,
        "new_catalog_created": False,
        "heldout_ids_frozen": False,
        "outcome_calls": 0,
        "locks": dry_plan["locks"],
    }
    write_json(args.summary_out, summary)
    print(canonical_json(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
