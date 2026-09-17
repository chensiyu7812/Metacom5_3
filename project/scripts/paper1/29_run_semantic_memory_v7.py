#!/usr/bin/env python3
"""Run the authorized v7 semantic-memory DEV replay or full 401 compile.

The caller exports DASHSCOPE_API_KEY; this script never reads a secret file or
prints any credential.  Both modes are outcome-blind and require all four
Paper-1 outcome locks to remain CLOSED.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from decimal import Decimal
import json
from pathlib import Path
import sys
from typing import Any

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.api import OpenAICompatibleClient  # noqa: E402
from metacom_pm.config import endpoint_from_config, load_config  # noqa: E402
from metacom_pm.io import (  # noqa: E402
    canonical_json,
    iter_jsonl,
    sha256_file,
    write_json,
)
from metacom_pm.paper1.data.memory_source import load_sanitized_runtime_users  # noqa: E402
from metacom_pm.paper1.outcome_lock import (  # noqa: E402
    assert_pre_outcome_locked,
    load_public_only_config,
)
from metacom_pm.paper1.semantic_memory.authorization import (  # noqa: E402
    FULL_SCOPE,
    load_live_authorization,
)
from metacom_pm.paper1.semantic_memory.batch import (  # noqa: E402
    ordered_public_sessions,
    run_session_prefix,
)
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
from metacom_pm.paper1.semantic_memory.input_projection import (  # noqa: E402
    build_session_compile_input,
)
from metacom_pm.paper1.semantic_memory.precision_qualification import (  # noqa: E402
    MEPrecisionDecision,
    MPPrecisionDecision,
    MSSemanticAuditDecision,
)
from metacom_pm.paper1.semantic_memory.runtime import (  # noqa: E402
    CallParameters,
    SessionCompilationResult,
)
from metacom_pm.paper1.semantic_memory.runtime_v7 import (  # noqa: E402
    RuntimeBindingV7,
    SemanticMemoryCompilerV7,
    precision_binding_violations,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("plan", "dev", "full"), required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--budget-ledger", type=Path)
    parser.add_argument("--live", action="store_true")
    parser.add_argument(
        "--v6-results",
        type=Path,
        help="Required only for verifier-only old DEV replay.",
    )
    parser.add_argument(
        "--dev-plan",
        type=Path,
        default=PROJECT
        / "data/paper1_authority/paper1_semantic_memory_old_dev_regression_v7_20260820.json",
    )
    return parser.parse_args()


def _binding_and_price(config_path: Path) -> tuple[RuntimeBindingV7, PriceSnapshot]:
    config = load_config(config_path)
    raw = config.get("semantic_memory_compiler")
    if not isinstance(raw, dict):
        raise KeyError("config missing semantic_memory_compiler mapping")
    binding = RuntimeBindingV7(
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


def _dev_sources(
    *,
    users,
    v6_results: Path,
    selected_ids: set[str],
) -> tuple[tuple[Any, ExtractorSessionOutput], ...]:
    ordered = ordered_public_sessions(users)
    rows = list(iter_jsonl(v6_results))
    if len(rows) != len(ordered):
        raise RuntimeError("old DEV replay requires the complete 401-session v6 artifact")
    accepted_by_owner: dict[str, list[AcceptedSemanticMemoryUnit]] = defaultdict(list)
    selected: list[tuple[Any, ExtractorSessionOutput]] = []
    found: set[str] = set()
    for raw, ordered_item in zip(rows, ordered):
        result = SessionCompilationResult.model_validate(raw)
        if (result.owner_id, result.session_id) != (
            ordered_item.owner_id,
            ordered_item.session.session_id,
        ):
            raise RuntimeError("v6 DEV source rows are not the exact ordered public sessions")
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
                        mp_facts=tuple(p for p in proposals if isinstance(p, ProposedMPMemoryUnit)),
                        ms_memories=tuple(p for p in proposals if isinstance(p, ProposedMSMemoryUnit)),
                        me_experiences=tuple(p for p in proposals if isinstance(p, ProposedMEMemoryUnit)),
                    ),
                )
            )
            found.update(unit.memory_id for unit in chosen)
        accepted_by_owner[ordered_item.owner_id].extend(result.accepted_units)
    missing = selected_ids - found
    if missing:
        raise RuntimeError(f"old DEV IDs absent from v6 artifact: {sorted(missing)}")
    return tuple(selected)


def _decision_accepted(decision: object) -> bool:
    if isinstance(decision, (MPPrecisionDecision, MEPrecisionDecision)):
        return decision.accepted
    if isinstance(decision, MSSemanticAuditDecision):
        return decision.accepted_for_candidate_source
    raise TypeError(type(decision))


def _run_dev(
    *,
    compiler: SemanticMemoryCompilerV7,
    users,
    v6_results: Path,
    dev_plan: Path,
    output_path: Path,
) -> dict[str, Any]:
    plan = json.loads(dev_plan.read_text(encoding="utf-8"))
    expected_by_id = {row["memory_id"]: row for row in plan["rows"]}
    output_rows: list[dict[str, Any]] = []
    schema_rejections = 0
    for source, proposals in _dev_sources(
        users=users,
        v6_results=v6_results,
        selected_ids=set(expected_by_id),
    ):
        verifier, rejected = compiler.verify_existing_proposals(
            source=source,
            extractor=proposals,
        )
        schema_rejections += len(rejected)
        proposal_by_id = {proposal.proposal_id: proposal for proposal in proposals.proposals}
        decision_by_id = {decision.proposal_id: decision for decision in verifier.decisions}
        for memory_id, proposal in proposal_by_id.items():
            expected = expected_by_id[memory_id]
            decision = decision_by_id.get(memory_id)
            binding_violations = (
                precision_binding_violations(source, proposal, decision)
                if decision is not None
                else ("missing_or_schema_invalid_decision",)
            )
            accepted = bool(
                decision is not None
                and _decision_accepted(decision)
                and not binding_violations
            )
            observed = "ACCEPT" if accepted else "REJECT_FAIL_CLOSED"
            output_rows.append(
                {
                    "memory_id": memory_id,
                    "memory_class": expected["memory_class"],
                    "old_dev_verdict": expected["old_dev_verdict"],
                    "expected_v7_disposition": expected["expected_v7_disposition"],
                    "observed_v7_disposition": observed,
                    "matches_preregistered_expectation": observed
                    == expected["expected_v7_disposition"],
                    "precision_decision": (
                        decision.model_dump(mode="json") if decision is not None else None
                    ),
                    "binding_violations": binding_violations,
                }
            )
    output_rows.sort(key=lambda row: list(expected_by_id).index(row["memory_id"]))
    pass_rows = [row for row in output_rows if row["old_dev_verdict"] == "PASS"]
    fail_rows = [row for row in output_rows if row["old_dev_verdict"] != "PASS"]
    report: dict[str, Any] = {
        "protocol": "pm-paper1-semantic-memory-v7-old-dev-live-regression-v1",
        "status": "DEV_DIAGNOSTIC_NOT_HELDOUT_QUALIFICATION",
        "identity": {
            "runtime_binding_sha256": compiler.binding.identity_sha256,
            "v6_results_sha256": sha256_file(v6_results),
            "dev_plan_sha256": sha256_file(dev_plan),
        },
        "preregistered_interpretation": {
            "unit": "all 32 previously human-inspected DEV candidates replayed without item blacklist",
            "known_fail_check": "report every old FAIL/REVIEW candidate accepted by v7",
            "old_pass_check": "report every old PASS candidate rejected by v7 and per-class retention; no posthoc PASS line",
            "role": "diagnostic regression only; never held-out qualification or quantity target",
        },
        "counts": {
            "items": len(output_rows),
            "schema_rejections": schema_rejections,
            "known_fail_or_review_rejected": sum(
                row["observed_v7_disposition"] == "REJECT_FAIL_CLOSED" for row in fail_rows
            ),
            "known_fail_or_review_total": len(fail_rows),
            "old_pass_retained": sum(
                row["observed_v7_disposition"] == "ACCEPT" for row in pass_rows
            ),
            "old_pass_total": len(pass_rows),
            "by_class_and_old_verdict_and_observed": dict(
                Counter(
                    f"{row['memory_class']}|{row['old_dev_verdict']}|{row['observed_v7_disposition']}"
                    for row in output_rows
                )
            ),
        },
        "rows": output_rows,
        "outcome_calls": 0,
    }
    write_json(output_path, report)
    return report


def _validate_live_gate(
    *,
    args: argparse.Namespace,
    binding: RuntimeBindingV7,
    price: PriceSnapshot,
) -> None:
    if args.authorization is None or args.budget_ledger is None:
        raise RuntimeError("--live requires --authorization and --budget-ledger")
    authorization = load_live_authorization(args.authorization)
    if authorization.scope != FULL_SCOPE or authorization.maximum_sessions != 401:
        raise RuntimeError("v7 qualification authorization must bind the full 401-session scope")
    if authorization.runtime_binding_sha256 != binding.identity_sha256:
        raise RuntimeError("authorization does not bind this exact v7 runtime")
    if authorization.sanitized_runtime_sha256 != sha256_file(args.runtime):
        raise RuntimeError("authorization does not bind this sanitized runtime")
    if authorization.price_snapshot_id != price.snapshot_id:
        raise RuntimeError("authorization price snapshot ID mismatch")
    if authorization.price_snapshot_sha256 != price.identity_sha256:
        raise RuntimeError("authorization exact price identity mismatch")


def main() -> int:
    args = parse_args()
    locks = load_public_only_config(PROJECT / "configs/paper1_public_only.yaml")
    assert_pre_outcome_locked(locks)
    binding, price = _binding_and_price(args.config)
    users = load_sanitized_runtime_users(args.runtime)
    plan = {
        "status": "DRY_PLAN_NO_API_CALL",
        "mode": args.mode,
        "public_sessions": len(ordered_public_sessions(users)),
        "model": binding.endpoint.model,
        "provider": binding.provider,
        "region": binding.region,
        "runtime_binding_sha256": binding.identity_sha256,
        "runtime_sha256": sha256_file(args.runtime),
        "price_snapshot_sha256": price.identity_sha256,
        "hard_budget_usd": "5.00",
        "outcome_calls": 0,
        "locks": {key: value["status"] for key, value in locks.items() if key.endswith("OUTCOME_LOCK")},
    }
    if args.mode == "plan" or not args.live:
        print(canonical_json(plan))
        return 0
    _validate_live_gate(args=args, binding=binding, price=price)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    client = OpenAICompatibleClient(binding.endpoint)
    try:
        compiler = SemanticMemoryCompilerV7(
            binding=binding,
            price=price,
            client=client,
            cache_root=args.output_dir / "success_cache",
            attempt_ledger_root=args.output_dir / "attempt_ledgers",
            budget_ledger_path=args.budget_ledger,
        )
        if args.mode == "dev":
            if args.v6_results is None:
                raise RuntimeError("DEV replay requires --v6-results")
            report = _run_dev(
                compiler=compiler,
                users=users,
                v6_results=args.v6_results,
                dev_plan=args.dev_plan,
                output_path=args.output_dir / "old_dev_live_regression.json",
            )
        else:
            report = run_session_prefix(
                users=users,
                compiler=compiler,
                maximum_sessions=401,
                results_path=args.output_dir / "session_results.jsonl",
                report_path=args.output_dir / "batch_report.json",
            )
    finally:
        client.close()
    print(canonical_json(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
