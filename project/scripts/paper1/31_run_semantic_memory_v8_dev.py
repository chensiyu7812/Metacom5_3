#!/usr/bin/env python3
"""Run only the researcher-authorized 29-session Semantic Memory v8 DEV replay.

There is intentionally no full-catalog mode.  The caller supplies the API key
through the environment; this script never loads or prints a credential.
"""

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
from metacom_pm.io import (  # noqa: E402
    append_jsonl,
    canonical_json,
    iter_jsonl,
    read_json,
    sha256_file,
    write_json,
)
from metacom_pm.paper1.data.memory_source import load_sanitized_runtime_users  # noqa: E402
from metacom_pm.paper1.outcome_lock import (  # noqa: E402
    assert_pre_outcome_locked,
    load_public_only_config,
)
from metacom_pm.paper1.semantic_memory.batch import ordered_public_sessions  # noqa: E402
from metacom_pm.paper1.semantic_memory.budget import PriceSnapshot  # noqa: E402
from metacom_pm.paper1.semantic_memory.contracts import (  # noqa: E402
    AcceptedSemanticMemoryUnit,
    ExtractorSessionOutput,
    GroundedSupportingSpan,
    ProposedMEMemoryUnit,
    ProposedMPMemoryUnit,
    ProposedMSMemoryUnit,
    SupportingSpan,
)
from metacom_pm.paper1.semantic_memory.evidence_v8 import (  # noqa: E402
    V8_EVIDENCE_SCHEMA_VERSION,
)
from metacom_pm.paper1.semantic_memory.grounding import source_sha256  # noqa: E402
from metacom_pm.paper1.semantic_memory.input_projection import (  # noqa: E402
    build_session_compile_input,
)
from metacom_pm.paper1.semantic_memory.runtime import SessionCompilationResult  # noqa: E402
from metacom_pm.paper1.semantic_memory.runtime_v8_dev import (  # noqa: E402
    RuntimeBindingV8Dev,
    SemanticMemoryV8DevVerifier,
    V8_DEV_HARD_BUDGET_USD,
    V8_DEV_SCOPE,
    V8DevAuthorization,
)


DEFAULT_DEV_PLAN = (
    PROJECT
    / "data/paper1_authority/paper1_semantic_memory_old_dev_regression_v7_20260820.json"
)
DEFAULT_V7_REPORT = Path(
    "/home/chenzhi/paper1_runs/qwen_v7_qualification_20260820/old_dev_live_regression.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--v6-results", type=Path, required=True)
    parser.add_argument("--dev-plan", type=Path, default=DEFAULT_DEV_PLAN)
    parser.add_argument("--v7-report", type=Path, default=DEFAULT_V7_REPORT)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--budget-ledger", type=Path)
    parser.add_argument("--matrix-out", type=Path)
    parser.add_argument("--summary-out", type=Path)
    parser.add_argument("--live", action="store_true")
    return parser.parse_args()


def _binding_and_price(config_path: Path) -> tuple[RuntimeBindingV8Dev, PriceSnapshot]:
    config = load_config(config_path)
    raw = config.get("semantic_memory_v8_dev")
    if not isinstance(raw, dict):
        raise KeyError("config missing semantic_memory_v8_dev mapping")
    binding = RuntimeBindingV8Dev(
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
        input_usd_per_million_tokens=Decimal(
            str(price_raw["input_usd_per_million_tokens"])
        ),
        output_usd_per_million_tokens=Decimal(
            str(price_raw["output_usd_per_million_tokens"])
        ),
    )
    binding.checked_endpoint
    return binding, price


def _span_without_offsets(span: GroundedSupportingSpan) -> SupportingSpan:
    return SupportingSpan(
        span_id=span.span_id,
        turn_id=span.turn_id,
        exact_text=span.exact_text,
    )


def _unit_to_proposal(unit: AcceptedSemanticMemoryUnit):
    common = {
        "proposal_id": unit.memory_id,
        "supporting_spans": tuple(_span_without_offsets(span) for span in unit.supporting_spans),
        "entities": unit.entities,
        "linked_prior_relations": unit.linked_prior_relations,
    }
    if unit.memory_class.value == "MP":
        return ProposedMPMemoryUnit(
            **common,
            profile_field_type=unit.profile_field_type,
            factual_claim=unit.normalized_memory,
        )
    if unit.memory_class.value == "MS":
        return ProposedMSMemoryUnit(
            **common,
            continuity_type=unit.continuity_type,
            factual_claim=unit.normalized_memory,
            event_status=unit.timestamp_status,
        )
    return ProposedMEMemoryUnit(
        **common,
        historical_outcome_type=unit.historical_outcome_type,
        action=unit.action,
        observed_outcome=unit.observed_outcome,
        action_span_ids=unit.action_span_ids,
        observed_outcome_span_ids=unit.observed_outcome_span_ids,
    )


def build_old_dev_sources(
    *, users: Any, v6_results: Path, selected_ids: set[str]
) -> tuple[tuple[Any, ExtractorSessionOutput], ...]:
    ordered = ordered_public_sessions(users)
    rows = list(iter_jsonl(v6_results))
    if len(rows) != len(ordered):
        raise RuntimeError("v8 DEV requires the complete ordered 401-session v6 artifact")
    accepted_by_owner: dict[str, list[AcceptedSemanticMemoryUnit]] = defaultdict(list)
    selected: list[tuple[Any, ExtractorSessionOutput]] = []
    found: set[str] = set()
    for raw, ordered_item in zip(rows, ordered):
        result = SessionCompilationResult.model_validate(raw)
        if (result.owner_id, result.session_id) != (
            ordered_item.owner_id,
            ordered_item.session.session_id,
        ):
            raise RuntimeError("v6 artifact is not aligned to the public session order")
        source = build_session_compile_input(
            owner_id=ordered_item.owner_id,
            session=ordered_item.session,
            strictly_past_accepted_units=tuple(accepted_by_owner[ordered_item.owner_id]),
        )
        chosen = [unit for unit in result.accepted_units if unit.memory_id in selected_ids]
        if chosen:
            proposals = tuple(_unit_to_proposal(unit) for unit in chosen)
            selected.append(
                (
                    source,
                    ExtractorSessionOutput(
                        owner_id=source.owner_id,
                        session_id=source.session_id,
                        mp_facts=tuple(
                            p for p in proposals if isinstance(p, ProposedMPMemoryUnit)
                        ),
                        ms_memories=tuple(
                            p for p in proposals if isinstance(p, ProposedMSMemoryUnit)
                        ),
                        me_experiences=tuple(
                            p for p in proposals if isinstance(p, ProposedMEMemoryUnit)
                        ),
                    ),
                )
            )
            found.update(unit.memory_id for unit in chosen)
        accepted_by_owner[ordered_item.owner_id].extend(result.accepted_units)
    if selected_ids - found:
        raise RuntimeError(f"old DEV IDs absent from v6 artifact: {sorted(selected_ids - found)}")
    if len(selected) != 29:
        raise RuntimeError(f"v8 DEV source-session count drifted from 29 to {len(selected)}")
    return tuple(selected)


def _load_authorization(path: Path) -> V8DevAuthorization:
    try:
        return V8DevAuthorization.model_validate(read_json(path))
    except ValidationError as exc:
        raise RuntimeError(f"invalid v8 DEV authorization: {exc}") from exc


def _validate_live_gate(
    *, args: argparse.Namespace, binding: RuntimeBindingV8Dev, price: PriceSnapshot
) -> V8DevAuthorization:
    if args.authorization is None or args.budget_ledger is None:
        raise RuntimeError("--live requires --authorization and --budget-ledger")
    authorization = _load_authorization(args.authorization)
    exact = {
        "runtime_binding_sha256": binding.identity_sha256,
        "sanitized_runtime_sha256": sha256_file(args.runtime),
        "v6_results_sha256": sha256_file(args.v6_results),
        "dev_plan_sha256": sha256_file(args.dev_plan),
        "v7_report_sha256": sha256_file(args.v7_report),
        "price_snapshot_sha256": price.identity_sha256,
    }
    for field, observed in exact.items():
        if getattr(authorization, field) != observed:
            raise RuntimeError(f"authorization does not bind exact {field}")
    return authorization


def _existing_session_rows(
    results_path: Path, selected: tuple[tuple[Any, ExtractorSessionOutput], ...]
) -> list[dict[str, Any]]:
    rows = list(iter_jsonl(results_path)) if results_path.exists() else []
    if len(rows) > len(selected):
        raise RuntimeError("v8 DEV result file exceeds the fixed 29-session scope")
    for index, row in enumerate(rows):
        source, proposals = selected[index]
        if (row.get("owner_id"), row.get("session_id")) != (
            source.owner_id,
            source.session_id,
        ):
            raise RuntimeError("v8 DEV resume rows are not an exact source-session prefix")
        if row.get("source_sha256") != source_sha256(source):
            raise RuntimeError("v8 DEV resume source identity mismatch")
        if row.get("proposal_ids") != [p.proposal_id for p in proposals.proposals]:
            raise RuntimeError("v8 DEV resume proposal identity mismatch")
    return rows


def _run_sessions(
    *,
    verifier: SemanticMemoryV8DevVerifier,
    selected: tuple[tuple[Any, ExtractorSessionOutput], ...],
    results_path: Path,
) -> list[dict[str, Any]]:
    rows = _existing_session_rows(results_path, selected)
    for source, proposals in selected[len(rows) :]:
        row: dict[str, Any] = {
            "protocol": "paper1-semantic-memory-v8-dev-session-result-v1",
            "runtime_binding_sha256": verifier.binding.identity_sha256,
            "owner_id": source.owner_id,
            "session_id": source.session_id,
            "source_sha256": source_sha256(source),
            "proposal_ids": [p.proposal_id for p in proposals.proposals],
            "evidence_schema_version": V8_EVIDENCE_SCHEMA_VERSION,
            "outcome_calls": 0,
        }
        try:
            evidence, rejected, decisions = verifier.verify_existing_proposals(
                source=source, extractor=proposals
            )
            row.update(
                {
                    "call_status": "SUCCEEDED",
                    "typed_evidence": [
                        item.model_dump(mode="json") for item in evidence.evidence
                    ],
                    "schema_rejections": [
                        item.model_dump(mode="json") for item in rejected
                    ],
                    "deterministic_decisions": [
                        item.model_dump(mode="json") for item in decisions
                    ],
                }
            )
        except Exception as exc:  # fail closed, never retry a physical call
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
    return rows


def _build_matrix(
    *,
    plan: dict[str, Any],
    v7_report: dict[str, Any],
    session_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    v7_by_id = {row["memory_id"]: row for row in v7_report["rows"]}
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
            proposal_id = item.get("proposal_id")
            if proposal_id:
                schema_by_id[proposal_id].extend(item.get("violations", []))
    matrix: list[dict[str, Any]] = []
    for old in plan["rows"]:
        memory_id = old["memory_id"]
        human_positive = old["old_dev_verdict"] == "PASS"
        evidence = evidence_by_id.get(memory_id)
        decision = decision_by_id.get(memory_id)
        accepted = bool(decision and decision["accepted"])
        if decision is None:
            mismatch = "CALL_FAILURE" if memory_id in failed_ids else "SCHEMA_REJECT"
            local_reasons = schema_by_id.get(memory_id) or [mismatch.lower()]
        else:
            local_reasons = [
                *decision["gate_reasons"],
                *decision["binding_violations"],
                *decision["internal_contradictions"],
            ]
            if accepted == human_positive:
                mismatch = "MATCH"
            elif accepted:
                mismatch = "SEMANTIC_FALSE_ACCEPT"
            elif decision["binding_violations"] and not (
                decision["gate_reasons"] or decision["internal_contradictions"]
            ):
                mismatch = "LOCAL_CODE_REJECT"
            else:
                mismatch = "SEMANTIC_FALSE_REJECT"
        matrix.append(
            {
                "protocol": "paper1-semantic-memory-v8-dev-item-matrix-v1",
                "memory_id": memory_id,
                "memory_class": old["memory_class"],
                "old_human_label": old["old_dev_verdict"],
                "old_human_reason": old["old_dev_reason"],
                "v7_verdict": v7_by_id[memory_id]["observed_v7_disposition"],
                "v8_typed_evidence": evidence,
                "deterministic_v8_verdict": (
                    "ACCEPT" if accepted else "REJECT_FAIL_CLOSED"
                ),
                "mismatch_reason": mismatch,
                "local_gate_reason": local_reasons,
                "outcome_calls": 0,
            }
        )
    fail_rows = [row for row in matrix if row["old_human_label"] != "PASS"]
    pass_rows = [row for row in matrix if row["old_human_label"] == "PASS"]
    counts = {
        "items": len(matrix),
        "source_sessions": len(session_rows),
        "provider_call_successes": sum(
            row["call_status"] == "SUCCEEDED" for row in session_rows
        ),
        "provider_call_failures": sum(
            row["call_status"] != "SUCCEEDED" for row in session_rows
        ),
        "typed_evidence_internal_contradiction": sum(
            bool(decision_by_id.get(row["memory_id"], {}).get("internal_contradictions"))
            for row in matrix
        ),
        "known_fail_or_review_rejection": sum(
            row["deterministic_v8_verdict"] == "REJECT_FAIL_CLOSED"
            for row in fail_rows
        ),
        "known_fail_or_review_total": len(fail_rows),
        "old_pass_retention": sum(
            row["deterministic_v8_verdict"] == "ACCEPT" for row in pass_rows
        ),
        "old_pass_total": len(pass_rows),
        "semantic_false_accept": sum(
            row["mismatch_reason"] == "SEMANTIC_FALSE_ACCEPT" for row in matrix
        ),
        "semantic_false_reject": sum(
            row["mismatch_reason"] == "SEMANTIC_FALSE_REJECT" for row in matrix
        ),
        "local_code_reject": sum(
            row["mismatch_reason"] == "LOCAL_CODE_REJECT" for row in matrix
        ),
        "schema_reject": sum(row["mismatch_reason"] == "SCHEMA_REJECT" for row in matrix),
        "call_failure_items": sum(
            row["mismatch_reason"] == "CALL_FAILURE" for row in matrix
        ),
    }
    return matrix, counts


def main() -> int:
    args = parse_args()
    locks = load_public_only_config(PROJECT / "configs/paper1_public_only.yaml")
    assert_pre_outcome_locked(locks)
    binding, price = _binding_and_price(args.config)
    users = load_sanitized_runtime_users(args.runtime)
    plan = read_json(args.dev_plan)
    v7_report = read_json(args.v7_report)
    selected = build_old_dev_sources(
        users=users,
        v6_results=args.v6_results,
        selected_ids={row["memory_id"] for row in plan["rows"]},
    )
    dry_plan = {
        "protocol": "paper1-semantic-memory-v8-dev-plan-v1",
        "status": "DRY_PLAN_NO_API_CALL",
        "scope": V8_DEV_SCOPE,
        "items": sum(len(proposals.proposals) for _, proposals in selected),
        "source_sessions": len(selected),
        "maximum_provider_calls": len(selected),
        "model": binding.endpoint.model,
        "runtime_binding_sha256": binding.identity_sha256,
        "sanitized_runtime_sha256": sha256_file(args.runtime),
        "v6_results_sha256": sha256_file(args.v6_results),
        "dev_plan_sha256": sha256_file(args.dev_plan),
        "v7_report_sha256": sha256_file(args.v7_report),
        "price_snapshot_sha256": price.identity_sha256,
        "hard_budget_usd": str(V8_DEV_HARD_BUDGET_USD),
        "full_401_compile_authorized": False,
        "outcome_calls": 0,
        "locks": {
            key: value["status"]
            for key, value in locks.items()
            if key.endswith("OUTCOME_LOCK")
        },
    }
    if not args.live:
        print(canonical_json(dry_plan))
        return 0
    _validate_live_gate(args=args, binding=binding, price=price)
    if args.matrix_out is None or args.summary_out is None:
        raise RuntimeError("live v8 DEV requires --matrix-out and --summary-out")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    client = OpenAICompatibleClient(binding.endpoint)
    try:
        verifier = SemanticMemoryV8DevVerifier(
            binding=binding,
            price=price,
            client=client,
            cache_root=args.output_dir / "success_cache",
            attempt_ledger_root=args.output_dir / "attempt_ledgers",
            budget_ledger_path=args.budget_ledger,
        )
        session_rows = _run_sessions(
            verifier=verifier,
            selected=selected,
            results_path=args.output_dir / "session_results.jsonl",
        )
        accounted = verifier.budget.accounted_cost_usd
    finally:
        client.close()
    matrix, counts = _build_matrix(plan=plan, v7_report=v7_report, session_rows=session_rows)
    args.matrix_out.parent.mkdir(parents=True, exist_ok=True)
    if args.matrix_out.exists():
        raise RuntimeError("refusing to overwrite an existing v8 DEV matrix")
    for row in matrix:
        append_jsonl(args.matrix_out, row)
    summary = {
        "protocol": "paper1-semantic-memory-v8-dev-results-v1",
        "status": "DEV_COMPLETE_STOP_FOR_RESEARCHER_REVIEW_401_NOT_AUTHORIZED",
        "scope": V8_DEV_SCOPE,
        "identity": {
            **{key: value for key, value in dry_plan.items() if key.endswith("sha256")},
            "session_results_sha256": sha256_file(args.output_dir / "session_results.jsonl"),
            "matrix_sha256": sha256_file(args.matrix_out),
        },
        "counts": counts,
        "mismatch_distribution": dict(Counter(row["mismatch_reason"] for row in matrix)),
        "cost": {
            "accounted_usd": str(accounted),
            "hard_cap_usd": str(V8_DEV_HARD_BUDGET_USD),
            "remaining_usd": str(V8_DEV_HARD_BUDGET_USD - accounted),
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

